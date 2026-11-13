#!/usr/bin/env python3
"""Talent Alpha deterministic pipeline: trust-boundary join, reconcile, render, verify.

Agents emit structured JSON. The production build command requires both judges,
checks the card against its sources and schema, renders and verifies it, and records
state last. These structural checks do not prove a source story or an inferred fit true.

Subcommands
-----------
build       reconcile + accuracy/schema checks + render + verify + record state
join        raw new-events + scanner shortlist -> trusted_candidates.json
            (drops any id the scanner invented; never in the raw batch)
reconcile   trusted_candidates + advocate verdicts + skeptic verdicts
            -> content JSON matching references/content-schemas/card.content-schema.json
render      content JSON + template -> final self-contained HTML card
verify      scan a rendered card for leftover placeholders, banned filler,
            and em dashes; exits nonzero on any finding

Usage (see skills/talent-alpha/SKILL.md for the full run):

    python3 render.py join --raw new_events.json --shortlist shortlist.json --out trusted.json
    python3 render.py reconcile --trusted trusted.json \\
        --advocate advocate_verdicts.json --skeptic skeptic_verdicts.json \\
        --author "Your name" --company-name "Halcyon Silicon" \\
        --role-title "Manufacturing Process Engineer" --role-location "Austin, TX" \\
        --out content.json
    python3 render.py render --template ../references/templates/overnight_card.template.html \\
        --content content.json --out card.html --strict
    python3 render.py verify --doc card.html
"""

import argparse
import datetime
import html
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import runlog
from state import (
    MAX_AGE_DAYS,
    WINDOW_DAYS,
    age_in_days,
    parse_as_of,
    parse_timestamp,
    utc_today,
)

log = runlog.get_logger("talent-alpha.render")

TIER_RANK = {"S": 3, "A": 2, "B": 1, "C": 0}
TIER_BY_RANK = ["C", "B", "A", "S"]
TIER_COLOR = {
    "S": "#C8202E",
    "A": "#1B3A2C",
    "B": "#8A6B22",
    "HELD": "rgba(20,23,28,.45)",
}
AXES = ["openness", "role_fit", "product_fit", "region_fit", "size_fit", "stage_fit"]
# An axis name in card prose ("stage_fit H is inferred from ...") means a judge explained
# a score on the card instead of keeping it in the diagram. The template itself has none.
AXIS_TOKEN_RE = re.compile(r"\b[A-Za-z]+_fit\b")

BANNED_FILLER = ["TBD", "N/A", "Data not available", "NOT_FOUND"]

TEMPLATE_SLOTS = (
    "author",
    "run-date",
    "role-name",
    "role-meta",
    "tier-counts",
    "run-id",
    "hero-tag",
    "hero-company",
    "hero-loc",
    "hero-titles",
    "hero-why",
    "hero-edge",
    "hero-hook",
    "hero-source",
    "c-summary",
    "foot-left",
    "foot-right",
)
HERO_TAG_ANCHOR = '<span class="chipS" data-slot="hero-tag">-</span>'
HERO_GRAPH_ANCHOR = 'data-bands="M,M,M,M,M,M" data-tier="S" data-size="150"'
CARD_ANCHOR = "<!-- CARD:START -->\n<!-- CARD:END -->"

CONTENT_SCHEMA = (
    Path(__file__).resolve().parent.parent
    / "references/content-schemas/card.content-schema.json"
)


# ---------------------------------------------------------------- utilities


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def esc(s):
    return html.escape(str(s) if s is not None else "", quote=False)


def esc_attr(s):
    """For a value inside a double-quoted attribute: quotes are escaped too.

    Bands, tier and the wildcard axis come from judge output and the source URL from a
    third-party feed; none of them may close the attribute they sit in."""
    return html.escape(str(s) if s is not None else "", quote=True)


SAFE_LINK = re.compile(r"^https?://", re.IGNORECASE)


def js_round(x):
    """Match JS Math.round: half rounds toward +Infinity, not to-even."""
    return math.floor(x + 0.5)


def age_days_of(published_at, as_of):
    """Whole days from the event's UTC date to the run date (state.age_in_days)."""
    days = age_in_days(published_at, as_of) if published_at else None
    return 999 if days is None else max(0, days)


def age_label_of(days, event_type=""):
    """The badge text. An event older than its source window says so: the card's
    count bar names the window, and a badge must not read as fresher than it is."""
    if days <= 0:
        label = "today"
    elif days == 1:
        label = "1d ago"
    else:
        label = f"{days}d ago"
    window = WINDOW_DAYS.get(event_type)
    if window is not None and days > window:
        label += f", outside the {window}d window"
    return label


def window_note_of(as_of):
    return (
        f"WARN: {WINDOW_DAYS['layoff']}d; funding news: "
        f"{WINDOW_DAYS['funding_distress']}d; ages as of {as_of.isoformat()}"
    )


def run_reference_time(as_of):
    """The moment a run date stands for: now, unless the run date is in the past
    (a frozen fixture run), then the end of that day."""
    now = datetime.datetime.now(datetime.timezone.utc)
    end_of_day = datetime.datetime.combine(
        as_of + datetime.timedelta(days=1), datetime.time(), datetime.timezone.utc
    )
    return min(now, end_of_day)


# --------------------------------------------------------------- join (trust boundary)


def grounded_extraction(event, value):
    """A scanner extraction must occur in the source's title or snippet."""
    if not isinstance(value, str) or not value.strip():
        return ""
    tokens = re.findall(r"\w+", value.casefold())
    evidence = " ".join(str(event.get(k, "")) for k in ("title", "snippet"))
    words = " " + " ".join(re.findall(r"\w+", evidence.casefold())) + " "
    return value.strip() if tokens and " " + " ".join(tokens) + " " in words else ""


def resolved_company(event, extracted):
    if event.get("company"):
        return event["company"]
    if event.get("event_type") == "funding_distress":
        return grounded_extraction(event, extracted)
    return ""


def index_unique(rows, key, label):
    if not isinstance(rows, list):
        raise TypeError(f"{label} must be an array")
    result = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get(key), str)
            or not row[key]
        ):
            raise ValueError(f"{label}: every item needs a nonempty {key}")
        if row[key] in result:
            raise ValueError(f"{label}: duplicate {key} {row[key]!r}")
        result[row[key]] = row
    return result


def event_problems(e, as_of=None):
    """Why this raw event is not fit to score. Empty list means it is.

    The join is the trust boundary, but it used to inspect only the agent:
    it dropped an id the scanner invented, then accepted whatever the batch
    itself said. A fabricated event with a future date, a negative headcount
    and an unreachable source URL rendered as a confident tier-S card. These
    are the cheap structural checks that make the batch pass through the same
    boundary as the agent. They cannot tell you an event is TRUE; they only
    reject events that cannot be true.
    """
    problems = []

    if not (e.get("company") or "").strip():
        problems.append("no company name")
    if e.get("event_type") not in tuple(WINDOW_DAYS):
        problems.append("invalid event_type")
    if not (e.get("source_name") or "").strip():
        problems.append("no source_name")

    if not (e.get("source_url") or "").strip():
        problems.append("no source_url, so no reader can check the claim")
    else:
        try:
            url = urlsplit(e["source_url"])
            if url.scheme.lower() not in ("http", "https") or not url.hostname:
                problems.append("source_url must be an absolute http(s) URL")
        except ValueError:
            problems.append("invalid source_url")

    published = e.get("published_at")
    if not published:
        problems.append("no published_at")
    else:
        try:
            dt = parse_timestamp(published)
        except (ValueError, TypeError):
            problems.append(f"unparseable published_at {published!r}")
        else:
            # A future date is not just wrong, it scores BEST: age_days_of
            # clamps negatives to 0, which labels it "today". Future means after
            # the run date (now, for a run dated today), with a day of slack.
            reference = run_reference_time(as_of or utc_today())
            ahead = (dt - reference).total_seconds()
            if ahead > 86400:
                problems.append(
                    f"published_at is in the future of the run date ({published})"
                )

    affected = e.get("employees_affected")
    if affected is not None:
        if not isinstance(affected, int) or isinstance(affected, bool):
            problems.append(f"employees_affected is not an integer ({affected!r})")
        elif affected < 0:
            problems.append(f"negative employees_affected ({affected})")

    return problems


def cmd_join(args):
    raw_events = load(args.raw)
    by_id = index_unique(raw_events, "event_id", "raw events")
    shortlist = load(args.shortlist)
    opportunities = shortlist.get("opportunities", [])
    index_unique(opportunities, "id", "shortlist")

    rejected = {}

    trusted = []
    dropped = []
    for o in opportunities:
        oid = o.get("id")
        base = by_id.get(oid)
        if base is None:
            dropped.append(oid)
            continue
        # Validate the resolved company, not the intentionally empty funding field.
        event = dict(base, company=resolved_company(base, o.get("company")))
        problems = event_problems(event, args.as_of)
        if problems:
            rejected[oid] = problems
            continue
        trusted.append(
            {
                "id": o["id"],
                "company": event["company"],
                "event_type": base.get("event_type") or o.get("event_type", ""),
                # The scanner inferred these; no source names them. The key says so,
                # so a judge cannot read them as a fact from the filing.
                "inferred_functions": o.get("functions", []),
                "location": base.get("location")
                or grounded_extraction(base, o.get("location")),
                "employees_affected": base.get("employees_affected"),
                "published_at": base.get("published_at"),
                "score": o.get("score"),
                "why": o.get("why", ""),
                "source_name": base.get("source_name", ""),
                "source_url": base.get("source_url", ""),
                "title": base.get("title", ""),
                "snippet": base.get("snippet", ""),
            }
        )

    dump(args.out, trusted)
    msg = (
        f"join: {len(opportunities)} shortlisted, {len(dropped)} dropped (id not in trusted batch), "
        f"{len(rejected)} dropped (event failed batch checks), {len(trusted)} trusted -> {args.out}"
    )
    if dropped:
        msg += f"\n  invented ids: {dropped}"
    for eid, problems in rejected.items():
        msg += f"\n  unusable event {eid}: " + "; ".join(problems)
    print(msg)
    log.info(
        "join: %d shortlisted, %d trusted, %d dropped",
        len(opportunities),
        len(trusted),
        len(dropped) + len(rejected),
    )
    if opportunities and not trusted:
        # A quiet night is an empty SHORTLIST, and 2.2 already stops there. A
        # non-empty shortlist where nothing survives is a data fault: fail loud
        # rather than hand the next step an empty batch to render around.
        print(
            "join: a shortlist arrived but nothing survived the trust boundary. "
            "Fix the pull step; do not render a card from this run.",
            file=sys.stderr,
        )
        sys.exit(1)


# --------------------------------------------------------------- reconcile


def cmd_reconcile(args):
    trusted = load(args.trusted)
    trusted_by_id = index_unique(trusted, "id", "trusted candidates")
    advocate = load(args.advocate).get("verdicts", [])
    skeptic = load(args.skeptic).get("verdicts", [])
    advocate_by_id = index_unique(advocate, "id", "advocate verdicts")
    skeptic_by_id = index_unique(skeptic, "id", "skeptic verdicts")
    if args.min_shown < 0 or args.max_shown < 1:
        raise ValueError("min-shown must be nonnegative and max-shown must be positive")
    properties = load(CONTENT_SCHEMA)["properties"]["candidates"]["items"]["properties"]
    for name, verdicts in (("advocate", advocate_by_id), ("skeptic", skeptic_by_id)):
        missing = sorted(set(trusted_by_id) - set(verdicts))
        extra = sorted(set(verdicts) - set(trusted_by_id))
        if missing or extra:
            raise ValueError(
                f"{name} coverage mismatch: missing {missing}, unknown {extra}"
            )
        for verdict in verdicts.values():
            if verdict.get("tier") not in TIER_RANK:
                raise ValueError(f"{name}: invalid tier for {verdict['id']!r}")
            if any(verdict.get(axis) not in ("H", "M", "L") for axis in AXES):
                raise ValueError(
                    f"{name}: invalid or missing fit axis for {verdict['id']!r}"
                )
            for key in ("why", "hook", "edge", "titles", "wildcard"):
                if key not in verdict:
                    raise ValueError(f"{name}: missing {key} for {verdict['id']!r}")
                issues = schema_problems(verdict[key], properties[key], f"{name}.{key}")
                if issues:
                    raise ValueError("; ".join(issues))

    as_of = args.as_of or utc_today()
    finals = []
    for a in advocate:
        # Coverage and field checks above already raised on any unknown id or missing key.
        t = trusted_by_id[a["id"]]
        age_days = age_days_of(t.get("published_at"), as_of)
        s = skeptic_by_id[a["id"]]
        rank_a = TIER_RANK[a["tier"]]
        rank_s = TIER_RANK[s["tier"]]
        blended = js_round((rank_a + rank_s) / 2)
        finals.append(
            {
                "id": a["id"],
                "company": t["company"],
                "location": t["location"],
                "employees_affected": t.get("employees_affected"),
                "event_type": t["event_type"],
                "event_age_label": age_label_of(age_days, t["event_type"]),
                "age_days": age_days,
                "titles": a["titles"],
                "tier": TIER_BY_RANK[blended],
                "_rank": blended,
                "_disagree": abs(rank_a - rank_s) >= 3,
                "bands": [a[axis] for axis in AXES],
                "wildcard": a["wildcard"],
                "why": a["why"],
                "hook": a["hook"],
                "edge": a["edge"],
                "held": False,
                "hold_reason": "",
                "source_name": t.get("source_name", ""),
                "source_url": t.get("source_url", ""),
            }
        )

    finals.sort(key=lambda f: (-f["_rank"], f["age_days"]))

    for idx, f in enumerate(finals):
        if idx >= args.max_shown:
            f["held"] = True
            f["tier"] = "HELD"
            f["hold_reason"] = f"beyond the top {args.max_shown} this run"
        elif f["_disagree"]:
            f["held"] = True
            f["tier"] = "HELD"
            f["hold_reason"] = "judges disagreed sharply"
        del f["_rank"]
        del f["_disagree"]

    content = {
        "run": {
            "author": args.author,
            "run_date": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            ),
            "company_name": args.company_name,
            "role_title": args.role_title,
            "role_location": args.role_location,
            "scanned_count": len(finals),
            "window_note": window_note_of(as_of),
        },
        "candidates": finals,
    }
    dump(args.out, content)
    shown = sum(1 for f in finals if not f["held"])
    held = sum(1 for f in finals if f["held"])
    print(
        f"reconcile: {len(finals)} candidates, {shown} shown, {held} held -> {args.out}"
    )
    log.info("reconcile: %d candidates, %d shown, %d held", len(finals), shown, held)


# --------------------------------------------------------------- render


def validate_template(doc):
    """Reject incomplete templates before a card can replace output or retire events."""
    slots = re.findall(r'data-slot="([a-zA-Z0-9_-]+)"', doc)
    invalid = [name for name in TEMPLATE_SLOTS if slots.count(name) != 1]
    anchors = (
        HERO_TAG_ANCHOR,
        HERO_GRAPH_ANCHOR,
        CARD_ANCHOR,
        "<!-- HERO:START -->",
        "<!-- HERO:END -->",
    )
    if invalid or any(doc.count(anchor) != 1 for anchor in anchors):
        raise ValueError(
            "invalid card template: preserve one of each required data-slot, "
            "hero anchor and card block"
            + (f"; invalid slots: {invalid}" if invalid else "")
        )
    spans = []
    for name in TEMPLATE_SLOTS:
        match = re.search(
            r'<[a-zA-Z0-9]+[^>]*data-slot="' + re.escape(name) + r'"[^>]*>', doc
        )
        if match is None:
            raise ValueError(f"invalid card template: slot {name} has no element")
        try:
            start, end = element_span(doc, match.start())
        except ValueError as exc:
            raise ValueError(f"invalid card template: {exc}") from exc
        spans.append((match.start(), start, end, name))
    for opening, start, end, name in spans:
        if any(start <= other < end for other, _, _, _ in spans):
            raise ValueError(f"invalid card template: nested slot inside {name}")
        if any(start <= doc.index(anchor) < end for anchor in anchors):
            raise ValueError(f"invalid card template: render anchor inside {name}")
    if (
        not doc.index("<!-- HERO:START -->")
        < doc.index("<!-- HERO:END -->")
        < doc.index(CARD_ANCHOR)
    ):
        raise ValueError("invalid card template: hero and card blocks are out of order")


def element_span(doc, open_start):
    tag_match = re.match(r"<([a-zA-Z0-9]+)", doc[open_start:])
    tag = tag_match.group(1)
    content_start = doc.index(">", open_start) + 1
    pattern = re.compile(r"<" + tag + r"\b[^>]*>|</" + tag + r">")
    depth = 1
    for m in pattern.finditer(doc, content_start):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth == 0:
            return content_start, m.start()
    raise ValueError(f"unbalanced <{tag}> starting at {open_start}")


def fill_slot(doc, slot, content):
    pattern = re.compile(
        r'<[a-zA-Z0-9]+[^>]*data-slot="' + re.escape(slot) + r'"[^>]*>'
    )
    m = pattern.search(doc)
    if not m:
        raise ValueError(f"invalid card template: missing slot {slot}")
    a, b = element_span(doc, m.start())
    return doc[:a] + content + doc[b:]


def loc_line(it):
    line = it["location"]
    if it.get("employees_affected"):
        line += f" · {it['employees_affected']} affected"
    return line


def source_html(it):
    """The source line under a candidate, as a real link.

    Every claim on this card came from one fetched event. Without the link,
    a reader cannot check any of it, and a fabricated or mis-parsed event
    looks exactly like a real one. A candidate with no usable source_url
    should never reach here (cmd_join rejects it), so the no-link branch is
    a last-resort honest label, not a normal path.
    """
    name = it.get("source_name") or "source"
    url = (it.get("source_url") or "").strip()
    if not url:
        return f'<div class="srcline">Source: {esc(name)} (no link on file)</div>'
    if not SAFE_LINK.match(url):
        # only http(s) becomes a link; a javascript: or data: URL from a feed never does
        return f'<div class="srcline">Source: {esc(name)} (link withheld: not an http(s) URL)</div>'
    return (
        f'<div class="srcline">Source: '
        f'<a href="{esc_attr(url)}" rel="noopener noreferrer">{esc(name)}</a></div>'
    )


def render_card(it):
    wc = it.get("wildcard") or {}
    wc_attr = f' data-wc="{esc_attr(wc["axis_index"])}"' if wc.get("fired") else ""
    bridge_chip = (
        f'<span class="bridge">◆ {esc(wc.get("bridge", ""))}</span>'
        if wc.get("fired")
        else ""
    )
    titles = "".join(f"<span>{esc(t)}</span>" for t in it.get("titles", []))
    return (
        '<div class="card">'
        f'<div class="hex" data-bands="{esc_attr(",".join(it["bands"]))}" data-tier="{esc_attr(it["tier"])}" data-size="120"{wc_attr}></div>'
        f'<div><span class="tagA">{esc(it["event_type"] + " · " + it["event_age_label"])}</span>{bridge_chip}'
        f'<div class="co">{esc(it["company"])}</div><div class="loc">{esc(loc_line(it))}</div>'
        f'<div class="titles">{titles}</div></div>'
        '<div class="pillars3">'
        f'<div><div class="pl why">Why now</div><div class="ptext">{esc(it["why"])}</div></div>'
        f'<div><div class="pl hook">The hook</div><div class="ptext">{esc(it["hook"])}</div></div>'
        f'<div><div class="pl edge">The edge</div><div class="ptext dim">{esc(it["edge"] or "none yet")}</div></div>'
        "</div>" + source_html(it) + "</div>"
    )


def schema_problems(value, schema, path="card"):
    """Check the schema vocabulary used by this card, without runtime dependencies.

    New constraints must be implemented here before they can be used in the schema;
    unsupported keywords fail instead of silently skipping validation.
    """
    supported = {
        "$schema",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "enum",
    }
    unknown = set(schema) - supported
    if unknown:
        raise ValueError(f"unsupported schema keywords at {path}: {sorted(unknown)}")
    types = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
        "null": value is None,
    }
    expected = schema.get("type", [])
    expected = [expected] if isinstance(expected, str) else expected
    if any(t not in types for t in expected):
        raise ValueError(f"unsupported schema type at {path}: {expected}")
    if expected and not any(types[t] for t in expected):
        return [f"{path}: expected {' or '.join(expected)}"]
    problems = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: invalid value {value!r}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        problems.extend(
            f"{path}.{k} missing" for k in schema.get("required", []) if k not in value
        )
        if schema.get("additionalProperties") is False:
            problems.extend(
                f"{path}.{k}: unexpected field" for k in value if k not in properties
            )
        for key, child in properties.items():
            if key in value:
                problems.extend(schema_problems(value[key], child, f"{path}.{key}"))
    if isinstance(value, list):
        for key, fails in (
            ("minItems", len(value) < schema.get("minItems", 0)),
            ("maxItems", len(value) > schema.get("maxItems", len(value))),
        ):
            if fails:
                problems.append(f"{path}: violates {key}={schema[key]}")
        if "items" in schema:
            for i, item in enumerate(value):
                problems.extend(schema_problems(item, schema["items"], f"{path}[{i}]"))
    if type(value) is int:
        for key, fails in (
            ("minimum", value < schema.get("minimum", value)),
            ("maximum", value > schema.get("maximum", value)),
        ):
            if fails:
                problems.append(f"{path}: violates {key}={schema[key]}")
    return problems


def validate_content(content, strict):
    problems = schema_problems(content, load(CONTENT_SCHEMA))
    if not problems:
        seen = set()
        for c in content["candidates"]:
            if c["id"] in seen:
                problems.append(f"duplicate candidate id {c['id']!r}")
            seen.add(c["id"])
            for key in ("id", "company", "source_name", "source_url", "why"):
                if not c[key].strip():
                    problems.append(f"candidate {c['id']!r}: {key} is empty")
            if c["held"] != (c["tier"] == "HELD") or c["held"] != bool(
                c["hold_reason"].strip()
            ):
                problems.append(f"candidate {c['id']!r}: inconsistent held/tier/reason")
            wc = c["wildcard"]
            if wc["fired"] and (wc["axis_index"] < 0 or not wc["bridge"].strip()):
                problems.append(
                    f"candidate {c['id']!r}: wildcard needs an axis and bridge"
                )
    if problems and strict:
        print(
            "STRICT RENDER FAILED. Nothing written. Route this back to the producing "
            "agent (scanner/advocate/skeptic) or the reconcile step as a patch, never "
            "hand-edit the output.",
            file=sys.stderr,
        )
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
    return problems


def cmd_render(args):
    content = load(args.content)
    problems = validate_content(content, args.strict)
    if problems and args.strict:
        sys.exit(1)

    with open(args.template, "r", encoding="utf-8") as f:
        doc = f.read()
    validate_template(doc)

    run = content["run"]
    doc = fill_slot(doc, "author", esc(run["author"]))
    doc = fill_slot(doc, "run-date", esc(run["run_date"]))
    doc = fill_slot(doc, "role-name", esc(run["role_title"]))
    doc = fill_slot(
        doc, "role-meta", esc(run["company_name"] + " · " + run["role_location"])
    )

    all_candidates = content["candidates"]
    shown = [c for c in all_candidates if not c["held"]]
    held = [c for c in all_candidates if c["held"]]

    counts = {"S": 0, "A": 0, "B": 0, "C": 0}
    for c in shown:
        if c["tier"] in counts:
            counts[c["tier"]] += 1
    tier_counts_html = (
        f'<b style="color:var(--red)">{counts["S"]} S</b> · '
        f'<b style="color:var(--green)">{counts["A"]} A</b> · '
        f'<b style="color:var(--gold-dk)">{counts["B"]} B</b> · '
        f'<b style="color:var(--gray)">{counts["C"]} C</b>'
    )
    if held:
        tier_counts_html += f' · <b style="color:var(--gray)">{len(held)} held</b>'
    doc = fill_slot(doc, "tier-counts", tier_counts_html)
    doc = fill_slot(
        doc,
        "run-id",
        f"{len(all_candidates)} signals scanned · {esc(run['window_note'])}",
    )

    held_summary = (
        (
            f"{len(held)} item"
            + ("s" if len(held) != 1 else "")
            + " held for review (judge disagreement or overflow): "
            + "; ".join(
                f"{h['company']} ({h['hold_reason'] or 'disagreement'})" for h in held
            )
        )
        if held
        else "clean"
    )

    if not shown:
        summary = (
            f"No auto-cleared movements, but {held_summary}"
            if held
            else "No movements cleared the bar this run. Next scan will pick up where this one left off."
        )
        doc = fill_slot(doc, "c-summary", esc(summary))
        # Honest empty state: remove the hero block rather than leave it full
        # of unfilled "-" placeholders (see references/00_SHARED_CORE.md 6).
        doc = re.sub(
            r"<!-- HERO:START -->.*?<!-- HERO:END -->", "", doc, flags=re.DOTALL
        )
    else:
        hero, rest = shown[0], shown[1:]
        chip_color = TIER_COLOR.get(hero["tier"], TIER_COLOR["HELD"])
        tag_text = esc(
            hero["tier"] + " · " + hero["event_type"] + " " + hero["event_age_label"]
        )
        if hero["tier"] == "S":
            hero_chip = f'<span class="chipS">{tag_text}</span>'
        else:
            hero_chip = f'<span class="chipS" style="background:none;border:1px solid {chip_color};color:{chip_color}">{tag_text}</span>'
        doc = doc.replace(HERO_TAG_ANCHOR, hero_chip)
        doc = fill_slot(doc, "hero-company", esc(hero["company"]))
        doc = fill_slot(doc, "hero-loc", esc(loc_line(hero)))
        doc = fill_slot(
            doc,
            "hero-titles",
            "".join(f"<span>{esc(t)}</span>" for t in hero.get("titles", [])),
        )
        doc = fill_slot(doc, "hero-why", esc(hero["why"]))
        doc = fill_slot(
            doc,
            "hero-edge",
            esc(hero["edge"] or "Not enough signal for a leverage read yet."),
        )
        doc = fill_slot(doc, "hero-hook", f'"{esc(hero["hook"])}"')
        doc = fill_slot(doc, "hero-source", source_html(hero))
        wc = hero.get("wildcard") or {}
        wc_attr = f' data-wc="{esc_attr(wc["axis_index"])}"' if wc.get("fired") else ""
        doc = doc.replace(
            HERO_GRAPH_ANCHOR,
            f'data-bands="{esc_attr(",".join(hero["bands"]))}" data-tier="{esc_attr(hero["tier"])}" data-size="150"{wc_attr}',
        )
        cards_html = "".join(render_card(it) for it in rest)
        doc = doc.replace(
            CARD_ANCHOR,
            "<!-- CARD:START -->" + cards_html + "<!-- CARD:END -->",
        )
        doc = fill_slot(doc, "c-summary", esc(held_summary))
    doc = fill_slot(
        doc,
        "foot-left",
        "Talent Alpha · overnight brief · WARN + funding-distress categories",
    )
    doc = fill_slot(
        doc, "foot-right", "Sources travel untrusted · nothing sends automatically"
    )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    log.info(
        "render: wrote %s (%d shown, %d held, %d schema warning(s))",
        args.out,
        len(shown),
        len(held),
        len(problems),
    )
    print(
        f"render: wrote {args.out} ({len(shown)} shown, {len(held)} held)"
        + (
            f" -- {len(problems)} schema warning(s), non-strict"
            if problems and not args.strict
            else ""
        )
    )


# --------------------------------------------------------------- verify


def cmd_verify(args):
    with open(args.doc, "r", encoding="utf-8") as f:
        doc = f.read()

    findings = []
    for phrase in BANNED_FILLER:
        if phrase in doc:
            findings.append(f'banned filler string present: "{phrase}"')
    if "—" in doc:
        findings.append("em dash (—) present")
    axis_tokens = sorted(set(AXIS_TOKEN_RE.findall(doc)))
    if axis_tokens:
        findings.append(
            f"fit-axis name in card text: {axis_tokens}; remove the ungrounded claim "
            "from why/hook/edge, do not substitute an inference"
        )
    unfilled = re.findall(r'data-slot="([a-zA-Z0-9_-]+)">-<', doc)
    if unfilled:
        findings.append(
            f"unfilled slot placeholder(s) still showing '-': {sorted(set(unfilled))}"
        )

    log.info("verify: %s, %d finding(s)", args.doc, len(findings))
    if findings:
        print(f"VERIFY FAILED: {args.doc}", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        sys.exit(1)
    print(f"verify OK: {args.doc}")


# --------------------------------------------------------------- main


def noon_targeting(content, raw):
    """Export employer signals for review, using the card's checked verdicts."""
    signals = []
    for candidate in content["candidates"]:
        if candidate["held"] or candidate["tier"] not in ("S", "A"):
            continue
        event = raw[candidate["id"]]
        published = parse_timestamp(event["published_at"]).date()
        signals.append(
            {
                "event_id": candidate["id"],
                "company": candidate["company"],
                "event_type": candidate["event_type"],
                "event_location": candidate["location"],
                "reported_titles": candidate["titles"],
                "tier": candidate["tier"],
                "published_on": published.isoformat(),
                "use_through": (
                    published
                    + datetime.timedelta(days=WINDOW_DAYS[event["event_type"]])
                ).isoformat(),
                "source_url": candidate["source_url"],
            }
        )
    return {
        "schema_version": 1,
        "role": {
            "title": content["run"]["role_title"],
            "location": content["run"]["role_location"],
        },
        "signals": signals,
    }


def cmd_build(args):
    """Publish a checked local card, then record state. Failures leave state untouched."""
    import state
    import validate_card

    content_path, html_path = Path(args.out), Path(args.html)
    input_paths = [
        args.raw,
        args.trusted,
        args.advocate,
        args.skeptic,
        args.profile,
        args.state,
        args.template,
    ]
    output_paths = [content_path, html_path]
    if args.noon_handoff:
        output_paths.append(content_path.with_name("noon-targeting.json"))
    outputs = {path.resolve() for path in output_paths}
    if len(outputs) != len(output_paths) or any(
        Path(p).resolve() in outputs for p in input_paths
    ):
        raise ValueError(
            "outputs must be separate from each other and from input/state files"
        )
    raw = index_unique(load(args.raw), "event_id", "raw events")
    for candidate in load(args.trusted):
        event = raw.get(candidate.get("id"))
        if event is None:
            raise ValueError(
                f"trusted id {candidate.get('id')!r} is absent from the pull"
            )
        if candidate.get("published_at") != event.get("published_at"):
            raise ValueError(
                f"published_at differs from the pull for {candidate['id']!r}"
            )
        issues = event_problems(
            dict(event, company=resolved_company(event, candidate.get("company"))),
            args.as_of,
        )
        if issues:
            raise ValueError(
                f"unusable source event {candidate['id']!r}: " + "; ".join(issues)
            )
    profile = Path(args.profile).read_text(encoding="utf-8")
    leverage = validate_card.leverage_from_profile(profile)
    company_facts = validate_card.company_facts_from_profile(profile)
    seen = state.load_state(args.state)["seen_events"]
    if any(not text.strip() for text in (args.company_name, args.role_title)):
        raise ValueError(
            "company-name and role-title are required for a role-specific card"
        )
    # Stage both files away from the final paths: a validation failure cannot replace
    # a previous good card, and a failed render cannot mark anything seen.
    with tempfile.TemporaryDirectory(
        prefix=".talent-alpha-build-", dir=content_path.parent
    ) as temp:
        staged_content, staged_html = (
            Path(temp) / "content.json",
            Path(temp) / "card.html",
        )
        reconcile_args = argparse.Namespace(**vars(args))
        reconcile_args.out = str(staged_content)
        cmd_reconcile(reconcile_args)
        content = load(staged_content)
        findings, warnings, _ = validate_card.check_card(
            content,
            load(args.advocate),
            load(args.skeptic),
            raw,
            leverage,
            args.max_shown,
            seen,
            company_facts,
        )
        for warning in warnings:
            print(f"build warning: {warning}", file=sys.stderr)
        if findings:
            raise ValueError("card accuracy checks failed: " + "; ".join(findings))
        cmd_render(
            argparse.Namespace(
                content=str(staged_content),
                template=args.template,
                out=str(staged_html),
                strict=True,
            )
        )
        cmd_verify(argparse.Namespace(doc=str(staged_html)))
        staged_outputs = [staged_content, staged_html]
        if args.noon_handoff:
            staged_noon = Path(temp) / "noon-targeting.json"
            dump(staged_noon, noon_targeting(content, raw))
            staged_outputs.append(staged_noon)
        for staged, output in zip(staged_outputs, output_paths):
            os.replace(staged, output)
    state.cmd_record(
        argparse.Namespace(
            candidates=str(content_path), state=args.state, max_age_days=MAX_AGE_DAYS
        )
    )
    print(f"build OK: {html_path}; state recorded after validation and verification")
    if args.noon_handoff:
        print(f"Noon targeting for review: {output_paths[-1]}")


def config_problems(path):
    config = path if isinstance(path, dict) else load(path)
    issues = schema_problems(
        config, load(CONTENT_SCHEMA.with_name("n8n-config.schema.json")), "config"
    )
    # Name every blank field at once, even beside a schema problem, so a user fixes
    # the export in one pass instead of one field per attempt.
    config = config if isinstance(config, dict) else {}
    role = config.get("openRole") if isinstance(config.get("openRole"), dict) else {}
    for key, value in (
        ("targetSectors", config.get("targetSectors")),
        ("openRole.id", role.get("id")),
        ("openRole.title", role.get("title")),
    ):
        if isinstance(value, str) and not value.strip():
            issues.append(f"{key} cannot be empty")
    functions = role.get("functions")
    if isinstance(functions, list) and any(
        isinstance(f, str) and not f.strip() for f in functions
    ):
        issues.append("openRole.functions cannot contain empty strings")
    criteria = config.get("sourcingCriteria", {})
    if isinstance(criteria, dict):
        for key in (
            "skills",
            "eligibleLocations",
            "priorityTriggers",
            "excludeCompanies",
        ):
            values = criteria.get(key, [])
            if isinstance(values, list) and any(
                isinstance(v, str) and not v.strip() for v in values
            ):
                issues.append(f"sourcingCriteria.{key} cannot contain empty strings")
        event_types = criteria.get("eventTypes")
        if (
            config.get("includeFundingDistress") is False
            and isinstance(event_types, list)
            and all(t == "funding_distress" for t in event_types)
        ):
            issues.append("no enabled event types")
    return issues


def cmd_check_config(args):
    """A setup error is an answer for the user, not a crash: one line, exit 1."""
    try:
        issues = config_problems(args.config)
    except (OSError, ValueError) as exc:  # unreadable file or not JSON
        issues = [f"cannot read {args.config}: {exc}"]
    if issues:
        print("check-config: invalid n8n Config: " + "; ".join(issues), file=sys.stderr)
        sys.exit(1)
    print(f"config OK: {args.config}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser(
        "join",
        help="Trust-boundary join: scanner shortlist against the raw trusted batch.",
    )
    j.add_argument("--raw", required=True)
    j.add_argument("--shortlist", required=True)
    j.add_argument("--out", required=True)
    j.add_argument(
        "--as-of",
        type=parse_as_of,
        default=None,
        help="Run date (YYYY-MM-DD) that event ages count to; default today (UTC).",
    )
    j.set_defaults(func=cmd_join)

    r = sub.add_parser(
        "reconcile", help="Blend advocate + skeptic verdicts into content JSON."
    )
    r.add_argument("--trusted", required=True)
    r.add_argument("--advocate", required=True)
    r.add_argument("--skeptic", required=True)
    r.add_argument("--author", required=True)
    r.add_argument("--company-name", required=True)
    r.add_argument("--role-title", required=True)
    r.add_argument("--role-location", required=True)
    r.add_argument(
        "--min-shown",
        type=int,
        default=4,
        help="Accepted for existing callers; must be nonnegative, otherwise ignored.",
    )
    r.add_argument(
        "--max-shown",
        type=int,
        default=10,
        help="Hard cap on shown candidates (default 10).",
    )
    r.add_argument("--out", required=True)
    r.add_argument(
        "--as-of",
        type=parse_as_of,
        default=None,
        help="Run date (YYYY-MM-DD) that event ages count to; default today (UTC).",
    )
    r.set_defaults(func=cmd_reconcile)

    b = sub.add_parser(
        "build",
        parents=[r],
        add_help=False,
        help="Reconcile, validate, render, verify, then record state.",
    )
    b.add_argument("--raw", required=True, help="This run's deduped new_events.json.")
    b.add_argument(
        "--profile", required=True, help="The saved onepromptman-profile.md."
    )
    b.add_argument("--state", required=True)
    b.add_argument("--html", required=True, help="Final HTML card path.")
    b.add_argument(
        "--noon-handoff",
        action="store_true",
        help="Write a Noon targeting proposal alongside the checked card content.",
    )
    b.add_argument(
        "--template",
        default=str(
            CONTENT_SCHEMA.parent.parent / "templates/overnight_card.template.html"
        ),
    )
    b.set_defaults(func=cmd_build)

    config = sub.add_parser(
        "check-config", help="Validate the setup-generated n8n Config JSON."
    )
    config.add_argument("--config", required=True)
    config.set_defaults(func=cmd_check_config)

    d = sub.add_parser("render", help="Fill the template from content JSON.")
    d.add_argument("--template", required=True)
    d.add_argument("--content", required=True)
    d.add_argument("--out", required=True)
    d.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 1, write nothing) on any missing required field.",
    )
    d.set_defaults(func=cmd_render)

    v = sub.add_parser(
        "verify",
        help="Scan a rendered card for leftover placeholders and banned filler.",
    )
    v.add_argument("--doc", required=True)
    v.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    runlog.setup()
    log.debug("render.py %s", args.cmd)
    args.func(args)
    return 0


if __name__ == "__main__":
    runlog.run(main)

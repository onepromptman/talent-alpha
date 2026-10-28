#!/usr/bin/env python3
"""Talent Alpha deterministic pipeline: trust-boundary join, reconcile, render, verify.

No agent output reaches the final card without passing through this script.
Agents (scanner, advocate, skeptic) emit structured JSON only; this script
does every formatting and every trust decision. That split is the point: an
agent that invents a plausible-looking id, or grades its own candidate as a
stronger fit than it is, cannot make that call stick, because this script
never trusts an agent's own claim of a company/location/id when the trusted
event batch says otherwise.

Subcommands
-----------
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
import re
import sys

TIER_RANK = {"S": 3, "A": 2, "B": 1, "C": 0}
TIER_BY_RANK = ["C", "B", "A", "S"]
TIER_COLOR = {"S": "#C8202E", "A": "#1B3A2C", "B": "#8A6B22", "HELD": "rgba(20,23,28,.45)"}
AXES = ["openness", "role_fit", "product_fit", "region_fit", "size_fit", "stage_fit"]

BANNED_FILLER = ["TBD", "N/A", "Data not available", "NOT_FOUND"]

REQUIRED_RUN_KEYS = [
    "author", "run_date", "company_name", "role_title", "role_location",
    "scanned_count", "window_note",
]
REQUIRED_CANDIDATE_KEYS = [
    "id", "company", "location", "employees_affected", "event_type",
    "event_age_label", "age_days", "titles", "tier", "bands", "wildcard",
    "why", "hook", "edge", "held", "hold_reason", "source_name", "source_url",
]


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


def age_days_of(published_at):
    if not published_at:
        return 999
    try:
        dt = datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 999
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = (now - dt).total_seconds() / 86400.0
    return max(0, math.floor(delta))


def age_label_of(days):
    if days <= 0:
        return "today"
    if days == 1:
        return "1d ago"
    return f"{days}d ago"


# --------------------------------------------------------------- join (trust boundary)

def event_problems(e):
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

    if not (e.get("source_url") or "").strip():
        problems.append("no source_url, so no reader can check the claim")

    published = e.get("published_at")
    if not published:
        problems.append("no published_at")
    else:
        try:
            dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            problems.append(f"unparseable published_at {published!r}")
        else:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            # A future date is not just wrong, it scores BEST: age_days_of
            # clamps negatives to 0, which labels it "today".
            ahead = (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if ahead > 86400:
                problems.append(f"published_at is in the future ({published})")

    affected = e.get("employees_affected")
    if affected is not None:
        if not isinstance(affected, (int, float)) or isinstance(affected, bool):
            problems.append(f"employees_affected is not a number ({affected!r})")
        elif affected < 0:
            problems.append(f"negative employees_affected ({affected})")

    return problems


def cmd_join(args):
    raw_events = load(args.raw)
    by_id = {e["event_id"]: e for e in raw_events}
    shortlist = load(args.shortlist)
    opportunities = shortlist.get("opportunities", [])

    # Reject unusable events before any shortlist entry can reference one.
    rejected = {}
    for eid, e in list(by_id.items()):
        problems = event_problems(e)
        if problems:
            rejected[eid] = problems
            del by_id[eid]

    trusted = []
    dropped = []
    unusable = []
    for o in opportunities:
        oid = o.get("id")
        if oid in rejected:
            unusable.append(oid)
            continue
        base = by_id.get(oid)
        if base is None:
            dropped.append(oid)
            continue
        trusted.append({
            "id": o["id"],
            "company": base.get("company") or o.get("company", ""),
            "event_type": base.get("event_type") or o.get("event_type", ""),
            "functions": o.get("functions", []),
            "location": base.get("location") or o.get("location", ""),
            "employees_affected": base.get("employees_affected"),
            "published_at": base.get("published_at"),
            "score": o.get("score"),
            "why": o.get("why", ""),
            "source_name": base.get("source_name", ""),
            "source_url": base.get("source_url", ""),
        })

    dump(args.out, trusted)
    msg = (f"join: {len(opportunities)} shortlisted, {len(dropped)} dropped (id not in trusted batch), "
           f"{len(unusable)} dropped (event failed batch checks), {len(trusted)} trusted -> {args.out}")
    if dropped:
        msg += f"\n  invented ids: {dropped}"
    for eid, problems in rejected.items():
        msg += f"\n  unusable event {eid}: " + "; ".join(problems)
    print(msg)
    if opportunities and not trusted:
        # A quiet night is an empty SHORTLIST, and 2.2 already stops there. A
        # non-empty shortlist where nothing survives is a data fault: fail loud
        # rather than hand the next step an empty batch to render around.
        print("join: a shortlist arrived but nothing survived the trust boundary. "
              "Fix the pull step; do not render a card from this run.", file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------- reconcile

def cmd_reconcile(args):
    trusted = load(args.trusted)
    trusted_by_id = {t["id"]: t for t in trusted}
    advocate = load(args.advocate).get("verdicts", [])
    skeptic = load(args.skeptic).get("verdicts", [])
    skeptic_by_id = {v["id"]: v for v in skeptic}

    finals = []
    for a in advocate:
        t = trusted_by_id.get(a.get("id"))
        if t is None:
            continue  # advocate invented or mis-copied an id; drop, same as join
        age_days = age_days_of(t.get("published_at"))
        s = skeptic_by_id.get(a["id"])
        rank_a = TIER_RANK[a["tier"]]
        rank_s = TIER_RANK[s["tier"]] if s else rank_a
        blended = js_round((rank_a + rank_s) / 2)
        finals.append({
            "id": a["id"],
            "company": t["company"],
            "location": t["location"],
            "employees_affected": t.get("employees_affected"),
            "event_type": t["event_type"],
            "event_age_label": age_label_of(age_days),
            "age_days": age_days,
            "titles": a.get("titles", []),
            "tier": TIER_BY_RANK[blended],
            "_rank": blended,
            "_disagree": abs(rank_a - rank_s) >= 3,
            "bands": [a.get(axis, "M") for axis in AXES],
            "wildcard": a.get("wildcard", {"fired": False, "axis_index": -1, "bridge": ""}),
            "why": a.get("why", ""),
            "hook": a.get("hook", ""),
            "edge": a.get("edge", ""),
            "held": False,
            "hold_reason": "",
            "source_name": t.get("source_name", ""),
            "source_url": t.get("source_url", ""),
        })

    finals.sort(key=lambda f: (-f["_rank"], f["age_days"]))

    for idx, f in enumerate(finals):
        if idx >= args.max_shown:
            f["held"] = True
            f["tier"] = "HELD"
            f["hold_reason"] = f"beyond the top {args.max_shown} this run"
        elif f["_disagree"] and idx >= args.min_shown:
            f["held"] = True
            f["tier"] = "HELD"
            f["hold_reason"] = "judges disagreed sharply"
        del f["_rank"]
        del f["_disagree"]

    content = {
        "run": {
            "author": args.author,
            "run_date": datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "company_name": args.company_name,
            "role_title": args.role_title,
            "role_location": args.role_location,
            "scanned_count": len(finals),
            "window_note": "72h window",
        },
        "candidates": finals,
    }
    dump(args.out, content)
    shown = sum(1 for f in finals if not f["held"])
    held = sum(1 for f in finals if f["held"])
    print(f"reconcile: {len(finals)} candidates, {shown} shown, {held} held -> {args.out}")


# --------------------------------------------------------------- render

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
    pattern = re.compile(r'<[a-zA-Z0-9]+[^>]*data-slot="' + re.escape(slot) + r'"[^>]*>')
    m = pattern.search(doc)
    if not m:
        return doc
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
    return (f'<div class="srcline">Source: '
            f'<a href="{esc_attr(url)}" rel="noopener noreferrer">{esc(name)}</a></div>')


def render_card(it):
    wc = it.get("wildcard") or {}
    wc_attr = f' data-wc="{esc_attr(wc["axis_index"])}"' if wc.get("fired") else ""
    bridge_chip = f'<span class="bridge">◆ {esc(wc.get("bridge", ""))}</span>' if wc.get("fired") else ""
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
        "</div>"
        + source_html(it)
        + "</div>"
    )


def validate_content(content, strict):
    problems = []
    run = content.get("run", {})
    for key in REQUIRED_RUN_KEYS:
        if key not in run:
            problems.append(f"run.{key} missing")
    for i, c in enumerate(content.get("candidates", [])):
        for key in REQUIRED_CANDIDATE_KEYS:
            if key not in c:
                problems.append(f"candidates[{i}].{key} missing (id={c.get('id', '?')})")
        if "wildcard" in c:
            for key in ("fired", "axis_index", "bridge"):
                if key not in c["wildcard"]:
                    problems.append(f"candidates[{i}].wildcard.{key} missing (id={c.get('id', '?')})")
    if problems and strict:
        print("STRICT RENDER FAILED. Nothing written. Route this back to the producing "
              "agent (scanner/advocate/skeptic) or the reconcile step as a patch, never "
              "hand-edit the output.", file=sys.stderr)
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

    run = content["run"]
    doc = fill_slot(doc, "author", esc(run["author"]))
    doc = fill_slot(doc, "run-date", esc(run["run_date"]))
    doc = fill_slot(doc, "role-name", esc(run["role_title"]))
    doc = fill_slot(doc, "role-meta", esc(run["company_name"] + " · " + run["role_location"]))

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
    doc = fill_slot(doc, "run-id", f'{len(shown) + len(held)} signals scanned · {esc(run["window_note"])}')

    held_summary = (
        f'{len(held)} item' + ("s" if len(held) != 1 else "") + " held for review (judge disagreement or overflow): "
        + "; ".join(f'{h["company"]} ({h["hold_reason"] or "disagreement"})' for h in held)
    ) if held else "clean"

    if not shown:
        summary = f"No auto-cleared movements, but {held_summary}" if held else \
            "No movements cleared the bar this run. Next scan will pick up where this one left off."
        doc = fill_slot(doc, "c-summary", esc(summary))
        # Honest empty state: remove the hero block rather than leave it full
        # of unfilled "-" placeholders (see references/00_SHARED_CORE.md 6).
        doc = re.sub(r"<!-- HERO:START -->.*?<!-- HERO:END -->", "", doc, flags=re.DOTALL)
        doc = fill_slot(doc, "foot-left", "Talent Alpha · overnight brief · WARN + funding-distress categories")
        doc = fill_slot(doc, "foot-right", "Sources travel untrusted · nothing sends automatically")
    else:
        hero, rest = shown[0], shown[1:]
        chip_color = TIER_COLOR.get(hero["tier"], TIER_COLOR["HELD"])
        tag_text = esc(hero["tier"] + " · " + hero["event_type"] + " " + hero["event_age_label"])
        if hero["tier"] == "S":
            hero_chip = f'<span class="chipS">{tag_text}</span>'
        else:
            hero_chip = f'<span class="chipS" style="background:none;border:1px solid {chip_color};color:{chip_color}">{tag_text}</span>'
        doc = doc.replace('<span class="chipS" data-slot="hero-tag">-</span>', hero_chip)
        doc = fill_slot(doc, "hero-company", esc(hero["company"]))
        doc = fill_slot(doc, "hero-loc", esc(loc_line(hero)))
        doc = fill_slot(doc, "hero-titles", "".join(f"<span>{esc(t)}</span>" for t in hero.get("titles", [])))
        doc = fill_slot(doc, "hero-why", esc(hero["why"]))
        doc = fill_slot(doc, "hero-edge", esc(hero["edge"] or "Not enough signal for a leverage read yet."))
        doc = fill_slot(doc, "hero-hook", f'"{esc(hero["hook"])}"')
        doc = fill_slot(doc, "hero-source", source_html(hero))
        wc = hero.get("wildcard") or {}
        wc_attr = f' data-wc="{esc_attr(wc["axis_index"])}"' if wc.get("fired") else ""
        doc = doc.replace(
            'data-bands="M,M,M,M,M,M" data-tier="S" data-size="150"',
            f'data-bands="{esc_attr(",".join(hero["bands"]))}" data-tier="{esc_attr(hero["tier"])}" data-size="150"{wc_attr}',
        )
        cards_html = "".join(render_card(it) for it in rest)
        doc = doc.replace("<!-- CARD:START -->\n<!-- CARD:END -->", "<!-- CARD:START -->" + cards_html + "<!-- CARD:END -->")
        doc = fill_slot(doc, "c-summary", esc(held_summary))
        doc = fill_slot(doc, "foot-left", "Talent Alpha · overnight brief · WARN + funding-distress categories")
        doc = fill_slot(doc, "foot-right", "Sources travel untrusted · nothing sends automatically")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"render: wrote {args.out} ({len(shown)} shown, {len(held)} held)"
          + (f" -- {len(problems)} schema warning(s), non-strict" if problems and not args.strict else ""))


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
    unfilled = re.findall(r'data-slot="([a-zA-Z0-9_-]+)">-<', doc)
    if unfilled:
        findings.append(f"unfilled slot placeholder(s) still showing '-': {sorted(set(unfilled))}")

    if findings:
        print(f"VERIFY FAILED: {args.doc}", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        sys.exit(1)
    print(f"verify OK: {args.doc}")


# --------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser("join", help="Trust-boundary join: scanner shortlist against the raw trusted batch.")
    j.add_argument("--raw", required=True)
    j.add_argument("--shortlist", required=True)
    j.add_argument("--out", required=True)
    j.set_defaults(func=cmd_join)

    r = sub.add_parser("reconcile", help="Blend advocate + skeptic verdicts into content JSON.")
    r.add_argument("--trusted", required=True)
    r.add_argument("--advocate", required=True)
    r.add_argument("--skeptic", required=True)
    r.add_argument("--author", required=True)
    r.add_argument("--company-name", required=True)
    r.add_argument("--role-title", required=True)
    r.add_argument("--role-location", required=True)
    r.add_argument("--min-shown", type=int, default=4, help="Top N always shown (default 4).")
    r.add_argument("--max-shown", type=int, default=10, help="Hard cap on shown candidates (default 10).")
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_reconcile)

    d = sub.add_parser("render", help="Fill the template from content JSON.")
    d.add_argument("--template", required=True)
    d.add_argument("--content", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--strict", action="store_true", help="Fail (exit 1, write nothing) on any missing required field.")
    d.set_defaults(func=cmd_render)

    v = sub.add_parser("verify", help="Scan a rendered card for leftover placeholders and banned filler.")
    v.add_argument("--doc", required=True)
    v.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

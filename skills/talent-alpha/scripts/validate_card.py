"""Validate a Talent Alpha content file against its source batch and judge files.

The production render.py build command invokes check_card before rendering or recording
state. This CLI remains available for frozen evals and checking saved artifacts:

    python validate_card.py check --card <run>/content.json --pull <inputs>

The pull folder contains raw_events.json, optionally onepromptman-profile.md and a
pre-run talent-alpha-state.json. Judge verdict files are siblings of the card.
Checks cover source identity, grounded extractions, numeric claims, copied judge prose,
tier/hold/order rules and already-seen IDs. Lexical overlap and derived percentages are
warnings; these heuristics cannot establish semantic truth or sourcing recall.
Exit 0 means no findings, 1 means findings, and 2 means invalid CLI inputs.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from render import grounded_extraction, resolved_company

TIER_RANK = {"S": 3, "A": 2, "B": 1, "C": 0}
TIER_BY_RANK = ["C", "B", "A", "S"]
AXES = ["openness", "role_fit", "product_fit", "region_fit", "size_fit", "stage_fit"]
CARD_TEXT_FIELDS = ("why", "hook", "edge")

MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?[KkMm]?")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s?%")
BIGINT_RE = re.compile(
    r"(?<![\d.$])\d{2,3}(?:,\d{3})+(?![\d%])|(?<![\d.$,])\d{2,}(?![\d%,])"
)
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
WORD5_RE = re.compile(r"[A-Za-z]{5,}")

FILED_SOURCE = "WARN Firehose"
REPORTED_SOURCE = "Web Search"
WRONG_LABEL_FOR_FILED = re.compile(r"\breported\b", re.IGNORECASE)
WRONG_LABEL_FOR_REPORTED = re.compile(
    r"\b(WARN filing|WARN Act filing|officially filed)\b", re.IGNORECASE
)


# ----------------------------------------------------------------------------- utilities


def load(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm_num(tok: str) -> str:
    t = tok.replace("$", "").replace(",", "").replace(" ", "").replace("%", "").strip()
    mult = 1
    if t and t[-1] in "KkMm":
        mult = 1000 if t[-1] in "Kk" else 1_000_000
        t = t[:-1]
    try:
        val = float(t) * mult
    except ValueError:
        return tok
    return str(int(val)) if val == int(val) else str(val)


def claim_numbers(
    text: str, patterns: tuple = (MONEY_RE, PERCENT_RE, BIGINT_RE)
) -> set[str]:
    """Money, percent, and 2+-digit integer tokens in `text`, normalized. A bare four-digit
    year (2020, not 20.20 or a comma-grouped figure) is furniture, not a claim.

    `patterns` narrows which token kinds to extract: callers building the trusted POOL
    (event/profile literals) want all three; the card-text FABRICATION check wants money
    and bare integers only, scoring an untraceable percent as a warning instead (see
    PERCENT_RE's separate use in `check_card` -- a derived percentage like "cut roughly 26%
    of the plant" is arithmetic, not an invented figure)."""
    found: set[str] = set()
    for pat in patterns:
        for m in pat.finditer(text):
            tok = m.group(0)
            if pat is BIGINT_RE and YEAR_RE.match(tok):
                continue
            found.add(norm_num(tok))
    return found


def words5(text: str) -> set[str]:
    return {w.lower() for w in WORD5_RE.findall(text)}


def js_round(x: float) -> int:
    """Match render.py's js_round: half rounds toward +Infinity, not to-even."""
    return math.floor(x + 0.5)


def leverage_from_profile(text: str) -> str | None:
    section = re.search(
        r"^## Kit: talent-alpha\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    if not section:
        return None
    m = re.search(r"^leverage:[ \t]*(.+)$", section.group(1), re.MULTILINE)
    if not m:
        return None
    raw = m.group(1).strip()
    # Strip a trailing provenance tag: "(stated by user)" or "(web, ..., confirmed by user)"
    raw = re.sub(r"\s*\((?:stated by user|web,[^)]*)\)\s*$", "", raw)
    return raw.strip()


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def leverage_sentences(leverage: str, min_words: int = 6) -> list[str]:
    return [
        s.strip()
        for s in SENTENCE_SPLIT_RE.split(leverage)
        if len(s.strip().split()) >= min_words
    ]


# ----------------------------------------------------------------------------- check


def check_card(
    card: dict,
    advocate: dict,
    skeptic: dict,
    raw_events: dict[str, dict],
    leverage: str | None,
    min_shown: int,
    max_shown: int,
    seen_events: dict | None = None,
) -> tuple[list[str], list[str], dict]:
    findings: list[str] = []
    warnings: list[str] = []

    if not isinstance(card.get("run"), dict) or not isinstance(
        card.get("candidates"), list
    ):
        findings.append(
            "card JSON is not the reconcile shape: missing `run` or `candidates`"
        )
        return findings, warnings, {"count": 0, "shown": 0, "held": 0, "top_tier": None}

    adv_verdicts = advocate.get("verdicts", [])
    skp_verdicts = skeptic.get("verdicts", [])
    adv_by_id = {v["id"]: v for v in adv_verdicts if "id" in v}
    skp_by_id = {v["id"]: v for v in skp_verdicts if "id" in v}

    if not adv_verdicts or not skp_verdicts:
        findings.append(
            "advocate_verdicts.json or skeptic_verdicts.json has no verdicts"
        )

    # Defense in depth for externally supplied or edited content. The production build
    # command also requires both judges to cover every trusted candidate.
    for aid in adv_by_id:
        if aid not in skp_by_id:
            findings.append(f"no skeptic verdict for id {aid!r}")

    if (
        adv_verdicts
        and skp_verdicts
        and json.dumps(adv_verdicts, sort_keys=True)
        == json.dumps(skp_verdicts, sort_keys=True)
    ):
        warnings.append(
            "advocate_verdicts.json and skeptic_verdicts.json are byte-identical; "
            "confirm they were produced independently (agreement alone is not proof of copying)"
        )

    leverage_pool: set[str] = claim_numbers(leverage) if leverage else set()
    leverage_words = words5(leverage) if leverage else set()
    leverage_sents = leverage_sentences(leverage) if leverage else []

    candidates = card["candidates"]
    prev_key: tuple[int, int] | None = None

    for idx, c in enumerate(candidates):
        cid = c.get("id", f"<idx {idx}>")
        if not leverage and c.get("edge", "").strip():
            findings.append(
                f"candidate {cid}: edge supplied but this kit has no saved leverage"
            )

        if seen_events and c.get("id") in seen_events:
            findings.append(
                f"candidate {cid}: this id is already in seen_events "
                "(talent-alpha-state.json) -- the dedupe contract was violated, "
                "most likely by joining against raw_events.json instead of the "
                "deduped new_events.json"
            )

        a = adv_by_id.get(c.get("id"))
        if a is None:
            findings.append(f"candidate {cid}: no advocate verdict for this id")
            continue
        s = skp_by_id.get(c.get("id"))

        rank_a = TIER_RANK.get(a.get("tier"), 0)
        rank_s = TIER_RANK[s["tier"]] if s and s.get("tier") in TIER_RANK else rank_a
        blended = js_round((rank_a + rank_s) / 2)
        disagree = abs(rank_a - rank_s) >= 3

        sort_key = (-blended, c.get("age_days", 0))
        if prev_key is not None and sort_key < prev_key:
            findings.append(
                f"candidate {cid}: out of reconcile order (blended rank / age_days)"
            )
        prev_key = sort_key

        if idx >= max_shown:
            exp_held, exp_reason, exp_tier = (
                True,
                f"beyond the top {max_shown} this run",
                "HELD",
            )
        elif disagree:
            exp_held, exp_reason, exp_tier = True, "judges disagreed sharply", "HELD"
        else:
            exp_held, exp_reason, exp_tier = False, "", TIER_BY_RANK[blended]

        if c.get("held") != exp_held:
            findings.append(
                f"candidate {cid}: held={c.get('held')!r}, expected {exp_held!r}"
            )
        if c.get("hold_reason") != exp_reason:
            findings.append(
                f"candidate {cid}: hold_reason={c.get('hold_reason')!r}, expected {exp_reason!r}"
            )
        if c.get("tier") != exp_tier:
            findings.append(
                f"candidate {cid}: tier={c.get('tier')!r}, expected {exp_tier!r}"
            )

        event = raw_events.get(c.get("id"))
        if event is None:
            findings.append(f"candidate {cid}: id not present in the trusted pull")
        else:
            for field, event_key in (
                ("company", "company"),
                ("location", "location"),
                ("event_type", "event_type"),
                ("employees_affected", "employees_affected"),
                ("source_name", "source_name"),
                ("source_url", "source_url"),
            ):
                expected = event.get(event_key)
                if field == "company":
                    expected = resolved_company(event, c.get(field))
                elif field == "location" and not expected:
                    expected = grounded_extraction(event, c.get(field))
                if c.get(field) != expected:
                    findings.append(
                        f"candidate {cid}: {field}={c.get(field)!r} does not match the "
                        f"trusted pull's {event_key}={event.get(event_key)!r}"
                    )

            # render.py's reconcile copies why/hook/edge/titles onto the card straight off
            # the advocate verdict (cmd_reconcile: "why": a.get("why", ""), etc.); nothing
            # mechanically stops a session from patching content.json by hand after the
            # fact (Edit is in allowed_tools; SKILL.md 2.6 forbids it only by instruction).
            for field, a_key in (("why", "why"), ("hook", "hook"), ("edge", "edge")):
                if (c.get(field) or "") != (a.get(a_key, "") or ""):
                    findings.append(
                        f"candidate {cid}: {field}={c.get(field)!r} does not match the "
                        f"advocate verdict's {a_key}={a.get(a_key, '')!r} verbatim"
                    )
            if (c.get("titles") or []) != (a.get("titles") or []):
                findings.append(
                    f"candidate {cid}: titles={c.get('titles')!r} does not match the "
                    f"advocate verdict's titles={a.get('titles')!r} verbatim"
                )

            event_words = words5(
                " ".join(str(event.get(k, "")) for k in ("title", "snippet", "company"))
            )
            event_pool = claim_numbers(
                " ".join(str(event.get(k, "")) for k in ("title", "snippet"))
            )
            if event.get("employees_affected") is not None:
                event_pool.add(norm_num(str(event["employees_affected"])))
            # A tier that names an external source also names its date
            # (00_SHARED_CORE.md); EVENT_PIPELINE_SCHEMA.md puts <published_at> on every
            # judge batch line, so a card that names the date is following instructions,
            # not inventing a number.
            # DATE ONLY (first 10 chars). The full ISO stamp would fold the clock
            # into the trusted pool: "2026-09-05T20:00:00Z" legitimizes "20" and
            # "00", so a card claiming "20 employees" would trace clean purely
            # because the event happened at 20:00 UTC.
            event_pool |= claim_numbers(str(event.get("published_at", ""))[:10])

            filed = event.get("source_name") == FILED_SOURCE
            reported = event.get("source_name") == REPORTED_SOURCE

            for field in CARD_TEXT_FIELDS:
                text = c.get(field) or ""
                if not text:
                    continue
                allowed = event_pool | leverage_pool
                for tok in claim_numbers(text, patterns=(MONEY_RE, BIGINT_RE)):
                    if tok not in allowed:
                        findings.append(
                            f"candidate {cid}: {field} states a figure not in the pull or "
                            f"profile: {tok}"
                        )
                # A derived percentage (e.g. "cut roughly 26% of the plant" from a
                # headcount and a total) is arithmetic, not an invented number; the pool
                # holds only literals, so nothing derived can ever pass here. EVAL_TUNING
                # Rule 1: a check that can reject a correct output costs a repair lap per
                # run. Warning, not a finding.
                for tok in claim_numbers(text, patterns=(PERCENT_RE,)):
                    if tok not in allowed:
                        warnings.append(
                            f"warning: candidate {cid} {field} states a percent figure "
                            f"not in the pull or profile: {tok}"
                        )
                for sent in leverage_sents:
                    if sent in text:
                        warnings.append(
                            f"candidate {cid}: {field} quotes a COMPANY_PROFILE sentence "
                            f"verbatim: {sent[:80]!r}"
                        )
                if not (words5(text) & (event_words | leverage_words)):
                    warnings.append(
                        f"warning: candidate {cid} {field} shares no word with the pull "
                        f"or the profile: {text[:80]!r}"
                    )
                if filed and WRONG_LABEL_FOR_FILED.search(text):
                    warnings.append(
                        f"warning: candidate {cid} {field} calls a Filed (WARN Firehose) "
                        f"event 'reported': {text[:80]!r}"
                    )
                if reported and WRONG_LABEL_FOR_REPORTED.search(text):
                    warnings.append(
                        f"warning: candidate {cid} {field} calls a Reported (Web Search) "
                        f"event a filing: {text[:80]!r}"
                    )

            for title in c.get("titles") or []:
                allowed = event_pool | leverage_pool
                for tok in claim_numbers(str(title), patterns=(MONEY_RE, BIGINT_RE)):
                    if tok not in allowed:
                        findings.append(
                            f"candidate {cid}: titles state a figure not in the pull or "
                            f"profile: {tok}"
                        )
                for tok in claim_numbers(str(title), patterns=(PERCENT_RE,)):
                    if tok not in allowed:
                        warnings.append(
                            f"warning: candidate {cid} titles state a percent figure not "
                            f"in the pull or profile: {tok}"
                        )

    if len(candidates) < 5:
        warnings.append(
            f"warning: only {len(candidates)} candidate(s) on the card (fewer than 5) -- "
            "a row-count floor above what a slow night's data actually supports would "
            "force invention, so this is a warning, never a finding"
        )

    shown = sum(1 for c in candidates if not c.get("held"))
    held = sum(1 for c in candidates if c.get("held"))
    top_tier = candidates[0]["tier"] if candidates else None
    return (
        findings,
        warnings,
        {"count": len(candidates), "shown": shown, "held": held, "top_tier": top_tier},
    )


# ----------------------------------------------------------------------------- CLI


def cmd_check(args: argparse.Namespace) -> int:
    card_path = Path(args.card)
    run_folder = card_path.parent
    pull_dir = Path(args.pull)

    try:
        card = load(card_path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"validate_card: cannot read --card {card_path}: {e}", file=sys.stderr)
        return 2

    adv_path = run_folder / "advocate_verdicts.json"
    skp_path = run_folder / "skeptic_verdicts.json"
    if not adv_path.exists() or not skp_path.exists():
        print(
            f"validate_card: expected advocate_verdicts.json and skeptic_verdicts.json "
            f"beside {card_path.name} in {run_folder}",
            file=sys.stderr,
        )
        return 2
    advocate = load(adv_path)
    skeptic = load(skp_path)

    events_path = pull_dir / "raw_events.json"
    if not events_path.exists():
        print(
            f"validate_card: no raw_events.json under --pull {pull_dir}",
            file=sys.stderr,
        )
        return 2
    raw_events = {e["event_id"]: e for e in load(events_path)}

    profile_path = pull_dir / "onepromptman-profile.md"
    leverage = None
    if profile_path.exists():
        leverage = leverage_from_profile(profile_path.read_text(encoding="utf-8"))

    # The dedupe contract's WRITE side (seen_events) is what a run that joins raw_events.json
    # instead of the deduped new_events.json would otherwise ship past unnoticed; absent
    # entirely, degrade to no check rather than a usage error (older pull dirs may not carry
    # one).
    state_path = pull_dir / "talent-alpha-state.json"
    seen_events: dict = {}
    if state_path.exists():
        seen_events = load(state_path).get("seen_events", {})

    findings, warnings, stats = check_card(
        card,
        advocate,
        skeptic,
        raw_events,
        leverage,
        args.min_shown,
        args.max_shown,
        seen_events,
    )

    for f in findings:
        print(f"{card_path.name}: {f}")
    for w in warnings:
        print(f"{card_path.name}: {w}")

    print(
        f"validate_card: {stats['count']} card(s), {stats['shown']} shown, "
        f"{stats['held']} held, top tier {stats['top_tier']}"
    )
    if findings:
        print(f"check: {len(findings)} finding(s)")
        return 1
    print("check: clean" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validate_card.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser(
        "check", help="Validate a reconciled card against its fixture pull."
    )
    c.add_argument("--card", required=True, help="Path to the reconciled content.json.")
    c.add_argument(
        "--pull",
        required=True,
        help="Path to the fixture dir (raw_events.json, onepromptman-profile.md).",
    )
    c.add_argument("--min-shown", type=int, default=4)
    c.add_argument("--max-shown", type=int, default=10)
    c.set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

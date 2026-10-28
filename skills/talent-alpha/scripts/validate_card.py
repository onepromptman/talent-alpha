"""Card-accuracy contract for Talent Alpha: the layer `render.py` does not already check.

`render.py verify` already scans the rendered HTML for filler, unfilled slot placeholders,
and em dashes; `render.py render --strict` already fails closed on a missing required
content field. This script does not re-implement either. Its job is everything neither
covers: the two judges are actually independent, the blend formula was applied correctly,
and the free-text fields (`why`, `hook`, `edge`, `titles`) trace to the trusted pull or the
company profile rather than being invented -- the risks the card-accuracy eval
(`evals/card-accuracy/`) names.

    python3 validate_card.py check --card <run folder>/content.json --pull <fixture dir>
        [--min-shown 4] [--max-shown 10]

`--card` is the reconciled content JSON `render.py reconcile` writes (`run` + `candidates`).
Its sibling files in the same run folder, `advocate_verdicts.json` and `skeptic_verdicts.json`
(the exact names `SKILL.md` step 2.5 has each judge write), are read alongside it: the card
itself carries only the BLENDED tier, so the "was a judge actually skipped" and "was the
blend formula applied correctly" checks are impossible from the card alone (`render.py`
falls back to the advocate's own tier when a skeptic verdict is missing for an id, so a
skipped judge renders a perfectly normal-looking card -- the card cannot indict itself).

`--pull` is the fixture directory: `raw_events.json` (the frozen pull, keyed on `event_id`,
`EVENT_PIPELINE_SCHEMA.md` shape), `onepromptman-profile.md` (for the `## Kit:
talent-alpha` block's `leverage` paragraph, i.e. COMPANY_PROFILE), and, optionally,
`talent-alpha-state.json` (the dedupe state file, §6 of the same schema doc -- its
`seen_events` keys feed the dedupe check below; absent entirely, that one check degrades
to a no-op rather than a usage error).

Checks (FINDINGS -- fail the run):

  - grounding    every candidate id resolves to an advocate verdict; every advocate id
                 resolves to a skeptic verdict (a skipped skeptic is otherwise invisible,
                 per the docstring above)
  - identity     advocate_verdicts.json and skeptic_verdicts.json are not byte-identical
                 (the two judges did not just mirror one output)
  - engine-pinned fields (company, location, event_type, employees_affected, source_name,
                 source_url) match the trusted event exactly -- these ARE already pinned by
                 `render.py join`+`reconcile`, so this only catches a hand-edited card
                 (SKILL.md 2.6 forbids hand-editing the output)
  - tier         candidate tier == TIER_BY_RANK[js_round((rank_a + rank_s) / 2)] (rank_s
                 falls back to rank_a when the skeptic verdict is missing, matching
                 render.py exactly) unless held, in which case tier must be "HELD"
  - held         held/hold_reason reproduces reconcile's two rules over the card's own
                 array order (which IS reconcile's post-sort order): idx >= --max-shown ->
                 "beyond the top N this run"; disagreement (|rank_a - rank_s| >= 3) at
                 idx >= --min-shown -> "judges disagreed sharply"; else not held
  - order        the card's candidate order is non-increasing blended rank, ties broken by
                 ascending age_days (reconcile's own sort key)
  - fabrication  a money or large-integer figure in why/hook/edge/titles that is not the
                 trusted event's own employees_affected, its own published_at, nor a figure
                 stated in the profile's leverage paragraph is an invented number, not a
                 phrasing choice (EVAL_TUNING.md: a hard finding an agent can satisfy by
                 deleting content will be satisfied by deleting content -- deleting a number
                 an agent has no reason to invent in the first place is not a defect this
                 makes worse). A percent figure is NOT here -- see WARNINGS -- because a
                 correctly DERIVED percentage (e.g. a headcount over a total) is arithmetic,
                 not an invented literal, and the pool holds only literals.
  - copied       a candidate's why/hook/edge/titles equals the matching advocate verdict's
                 own fields verbatim (render.py's reconcile copies these fields straight off
                 the advocate verdict; nothing else in the pipeline mechanically stops a
                 session from hand-patching content.json afterward)
  - dedupe       no candidate id appears in the pull dir's talent-alpha-state.json
                 `seen_events` (an already-seen event reaching the card means something
                 joined against raw_events.json instead of the deduped new_events.json --
                 the card alone cannot reveal this either)

WARNINGS (printed, never fail the run -- EVAL_TUNING.md: traceability of a free-text column
is a warning, not a finding, because a hard fail here is trivially gamed by deleting the
one word that would have triggered it):

  - a why/hook/edge with no 5+-letter word in common with the trusted event's own text
    (title/snippet/company) or the leverage paragraph
  - prose that names the OTHER provenance tier's vocabulary (a Filed/WARN-Firehose event
    described as "reported"; a Reported/Web-Search event described as "filed") -- real, but
    a keyword match on ordinary English ("no problems reported") is too blunt to fail a
    correct run on, so it surfaces for a human, per the same EVAL_TUNING rule above
  - a percent figure in why/hook/edge/titles with no literal match in the pull or profile
    pool (EVAL_TUNING Rule 1: a check that can reject a correct output costs a repair lap
    per run -- a derived percentage is the common case, not the exception)
  - a leverage-paragraph sentence (6+ words) appearing verbatim inside a candidate's
    why/hook/edge (demoted from a finding: the risk this pipeline names is a paraphrase
    that misstates the profile, and an exact quote is the one form of edge that cannot do
    that)
  - fewer than 5 candidates on the card (a row-count floor above what a slow night's data
    actually supports would force invention, per EVAL_TUNING's row-floor lesson)

Exit 0 clean (warnings allowed), 1 with findings (one line each), 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

TIER_RANK = {"S": 3, "A": 2, "B": 1, "C": 0}
TIER_BY_RANK = ["C", "B", "A", "S"]
AXES = ["openness", "role_fit", "product_fit", "region_fit", "size_fit", "stage_fit"]
CARD_TEXT_FIELDS = ("why", "hook", "edge")

MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?[KkMm]?")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s?%")
BIGINT_RE = re.compile(r"(?<![\d.$])\d{2,3}(?:,\d{3})+(?![\d%])|(?<![\d.$,])\d{2,}(?![\d%,])")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
WORD5_RE = re.compile(r"[A-Za-z]{5,}")

FILED_SOURCE = "WARN Firehose"
REPORTED_SOURCE = "Web Search"
WRONG_LABEL_FOR_FILED = re.compile(r"\breported\b", re.I)
WRONG_LABEL_FOR_REPORTED = re.compile(r"\b(WARN filing|WARN Act filing|officially filed)\b", re.I)


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


def claim_numbers(text: str, patterns: tuple = (MONEY_RE, PERCENT_RE, BIGINT_RE)) -> set[str]:
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
    m = re.search(r"^\s*leverage:\s*(.+)$", text, re.M)
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

    if not isinstance(card.get("run"), dict) or not isinstance(card.get("candidates"), list):
        findings.append("card JSON is not the reconcile shape: missing `run` or `candidates`")
        return findings, warnings, {"count": 0, "shown": 0, "held": 0, "top_tier": None}

    adv_verdicts = advocate.get("verdicts", [])
    skp_verdicts = skeptic.get("verdicts", [])
    adv_by_id = {v["id"]: v for v in adv_verdicts if "id" in v}
    skp_by_id = {v["id"]: v for v in skp_verdicts if "id" in v}

    if not adv_verdicts or not skp_verdicts:
        findings.append("advocate_verdicts.json or skeptic_verdicts.json has no verdicts")

    # A judge cannot be caught skipping a candidate from the card alone (render.py falls
    # back to the advocate's own tier silently); check the raw verdict files instead.
    for aid in adv_by_id:
        if aid not in skp_by_id:
            findings.append(
                f"no skeptic verdict for id {aid!r} (render.py falls back to the "
                "advocate's own tier, which the rendered card cannot reveal)"
            )

    if adv_verdicts and skp_verdicts:
        if json.dumps(adv_verdicts, sort_keys=True) == json.dumps(skp_verdicts, sort_keys=True):
            findings.append(
                "advocate_verdicts.json and skeptic_verdicts.json are byte-identical; "
                "the two judges must not mirror each other"
            )

    leverage_pool: set[str] = claim_numbers(leverage) if leverage else set()
    leverage_words = words5(leverage) if leverage else set()
    leverage_sents = leverage_sentences(leverage) if leverage else []

    candidates = card["candidates"]
    prev_key: tuple[int, int] | None = None

    for idx, c in enumerate(candidates):
        cid = c.get("id", f"<idx {idx}>")

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
            exp_held, exp_reason, exp_tier = True, f"beyond the top {max_shown} this run", "HELD"
        elif disagree and idx >= min_shown:
            exp_held, exp_reason, exp_tier = True, "judges disagreed sharply", "HELD"
        else:
            exp_held, exp_reason, exp_tier = False, "", TIER_BY_RANK[blended]

        if c.get("held") != exp_held:
            findings.append(f"candidate {cid}: held={c.get('held')!r}, expected {exp_held!r}")
        if c.get("hold_reason") != exp_reason:
            findings.append(
                f"candidate {cid}: hold_reason={c.get('hold_reason')!r}, expected {exp_reason!r}"
            )
        if c.get("tier") != exp_tier:
            findings.append(f"candidate {cid}: tier={c.get('tier')!r}, expected {exp_tier!r}")

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
                if c.get(field) != event.get(event_key):
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
    return findings, warnings, {"count": len(candidates), "shown": shown, "held": held, "top_tier": top_tier}


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
        print(f"validate_card: no raw_events.json under --pull {pull_dir}", file=sys.stderr)
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
        card, advocate, skeptic, raw_events, leverage, args.min_shown, args.max_shown,
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
    c = sub.add_parser("check", help="Validate a reconciled card against its fixture pull.")
    c.add_argument("--card", required=True, help="Path to the reconciled content.json.")
    c.add_argument("--pull", required=True, help="Path to the fixture dir (raw_events.json, onepromptman-profile.md).")
    c.add_argument("--min-shown", type=int, default=4)
    c.add_argument("--max-shown", type=int, default=10)
    c.set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

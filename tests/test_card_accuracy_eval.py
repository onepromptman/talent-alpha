"""Tests for the talent-alpha `card-accuracy` eval: the fixture, `scripts/validate_card.py`,
and the case's own structural pins (post_run line, model, web-tool exclusion).

Run from the module directory: `python -m pytest -q tests`. Nothing here spends a model
call: `scripts/state.py`, `scripts/render.py`, and `scripts/validate_card.py` are pure
deterministic CLIs, exercised the same way the eval's own prompt shells out to them
(subprocess, not import), matching `tests/test_build.py`.

The "shaped positive fixture" this file builds (`_build_shaped_run`) is not hand-typed: it
runs the real `state.py dedupe` -> `render.py join` -> `render.py reconcile` ->
`render.py render --strict` -> `render.py verify` chain against
`evals/fixtures/raw_events.json` (the frozen pull) and
`tests/fixtures/card-accuracy/{shortlist,advocate_verdicts,skeptic_verdicts}.json` (a
hand-authored but representative scanner shortlist and judge pair). That proves mutual
satisfiability against the ACTUAL reconcile formula, not a paraphrase of it
(EVAL_TUNING.md: "prove mutual satisfiability with a shaped positive fixture that a real
agent could produce").
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = MODULE_ROOT / "skills" / "talent-alpha"
SCRIPTS = SKILL_ROOT / "scripts"
TEMPLATE = SKILL_ROOT / "references" / "templates" / "overnight_card.template.html"

EVAL_FIXTURES = MODULE_ROOT / "evals" / "fixtures"
RAW_EVENTS = EVAL_FIXTURES / "raw_events.json"
STATE_FIXTURE = EVAL_FIXTURES / "talent-alpha-state.json"
PROFILE_FIXTURE = EVAL_FIXTURES / "onepromptman-profile.md"

TEST_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "card-accuracy"
SHORTLIST_FIXTURE = TEST_FIXTURES / "shortlist.json"
ADVOCATE_FIXTURE = TEST_FIXTURES / "advocate_verdicts.json"
SKEPTIC_FIXTURE = TEST_FIXTURES / "skeptic_verdicts.json"

CASE_DIR = MODULE_ROOT / "evals" / "card-accuracy"
MODULE_YAML = MODULE_ROOT / "MODULE.yaml"

AUTHOR = "Priya Nakamura"
COMPANY = "Solstice Yards"
ROLE_TITLE = "Senior Reliability Engineer"
ROLE_LOCATION = "Denver, CO"


def run(cmd, cwd):
    return subprocess.run(
        [sys.executable, *cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _reconcile(
    tmp_path, trusted, advocate_path, skeptic_path, min_shown=4, max_shown=10
):
    content_path = tmp_path / "content.json"
    proc = run(
        [
            "scripts/render.py",
            "reconcile",
            "--trusted",
            str(trusted),
            "--advocate",
            str(advocate_path),
            "--skeptic",
            str(skeptic_path),
            "--author",
            AUTHOR,
            "--company-name",
            COMPANY,
            "--role-title",
            ROLE_TITLE,
            "--role-location",
            ROLE_LOCATION,
            "--min-shown",
            str(min_shown),
            "--max-shown",
            str(max_shown),
            "--out",
            str(content_path),
        ],
        cwd=SKILL_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return content_path


def _build_shaped_run(tmp_path, skeptic_verdicts=None, min_shown=4, max_shown=10):
    """Run the real dedupe -> join -> reconcile chain against the fixture pull and the
    (possibly mutated) judge verdicts. Returns (content_path, advocate_path, skeptic_path)
    -- all three siblings in tmp_path, matching the run folder layout validate_card.py
    expects. `skeptic_verdicts`, when given, replaces the fixture's skeptic verdicts (used
    to shape the "skipped skeptic" mutation before reconcile ever runs). `min_shown` /
    `max_shown` thread through to the real reconcile call so a HELD-branch test reconciles
    and validates against the SAME thresholds."""
    new_events = tmp_path / "new_events.json"
    dedupe = run(
        [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(RAW_EVENTS),
            "--state",
            str(STATE_FIXTURE),
            "--out",
            str(new_events),
        ],
        cwd=SKILL_ROOT,
    )
    assert dedupe.returncode == 0, dedupe.stdout + dedupe.stderr

    trusted = tmp_path / "trusted_candidates.json"
    join = run(
        [
            "scripts/render.py",
            "join",
            "--raw",
            str(new_events),
            "--shortlist",
            str(SHORTLIST_FIXTURE),
            "--out",
            str(trusted),
        ],
        cwd=SKILL_ROOT,
    )
    assert join.returncode == 0, join.stdout + join.stderr

    advocate_path = tmp_path / "advocate_verdicts.json"
    advocate_path.write_text(
        ADVOCATE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    skeptic_path = tmp_path / "skeptic_verdicts.json"
    if skeptic_verdicts is None:
        skeptic_path.write_text(
            SKEPTIC_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        skeptic_path.write_text(json.dumps(skeptic_verdicts), encoding="utf-8")

    content_path = _reconcile(
        tmp_path,
        trusted,
        advocate_path,
        skeptic_path,
        min_shown=min_shown,
        max_shown=max_shown,
    )
    return content_path, advocate_path, skeptic_path


def _validate(content_path, extra_args=()):
    return run(
        [
            "scripts/validate_card.py",
            "check",
            "--card",
            str(content_path),
            "--pull",
            str(EVAL_FIXTURES),
            *extra_args,
        ],
        cwd=SKILL_ROOT,
    )


# --------------------------------------------------------------------- fixture pins


def test_dedupe_drops_exactly_the_seeded_event(tmp_path):
    """The eval fixture's state file already carries `warn-099888` as seen; a dedupe
    against `raw_events.json` must drop that one id and nothing else."""
    out = tmp_path / "new_events.json"
    proc = run(
        [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(RAW_EVENTS),
            "--state",
            str(STATE_FIXTURE),
            "--out",
            str(out),
        ],
        cwd=SKILL_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fresh = json.loads(out.read_text(encoding="utf-8"))
    ids = {e["event_id"] for e in fresh}
    assert "warn-099888" not in ids
    assert len(ids) == 5


def test_join_drops_nothing_from_the_shaped_shortlist(tmp_path):
    """The test-fixture shortlist copies every deduped event's id exactly; join must
    trust all 5 and drop none."""
    new_events = tmp_path / "new_events.json"
    run(
        [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(RAW_EVENTS),
            "--state",
            str(STATE_FIXTURE),
            "--out",
            str(new_events),
        ],
        cwd=SKILL_ROOT,
    )
    trusted = tmp_path / "trusted_candidates.json"
    proc = run(
        [
            "scripts/render.py",
            "join",
            "--raw",
            str(new_events),
            "--shortlist",
            str(SHORTLIST_FIXTURE),
            "--out",
            str(trusted),
        ],
        cwd=SKILL_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 dropped" in proc.stdout
    assert len(json.loads(trusted.read_text(encoding="utf-8"))) == 5


# --------------------------------------------------------------------- (a) positive fixture


def test_validate_card_passes_on_the_shaped_positive_fixture(tmp_path):
    """The real chain (dedupe -> join -> reconcile) over the fixture pull and the
    hand-authored-but-representative judge verdicts renders --strict, verifies clean, and
    validate_card.py finds nothing wrong: proof the checks are mutually satisfiable, not
    just individually correct."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path)

    html = tmp_path / "overnight_card.html"
    render = run(
        [
            "scripts/render.py",
            "render",
            "--template",
            str(TEMPLATE),
            "--content",
            str(content_path),
            "--out",
            str(html),
            "--strict",
        ],
        cwd=SKILL_ROOT,
    )
    assert render.returncode == 0, render.stdout + render.stderr

    verify = run(["scripts/render.py", "verify", "--doc", str(html)], cwd=SKILL_ROOT)
    assert verify.returncode == 0, verify.stdout + verify.stderr

    validate = _validate(content_path)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "check: clean" in validate.stdout


# --------------------------------------------------------------------- (b) five distinct FAIL checks


def test_validate_card_fails_on_skipped_skeptic_verdict(tmp_path):
    """A skeptic verdict missing for one id renders a perfectly normal-looking card
    (render.py falls back to the advocate's own tier); validate_card.py must catch it from
    the raw verdict files, which the card itself cannot reveal."""
    full_skeptic = json.loads(SKEPTIC_FIXTURE.read_text(encoding="utf-8"))
    dropped_id = full_skeptic["verdicts"][-1]["id"]
    truncated = {
        "verdicts": [v for v in full_skeptic["verdicts"] if v["id"] != dropped_id]
    }

    content_path, _adv, _skp = _build_shaped_run(tmp_path, skeptic_verdicts=truncated)
    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert f"no skeptic verdict for id {dropped_id!r}" in proc.stdout


def test_validate_card_fails_on_wrong_tier(tmp_path):
    """A card tier that does not equal TIER_BY_RANK[js_round((rank_a + rank_s) / 2)] is a
    finding, whether from a reconcile bug or a hand-edited card."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    original_tier = content["candidates"][0]["tier"]
    content["candidates"][0]["tier"] = "C" if original_tier != "C" else "S"
    content_path.write_text(json.dumps(content), encoding="utf-8")

    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "expected" in proc.stdout


def test_validate_card_fails_on_untraceable_why(tmp_path):
    """A figure in `why` that is neither the trusted event's own employees_affected nor a
    number in the profile's leverage paragraph is an invented number, not a phrasing
    choice, and must fail (a fabrication finding, not a free-text traceability warning)."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    content["candidates"][0]["why"] += (
        " 412 employees were actually affected, according to internal sources."
    )
    content_path.write_text(json.dumps(content), encoding="utf-8")

    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "states a figure not in the pull or profile: 412" in proc.stdout


def test_validate_card_warns_on_verbatim_profile_sentence_in_edge(tmp_path):
    """A full leverage-paragraph sentence copied verbatim into `edge` is a WARNING, not a
    finding: an exact quote is the one form of `edge` that CANNOT misattribute the profile
    (the risk this pipeline actually names), while a distorted paraphrase -- the real risk
    -- would sail through unflagged either way. Demoted per the pre-spend review of this
    eval; a passing run may still carry this warning without failing.

    The mutation goes into the ADVOCATE verdict, then re-reconciles, rather than patching
    `content.json` directly: reconcile copies `edge` onto the card verbatim from the
    advocate, so a hand-patched card that diverges from its advocate verdict is exactly
    what the new copied-verbatim FINDING (check 5) exists to catch. Mutating the source the
    card is genuinely copied from is the only way to isolate this check from that one."""
    content_path, adv_path, skp_path = _build_shaped_run(tmp_path)
    hero_id = json.loads(content_path.read_text(encoding="utf-8"))["candidates"][0][
        "id"
    ]

    advocate = json.loads(adv_path.read_text(encoding="utf-8"))
    verbatim_sentence = (
        "We cover full relocation, including moving costs and 45 days of temporary "
        "housing for anyone relocating to Denver."
    )
    hero_verdict = next(v for v in advocate["verdicts"] if v["id"] == hero_id)
    hero_verdict["edge"] = verbatim_sentence
    adv_path.write_text(json.dumps(advocate), encoding="utf-8")

    trusted = tmp_path / "trusted_candidates.json"
    content_path = _reconcile(tmp_path, trusted, adv_path, skp_path)

    proc = _validate(content_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "quotes a COMPANY_PROFILE sentence verbatim" in proc.stdout
    assert "check: clean" in proc.stdout and "warning" in proc.stdout


def test_validate_card_fails_on_mismatched_source_name(tmp_path):
    """A card's source_name must match the trusted pull's source_name verbatim; a hand
    edit that drifts it (or a bug that relabels a Filed WARN Firehose event as a Web
    Search Reported one) is a finding."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    assert content["candidates"][0]["source_name"] == "WARN Firehose"
    content["candidates"][0]["source_name"] = "Web Search"
    content_path.write_text(json.dumps(content), encoding="utf-8")

    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert (
        "source_name='Web Search' does not match the trusted pull's source_name='WARN Firehose'"
        in proc.stdout
    )


def test_validate_card_fails_on_card_text_diverging_from_advocate_verdict(tmp_path):
    """render.py's reconcile copies why/hook/edge/titles straight off the advocate verdict
    (cmd_reconcile: `"why": a.get("why", "")`, `"hook": a.get("hook", "")`,
    `"edge": a.get("edge", "")`, `"titles": a.get("titles", [])`); nothing else in the
    pipeline stops a session from patching content.json by hand afterward to clear a
    render/verify failure (Edit is in allowed_tools; SKILL.md 2.6 forbids this only by
    instruction, not mechanically). validate_card.py must catch the divergence directly."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    content["candidates"][0]["hook"] = (
        "A hand-edited hook that never went through a judge."
    )
    content_path.write_text(json.dumps(content), encoding="utf-8")

    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "does not match the advocate verdict's hook" in proc.stdout


def test_validate_card_fails_on_seen_event_id(tmp_path):
    """A run that joins raw_events.json (the full, UNDEDUPED batch) instead of
    new_events.json ships a candidate whose id is already in the pull dir's
    talent-alpha-state.json `seen_events` -- every other check is happy to pass it (its
    fields trace fine to the trusted pull), so only a direct check against the state file
    catches the dedupe-contract violation."""
    shortlist = json.loads(SHORTLIST_FIXTURE.read_text(encoding="utf-8"))
    shortlist["opportunities"].append(
        {
            "id": "warn-099888",
            "company": "Thistledown Hardware",
            "event_type": "layoff",
            "functions": ["Test Engineer"],
            "location": "Denver, CO",
            "score": 50,
            "why": "Smaller named layoff, already seen on a prior run.",
        }
    )
    shortlist_path = tmp_path / "shortlist.json"
    shortlist_path.write_text(json.dumps(shortlist), encoding="utf-8")

    trusted = tmp_path / "trusted_candidates.json"
    join = run(
        [
            "scripts/render.py",
            "join",
            "--raw",
            str(RAW_EVENTS),  # undeduped -- the bug this check exists to catch
            "--shortlist",
            str(shortlist_path),
            "--out",
            str(trusted),
        ],
        cwd=SKILL_ROOT,
    )
    assert join.returncode == 0, join.stdout + join.stderr

    extra_verdict = {
        "id": "warn-099888",
        "tier": "C",
        "openness": "L",
        "role_fit": "L",
        "product_fit": "L",
        "region_fit": "M",
        "size_fit": "L",
        "stage_fit": "L",
        "wildcard": {"fired": False, "axis_index": -1, "bridge": ""},
        "titles": ["Test Engineer"],
        "why": "Small, stale layoff.",
        "hook": "",
        "edge": "",
    }

    advocate = json.loads(ADVOCATE_FIXTURE.read_text(encoding="utf-8"))
    advocate["verdicts"].append(extra_verdict)
    advocate_path = tmp_path / "advocate_verdicts.json"
    advocate_path.write_text(json.dumps(advocate), encoding="utf-8")

    skeptic = json.loads(SKEPTIC_FIXTURE.read_text(encoding="utf-8"))
    skeptic["verdicts"].append(extra_verdict)
    skeptic_path = tmp_path / "skeptic_verdicts.json"
    skeptic_path.write_text(json.dumps(skeptic), encoding="utf-8")

    content_path = _reconcile(tmp_path, trusted, advocate_path, skeptic_path)
    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "warn-099888" in proc.stdout and "seen_events" in proc.stdout


def test_validate_card_warns_on_small_batch(tmp_path):
    """Fewer than 5 candidates on the card is a WARNING, never a finding: a row-count floor
    above what a slow night's data actually supports would force invention (EVAL_TUNING's
    row-floor lesson). Slicing to the first 2 of the shaped fixture's 5 sorted candidates
    keeps every other check clean (idx 0/1 are shown either way, below both --min-shown 4
    and --max-shown 10), isolating this one."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    content["candidates"] = content["candidates"][:2]
    content_path.write_text(json.dumps(content), encoding="utf-8")

    proc = _validate(content_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "fewer than 5" in proc.stdout
    assert "check: clean" in proc.stdout


def test_validate_card_pins_held_branch_and_reason_string(tmp_path):
    """The shaped fixture's default --max-shown 10 never exercises the HELD branch (5
    candidates, 0 held) -- zero test coverage of it. Reconciling and validating against
    --max-shown 3 instead holds 2 of the 5 for 'beyond the top 3 this run', proving both
    that a CORRECT held/hold_reason passes clean and that a WRONG one is caught, with the
    literal reason string pinned either way."""
    content_path, _adv, _skp = _build_shaped_run(tmp_path, max_shown=3)

    clean = _validate(content_path, extra_args=("--min-shown", "4", "--max-shown", "3"))
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "validate_card: 5 card(s), 3 shown, 2 held" in clean.stdout

    content = json.loads(content_path.read_text(encoding="utf-8"))
    held_candidates = [c for c in content["candidates"] if c["held"]]
    assert len(held_candidates) == 2, (
        "expected exactly 2 held candidates at --max-shown 3"
    )
    held_candidates[0]["hold_reason"] = "wrong reason"
    content_path.write_text(json.dumps(content), encoding="utf-8")

    broken = _validate(
        content_path, extra_args=("--min-shown", "4", "--max-shown", "3")
    )
    assert broken.returncode == 1, broken.stdout + broken.stderr
    assert "expected 'beyond the top 3 this run'" in broken.stdout


# --------------------------------------------------------------------- (c) case structure pins


def test_module_yaml_post_run_line_for_card_accuracy():
    """Pin the literal post_run command: dropping --pull or --min-shown/--max-shown here
    would silently disable the checks that need them (EVAL_TUNING.md: dropping a flag from
    post_run can silently disable a check)."""
    text = MODULE_YAML.read_text(encoding="utf-8")
    m = re.search(r"card-accuracy:\s*(.+)", text)
    assert m, "card-accuracy post_run line not found"
    line = m.group(1)
    assert line == (
        "python skills/talent-alpha/scripts/validate_card.py check "
        "--card {workspace}/out/card.content.json --pull {workspace}/fixtures "
        "--min-shown 4 --max-shown 10"
    )


def test_prompt_pins_model_and_excludes_web_tools():
    """`prompt.md` pins `model:` (ANTHROPIC_MODEL is not inherited by eval runs) and does
    not add WebSearch/WebFetch to allowed_tools (the run makes no web queries; the eval's
    own graders assert zero calls to either)."""
    # function-core is fetched at the core.lock pin (tools/fetch_core.py), not vendored;
    # tools/gates.sh exports FUNCTION_CORE_DIR for the evaluate run.
    fc = os.environ.get("FUNCTION_CORE_DIR")
    if not fc:
        pytest.skip("FUNCTION_CORE_DIR not set; run via tools/gates.sh")
    core_build = Path(fc) / "build"
    if str(core_build) not in sys.path:
        sys.path.insert(0, str(core_build))
    import eval_runner

    case = eval_runner.load_case(CASE_DIR)
    assert case.model == "claude-sonnet-5"
    assert "WebSearch" not in case.allowed_tools
    assert "WebFetch" not in case.allowed_tools


def test_case_declares_both_web_tool_graders_at_max_zero():
    text = (CASE_DIR / "graders" / "no-websearch.md").read_text(encoding="utf-8")
    assert "max: 0" in text
    text = (CASE_DIR / "graders" / "no-webfetch.md").read_text(encoding="utf-8")
    assert "max: 0" in text


# --------------------------------------------------------------------- spawn graders (item 1)

SPAWN_GRADER_AGENT = {
    "spawned-scanner.md": "scanner",
    "spawned-advocate.md": "advocate",
    "spawned-skeptic.md": "skeptic",
    "spawned-critic-twice.md": "critic",
}


def _input_match(grader_path: Path) -> str:
    text = grader_path.read_text(encoding="utf-8")
    m = re.search(r"^input_match:\s*'(.+)'\s*$", text, re.MULTILINE)
    assert m, f"no input_match line in {grader_path}"
    return m.group(1)


@pytest.mark.parametrize("grader_file,agent", sorted(SPAWN_GRADER_AGENT.items()))
def test_spawn_grader_matches_namespaced_and_bare_subagent_type(grader_file, agent):
    """Each `spawned-*` grader's `input_match` is checked against
    `json.dumps(inp, ensure_ascii=False, sort_keys=True)` of the PARSED Agent tool input
    (verified fact: clean JSON, unescaped quotes, a space after every colon), and a real
    kept run shows plugin subagent types emitted NAMESPACED (`talent-one:jdbot` style). The
    grader must therefore match both a namespaced and a bare spawn of ITS OWN agent, and
    must NOT match a spawn of any of the other three agents (namespaced or bare) -- the
    fix must not become a bare substring like "critic" that an advocate's own prompt text
    could satisfy."""
    pattern = _input_match(CASE_DIR / "graders" / grader_file)

    own_namespaced = json.dumps(
        {"subagent_type": f"talent-alpha:{agent}"}, sort_keys=True
    )
    own_bare = json.dumps({"subagent_type": agent}, sort_keys=True)
    assert re.search(pattern, own_namespaced), (
        f"{grader_file}'s input_match must match a namespaced spawn of {agent!r}"
    )
    assert re.search(pattern, own_bare), (
        f"{grader_file}'s input_match must match a bare spawn of {agent!r}"
    )

    for other in set(SPAWN_GRADER_AGENT.values()) - {agent}:
        other_namespaced = json.dumps(
            {"subagent_type": f"talent-alpha:{other}"}, sort_keys=True
        )
        other_bare = json.dumps({"subagent_type": other}, sort_keys=True)
        assert not re.search(pattern, other_namespaced), (
            f"{grader_file}'s input_match must NOT match a spawn of {other!r} ({own_namespaced!r})"
        )
        assert not re.search(pattern, other_bare), (
            f"{grader_file}'s input_match must NOT match a spawn of {other!r} ({own_bare!r})"
        )


# --------------------------------------------------------------------- state.py record (item 8)


def test_prompt_pins_the_state_record_step():
    """SKILL.md 2.7 records this run's reconciled candidates as seen after a successful
    render; the eval's own prompt must exercise that write, not just the dedupe READ at
    step 3, or the next run's dedupe is untested."""
    text = (CASE_DIR / "prompt.md").read_text(encoding="utf-8")
    assert "state.py record" in text
    assert "--candidates" in text
    assert "--state ./talent-alpha-state.json" in text


def test_case_declares_a_state_record_grader():
    """A `tool_used` Bash grader with `min >= 1` pins that the run actually called
    `state.py record`, not merely that the prompt asked it to."""
    matches = [
        g
        for g in (CASE_DIR / "graders").glob("*.md")
        if "tool: Bash" in g.read_text(encoding="utf-8") and "record" in _input_match(g)
    ]
    assert matches, "expected a tool_used Bash grader pinning the state.py record step"
    for g in matches:
        text = g.read_text(encoding="utf-8")
        m = re.search(r"^min:\s*(\d+)\s*$", text, re.MULTILINE)
        assert m and int(m.group(1)) >= 1, f"{g.name} should require at least 1 call"


def test_published_at_pool_is_date_only_not_the_clock(tmp_path):
    """The trusted pool takes the event's DATE, not its full ISO timestamp.

    The agents are directed to name a source's date, so `published_at` has to be
    traceable -- but folding the whole stamp in legitimizes the clock too:
    `2026-09-05T20:00:00Z` would put `20` and `00` in the pool, so a card claiming
    "20 employees" traces clean purely because the event happened at 20:00 UTC.
    Only the first 10 characters are pooled. This pins that: the hour is still an
    invented figure.
    """
    content_path, _adv, _skp = _build_shaped_run(tmp_path)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    raw = json.loads(RAW_EVENTS.read_text(encoding="utf-8"))
    events = raw if isinstance(raw, dict) else {e["event_id"]: e for e in raw}
    cid = content["candidates"][0]["id"]
    ev = events[cid]
    stamp = str(ev["published_at"])
    hour = stamp[11:13]  # "20" from 2026-09-05T20:00:00Z
    assert hour.isdigit() and len(hour) == 2, stamp
    # the hour must not already be traceable from the event's own text
    assert hour not in json.dumps(ev.get("title", "")) + json.dumps(
        ev.get("snippet", "")
    )

    content["candidates"][0]["why"] += (
        f" Roughly {hour} people on the test line were let go."
    )
    content_path.write_text(json.dumps(content), encoding="utf-8")

    proc = _validate(content_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert f"states a figure not in the pull or profile: {hour}" in proc.stdout, (
        proc.stdout
    )

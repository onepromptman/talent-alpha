"""Build-integrity tests for the talent-alpha module.

Run from the module directory: `python -m pytest -q tests`.

Dependencies: pytest and stdlib only. Nothing here talks to a model; both
scripts under test (`scripts/render.py`, `scripts/state.py`) are pure
deterministic CLIs, exercised the same way the orchestrator skill shells out
to them (subprocess, not import), matching talent-one's tests/test_build.py.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = MODULE_ROOT / "skills" / "talent-alpha"
SCRIPTS = SKILL_ROOT / "scripts"
REF = SKILL_ROOT / "references"
TEMPLATE = REF / "templates" / "overnight_card.template.html"
EXAMPLE_CONTENT = REF / "content-schemas" / "card.example-content.json"


def run(cmd, cwd):
    return subprocess.run(
        [sys.executable, *cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------- (a)


def test_shipped_example_renders_strict_and_verifies_clean(tmp_path):
    """The shipped `card.example-content.json` renders with --strict (no
    missing required field) against the real template, and the rendered card
    passes `render.py verify` clean (no banned filler, no em dash, no
    leftover unfilled slot placeholder)."""
    assert TEMPLATE.is_file(), TEMPLATE
    assert EXAMPLE_CONTENT.is_file(), EXAMPLE_CONTENT

    out = tmp_path / "overnight_card.html"
    render = run(
        [
            "scripts/render.py",
            "render",
            "--template",
            str(TEMPLATE),
            "--content",
            str(EXAMPLE_CONTENT),
            "--out",
            str(out),
            "--strict",
        ],
        cwd=SKILL_ROOT,
    )
    assert render.returncode == 0, (
        f"render --strict failed:\n{render.stdout}\n{render.stderr}"
    )
    assert out.is_file(), f"render reported success but wrote nothing to {out}"

    verify = run(["scripts/render.py", "verify", "--doc", str(out)], cwd=SKILL_ROOT)
    assert verify.returncode == 0, (
        f"verify failed on a clean render:\n{verify.stdout}\n{verify.stderr}"
    )


def test_render_strict_fails_closed_on_missing_field(tmp_path):
    """A content JSON missing a field the schema requires (here, the hero
    candidate's `why`) fails --strict (exit 1) and writes nothing to --out,
    rather than shipping a silently blanked region."""
    content = json.loads(EXAMPLE_CONTENT.read_text(encoding="utf-8"))
    del content["candidates"][0]["why"]
    broken = tmp_path / "broken-content.json"
    broken.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "should-not-exist.html"
    render = run(
        [
            "scripts/render.py",
            "render",
            "--template",
            str(TEMPLATE),
            "--content",
            str(broken),
            "--out",
            str(out),
            "--strict",
        ],
        cwd=SKILL_ROOT,
    )
    assert render.returncode == 1, (
        "render --strict should fail closed on a missing required field"
    )
    assert not out.is_file(), "render --strict must write nothing to --out on failure"


# --------------------------------------------------------------------- (b)


def test_state_dedupe_then_record_round_trip(tmp_path):
    """dedupe against an empty state lets every event through; record marks
    the reconciled candidates seen; a second dedupe against the updated state
    then drops those same event ids as already-seen. Exercises the full
    read-then-write cycle `scripts/state.py`'s own docstring specifies."""
    state_path = tmp_path / "talent-alpha-state.json"
    events = [
        {"event_id": "warn-1", "company": "Northwind Robotics"},
        {"event_id": "warn-2", "company": "Halcyon Silicon"},
    ]
    events_path = tmp_path / "raw_events.json"
    events_path.write_text(json.dumps(events), encoding="utf-8")

    first_out = tmp_path / "new_events.json"
    dedupe1 = run(
        [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(events_path),
            "--state",
            str(state_path),
            "--out",
            str(first_out),
        ],
        cwd=SKILL_ROOT,
    )
    assert dedupe1.returncode == 0, dedupe1.stdout + dedupe1.stderr
    fresh = json.loads(first_out.read_text(encoding="utf-8"))
    assert [e["event_id"] for e in fresh] == ["warn-1", "warn-2"], (
        "first dedupe against an empty state should pass every event through"
    )

    candidates = {
        "candidates": [
            {"id": "warn-1", "company": "Northwind Robotics"},
            {"id": "warn-2", "company": "Halcyon Silicon"},
        ]
    }
    candidates_path = tmp_path / "content.json"
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

    record = run(
        [
            "scripts/state.py",
            "record",
            "--candidates",
            str(candidates_path),
            "--state",
            str(state_path),
        ],
        cwd=SKILL_ROOT,
    )
    assert record.returncode == 0, record.stdout + record.stderr
    assert state_path.is_file(), "record should have written the state file"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state["seen_events"]) == {"warn-1", "warn-2"}

    second_out = tmp_path / "new_events_2.json"
    dedupe2 = run(
        [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(events_path),
            "--state",
            str(state_path),
            "--out",
            str(second_out),
        ],
        cwd=SKILL_ROOT,
    )
    assert dedupe2.returncode == 0, dedupe2.stdout + dedupe2.stderr
    still_fresh = json.loads(second_out.read_text(encoding="utf-8"))
    assert still_fresh == [], (
        "a second dedupe against the just-updated state should drop every "
        "event already marked seen by record"
    )


def test_pruned_old_event_cannot_come_back_as_new(tmp_path):
    """The 2026-11-06 plugin rerun: the fixture's seen id warn-099888 (event dated
    2026-08-20) was pruned from state after 30 days, and the next dedupe admitted the
    same event as new. Dedupe now drops any event older than its source window on
    the run date, so a pruned id stays out; the 30-day prune itself is unchanged."""
    today = datetime.datetime.now(datetime.timezone.utc).date()

    def day(n):
        return (today - datetime.timedelta(days=n)).isoformat()

    state_path = tmp_path / "talent-alpha-state.json"
    old_stamp = (today - datetime.timedelta(days=40)).isoformat() + "T06:00:00Z"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "seen_events": {"warn-old": {"first_seen_at": old_stamp}},
                "last_run_at": old_stamp,
            }
        ),
        encoding="utf-8",
    )
    candidates_path = tmp_path / "content.json"
    candidates_path.write_text(
        json.dumps({"candidates": [{"id": "warn-new", "company": "Acme"}]}),
        encoding="utf-8",
    )
    record = run(
        [
            "scripts/state.py",
            "record",
            "--candidates",
            str(candidates_path),
            "--state",
            str(state_path),
        ],
        cwd=SKILL_ROOT,
    )
    assert record.returncode == 0, record.stdout + record.stderr
    assert "1 pruned" in record.stdout
    seen = json.loads(state_path.read_text(encoding="utf-8"))["seen_events"]
    assert set(seen) == {"warn-new"}, "the 30-day prune must still drop warn-old"

    events = [
        {"event_id": "warn-old", "event_type": "layoff", "published_at": day(41)},
        {"event_id": "warn-3d", "event_type": "layoff", "published_at": day(3)},
        {"event_id": "warn-4d", "event_type": "shutdown", "published_at": day(4)},
        {
            "event_id": "fund-7d",
            "event_type": "funding_distress",
            "published_at": day(7),
        },
        {
            "event_id": "fund-8d",
            "event_type": "funding_distress",
            "published_at": day(8),
        },
        {"event_id": "warn-new", "event_type": "layoff", "published_at": day(0)},
        {"event_id": "warn-nodate", "event_type": "layoff", "published_at": "soon"},
    ]
    events_path = tmp_path / "raw_events.json"
    events_path.write_text(json.dumps(events), encoding="utf-8")
    out = tmp_path / "new_events.json"
    dedupe = run(
        [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(events_path),
            "--state",
            str(state_path),
            "--out",
            str(out),
        ],
        cwd=SKILL_ROOT,
    )
    assert dedupe.returncode == 0, dedupe.stdout + dedupe.stderr
    fresh = [e["event_id"] for e in json.loads(out.read_text(encoding="utf-8"))]
    # An unparseable date is passed on: the trust-boundary join rejects it by name.
    assert fresh == ["warn-3d", "fund-7d", "warn-nodate"]
    assert "1 already seen, 3 outside the source window" in dedupe.stdout
    for dropped in ("warn-old (41d old", "warn-4d (4d old", "fund-8d (8d old"):
        assert f"outside window: {dropped}" in dedupe.stdout


def test_frozen_fixture_needs_its_run_date(tmp_path):
    """The eval fixture is dated 2026-09-05..07. Run as of 2026-09-07 every unseen
    event is in its window; run as of today none is, and dedupe says so."""
    fixtures = MODULE_ROOT / "evals" / "fixtures"
    results = {}
    for as_of in ("2026-09-07", None):
        out = tmp_path / f"new-{as_of}.json"
        cmd = [
            "scripts/state.py",
            "dedupe",
            "--events",
            str(fixtures / "raw_events.json"),
            "--state",
            str(fixtures / "talent-alpha-state.json"),
            "--out",
            str(out),
        ]
        proc = run(cmd + (["--as-of", as_of] if as_of else []), cwd=SKILL_ROOT)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        results[as_of] = (len(json.loads(out.read_text(encoding="utf-8"))), proc.stdout)
    assert results["2026-09-07"][0] == 5
    assert "1 already seen, 0 outside" in results["2026-09-07"][1]
    assert results[None][0] == 0
    assert "1 already seen, 5 outside" in results[None][1]
    bad = run(
        ["scripts/state.py", "dedupe", "--as-of", "07/09/2026", "--events", "x"]
        + ["--state", "y", "--out", str(tmp_path / "z.json")],
        cwd=SKILL_ROOT,
    )
    assert bad.returncode == 2 and "YYYY-MM-DD" in bad.stderr


def test_state_record_is_atomic_write(tmp_path):
    """`write_state_atomic` writes via a temp file plus rename, per its own
    docstring, so the state file is never left half-written. Sanity check:
    after record, no stray `.talent-alpha-state-*` temp file survives beside
    it (the docstring's own claim, verified rather than trusted)."""
    state_path = tmp_path / "talent-alpha-state.json"
    candidates_path = tmp_path / "content.json"
    candidates_path.write_text(
        json.dumps({"candidates": [{"id": "warn-9", "company": "Acme"}]}),
        encoding="utf-8",
    )
    record = run(
        [
            "scripts/state.py",
            "record",
            "--candidates",
            str(candidates_path),
            "--state",
            str(state_path),
        ],
        cwd=SKILL_ROOT,
    )
    assert record.returncode == 0, record.stdout + record.stderr
    leftovers = [
        p.name for p in tmp_path.iterdir() if p.name.startswith(".talent-alpha-state-")
    ]
    assert not leftovers, f"atomic write left a stray temp file: {leftovers}"


# --------------------------------------------------------------------- (d)


def test_example_content_reproduces_shipped_sample_byte_for_byte(tmp_path):
    """The renderer is deterministic and the shipped sample is its golden set:
    rendering `card.example-content.json` must reproduce
    `samples/01_Overnight_Card_SAMPLE.html` exactly (line endings folded; the
    checkout may be CRLF on Windows). Any renderer or template change that
    alters output fails here and must ship with a regenerated sample.

    This mirrors talent-one's
    `test_example_content_reproduces_shipped_sample_byte_for_byte`, and it is
    the check that was missing: the template and the sample landed in the same
    initial commit and neither changed after, yet the sample never carried the
    source-provenance block (`.srcline` CSS, the `hero-source` slot, the
    per-card `Source:` line) that the template emits and the content schema
    requires (`source_name`/`source_url`). Nothing could catch that, because
    nothing compared the two.
    """
    sample = MODULE_ROOT / "samples" / "01_Overnight_Card_SAMPLE.html"
    assert sample.is_file(), sample

    out = tmp_path / "overnight_card.html"
    render = run(
        [
            str(SCRIPTS / "render.py"),
            "render",
            "--template",
            str(TEMPLATE),
            "--content",
            str(EXAMPLE_CONTENT),
            "--out",
            str(out),
            "--strict",
        ],
        cwd=MODULE_ROOT,
    )
    assert render.returncode == 0, render.stdout + render.stderr

    got = out.read_bytes().replace(b"\r\n", b"\n")
    want = sample.read_bytes().replace(b"\r\n", b"\n")
    assert got == want, (
        "the shipped sample no longer reproduces from card.example-content.json. "
        "If the renderer or template changed on purpose, regenerate it:\n"
        "  python skills/talent-alpha/scripts/render.py render "
        "--template skills/talent-alpha/references/templates/overnight_card.template.html "
        "--content skills/talent-alpha/references/content-schemas/card.example-content.json "
        "--out samples/01_Overnight_Card_SAMPLE.html --strict"
    )


def test_shipped_sample_carries_source_provenance():
    """Every card the module ships names where its claim came from. The content
    schema requires `source_name`/`source_url` per candidate, so a sample
    without a rendered `Source:` line is stale, not minimal -- which is exactly
    the state the sample shipped in until 2026-09-08."""
    sample = (MODULE_ROOT / "samples" / "01_Overnight_Card_SAMPLE.html").read_text(
        encoding="utf-8"
    )
    assert 'class="srcline"' in sample
    assert "Source:" in sample


def test_card_is_self_contained_and_fluid():
    """The card opens offline and makes no network request (the template used to
    load Google Fonts), and its sheet shrinks below 1280px instead of clipping the
    left edge (2026-11-06 plugin rerun). Source links are plain anchors, which are
    fetched only when clicked."""
    sample = MODULE_ROOT / "samples" / "01_Overnight_Card_SAMPLE.html"
    for doc in (TEMPLATE, sample):
        text = doc.read_text(encoding="utf-8")
        for loader in (
            r"<link\b",
            r"<script[^>]*\bsrc=",
            r"<img\b",
            r"<iframe\b",
            r"@import",
            r"url\(",
        ):
            assert not re.search(loader, text, re.IGNORECASE), (doc.name, loader)
        assert not re.search(r"[{;]width:1280px", text), "fixed-width sheet"
        assert "max-width:1280px" in text
        assert "@media (max-width:820px)" in text

"""Exercise the production plugin path, including failures before state is written."""

import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills/talent-alpha/scripts"
EXAMPLE = (
    ROOT / "skills/talent-alpha/references/content-schemas/card.example-content.json"
)


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def cli(script, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *map(str, args)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


@pytest.fixture
def batch(tmp_path):
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    event = {
        "event_id": "fund-test",
        "company": "",
        "location": "",
        "title": "Acme Sensors announces restructuring in Denver",
        "snippet": "Acme Sensors is cutting test roles after a funding round fell through.",
        "event_type": "funding_distress",
        "published_at": today,
        "employees_affected": None,
        "source_name": "Web Search",
        "source_url": "https://example.com/acme-restructuring",
    }
    shortlist = {
        "opportunities": [
            {
                "id": "fund-test",
                "company": "Acme Sensors",
                "location": "Denver",
                "score": 80,
                "functions": ["Test Engineer"],
                "why": "Reported restructuring affects test roles.",
            }
        ]
    }
    verdict = {
        "id": "fund-test",
        "tier": "A",
        "openness": "H",
        "role_fit": "H",
        "product_fit": "M",
        "region_fit": "H",
        "size_fit": "M",
        "stage_fit": "M",
        "wildcard": {"fired": False, "axis_index": -1, "bridge": ""},
        "titles": ["Test Engineer"],
        "why": "Acme Sensors reports restructuring affecting test roles.",
        "hook": "Saw the Acme Sensors restructuring news and wanted to connect.",
        "edge": "",
    }
    write(tmp_path / "raw.json", [event])
    write(tmp_path / "shortlist.json", shortlist)
    write(tmp_path / "advocate_verdicts.json", {"verdicts": [verdict]})
    write(tmp_path / "skeptic_verdicts.json", {"verdicts": [dict(verdict, tier="B")]})
    (tmp_path / "profile.md").write_text(
        "## Organization\nname: Example Co\n\n## Kit: talent-alpha\nleverage: \n",
        encoding="utf-8",
    )
    return tmp_path


def join(batch):
    return cli(
        "render.py",
        "join",
        "--raw",
        batch / "raw.json",
        "--shortlist",
        batch / "shortlist.json",
        "--out",
        batch / "trusted.json",
    )


def build(batch, *extra):
    return cli(
        "render.py",
        "build",
        "--raw",
        batch / "raw.json",
        "--trusted",
        batch / "trusted.json",
        "--advocate",
        batch / "advocate_verdicts.json",
        "--skeptic",
        batch / "skeptic_verdicts.json",
        "--profile",
        batch / "profile.md",
        "--state",
        batch / "state.json",
        "--author",
        "Recruiter",
        "--company-name",
        "Example Co",
        "--role-title",
        "Test Engineer",
        "--role-location",
        "Denver",
        "--out",
        batch / "content.json",
        "--html",
        batch / "card.html",
        *extra,
    )


def test_funding_extraction_and_date_only_survive_full_build_and_dedupe(batch):
    result = join(batch)
    assert result.returncode == 0, result.stderr
    trusted = json.loads((batch / "trusted.json").read_text())
    assert trusted[0]["company"] == "Acme Sensors"
    assert trusted[0]["location"] == "Denver"
    assert "test roles" in trusted[0]["snippet"]
    result = build(batch)
    assert result.returncode == 0, result.stdout + result.stderr
    content = json.loads((batch / "content.json").read_text())
    assert content["candidates"][0]["age_days"] >= 0
    assert "https://example.com/acme-restructuring" in (batch / "card.html").read_text()
    assert "fund-test" in json.loads((batch / "state.json").read_text())["seen_events"]
    result = cli(
        "state.py",
        "dedupe",
        "--events",
        batch / "raw.json",
        "--state",
        batch / "state.json",
        "--out",
        batch / "new.json",
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((batch / "new.json").read_text()) == []


@pytest.mark.parametrize("company", ["Invented Corporation", "Acme"])
def test_funding_company_must_occur_in_evidence(batch, company):
    data = json.loads((batch / "shortlist.json").read_text())
    data["opportunities"][0]["company"] = company
    # Acme alone is a supported literal extraction, unlike the invented company.
    write(batch / "shortlist.json", data)
    result = join(batch)
    assert result.returncode == (0 if company == "Acme" else 1)


@pytest.mark.parametrize(
    "judge,mutation",
    [
        ("skeptic", "missing"),
        ("advocate", "missing"),
        ("skeptic", "duplicate"),
        ("skeptic", "unknown"),
        ("skeptic", "tier"),
        ("advocate", "axis"),
    ],
)
def test_incomplete_or_invalid_judging_cannot_publish_or_record(batch, judge, mutation):
    assert join(batch).returncode == 0
    path = batch / f"{judge}_verdicts.json"
    data = json.loads(path.read_text())
    if mutation == "missing":
        data["verdicts"] = []
    elif mutation == "duplicate":
        data["verdicts"] *= 2
    elif mutation == "unknown":
        data["verdicts"][0]["id"] = "invented-id"
    else:
        data["verdicts"][0]["tier" if mutation == "tier" else "role_fit"] = "invalid"
    write(path, data)
    result = build(batch)
    assert result.returncode != 0
    assert not (batch / "state.json").exists()
    assert not (batch / "content.json").exists()
    assert not (batch / "card.html").exists()


@pytest.mark.parametrize(
    "failure", ["fabricated-number", "verify", "template", "schema"]
)
def test_failed_build_preserves_existing_card_and_state(batch, failure):
    assert join(batch).returncode == 0
    state = {"schema_version": 1, "seen_events": {}, "last_run_at": None}
    write(batch / "state.json", state)
    before = (batch / "state.json").read_bytes()
    (batch / "card.html").write_text("previous good card", encoding="utf-8")
    extra = ()
    if failure == "template":
        extra = ("--template", batch / "missing.html")
    else:
        path = batch / "advocate_verdicts.json"
        data = json.loads(path.read_text())
        if failure == "schema":
            data["verdicts"][0]["wildcard"]["axis_index"] = "invalid"
        else:
            data["verdicts"][0]["why"] += (
                " 98765 people." if failure == "fabricated-number" else " TBD"
            )
        write(path, data)
    result = build(batch, *extra)
    assert result.returncode != 0
    assert (batch / "state.json").read_bytes() == before
    assert (batch / "card.html").read_text() == "previous good card"
    assert not (batch / "content.json").exists()
    assert not list(batch.glob(".talent-alpha-build-*"))


def test_sharp_disagreement_is_held_even_in_first_slot(batch):
    assert join(batch).returncode == 0
    for judge, tier in (("advocate", "S"), ("skeptic", "C")):
        path = batch / f"{judge}_verdicts.json"
        data = json.loads(path.read_text())
        data["verdicts"][0]["tier"] = tier
        write(path, data)
    result = build(batch)
    assert result.returncode == 0, result.stdout + result.stderr
    candidate = json.loads((batch / "content.json").read_text())["candidates"][0]
    assert candidate["tier"] == "HELD" and candidate["held"]
    assert candidate["hold_reason"] == "judges disagreed sharply"
    assert 'data-slot="hero-company"' not in (batch / "card.html").read_text()


@pytest.mark.parametrize(
    "field,value",
    [
        ("tier", "invented"),
        ("bands", ["H"]),
        ("held", "false"),
        ("employees_affected", True),
        ("titles", "Engineer"),
        ("extra", "unexpected"),
    ],
)
def test_strict_render_enforces_shipped_schema(tmp_path, field, value):
    content = json.loads(EXAMPLE.read_text())
    content["candidates"][0][field] = value
    write(tmp_path / "content.json", content)
    result = cli(
        "render.py",
        "render",
        "--content",
        tmp_path / "content.json",
        "--template",
        ROOT / "skills/talent-alpha/references/templates/overnight_card.template.html",
        "--out",
        tmp_path / "card.html",
        "--strict",
    )
    assert result.returncode != 0
    assert not (tmp_path / "card.html").exists()


def test_in_batch_duplicates_do_not_cost_multiple_scoring_slots(batch):
    events = json.loads((batch / "raw.json").read_text())
    write(batch / "raw.json", events * 2)
    result = cli(
        "state.py",
        "dedupe",
        "--events",
        batch / "raw.json",
        "--state",
        batch / "state.json",
        "--out",
        batch / "new.json",
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads((batch / "new.json").read_text())) == 1


@pytest.mark.parametrize(
    "stamp", ["2026-01-01", "2026-01-01T12:00:00", "2026-01-01T12:00:00-07:00"]
)
def test_supported_timestamp_shapes_build(batch, stamp):
    events = json.loads((batch / "raw.json").read_text())
    events[0]["published_at"] = stamp
    write(batch / "raw.json", events)
    assert join(batch).returncode == 0
    result = build(batch)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "key,value",
    [
        ("published_at", "not-a-date"),
        ("published_at", "2099-01-01"),
        ("source_url", "javascript:alert(1)"),
        ("employees_affected", -1),
    ],
)
def test_unusable_events_do_not_reach_judges(batch, key, value):
    events = json.loads((batch / "raw.json").read_text())
    events[0][key] = value
    write(batch / "raw.json", events)
    result = join(batch)
    assert result.returncode != 0
    assert json.loads((batch / "trusted.json").read_text()) == []


def test_other_kits_profile_cannot_supply_leverage(batch):
    assert join(batch).returncode == 0
    (batch / "profile.md").write_text(
        "## Kit: other-kit\nleverage: Guaranteed $98765 bonus.\n\n"
        "## Kit: talent-alpha\nleverage: No bonus commitment.\n",
        encoding="utf-8",
    )
    path = batch / "advocate_verdicts.json"
    data = json.loads(path.read_text())
    data["verdicts"][0]["edge"] = "Guaranteed $98765 bonus."
    write(path, data)
    result = build(batch)
    assert result.returncode != 0
    assert "figure not in the pull or profile" in result.stderr
    assert not (batch / "state.json").exists()


def test_empty_leverage_requires_an_empty_edge(batch):
    assert join(batch).returncode == 0
    path = batch / "advocate_verdicts.json"
    data = json.loads(path.read_text())
    data["verdicts"][0]["edge"] = "An excellent culture and a guaranteed promotion."
    write(path, data)
    result = build(batch)
    assert result.returncode != 0
    assert "no saved leverage" in result.stderr
    assert not (batch / "state.json").exists()


@pytest.mark.parametrize("missing", [None, "targetSectors", "openRole"])
def test_setup_config_requires_sectors_and_role(tmp_path, missing):
    config = {
        "targetSectors": "industrial sensors, robotics",
        "companyProfile": "",
        "openRole": {
            "id": "ROLE-01",
            "title": "Test Engineer",
            "functions": ["Test Engineer"],
            "location": "",
        },
    }
    if missing:
        del config[missing]
    path = write(tmp_path / "config.json", config)
    result = cli("render.py", "check-config", "--config", path)
    assert result.returncode == (1 if missing else 0), result.stderr


def test_build_rejects_already_recorded_events(batch):
    assert join(batch).returncode == 0
    assert build(batch).returncode == 0
    before = (batch / "state.json").read_bytes()
    result = build(batch)
    assert result.returncode != 0
    assert "already in seen_events" in result.stderr
    assert (batch / "state.json").read_bytes() == before


@pytest.mark.parametrize("changed_file", ["raw.json", "trusted.json"])
def test_build_rechecks_source_dates_after_join(batch, changed_file):
    assert join(batch).returncode == 0
    path = batch / changed_file
    data = json.loads(path.read_text())
    data[0]["published_at"] = "2099-01-01"
    write(path, data)
    result = build(batch)
    assert result.returncode != 0
    assert not (batch / "state.json").exists()

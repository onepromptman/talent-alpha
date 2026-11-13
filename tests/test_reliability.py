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
    assert not (batch / "sourcing-handoff.json").exists()
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


def test_sourcing_handoff_uses_checked_company_signal(batch):
    assert join(batch).returncode == 0
    result = build(batch, "--sourcing-handoff")
    assert result.returncode == 0, result.stdout + result.stderr
    handoff = json.loads((batch / "sourcing-handoff.json").read_text(encoding="utf-8"))
    published = json.loads((batch / "raw.json").read_text())[0]["published_at"]
    expires = datetime.date.fromisoformat(published) + datetime.timedelta(days=7)
    name = "Test Engineer, Example Co (Talent Alpha: Acme Sensors)"
    evidence = (
        f"Acme Sensors: funding distress in Denver, reported {published},"
        f" use through {expires.isoformat()}."
        " Source: https://example.com/acme-restructuring"
    )
    assert handoff == {
        "schema_version": 3,
        "role": {"title": "Test Engineer", "location": "Denver"},
        "signals": [
            {
                "event_id": "fund-test",
                "company": "Acme Sensors",
                "event_type": "funding_distress",
                "event_location": "Denver",
                "reported_titles": ["Test Engineer"],
                "tier": "A",
                "published_on": published,
                "use_through": expires.isoformat(),
                "source_url": "https://example.com/acme-restructuring",
            }
        ],
        "targets": {
            "name": name,
            "titles": ["Test Engineer"],
            "locations": ["Denver"],
            "companies": ["Acme Sensors"],
            "exclude_companies": ["Example Co"],
            "use_through": expires.isoformat(),
            "evidence": [evidence],
        },
        "noon": {
            "name": name,
            "titles": ["Test Engineer"],
            "location": ["Denver"],
            "target_companies": ["Acme Sensors"],
            "exclude_after_create": ["Example Co"],
            "jd_evidence": [evidence],
        },
        "juicebox": {
            "name": name,
            "query": "Test Engineer currently at Acme Sensors, near Denver",
            "filters": {
                "job_titles": ["Test Engineer"],
                "current_companies": ["Acme Sensors"],
                "locations": ["Denver"],
                "exclude_companies": ["Example Co"],
            },
            "evidence": [evidence],
        },
    }


@pytest.mark.parametrize("tiers", [("B", "B"), ("S", "C")])
def test_sourcing_handoff_omits_lower_tier_and_held_events(batch, tiers):
    assert join(batch).returncode == 0
    for judge, tier in zip(("advocate", "skeptic"), tiers):
        path = batch / f"{judge}_verdicts.json"
        data = json.loads(path.read_text())
        data["verdicts"][0]["tier"] = tier
        write(path, data)
    result = build(batch, "--sourcing-handoff")
    assert result.returncode == 0, result.stdout + result.stderr
    handoff = json.loads((batch / "sourcing-handoff.json").read_text(encoding="utf-8"))
    assert handoff["signals"] == []
    assert handoff["targets"] is None
    assert handoff["noon"] is None
    assert handoff["juicebox"] is None


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
    handoff = batch / "sourcing-handoff.json"
    handoff.write_text("previous targeting proposal", encoding="utf-8")
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
    result = build(batch, "--sourcing-handoff", *extra)
    assert result.returncode != 0
    assert (batch / "state.json").read_bytes() == before
    assert (batch / "card.html").read_text() == "previous good card"
    assert handoff.read_text(encoding="utf-8") == "previous targeting proposal"
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
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ({"title": ""}, "openRole.title cannot be empty"),
        ({"sectors": ""}, "targetSectors cannot be empty"),
        ({"title": "", "sectors": ""}, "targetSectors cannot be empty"),
        ({"functions": [], "title": "", "sectors": ""}, "violates minItems"),
        ({"functions": [" "]}, "openRole.functions cannot contain empty strings"),
        ({"raw": "{not json"}, "cannot read"),
    ],
)
def test_check_config_rejects_blank_exports_in_one_line(tmp_path, mutation, expected):
    # The setup probes from the 2026-11-06 plugin rerun: each used to end in a raw
    # Python traceback; the user needs only the one actionable sentence.
    config = {
        "targetSectors": mutation.get("sectors", "industrial automation"),
        "companyProfile": "Solstice Yards pays below-market cash.",
        "openRole": {
            "id": "ROLE-01",
            "title": mutation.get("title", "Senior Reliability Engineer"),
            "functions": mutation.get("functions", ["Reliability Engineering"]),
            "location": "Denver, CO",
        },
    }
    path = tmp_path / "config.json"
    path.write_text(mutation.get("raw") or json.dumps(config), encoding="utf-8")
    result = cli("render.py", "check-config", "--config", path)
    assert result.returncode == 1
    assert result.stdout == ""
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1, result.stderr
    assert lines[0].startswith("check-config: invalid n8n Config: ")
    assert expected in lines[0]


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


@pytest.mark.parametrize("damage", ["empty", "cards", "duplicate-slot", "nested-slot"])
def test_invalid_template_cannot_publish_or_retire_events(batch, damage):
    assert join(batch).returncode == 0
    template = (
        ROOT / "skills/talent-alpha/references/templates/overnight_card.template.html"
    ).read_text(encoding="utf-8")
    if damage == "empty":
        template = "<html><body>Empty template</body></html>"
    elif damage == "cards":
        template = template.replace("<!-- CARD:START -->\n<!-- CARD:END -->", "")
    elif damage == "nested-slot":
        template = template.replace('<div data-slot="hero-source"></div>', "")
        template = template.replace(
            '<div class="ptext dim" data-slot="hero-edge">-</div>',
            '<div class="ptext dim" data-slot="hero-edge"><div data-slot="hero-source"></div></div>',
        )
    else:
        template += '<span data-slot="hero-company">Hidden duplicate</span>'
    path = batch / "template.html"
    path.write_text(template, encoding="utf-8")
    (batch / "card.html").write_text("previous good card", encoding="utf-8")
    result = build(batch, "--template", path)
    assert result.returncode != 0
    assert "template" in result.stderr.lower()
    assert (batch / "card.html").read_text() == "previous good card"
    assert not (batch / "content.json").exists()
    assert not (batch / "state.json").exists()


def test_build_cannot_replace_its_template(batch):
    assert join(batch).returncode == 0
    path = batch / "template.html"
    original = (
        ROOT / "skills/talent-alpha/references/templates/overnight_card.template.html"
    ).read_bytes()
    path.write_bytes(original)
    result = build(batch, "--template", path, "--html", path)
    assert result.returncode != 0
    assert path.read_bytes() == original
    assert not (batch / "state.json").exists()


# ---------------------------------------------------- 2026-11-07 first-install fixes


def set_verdict(batch, judge, **fields):
    path = batch / f"{judge}_verdicts.json"
    data = json.loads(path.read_text())
    data["verdicts"][0].update(fields)
    write(path, data)


def test_card_text_naming_a_fit_axis_fails_build_and_verify(batch):
    # The 2026-11-06 plugin rerun printed "stage_fit H is inferred from ..." in why-now.
    assert join(batch).returncode == 0
    set_verdict(
        batch,
        "advocate",
        why="Acme Sensors reports restructuring (stage_fit H is inferred from it).",
    )
    result = build(batch)
    assert result.returncode != 0
    assert "names the fit axis stage_fit" in result.stderr
    assert "do not substitute an inference" in result.stderr
    assert not (batch / "state.json").exists()
    assert not (batch / "card.html").exists()

    # verify is the backstop for a card rendered without the build's checks
    content = json.loads(EXAMPLE.read_text())
    content["candidates"][0]["why"] = "Closest match; stage_fit H is inferred from pay."
    write(batch / "axis.json", content)
    template = ROOT / "skills/talent-alpha/references/templates"
    rendered = cli(
        "render.py",
        "render",
        "--template",
        template / "overnight_card.template.html",
        "--content",
        batch / "axis.json",
        "--out",
        batch / "axis.html",
        "--strict",
    )
    assert rendered.returncode == 0, rendered.stderr
    verify = cli("render.py", "verify", "--doc", batch / "axis.html")
    assert verify.returncode == 1
    assert "fit-axis name in card text: ['stage_fit']" in verify.stderr


@pytest.mark.parametrize("stated", [False, True])
def test_size_and_stage_fit_need_a_stated_company_fact(batch, stated):
    assert join(batch).returncode == 0
    set_verdict(batch, "advocate", stage_fit="H")
    if stated:
        (batch / "profile.md").write_text(
            "## Kit: talent-alpha\nleverage: \n"
            "company_stage: Series B, venture-backed (stated by user)\n",
            encoding="utf-8",
        )
    result = build(batch)
    if stated:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
        assert "stage_fit='H' but the profile states no company_stage" in result.stderr
        assert "score M, the stated neutral value" in result.stderr
        assert not (batch / "state.json").exists()


def test_ages_window_note_and_legend_follow_the_run_date(batch):
    events = json.loads((batch / "raw.json").read_text())
    events[0]["published_at"] = "2026-09-05T20:00:00Z"
    write(batch / "raw.json", events)
    assert join(batch).returncode == 0
    result = build(batch, "--as-of", "2026-09-07")
    assert result.returncode == 0, result.stdout + result.stderr
    content = json.loads((batch / "content.json").read_text())
    candidate = content["candidates"][0]
    assert (candidate["age_days"], candidate["event_age_label"]) == (2, "2d ago")
    note = "WARN: 3d; funding news: 7d; ages as of 2026-09-07"
    assert content["run"]["window_note"] == note
    html = (batch / "card.html").read_text(encoding="utf-8")
    assert note in html and "2d ago" in html
    for promise in ("Act today", "this morning", "hours wide"):
        assert promise not in html

    # The same event run as of a later date reads old, and says it is past its window.
    reconcile = cli(
        "render.py",
        "reconcile",
        "--trusted",
        batch / "trusted.json",
        "--advocate",
        batch / "advocate_verdicts.json",
        "--skeptic",
        batch / "skeptic_verdicts.json",
        "--author",
        "Recruiter",
        "--company-name",
        "Example Co",
        "--role-title",
        "Test Engineer",
        "--role-location",
        "Denver",
        "--as-of",
        "2026-11-07",
        "--out",
        batch / "late.json",
    )
    assert reconcile.returncode == 0, reconcile.stderr
    late = json.loads((batch / "late.json").read_text())["candidates"][0]
    assert late["event_age_label"] == "63d ago, outside the 7d window"


def test_an_event_dated_after_the_run_date_is_rejected(batch):
    events = json.loads((batch / "raw.json").read_text())
    events[0]["published_at"] = "2026-09-10"
    write(batch / "raw.json", events)
    result = cli(
        "render.py",
        "join",
        "--raw",
        batch / "raw.json",
        "--shortlist",
        batch / "shortlist.json",
        "--as-of",
        "2026-09-07",
        "--out",
        batch / "trusted.json",
    )
    assert result.returncode != 0
    assert "in the future of the run date" in result.stdout


@pytest.mark.parametrize(
    "advocate,skeptic,held",
    [("S", "C", True), ("S", "B", False), ("A", "C", False)],
)
def test_only_a_three_rank_split_is_held(batch, advocate, skeptic, held):
    """Holds compare the verdicts that passed the critic (SKILL.md 2.55). The
    2026-11-06 rerun's lap-0 Verity split was S vs B, two ranks, which is never held;
    a critic repair from S to A against a C also lands below the line, by design."""
    assert join(batch).returncode == 0
    set_verdict(batch, "advocate", tier=advocate)
    set_verdict(batch, "skeptic", tier=skeptic)
    result = build(batch)
    assert result.returncode == 0, result.stdout + result.stderr
    candidate = json.loads((batch / "content.json").read_text())["candidates"][0]
    assert candidate["held"] is held


def test_critic_policy_and_repair_instruction_are_pinned():
    def flat(rel):
        return " ".join((ROOT / rel).read_text(encoding="utf-8").split())

    critic = flat("agents/critic.md")
    skill = flat("skills/talent-alpha/SKILL.md")
    assert "when any MED finding names a `why`, `hook` or `edge` slot" in critic
    assert "LOW findings are advisory" in critic
    assert "any MED finding on a `why`, `hook` or `edge` slot" in skill
    assert "removing the ungrounded claim; do not substitute an inference" in skill
    assert "<run folder>/laps/<judge>_verdicts.lap<N>.json" in skill
    assert "compares the verdicts that passed the critic" in skill


def test_setup_tool_check_and_eval_prompt_placeholders_are_pinned():
    # Setup names a missing WebSearch tool instead of guessing, walks
    # the n8n route step by step instead of handing over a file, and the eval prompt says
    # what a hand run substitutes for the harness placeholders.
    def flat(rel):
        return " ".join((ROOT / rel).read_text(encoding="utf-8").split())

    setup = flat("skills/talent-alpha-setup/SKILL.md")
    assert "Check for this session's WebSearch tool" in setup
    assert "Never substitute WebFetch, a connector, made-up news" in setup
    assert "step by step, waiting after each action" in setup
    assert (
        "never create a credential, import, activate or schedule anything in n8n"
        in setup
    )

    prompt = flat("evals/card-accuracy/prompt.md")
    assert "replace every `{{plugin_dir}}` with the loaded plugin's root" in prompt
    assert "ignore the `model:` line" in prompt
    assert "{{plugin_dir}}/skills/talent-alpha/scripts/render.py build" in prompt


def test_scanner_functions_are_labelled_inferred_through_to_the_card(batch):
    # First-install review: the scanner's guessed functions sat beside source facts
    # under a neutral key, and each run spent a repair lap rediscovering that.
    assert join(batch).returncode == 0
    trusted = json.loads((batch / "trusted.json").read_text())[0]
    assert trusted["inferred_functions"] == ["Test Engineer"]
    assert "functions" not in trusted
    result = build(batch)
    assert result.returncode == 0, result.stdout + result.stderr
    card = (batch / "card.html").read_text(encoding="utf-8")
    assert "Job titles are inferred from the signal, not named by the source." in card
    for brief in ("agents/advocate.md", "agents/skeptic.md", "agents/critic.md"):
        assert "`inferred_functions`" in (ROOT / brief).read_text(encoding="utf-8")


def test_legend_says_only_the_tier_is_blended(batch):
    # First-install review: bands, why, hook and edge are the advocate's alone.
    assert join(batch).returncode == 0
    verdicts = json.loads((batch / "skeptic_verdicts.json").read_text())
    verdicts["verdicts"][0].update(openness="L", why="A different skeptic read.")
    write(batch / "skeptic_verdicts.json", verdicts)
    result = build(batch)
    assert result.returncode == 0, result.stdout + result.stderr
    candidate = json.loads((batch / "content.json").read_text())["candidates"][0]
    assert candidate["bands"][0] == "H" and "skeptic" not in candidate["why"]
    card = (batch / "card.html").read_text(encoding="utf-8")
    assert "the average of both judges' tier calls" in card
    assert "The hexagon and the text are the advocate's read" in card
    assert "six-axis reads" not in card


def test_min_shown_is_accepted_but_no_longer_asked_or_documented(batch):
    # The flag never changed a card. Setup stopped asking for it; old callers still work.
    assert join(batch).returncode == 0
    result = build(batch, "--min-shown", "9")
    assert result.returncode == 0, result.stdout + result.stderr
    content = json.loads((batch / "content.json").read_text())
    assert [c["held"] for c in content["candidates"]] == [False]
    for rel in (
        "skills/talent-alpha-setup/SKILL.md",
        "skills/talent-alpha/SKILL.md",
        "PROFILE-SPEC.md",
        "evals/fixtures/onepromptman-profile.md",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "min_shown" not in text and "min-shown" not in text, rel


def test_public_repo_names_no_private_repository():
    # CI fetched a private repository, and the module file, README
    # and CONTRIBUTING pointed at others. A public checkout must stand on its own.
    assert not (ROOT / "KIT-CORE.md").exists()
    module = (ROOT / "MODULE.yaml").read_text(encoding="utf-8")
    assert "supersedes:" not in module and "\ncore:" not in module
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "git " not in ci and "fetch" not in ci
    for rel in ("README.md", "CONTRIBUTING.md", "MODULE.yaml"):
        text = (ROOT / rel).read_text(encoding="utf-8").lower()
        assert "talentai" not in text and "private" not in text, rel

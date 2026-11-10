"""Regressions from the review of the 1.5.0 release candidate."""

import copy
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import test_n8n_reliability as harness
from test_n8n_reliability import NODES, ROOT, _dated, execute
from test_targets import run, target

lookup = harness.lookup
pytestmark = harness.pytestmark


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "skills/talent-alpha/scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "n8n/tools"))
    return importlib.import_module("targets"), importlib.import_module(
        "build_workflows"
    )


@pytest.mark.parametrize("facts", [None, {}, {"size": "", "stage": " "}])
def test_missing_facts_neutralize_both_judges_without_stopping(lookup, facts):
    if facts is not None:
        lookup["Config"][0]["companyFacts"] = facts
    lookup["Config"][0]["companyProfile"] += " About 120 employees. Series B."
    for name in ("Judge Advocate", "Judge Skeptic"):
        for verdict in lookup[name][0]["output"]["verdicts"]:
            verdict.update(size_fit="H", stage_fit="L")
    code, result = execute("Reconcile Judges", [], lookup)
    assert code == 0, result
    assert all(row["json"]["bands"][4:] == ["M", "M"] for row in result["result"])
    assert all(
        v["size_fit"] == "H" for v in lookup["Judge Advocate"][0]["output"]["verdicts"]
    )


def test_judge_prompts_use_structured_facts_only():
    for name in ("Judge Advocate", "Judge Skeptic"):
        prompt = NODES[name]["parameters"]["messages"]["messageValues"][0]["message"]
        assert "COMPANY_FACTS" in prompt
        assert "COMPANY_PROFILE states the company" not in prompt


@pytest.mark.parametrize("stamp", [None, "", "not-a-date", "2099-01-01"])
def test_bad_feed_date_is_dropped_but_good_event_reaches_scanner(lookup, stamp):
    good = _dated("good", "layoff", 1)
    bad = dict(good, event_id="bad", published_at=stamp)
    code, result = execute("Batch For Scanner Agent", [bad, good], lookup)
    assert code == 0, result
    assert list(result["result"][0]["json"]["itemsById"]) == ["good"]
    code, result = execute("Batch For Scanner Agent", [bad], lookup)
    assert code == 0 and result["result"] == []


@pytest.mark.parametrize("source", ["WARN", "Funding-Distress"])
def test_missing_source_date_reaches_common_filter(lookup, source):
    if source == "WARN":
        payload = {
            "records": [
                {
                    "id": "no-date",
                    "company_name": "Example Co",
                    "source_url": "https://example.com/notice",
                }
            ]
        }
    else:
        payload = {
            "results": [
                {
                    "title": "Example Co cuts staff",
                    "url": "https://example.com/story",
                    "snippet": "Example Co reported job cuts across its industrial test engineering team.",
                }
            ]
        }
    code, result = execute("Normalize " + source + " Items", [payload])
    assert code == 0, result
    rows = [i["json"] for i in result["result"]]
    assert rows[0]["published_at"] is None
    code, result = execute("Batch For Scanner Agent", rows, lookup)
    assert code == 0 and result["result"] == []


@pytest.mark.parametrize(
    "types,enabled,valid",
    [
        (["funding_distress", "funding_distress"], False, False),
        (["funding_distress"], False, False),
        (["funding_distress", "funding_distress"], True, True),
        (["layoff", "funding_distress"], False, True),
        (["shutdown"], False, True),
        ([], True, False),
        (["unknown"], True, False),
    ],
)
def test_python_js_event_type_validation_agrees(lookup, modules, types, enabled, valid):
    config = lookup["Config"][0]
    config.update(
        includeFundingDistress=enabled, sourcingCriteria={"eventTypes": types}
    )
    python_valid = not modules[0].config_problems(config)
    code, _ = execute("Validate Config", [config])
    assert python_valid == (code == 0) == valid


def evaluate(expression, config):
    script = "const c=JSON.parse(process.argv[1]); const $=()=>({first:()=>({json:c})}); const $json=c; const $today={toFormat:()=> '2026-11-09'}; const source=process.argv[2]; process.stdout.write(source.replace(/\\{\\{([\\s\\S]*?)\\}\\}/g,(_,s)=>String(eval(s))));"
    result = subprocess.run(
        ["node", "-e", script, json.dumps(config), expression],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_funding_only_bypasses_warn_and_feeds_merge(lookup):
    config = lookup["Config"][0]
    config["sourcingCriteria"] = {"eventTypes": ["funding_distress"]}
    gate = NODES.get("WARN Enabled")
    assert gate is not None, "funding-only must not fetch WARN"
    expression = gate["parameters"]["conditions"]["conditions"][0]["leftValue"]
    assert evaluate(expression, config) == "=false"
    for types in (["shutdown"], ["layoff"], ["layoff", "funding_distress"]):
        config["sourcingCriteria"]["eventTypes"] = types
        assert evaluate(expression, config) == "=true"
    workflow = json.loads(harness.WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["connections"]["WARN Disabled"]["main"][0][0] == {
        "node": "Merge Category Feeds",
        "type": "main",
        "index": 0,
    }


def test_join_reads_config_once_per_batch(lookup, monkeypatch):
    rows = [_dated("first", "layoff", 1), _dated("second", "layoff", 1)]
    lookup["Batch For Scanner Agent"] = [
        {"itemsById": {r["event_id"]: r for r in rows}}
    ]
    node = copy.deepcopy(NODES["Trust-Boundary Join"])
    node["parameters"]["jsCode"] = (
        "const originalLookup = $; let configReads = 0; $ = name => { if (name === 'Config' && ++configReads > 1) throw new Error('Config read repeatedly'); return originalLookup(name); };\n"
        + node["parameters"]["jsCode"]
    )
    monkeypatch.setitem(NODES, "Trust-Boundary Join", node)
    code, result = execute(
        "Trust-Boundary Join",
        [{"opportunities": [{"id": r["event_id"]} for r in rows]}],
        lookup,
    )
    assert code == 0 and len(result["result"]) == 2, result


def test_renamed_playbook_heading_has_actionable_error(modules, monkeypatch):
    read = Path.read_text

    def changed(path, *args, **kwargs):
        text = read(path, *args, **kwargs)
        return (
            text.replace("## Apply the criteria every run", "## Renamed")
            if path.name == "03_TARGETING_PLAYBOOK.md"
            else text
        )

    monkeypatch.setattr(Path, "read_text", changed)
    with pytest.raises(ValueError, match="Apply the criteria every run"):
        modules[1].build(json.loads(harness.WORKFLOW.read_text(encoding="utf-8")))


def test_optional_priority_query_clause_is_complete(lookup):
    expression = NODES["Fetch Funding-Distress Signals"]["parameters"]["query"]
    config = lookup["Config"][0]
    assert "Priority context:" not in evaluate(expression, config)
    config["sourcingCriteria"] = {"priorityTriggers": ["site closure"]}
    assert "Priority context: site closure." in evaluate(expression, config)


def test_failed_profile_write_leaves_exports_unchanged(tmp_path, modules, monkeypatch):
    config = target()
    assert run(tmp_path, [config]).returncode == 0
    files = [
        tmp_path / "onepromptman-profile.md",
        *tmp_path.glob("talent-alpha-n8n-config*.json"),
    ]
    before = {p: p.read_bytes() for p in files}
    config["openRole"]["title"] = "Changed title"
    registry = tmp_path / "talent-alpha-targets.json"
    registry.write_text(json.dumps({"targets": [config]}), encoding="utf-8")
    profile = tmp_path / "onepromptman-profile.md"
    write = Path.write_text

    def fail_profile(path, *args, **kwargs):
        if path == profile or path.name.startswith(".talent-alpha-profile-"):
            raise PermissionError("synthetic profile write failure")
        return write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_profile)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "targets",
            "--targets",
            str(registry),
            "--out-dir",
            str(tmp_path),
            "--role",
            "ENG-01",
            "--profile",
            str(profile),
        ],
    )
    with pytest.raises(SystemExit) as error:
        modules[0].main()
    assert error.value.code == 1
    assert {p: p.read_bytes() for p in files} == before


def test_size_stage_profile_provenance_does_not_change_export(tmp_path):
    config = target()
    config["companyFacts"] = {"size": "120 employees", "stage": "Series B"}
    assert run(tmp_path, [config]).returncode == 0
    text = (tmp_path / "onepromptman-profile.md").read_text(encoding="utf-8")
    assert "company_size: 120 employees (stated by user)" in text
    assert "company_stage: Series B (stated by user)" in text
    exported = json.loads((tmp_path / "talent-alpha-n8n-config.json").read_text())
    assert exported["companyFacts"] == config["companyFacts"]


def test_failed_profile_replace_keeps_old_files(tmp_path, modules, monkeypatch):
    config = target()
    assert run(tmp_path, [config]).returncode == 0
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    profile = tmp_path / "onepromptman-profile.md"

    def fail_replace(path, destination):
        raise PermissionError("synthetic replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "targets",
            "--targets",
            str(tmp_path / "talent-alpha-targets.json"),
            "--out-dir",
            str(tmp_path),
            "--role",
            "ENG-01",
            "--profile",
            str(profile),
        ],
    )
    with pytest.raises(SystemExit) as error:
        modules[0].main()
    assert error.value.code == 1
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_explicit_facts_keep_valid_judge_scores(lookup):
    lookup["Config"][0]["companyFacts"] = {"size": "120 employees", "stage": "Series B"}
    for name in ("Judge Advocate", "Judge Skeptic"):
        for verdict in lookup[name][0]["output"]["verdicts"]:
            verdict.update(size_fit="H", stage_fit="L")
    code, result = execute("Reconcile Judges", [], lookup)
    assert code == 0, result
    assert all(row["json"]["bands"][4:] == ["H", "L"] for row in result["result"])

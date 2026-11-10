"""Recruiter preferences are carried through the exported execution nodes."""

import importlib.util
import json
import sys

import pytest
import test_n8n_reliability as harness
from test_n8n_reliability import ROOT, WORKFLOW, _dated, execute

lookup = harness.lookup
pytestmark = harness.pytestmark


def test_filters_run_before_scanner_and_preserve_role_criteria(lookup):
    config = lookup["Config"][0]
    config["includeFundingDistress"] = False
    config["sourcingCriteria"] = {
        "skills": ["test automation"],
        "eligibleLocations": ["Denver"],
        "eventTypes": ["layoff", "funding_distress"],
        "excludeCompanies": ["Excluded Co"],
    }
    fresh = _dated("fresh", "layoff", 1)
    excluded = dict(fresh, event_id="excluded", company="EXCLUDED CO")
    items = [
        fresh,
        _dated("old", "layoff", 10),
        _dated("funding", "funding_distress", 1),
        excluded,
    ]
    code, output = execute("Batch For Scanner Agent", items, lookup)
    assert code == 0, output
    batch = output["result"][0]["json"]
    assert list(batch["itemsById"]) == ["fresh"]
    assert (
        "test automation" in batch["agentPrompt"] and "Denver" in batch["agentPrompt"]
    )
    code, judges = execute("Batch For Judges", [dict(fresh, id="fresh")], lookup)
    assert code == 0 and "test automation" in judges["result"][0]["json"]["judgePrompt"]


@pytest.mark.parametrize(
    "mutation", ["event_type", "limit", "work_terms", "blank_skill"]
)
def test_config_preflight_rejects_bad_criteria_before_sources(lookup, mutation):
    config = lookup["Config"][0]
    config["sourcingCriteria"] = {}
    if mutation == "event_type":
        config["sourcingCriteria"]["eventTypes"] = ["funding_round"]
    elif mutation == "limit":
        config["maxShown"] = 0
    elif mutation == "work_terms":
        config["sourcingCriteria"]["workArrangement"] = "anywhere"
    else:
        config["sourcingCriteria"]["skills"] = [" "]
    code, result = execute("Validate Config", [config])
    assert code == 1 and "Config" in result["error"]


def test_held_candidate_does_not_use_shown_capacity(lookup):
    lookup["Config"][0]["maxShown"] = 4
    code, result = execute("Reconcile Judges", [], lookup)
    assert code == 0, result
    assert sum(not i["json"]["held"] for i in result["result"]) == 4
    lookup["Config"][0]["maxShown"] = 2
    code, result = execute("Reconcile Judges", [], lookup)
    assert code == 0 and sum(not i["json"]["held"] for i in result["result"]) == 2


def test_role_namespace_reaches_record_ids_without_changing_source_ids(lookup):
    lookup["Config"][0]["stateNamespace"] = "ENG-01"
    lookup["Config"][0]["companyName"] = "Example Co"
    _, result = execute("Reconcile Judges", [], lookup)
    rows = [i["json"] for i in result["result"]]
    code, card = execute("Render Scanner Report", rows, lookup)
    assert code == 0, card
    output = card["result"][0]["json"]
    assert {i["id"] for i in output["eventsToRecord"]} == {
        "ENG-01::" + i["id"] for i in rows
    }
    assert "Example Co" in output["renderedHtml"]
    lookup["Config"][0]["stateNamespace"] = ""
    _, legacy = execute("Render Scanner Report", rows, lookup)
    assert {i["id"] for i in legacy["result"][0]["json"]["eventsToRecord"]} == {
        i["id"] for i in rows
    }


def test_production_pin_does_not_disable_freshness():
    path = ROOT / "n8n/tools/build_workflows.py"
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location("workflow_build", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        workflow["pinData"] = {"Config": [{"json": {}}]}
        built = module.build(workflow)
    finally:
        sys.path.pop(0)
    for node in built["nodes"]:
        if node["name"] in ("Trust-Boundary Join", "Batch For Scanner Agent"):
            assert "const WINDOW_DAYS = null;" not in node["parameters"]["jsCode"]

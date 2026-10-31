"""Run exported Code nodes under Node with the same n8n input/lookup interface."""

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "n8n/talent-alpha.workflow.json"
NODES = {
    n["name"]: n for n in json.loads(WORKFLOW.read_text(encoding="utf-8"))["nodes"]
}
pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed for n8n code checks"
)


def execute(name, items=(), lookup=None):
    request = {
        "code": NODES[name]["parameters"]["jsCode"],
        "items": list(items),
        "lookup": lookup or {},
    }
    script = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const wrap = rows => rows.map(json => ({json}));
const $input = {all: () => wrap(input.items), first: () => ({json:input.items[0]})};
const $ = name => ({first: () => ({json: input.lookup[name][0]}), all: () => wrap(input.lookup[name])});
try { const result = new Function('$input','$',input.code)($input,$); process.stdout.write(JSON.stringify({result})); }
catch(error) { process.stdout.write(JSON.stringify({error:error.message})); process.exitCode=1; }
"""
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(request),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


@pytest.fixture
def lookup():
    raw = json.loads(
        (ROOT / "evals/fixtures/raw_events.json").read_text(encoding="utf-8")
    )
    rows = [dict(e, id=e["event_id"]) for e in raw if e["event_id"] != "warn-099888"]
    fixtures = ROOT / "tests/fixtures/card-accuracy"
    profile = (ROOT / "evals/fixtures/onepromptman-profile.md").read_text(
        encoding="utf-8"
    )
    leverage = next(
        line[10:] for line in profile.splitlines() if line.startswith("leverage:")
    )
    return {
        "Trust-Boundary Join": rows,
        "Judge Advocate": [
            {
                "output": json.loads(
                    (fixtures / "advocate_verdicts.json").read_text(encoding="utf-8")
                )
            }
        ],
        "Judge Skeptic": [
            {
                "output": json.loads(
                    (fixtures / "skeptic_verdicts.json").read_text(encoding="utf-8")
                )
            }
        ],
        "Config": [
            {
                "targetSectors": "sensors",
                "companyProfile": leverage,
                "openRole": {
                    "title": "Reliability Engineer",
                    "functions": ["Test Engineer"],
                    "location": "Denver",
                },
            }
        ],
    }


def test_exports_are_generated_from_maintained_code():
    result = subprocess.run(
        [sys.executable, str(ROOT / "n8n/tools/build_workflows.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_delivery_must_succeed_before_seen_records_are_written():
    w = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    edges = {
        name: [link["node"] for branch in value.get("main", []) for link in branch]
        for name, value in w["connections"].items()
    }
    assert edges["Reconcile Judges"] == ["Render Scanner Report"]
    assert edges["Render Scanner Report"] == ["Email Overnight Digest"]
    assert edges["Email Overnight Digest"] == ["Confirm Digest Delivery"]
    assert edges["Confirm Digest Delivery"] == ["Record Scanned Events"]
    for name in [
        "Fetch WARN Notices",
        "Signal Scanner Agent",
        "Judge Advocate",
        "Judge Skeptic",
        "Email Overnight Digest",
    ]:
        assert NODES[name]["onError"] == "stopWorkflow"
    assert not NODES["Fetch WARN Notices"]["parameters"]["options"]["response"][
        "response"
    ]["neverError"]


@pytest.mark.parametrize(
    "payload", [{"error": "unauthorized"}, {}, {"records": "wrong"}]
)
def test_warn_failure_does_not_become_empty_feed(payload):
    code, output = execute("Normalize WARN Items", [payload])
    assert code == 1 and "source failure" in output["error"]


def test_real_empty_feeds_do_not_invoke_scanner(lookup):
    _, warn = execute("Normalize WARN Items", [{"records": []}])
    _, funding = execute("Normalize Funding-Distress Items", [{"results": []}])
    items = [i["json"] for i in warn["result"] + funding["result"]]
    code, output = execute("Batch For Scanner Agent", items, lookup)
    assert code == 0 and output["result"] == []


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "unknown", "invalid-tier"]
)
def test_missing_or_invalid_skeptic_stops_reconciliation(lookup, mutation):
    verdicts = lookup["Judge Skeptic"][0]["output"]["verdicts"]
    if mutation == "missing":
        verdicts.pop()
    elif mutation == "duplicate":
        verdicts[-1] = copy.deepcopy(verdicts[0])
    elif mutation == "unknown":
        verdicts[0]["id"] = "made-up"
    else:
        verdicts[0]["tier"] = "invalid"
    code, output = execute("Reconcile Judges", lookup=lookup)
    assert code == 1 and output.get("error")


def test_reconcile_keeps_sources_and_holds_top_four_disagreement(lookup):
    code, result = execute("Reconcile Judges", lookup=lookup)
    assert code == 0, result
    cards = [i["json"] for i in result["result"]]
    assert all(c["source_name"] and c["source_url"] for c in cards)
    held = next(c for c in cards if c["id"] == "fund-88b2f4")
    assert cards.index(held) < 4 and held["held"]
    assert held["hold_reason"] == "judges disagreed sharply"
    code, rendered = execute("Render Scanner Report", cards, lookup)
    assert code == 0, rendered
    html = rendered["result"][0]["json"]["renderedHtml"]
    assert 'Source: <a href="https://' in html
    assert all(c["source_url"] in html for c in cards if not c["held"])


def test_unsupported_numeric_claim_stops_reconciliation(lookup):
    lookup["Judge Advocate"][0]["output"]["verdicts"][0]["why"] += (
        " 98765 engineers were affected."
    )
    code, result = execute("Reconcile Judges", lookup=lookup)
    assert code == 1 and "Unsupported numeric claim" in result["error"]


def test_punctuation_does_not_turn_a_valid_card_into_an_outage(lookup):
    _, result = execute("Reconcile Judges", lookup=lookup)
    cards = [item["json"] for item in result["result"]]
    cards[0]["why"] += (
        " Evidence is company-level — affected functions need confirmation."
    )
    code, result = execute("Render Scanner Report", cards, lookup)
    assert code == 0, result


@pytest.mark.parametrize(
    "reply,ok",
    [({"error": "delivery failed"}, False), ({"id": "gmail-test-message"}, True)],
)
def test_delivery_confirmation_gates_recording(reply, ok):
    lookup = {"Render Scanner Report": [{"eventsToRecord": [{"id": "warn-test"}]}]}
    code, result = execute("Confirm Digest Delivery", [reply], lookup)
    assert code == (0 if ok else 1)
    if ok:
        assert result["result"][0]["json"]["id"] == "warn-test"


def test_funding_extraction_must_match_original_news(lookup):
    raw = {
        "event_id": "fund-test",
        "company": "",
        "location": "",
        "event_type": "funding_distress",
        "published_at": "2026-01-01",
        "source_name": "Web Search",
        "source_url": "https://example.com/story",
        "title": "Acme Sensors is restructuring in Denver",
        "snippet": "Funding troubles threaten the test team.",
    }
    lookup["Batch For Scanner Agent"] = [{"itemsById": {"fund-test": raw}}]
    opportunity = {
        "id": "fund-test",
        "company": "Acme Sensors",
        "location": "Denver",
        "functions": [],
        "score": 80,
    }
    code, result = execute(
        "Trust-Boundary Join", [{"output": {"opportunities": [opportunity]}}], lookup
    )
    assert code == 0 and result["result"][0]["json"]["company"] == "Acme Sensors"
    opportunity["company"] = "Invented Company"
    code, result = execute(
        "Trust-Boundary Join", [{"output": {"opportunities": [opportunity]}}], lookup
    )
    assert code == 1 and "source text" in result["error"]

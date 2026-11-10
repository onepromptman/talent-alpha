"""Build an offline fixture workflow for execution by a real local n8n CLI.

External feeds, model responses, Gmail and Data Tables use explicit fixture
adapters. Config, branching, merges, batch/join, reconciliation, rendering and
delivery confirmation use the shipped nodes. This does not validate accounts.
"""

import argparse
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def make_workflow(case):
    workflow = json.loads(
        (ROOT / "n8n/talent-alpha.workflow.json").read_text(encoding="utf-8")
    )
    nodes = {n["name"]: n for n in workflow["nodes"]}
    workflow.update(
        id="talent-alpha-offline-" + case,
        name="Talent Alpha OFFLINE fixture " + case,
        active=False,
    )
    workflow.pop("pinData", None)
    workflow["settings"] = {"executionOrder": "v1"}
    workflow.pop("meta", None)
    for node in workflow["nodes"]:
        node.pop("credentials", None)
        node.pop("retryOnFail", None)
        node.pop("disabled", None)

    def stub(name, code):
        nodes[name].update(
            type="n8n-nodes-base.code", typeVersion=2, parameters={"jsCode": code}
        )

    raw = json.loads(
        (ROOT / "evals/fixtures/raw_events.json").read_text(encoding="utf-8")
    )
    raw = [e for e in raw if e["event_id"] != "warn-099888"]
    today = datetime.datetime.now(datetime.timezone.utc).date()
    for event in raw:
        event["published_at"] = (today - datetime.timedelta(days=1)).isoformat()
    if case == "stale":
        for event in raw:
            event["published_at"] = (today - datetime.timedelta(days=30)).isoformat()
    if case == "empty":
        raw = []
    if case == "bad-date":
        raw += [
            dict(raw[0], event_id="missing-date", published_at=None),
            dict(raw[1], event_id="invalid-date", published_at="not-a-date"),
        ]
    profile = (ROOT / "evals/fixtures/onepromptman-profile.md").read_text(
        encoding="utf-8"
    )
    leverage = next(
        line[10:] for line in profile.splitlines() if line.startswith("leverage:")
    )
    config = {
        "companyName": "Example Co",
        "companyProfile": leverage,
        "targetSectors": "industrial sensors",
        "stateNamespace": "ENG-01",
        "maxShown": 3,
        "includeFundingDistress": case != "warn-only",
        "openRole": {
            "id": "ENG-01",
            "title": "Reliability Engineer",
            "functions": ["Test Engineer"],
            "location": "Denver",
        },
    }
    if case == "bad-config":
        config["openRole"]["functions"] = []
    if case == "unknown-facts":
        config["companyFacts"] = {"size": "", "stage": ""}
        config["companyProfile"] += " About 120 employees. Series B."
    if case == "funding-only":
        config["sourcingCriteria"] = {"eventTypes": ["funding_distress"]}
    nodes["Config"]["parameters"]["jsonOutput"] = json.dumps(config)
    trigger = nodes["Nightly 06:00 Scan"]
    trigger.update(type="n8n-nodes-base.manualTrigger", typeVersion=1, parameters={})
    for name, funding in [
        ("Fetch WARN Notices", False),
        ("Fetch Funding-Distress Signals", True),
    ]:
        events = [e for e in raw if (e["event_type"] == "funding_distress") == funding]
        stub(
            name,
            "return "
            + json.dumps(
                [{"json": e} for e in events]
                or [{"json": {"_emptyFeed": "fixture", "event_id": "__empty"}}]
            )
            + ";",
        )
    if case == "warn-only":
        stub(
            "Fetch Funding-Distress Signals",
            "throw new Error('Disabled funding branch must not execute');",
        )
    for name in (
        "Normalize WARN Items",
        "Normalize Funding-Distress Items",
        "Skip Already-Scanned Events",
    ):
        stub(name, "return $input.all();")
    if case == "funding-only":
        stub(
            "Fetch WARN Notices",
            "throw new Error('Disabled WARN branch must not execute');",
        )
    if case == "repeat":
        stub("Skip Already-Scanned Events", "return [];")
    shortlist = json.loads(
        (ROOT / "tests/fixtures/card-accuracy/shortlist.json").read_text(
            encoding="utf-8"
        )
    )
    stub(
        "Signal Scanner Agent",
        "const data = "
        + json.dumps(shortlist)
        + "; const ids = new Set(Object.keys($('Batch For Scanner Agent').first().json.itemsById)); data.opportunities = data.opportunities.filter(o => ids.has(o.id)); return [{json: data}];",
    )
    for name, file in [
        ("Judge Advocate", "advocate_verdicts.json"),
        ("Judge Skeptic", "skeptic_verdicts.json"),
    ]:
        verdicts = json.loads(
            (ROOT / "tests/fixtures/card-accuracy" / file).read_text(encoding="utf-8")
        )
        for verdict in verdicts["verdicts"]:
            if case == "unknown-facts":
                verdict.update(size_fit="H", stage_fit="L")
            for field in ("why", "hook", "edge"):
                verdict[field] = re.sub(
                    r"2026-\d{2}-\d{2}",
                    (today - datetime.timedelta(days=1)).isoformat(),
                    verdict[field],
                )
        code = (
            "const data = "
            + json.dumps(verdicts)
            + "; const ids = new Set($('Trust-Boundary Join').all().map(i => i.json.id)); data.verdicts = data.verdicts.filter(v => ids.has(v.id)); "
        )
        if case == "bad-judge" and name == "Judge Skeptic":
            code += "data.verdicts.pop(); "
        stub(name, code + "return [{json: data}];")
    stub(
        "Email Overnight Digest",
        "return [{json: {id: 'offline-fixture-message'}}];"
        if case != "failed-send"
        else "throw new Error('Synthetic mail failure');",
    )
    stub(
        "Record Scanned Events",
        "const rows = $input.all(); if (rows.some(i => !i.json.id.startsWith('ENG-01::'))) throw new Error('Missing role namespace'); return rows;",
    )
    excluded = {
        "Haiku Scanner Model",
        "Sonnet Judge Model",
        "Scanner Output Parser",
        "Advocate Output Parser",
        "Skeptic Output Parser",
        "On Workflow Error",
        "Email Error Alert",
    }
    workflow["nodes"] = [n for n in workflow["nodes"] if n["name"] not in excluded]
    workflow["connections"] = {
        k: v for k, v in workflow["connections"].items() if k not in excluded
    }
    return workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--case",
        default="success",
        choices=[
            "success",
            "warn-only",
            "empty",
            "stale",
            "repeat",
            "bad-config",
            "bad-judge",
            "failed-send",
            "unknown-facts",
            "bad-date",
            "funding-only",
        ],
    )
    args = parser.parse_args()
    args.out.write_text(
        json.dumps(make_workflow(args.case), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("Offline fixture workflow written; all external services are substituted.")


if __name__ == "__main__":
    main()

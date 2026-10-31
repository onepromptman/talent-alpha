"""Apply maintained node code to public exports or a private n8n snapshot.

Run without arguments to update the two public exports; --check detects drift.
For a private workflow, use --input SNAPSHOT --out PATCHED outside the repository.
This tool never calls n8n and never copies credentials between workflows.
"""

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
NODE_CODE = {
    "Normalize WARN Items": "normalize-warn.js",
    "Normalize Funding-Distress Items": "normalize-funding.js",
    "Batch For Scanner Agent": "batch-scanner.js",
    "Trust-Boundary Join": "trust-join.js",
    "Batch For Judges": "batch-judges.js",
    "Reconcile Judges": "reconcile.js",
    "Render Scanner Report": "render.js",
}
DELIVERY = "Confirm Digest Delivery"


def connection(node):
    return {"main": [[{"node": node, "type": "main", "index": 0}]]}


def build(source):
    workflow = copy.deepcopy(source)
    nodes = {n["name"]: n for n in workflow["nodes"]}
    needed = set(NODE_CODE) | {
        "Email Overnight Digest",
        "Record Scanned Events",
        "Fetch WARN Notices",
    }
    if needed - nodes.keys():
        raise ValueError(
            f"not the Talent Alpha scanner: missing {sorted(needed - nodes.keys())}"
        )
    template = (
        ROOT.parent
        / "skills/talent-alpha/references/templates/overnight_card.template.html"
    ).read_text(encoding="utf-8")
    for name, filename in NODE_CODE.items():
        code = (CODE / filename).read_text(encoding="utf-8")
        if name == "Render Scanner Report":
            code = (
                "const TEMPLATE = "
                + json.dumps(template, ensure_ascii=True)
                + ";\n"
                + code
            )
        nodes[name]["parameters"]["jsCode"] = code
    for name in (
        "Fetch WARN Notices",
        "Fetch Funding-Distress Signals",
        "Signal Scanner Agent",
        "Judge Advocate",
        "Judge Skeptic",
        "Email Overnight Digest",
    ):
        nodes[name].pop("continueOnFail", None)
        nodes[name]["onError"] = "stopWorkflow"
    nodes["Fetch WARN Notices"]["parameters"].setdefault("options", {}).setdefault(
        "response", {}
    ).setdefault("response", {})["neverError"] = False
    nodes["Haiku Scanner Model"]["parameters"]["options"]["maxTokensToSample"] = 4096
    nodes["Sonnet Judge Model"]["parameters"]["options"]["maxTokensToSample"] = 8192
    funding = nodes["Fetch Funding-Distress Signals"]["parameters"]
    funding["query"] = (
        "=Companies in {{ $('Config').first().json.targetSectors }} facing layoffs tied to funding distress, a down round, missed earnings, or restructuring, reported in the last 7 days as of {{ $today.toFormat('yyyy-MM-dd') }}. Exclude generic industry roundups, trackers, and archive pages; return single-company news stories."
    )
    if DELIVERY not in nodes:
        node = {
            "id": "8a90c74c-6bcb-4a35-8c8d-752b9caed410",
            "name": DELIVERY,
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [3248, 416],
            "parameters": {},
        }
        workflow["nodes"].append(node)
        nodes[DELIVERY] = node
    nodes[DELIVERY]["parameters"]["jsCode"] = (CODE / "record-delivered.js").read_text(
        encoding="utf-8"
    )
    nodes[DELIVERY]["disabled"] = bool(nodes["Email Overnight Digest"].get("disabled"))
    workflow["connections"]["Reconcile Judges"] = connection("Render Scanner Report")
    workflow["connections"]["Render Scanner Report"] = connection(
        "Email Overnight Digest"
    )
    workflow["connections"]["Email Overnight Digest"] = connection(DELIVERY)
    workflow["connections"][DELIVERY] = connection("Record Scanned Events")
    return workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if bool(args.input) != bool(args.out):
        parser.error("--input and --out must be supplied together")
    paths = (
        [(args.input, args.out)]
        if args.input
        else [
            (p, p)
            for p in (
                ROOT / "talent-alpha.workflow.json",
                ROOT / "talent-alpha-demo.workflow.json",
            )
        ]
    )
    stale = []
    for src, dest in paths:
        source = json.loads(src.read_text(encoding="utf-8-sig"))
        result = build(source)
        if args.check:
            if result != source:
                stale.append(str(src))
        else:
            with dest.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if stale:
        raise SystemExit("Regenerate workflow exports: " + ", ".join(stale))


if __name__ == "__main__":
    main()

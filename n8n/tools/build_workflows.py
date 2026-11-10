"""Apply maintained node code to public exports or a private n8n snapshot.

Run without arguments to update the two public exports; --check detects drift.
For a private workflow, use --input SNAPSHOT --out PATCHED outside the repository.
This tool never calls n8n and never copies credentials between workflows.
"""

import argparse
import ast
import copy
import json
import re
from pathlib import Path

from layout_workflow import layout_workflow

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
CHAIN_PROMPTS = {
    "Signal Scanner Agent": "scanner.md",
    "Judge Advocate": "advocate.md",
    "Judge Skeptic": "skeptic.md",
}

STATE = ROOT.parent / "skills/talent-alpha/scripts/state.py"


def window_days():
    """The age windows live once, in state.py; the n8n join gets the same table."""
    match = re.search(
        r"^WINDOW_DAYS = (\{.*\})$", STATE.read_text(encoding="utf-8"), re.MULTILINE
    )
    if match is None:
        raise ValueError("WINDOW_DAYS not found in state.py")
    return ast.literal_eval(match.group(1))


def connection(node):
    return {"main": [[{"node": node, "type": "main", "index": 0}]]}


def playbook_rules():
    path = ROOT.parent / "skills/talent-alpha/references/03_TARGETING_PLAYBOOK.md"
    heading = "## Apply the criteria every run"
    _, separator, body = path.read_text(encoding="utf-8").partition(heading + "\n")
    if not separator:
        raise ValueError(f"{path.name}: missing required heading {heading!r}")
    return body.split("At setup's end", 1)[0].strip()


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
    schema = (
        ROOT.parent
        / "skills/talent-alpha/references/content-schemas/n8n-config.schema.json"
    ).read_text(encoding="utf-8")
    config_code = (
        "const CONFIG_SCHEMA = "
        + schema
        + ";\n"
        + (CODE / "config.js").read_text(encoding="utf-8")
    )
    # Only the shipped demo bypasses freshness. Arbitrary pinned production nodes
    # must never silently disable the live workflow's age checks.
    is_demo = bool(workflow.get("meta", {}).get("talentAlphaDemo"))
    for name, filename in NODE_CODE.items():
        code = (CODE / filename).read_text(encoding="utf-8")
        if name in ("Trust-Boundary Join", "Reconcile Judges"):
            code = (CODE / "model-output.js").read_text(encoding="utf-8") + "\n" + code
        if name in ("Trust-Boundary Join", "Batch For Scanner Agent"):
            # An export with pinned sample feeds (the demo) keeps fixed dates, so it
            # gets no window. A live export drops events older than their source window.
            window = None if is_demo else window_days()
            code = "const WINDOW_DAYS = " + json.dumps(window) + ";\n" + code
        if name == "Batch For Scanner Agent":
            code = config_code + "\n" + code
        if name == "Render Scanner Report":
            code = (
                "const TEMPLATE = "
                + json.dumps(template, ensure_ascii=True)
                + ";\n"
                + code
            )
        nodes[name]["parameters"]["jsCode"] = code
    rules = playbook_rules()
    for name, filename in CHAIN_PROMPTS.items():
        prompt = (
            (ROOT / "prompts" / filename)
            .read_text(encoding="utf-8")
            .split("\n---\n", 1)[1]
            .strip()
        )
        prompt += "\n\n" + rules
        nodes[name]["type"] = "@n8n/n8n-nodes-langchain.chainLlm"
        nodes[name]["typeVersion"] = 1.7
        nodes[name]["parameters"] = {
            "promptType": "define",
            "text": "={{ $json.agentPrompt }}"
            if name == "Signal Scanner Agent"
            else "={{ $json.judgePrompt }}",
            "hasOutputParser": True,
            "messages": {
                "messageValues": [
                    {"type": "SystemMessagePromptTemplate", "message": prompt}
                ]
            },
        }
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
        "=Companies in {{ $('Config').first().json.targetSectors }} with work related to {{ $('Config').first().json.openRole.functions.join(', ') }} in {{ ($('Config').first().json.sourcingCriteria?.eligibleLocations || []).join(', ') || $('Config').first().json.openRole.location || 'any location' }} facing layoffs tied to funding distress, a down round, missed earnings, or restructuring, reported in the last 7 days as of {{ $today.toFormat('yyyy-MM-dd') }}. {{ ($('Config').first().json.sourcingCriteria?.priorityTriggers || []).length ? 'Priority context: ' + $('Config').first().json.sourcingCriteria.priorityTriggers.join(', ') + '. ' : '' }}Exclude generic industry roundups, trackers, and archive pages; return dated single-company news stories with evidence of job impact."
    )

    def add_node(name, node_type, version, parameters):
        if name not in nodes:
            node = {
                "id": name.lower().replace(" ", "-"),
                "name": name,
                "type": node_type,
                "typeVersion": version,
                "position": [400, 440],
                "parameters": parameters,
            }
            workflow["nodes"].append(node)
            nodes[name] = node
        nodes[name]["parameters"] = parameters

    add_node(
        "Validate Config",
        "n8n-nodes-base.code",
        2,
        {
            "jsCode": config_code
            + "\nreturn [{json: validateConfig($input.first().json)}];"
        },
    )
    add_node(
        "Funding Enabled",
        "n8n-nodes-base.if",
        2.2,
        {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": "funding-enabled",
                        "leftValue": "={{ $json.includeFundingDistress !== false && (!$json.sourcingCriteria?.eventTypes || $json.sourcingCriteria.eventTypes.includes('funding_distress')) }}",
                        "rightValue": "",
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                            "singleValue": True,
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
    )
    add_node(
        "Funding Disabled",
        "n8n-nodes-base.code",
        2,
        {
            "jsCode": "return [{json: {_emptyFeed: 'funding', event_id: '__talent_alpha_empty_funding'}}];"
        },
    )
    warn_conditions = copy.deepcopy(nodes["Funding Enabled"]["parameters"])
    warn_conditions["conditions"]["conditions"][0].update(
        id="warn-enabled",
        leftValue="={{ !$json.sourcingCriteria?.eventTypes || $json.sourcingCriteria.eventTypes.some(t => t === 'layoff' || t === 'shutdown') }}",
    )
    add_node("WARN Enabled", "n8n-nodes-base.if", 2.2, warn_conditions)
    add_node(
        "WARN Disabled",
        "n8n-nodes-base.code",
        2,
        {
            "jsCode": "return [{json: {_emptyFeed: 'warn', event_id: '__talent_alpha_empty_warn'}}];"
        },
    )
    workflow["connections"]["Config"] = connection("Validate Config")
    workflow["connections"]["Validate Config"] = {
        "main": [
            [
                {"node": "WARN Enabled", "type": "main", "index": 0},
                {"node": "Funding Enabled", "type": "main", "index": 0},
            ]
        ]
    }
    workflow["connections"]["WARN Enabled"] = {
        "main": [
            [{"node": "Fetch WARN Notices", "type": "main", "index": 0}],
            [{"node": "WARN Disabled", "type": "main", "index": 0}],
        ]
    }
    workflow["connections"]["WARN Disabled"] = {
        "main": [[{"node": "Merge Category Feeds", "type": "main", "index": 0}]]
    }
    workflow["connections"]["Funding Enabled"] = {
        "main": [
            [{"node": "Fetch Funding-Distress Signals", "type": "main", "index": 0}],
            [{"node": "Funding Disabled", "type": "main", "index": 0}],
        ]
    }
    workflow["connections"]["Funding Disabled"] = {
        "main": [[{"node": "Merge Category Feeds", "type": "main", "index": 1}]]
    }
    nodes["Skip Already-Scanned Events"]["parameters"]["filters"]["conditions"][0][
        "keyValue"
    ] = "={{ ($('Config').first().json.stateNamespace ? $('Config').first().json.stateNamespace + '::' : '') + $json.event_id }}"
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
    return layout_workflow(workflow)


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
        if not args.input and src.name == "talent-alpha-demo.workflow.json":
            source.setdefault("meta", {})["talentAlphaDemo"] = True
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

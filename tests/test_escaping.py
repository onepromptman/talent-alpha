"""Every slot on the card is escaped, in both renderers.

Company names and source URLs come from third-party feeds; why, hook, edge, titles,
bands, tier and the wildcard axis come from model output; the role and company line
come from Config. None of them may add markup to the card or close the attribute it
sits in. The renderers are the n8n "Render Scanner Report" Code node (run under node
when it is installed) and `scripts/render.py` (always run).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = MODULE_ROOT / "skills" / "talent-alpha"
TEMPLATE = SKILL_ROOT / "references" / "templates" / "overnight_card.template.html"
EXAMPLE_CONTENT = (
    SKILL_ROOT / "references" / "content-schemas" / "card.example-content.json"
)
WORKFLOWS = [
    MODULE_ROOT / "n8n" / "talent-alpha.workflow.json",
    MODULE_ROOT / "n8n" / "talent-alpha-demo.workflow.json",
]

EVIL = '"><img src=x onerror=alert(1)>'
# a live tag, or a quote that closes an attribute and opens an event handler
MARKUP = re.compile(r"<img|\"\s*on[a-z]+=|<script>alert", re.IGNORECASE)


def _render_node_js(path: Path) -> str:
    wf = json.loads(path.read_text(encoding="utf-8"))
    (node,) = [n for n in wf["nodes"] if n["name"] == "Render Scanner Report"]
    return node["parameters"]["jsCode"]


def test_real_and_demo_workflows_share_one_render_node():
    assert _render_node_js(WORKFLOWS[0]) == _render_node_js(WORKFLOWS[1])


def test_render_py_escapes_feed_and_model_text_and_attributes(tmp_path):
    content = json.loads(EXAMPLE_CONTENT.read_text(encoding="utf-8"))
    hero, second, _third, held = content["candidates"]
    hero["company"] = "Acme" + EVIL
    hero["bands"] = ["H", EVIL, "M", "H", "H", "H"]
    hero["wildcard"] = {"fired": True, "axis_index": EVIL, "bridge": EVIL}
    hero["source_url"] = "javascript:alert(1)"
    second["bands"] = [EVIL, "M", "M", "M", "M", "M"]
    second["source_url"] = 'https://example.com/a"onmouseover="alert(1)'
    held["company"] = "Held" + EVIL
    content["run"]["window_note"] = "72h" + EVIL
    src = tmp_path / "content.json"
    src.write_text(json.dumps(content), encoding="utf-8")
    out = tmp_path / "card.html"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/render.py",
            "render",
            "--template",
            str(TEMPLATE),
            "--content",
            str(src),
            "--out",
            str(out),
            "--strict",
        ],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    doc = out.read_text(encoding="utf-8")
    assert not MARKUP.search(doc), "markup from a feed or a judge reached the card"
    assert 'href="javascript:' not in doc
    assert "link withheld: not an http(s) URL" in doc
    assert 'href="https://example.com/a&quot;onmouseover=&quot;alert(1)"' in doc


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_n8n_render_node_escapes_every_slot(workflow):
    config = {
        "openRole": {"title": "Engineer" + EVIL, "location": "Austin" + EVIL},
        "companyProfile": "Example Co" + EVIL + " -- profile",
    }

    def item(company, tier, held=False):
        return {
            "company": company + EVIL,
            "location": "Austin" + EVIL,
            "employees_affected": 12,
            "event_type": "layoff" + EVIL,
            "event_age_label": "today",
            "titles": ["T" + EVIL],
            "tier": tier,
            "bands": ["H", EVIL, "M", "M", "M", "M"],
            "wildcard": {"fired": True, "axis_index": EVIL, "bridge": EVIL},
            "why": EVIL,
            "hook": EVIL,
            "edge": EVIL,
            "held": held,
            "hold_reason": "judges disagreed sharply" + EVIL,
        }

    items = [item("Hero", "S"), item("Second", "A"), item("Held", "HELD", held=True)]
    harness = (
        "const CONFIG = " + json.dumps(config) + ";\n"
        "const ITEMS = " + json.dumps(items) + ";\n"
        "const $ = (name) => ({ first: () => ({ json: CONFIG }) });\n"
        "const $input = { all: () => ITEMS.map(j => ({ json: j })) };\n"
        "const out = (function(){\n" + _render_node_js(workflow) + "\n})();\n"
        "process.stdout.write(out[0].json.renderedHtml);\n"
    )
    proc = subprocess.run(
        ["node", "-e", harness], capture_output=True, text=True, timeout=30, check=False
    )
    assert proc.returncode == 0, proc.stderr
    doc = proc.stdout
    assert "Hero&quot;&gt;&lt;img" in doc and "Held&quot;&gt;&lt;img" in doc
    assert not MARKUP.search(doc), (
        "markup from a feed, a judge or Config reached the emailed card"
    )

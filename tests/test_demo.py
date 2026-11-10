"""The documented no-key first run must produce a checked card without overwriting it."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offline_demo_builds_checked_output_and_preserves_existing_folder(tmp_path):
    output = tmp_path / "demo"
    command = [sys.executable, str(ROOT / "tools/demo.py"), "--out", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    content = json.loads((output / "content.json").read_text(encoding="utf-8"))
    assert len(content["candidates"]) == 5
    assert sum(c["held"] for c in content["candidates"]) == 1
    state = json.loads((output / "state.json").read_text(encoding="utf-8"))
    assert set(state["seen_events"]) == {c["id"] for c in content["candidates"]}
    html = (output / "card.html").read_text(encoding="utf-8")
    assert "Source:" in html and "Solstice Yards" in html
    before = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in output.rglob("*")
        if p.is_file()
    }
    rerun = subprocess.run(command, capture_output=True, text=True, check=False)
    assert rerun.returncode == 2
    assert "already exists" in rerun.stderr
    assert before == {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in output.rglob("*")
        if p.is_file()
    }

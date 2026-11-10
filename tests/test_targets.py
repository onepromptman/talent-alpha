"""Saved roles retain their criteria and independent seen-event memory."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/talent-alpha/scripts/targets.py"


def target(role_id="ENG-01"):
    return {
        "companyName": "Example Co",
        "companyProfile": "We offer relocation support and ownership of the test lab.",
        "companyFacts": {"size": "", "stage": ""},
        "targetSectors": "industrial sensors, robotics",
        "openRole": {
            "id": role_id,
            "title": "Test Engineer",
            "functions": ["Reliability Engineer"],
            "location": "Denver, CO",
        },
        "sourcingCriteria": {
            "seniority": "senior",
            "skills": ["reliability testing"],
            "workArrangement": "onsite",
            "eligibleLocations": ["Denver, CO"],
            "eventTypes": ["layoff", "shutdown"],
            "priorityTriggers": ["plant closure"],
            "excludeCompanies": ["Excluded Co"],
        },
        "maxShown": 4,
        "includeFundingDistress": False,
    }


def run(tmp_path, configs, role="ENG-01"):
    source = tmp_path / "talent-alpha-targets.json"
    source.write_text(json.dumps({"targets": configs}), encoding="utf-8")
    profile = tmp_path / "onepromptman-profile.md"
    if not profile.exists():
        profile.write_text(
            "## Organization\nname: Example Co (stated by user)\n\n## Brand\ncredit: off\n\n## Kit: other\nkeep: unchanged\n",
            encoding="utf-8",
        )
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--targets",
            str(source),
            "--out-dir",
            str(tmp_path),
            "--role",
            role,
            "--profile",
            str(profile),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_role_switch_preserves_shared_profile_and_exports_criteria(tmp_path):
    configs = [target(), target("SALES-01")]
    configs[1]["openRole"]["title"] = "Account Executive"
    assert run(tmp_path, configs).returncode == 0
    profile = tmp_path / "onepromptman-profile.md"
    first = profile.read_text(encoding="utf-8")
    assert "state_file: talent-alpha-state-ENG-01.json" in first
    assert run(tmp_path, configs, "SALES-01").returncode == 0
    second = profile.read_text(encoding="utf-8")
    assert (
        first.split("## Kit: talent-alpha")[0]
        == second.split("## Kit: talent-alpha")[0]
    )
    assert second.count("## Kit: talent-alpha") == 1
    assert "state_file: talent-alpha-state-SALES-01.json" in second
    assert "Account Executive" in second
    active = json.loads((tmp_path / "talent-alpha-n8n-config.json").read_text())
    assert active["sourcingCriteria"] == configs[1]["sourcingCriteria"]
    assert active["maxShown"] == 4 and active["includeFundingDistress"] is False
    assert b"\r" not in profile.read_bytes()


def test_legacy_role_keeps_existing_memory(tmp_path):
    config = target()
    config["stateNamespace"] = ""
    assert run(tmp_path, [config]).returncode == 0
    assert (
        "state_file: talent-alpha-state.json"
        in (tmp_path / "onepromptman-profile.md").read_text()
    )


def test_custom_state_path_survives_role_switching(tmp_path):
    legacy = target()
    legacy["stateNamespace"] = ""
    legacy["stateFile"] = "memory/original.json"
    configs = [legacy, target("SECOND")]
    assert run(tmp_path, configs, "SECOND").returncode == 0
    assert run(tmp_path, configs).returncode == 0
    assert (
        "state_file: memory/original.json"
        in (tmp_path / "onepromptman-profile.md").read_text()
    )


def test_two_roles_cannot_share_custom_state(tmp_path):
    configs = [target(), target("SECOND")]
    for config in configs:
        config["stateFile"] = "memory/shared.json"
    result = run(tmp_path, configs)
    assert (
        result.returncode == 1 and "each role needs its own stateFile" in result.stderr
    )


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "path", "empty", "wrong_company", "namespace", "disabled", "range"],
)
def test_invalid_target_does_not_change_profile_or_export(tmp_path, mutation):
    good = target()
    assert run(tmp_path, [good]).returncode == 0
    profile = tmp_path / "onepromptman-profile.md"
    export = tmp_path / "talent-alpha-n8n-config.json"
    before = (profile.read_bytes(), export.read_bytes())
    bad = copy.deepcopy(good)
    configs = [bad]
    if mutation == "duplicate":
        configs.append(copy.deepcopy(bad))
    elif mutation == "path":
        bad["openRole"]["id"] = "../../escape"
    elif mutation == "empty":
        bad["openRole"]["functions"] = [" "]
    elif mutation == "wrong_company":
        bad["companyName"] = "Different Co"
    elif mutation == "namespace":
        bad["stateNamespace"] = "../escape"
    elif mutation == "disabled":
        bad["sourcingCriteria"]["eventTypes"] = ["funding_distress"]
    elif mutation == "range":
        bad["maxShown"] = 0
    assert run(tmp_path, configs).returncode == 1
    assert (profile.read_bytes(), export.read_bytes()) == before

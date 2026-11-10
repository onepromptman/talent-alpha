"""The plugin package must pass the account upload route as shipped."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DESCRIPTION_LIMIT = 500


def manifests():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text("utf-8"))
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text("utf-8"))
    return plugin, market


def test_every_manifest_description_fits_the_upload_limit():
    # Customize > Plugins > Upload plugin rejects a description over 500 characters
    # (first-install validation, 2026-11-06: the 638-character text was refused).
    plugin, market = manifests()
    descriptions = {
        "plugin.json": plugin["description"],
        "marketplace.json metadata": market["metadata"]["description"],
    }
    for entry in market["plugins"]:
        descriptions[f"marketplace.json plugin {entry['name']}"] = entry["description"]
    for where, text in descriptions.items():
        assert 0 < len(text) <= UPLOAD_DESCRIPTION_LIMIT, (where, len(text))


def test_versions_agree_across_manifests_module_and_readme():
    plugin, market = manifests()
    module = re.search(
        r"^version: (\S+)$", (ROOT / "MODULE.yaml").read_text("utf-8"), re.MULTILINE
    )
    badge = re.search(
        r"badge/version-([0-9.]+)-", (ROOT / "README.md").read_text("utf-8")
    )
    versions = {
        plugin["version"],
        market["metadata"]["version"],
        *(entry["version"] for entry in market["plugins"]),
        module.group(1),
        badge.group(1),
    }
    assert len(versions) == 1, versions

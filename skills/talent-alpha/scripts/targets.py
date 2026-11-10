"""Validate saved targets, export n8n configs, and activate one plugin role.

Setup supplies {"targets": [Config, ...]}. Every target is validated before any
file changes. Shared profile sections and other kits are preserved verbatim.
"""

import argparse
import json
import re
from pathlib import Path

from render import CONTENT_SCHEMA, config_problems, load, schema_problems


def prepare(path):
    data = load(path)
    if not isinstance(data, dict) or set(data) != {"targets"}:
        raise ValueError('expected {"targets": [Config, ...]}')
    targets = data["targets"]
    if not isinstance(targets, list) or not targets:
        raise ValueError("at least one target is required")
    schema = load(CONTENT_SCHEMA.with_name("n8n-config.schema.json"))
    ids, namespaces, state_paths = set(), set(), set()
    for config in targets:
        issues = schema_problems(config, schema, "target")
        if issues:
            raise ValueError("; ".join(issues))
        role_id = config["openRole"]["id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", role_id):
            raise ValueError(
                "role IDs need 1-64 letters, digits, underscores or hyphens"
            )
        config.setdefault("stateNamespace", role_id)
        namespace = config["stateNamespace"]
        if namespace and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", namespace):
            raise ValueError("stateNamespace must be empty or a safe role ID")
        if role_id.casefold() in ids or namespace.casefold() in namespaces:
            raise ValueError("role IDs and state namespaces must be unique")
        ids.add(role_id.casefold())
        namespaces.add(namespace.casefold())
        if not config.get("companyName", "").strip():
            raise ValueError("each saved target needs companyName")
        if "stateFile" in config and (
            not config["stateFile"].strip()
            or any(c in config["stateFile"] for c in "\r\n")
        ):
            raise ValueError("stateFile must be a nonempty single-line path")
        state_name = config.get("stateFile") or (
            f"talent-alpha-state-{namespace}.json"
            if namespace
            else "talent-alpha-state.json"
        )
        state_path = str((path.parent / state_name).resolve()).casefold()
        if state_path in state_paths:
            raise ValueError("each role needs its own stateFile")
        state_paths.add(state_path)
        # Kit fields consumed by the renderer are single lines, not YAML blocks.
        for value in (
            config["companyName"],
            config["companyProfile"],
            config.get("author", ""),
            *config.get("companyFacts", {}).values(),
        ):
            if "\n" in value or "\r" in value:
                raise ValueError("company fields must each be one line")
        issues = config_problems(config)
        if issues:
            raise ValueError("; ".join(issues))
    return targets


def activate(profile, config):
    text = profile.read_text(encoding="utf-8")
    org = re.search(
        r"^## Organization\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    name = re.search(r"^name:\s*(.+)$", org[1], re.MULTILINE) if org else None
    if (
        not name
        or re.sub(r"\s*\([^\n]*\)\s*$", "", name[1]).strip() != config["companyName"]
    ):
        raise ValueError(
            "confirm the Organization name in the shared profile before activating this target"
        )
    namespace = config["stateNamespace"]
    state_file = config.get("stateFile") or (
        f"talent-alpha-state-{namespace}.json"
        if namespace
        else "talent-alpha-state.json"
    )
    facts = config.get("companyFacts", {})
    block = "\n".join(
        [
            "## Kit: talent-alpha",
            "open_role: " + json.dumps(config["openRole"], ensure_ascii=False),
            "sourcing_criteria: "
            + json.dumps(config.get("sourcingCriteria", {}), ensure_ascii=False),
            "leverage: " + config["companyProfile"] + " (stated by user)",
            "company_size: " + facts.get("size", ""),
            "company_stage: " + facts.get("stage", ""),
            "signal_sources: "
            + json.dumps(
                [s.strip() for s in config["targetSectors"].split(",") if s.strip()],
                ensure_ascii=False,
            ),
            "max_shown: " + str(config.get("maxShown", 10)),
            "include_funding_distress: "
            + str(config.get("includeFundingDistress", True)).lower(),
            "author: " + config.get("author", "Your name"),
            "state_file: " + state_file,
            "targets_file: talent-alpha-targets.json",
            "",
        ]
    )
    match = re.search(
        r"^## Kit: talent-alpha\s*\n.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    return (
        text[: match.start()] + block + "\n" + text[match.end() :]
        if match
        else text.rstrip() + "\n\n" + block
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--role")
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    try:
        targets = prepare(args.targets)
        if bool(args.role) != bool(args.profile):
            raise ValueError("--role and --profile must be supplied together")
        selected = next((c for c in targets if c["openRole"]["id"] == args.role), None)
        if args.role and not selected:
            raise ValueError("unknown role ID")
        updated = activate(args.profile, selected) if selected else None
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for config in targets:
            dest = (
                args.out_dir
                / f"talent-alpha-n8n-config-{config['openRole']['id']}.json"
            )
            dest.write_text(
                json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        if selected:
            (args.out_dir / "talent-alpha-n8n-config.json").write_text(
                json.dumps(selected, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            args.profile.write_text(updated, encoding="utf-8", newline="\n")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"setup error: {exc}\n")
    print(
        f"Validated and exported {len(targets)} target(s)"
        + (f"; active role: {args.role}" if selected else "")
    )


if __name__ == "__main__":
    main()

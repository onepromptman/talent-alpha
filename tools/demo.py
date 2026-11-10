"""Build a fictional card locally with Python 3.10+, no keys or extra packages."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/talent-alpha/scripts"
# The fictional fixture events are dated 2026-09-05 to 2026-09-07. The demo runs as of
# the last of those days, so badges, the window note and the dedupe window agree.
FIXTURE_AS_OF = "2026-09-07"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("talent-alpha-demo"))
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        parser.error("output folder already exists; choose a new --out folder")
    output.mkdir(parents=True)
    inputs = output / "inputs"
    inputs.mkdir()
    for source in (ROOT / "evals/fixtures").iterdir():
        if source.is_file():
            shutil.copy2(source, inputs / source.name)
    for source in (ROOT / "tests/fixtures/card-accuracy").iterdir():
        if source.is_file():
            shutil.copy2(source, inputs / source.name)
    state = output / "state.json"
    shutil.copy2(inputs / "talent-alpha-state.json", state)

    def run(script, *arguments):
        subprocess.run(
            [sys.executable, str(SCRIPTS / script), *map(str, arguments)],
            check=True,
            env={**os.environ, "LOG_FILE": "", "LOG_LEVEL": "ERROR"},
        )

    run(
        "state.py",
        "dedupe",
        "--as-of",
        FIXTURE_AS_OF,
        "--events",
        inputs / "raw_events.json",
        "--state",
        state,
        "--out",
        output / "new_events.json",
    )
    run(
        "render.py",
        "join",
        "--as-of",
        FIXTURE_AS_OF,
        "--raw",
        output / "new_events.json",
        "--shortlist",
        inputs / "shortlist.json",
        "--out",
        output / "trusted.json",
    )
    run(
        "render.py",
        "build",
        "--as-of",
        FIXTURE_AS_OF,
        "--raw",
        output / "new_events.json",
        "--trusted",
        output / "trusted.json",
        "--advocate",
        inputs / "advocate_verdicts.json",
        "--skeptic",
        inputs / "skeptic_verdicts.json",
        "--profile",
        inputs / "onepromptman-profile.md",
        "--state",
        state,
        "--author",
        "Fictional example",
        "--company-name",
        "Solstice Yards",
        "--role-title",
        "Senior Reliability Engineer",
        "--role-location",
        "Denver, CO",
        "--out",
        output / "content.json",
        "--html",
        output / "card.html",
    )
    content = json.loads((output / "content.json").read_text(encoding="utf-8"))
    print(
        f"Demo complete: {len(content['candidates'])} fictional signals. Open {output / 'card.html'}"
    )
    print(
        f"Dated {FIXTURE_AS_OF} to match the frozen example events; prepared model "
        "outputs, no live news or model calls."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Demo stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)

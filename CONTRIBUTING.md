# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

Make changes directly in this repository. Keep runtime instructions, schemas and
tests together. The plugin has no third-party Python runtime dependencies. Tests
use pytest and Node; they do not need another repository, credentials or model calls.
Start with the [architecture guide](docs/architecture.md) for the source map.

## Set up

Use Python 3.10 or later and Node 24 for the full test suite. CI tests Python 3.10,
3.11 and 3.14 on Linux. Node executes exported n8n Code nodes in a fixture harness;
it is not required for plugin users. Check `python3 --version` and `node --version`.

On macOS or Linux, from the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt ruff==0.17.3
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt ruff==0.17.3
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\ruff.exe` below.

## Before you open a pull request

```bash
ruff check .
ruff format --check .
python -m pytest -q
python n8n/tools/build_workflows.py --check
```

Missing Node skips the JavaScript checks locally; that is not a full validation.
CI installs Node explicitly and runs a dependency audit as well. See
[CI](.github/workflows/ci.yml) and [account acceptance](docs/ACCEPTANCE.md).

When changing `n8n/code/`, `n8n/prompts/`, the shared template or targeting playbook,
run `python n8n/tools/build_workflows.py` and commit both workflow exports with the
source change. Workflow topology and node settings live in those exports; the
builder updates the maintained code, prompts and layout in place. Do not paste
fixes only into embedded Code-node strings. The golden-sample test prints the
regeneration command when a renderer/template change affects the sample HTML.

If Claude Code is installed, also run `claude plugin validate .`. This validates
the package structure; it does not establish live model or account acceptance.

## Package a reviewed commit

Use a clean checkout after the checks above pass. From the repository root:

```bash
git status --short
git archive --format=zip --output=../talent-alpha.zip HEAD
```

Choose an unused output filename if that path already exists. `git archive` exports
committed files only, with `.claude-plugin/plugin.json` at the ZIP root. It excludes
local environments, caches, profiles and run data. Uncommitted edits are not included.
Keep tests and fictional fixtures: the no-key demo uses them. Do not ZIP the whole
working directory, which can include credentials and personal configuration.

Before publishing, record the commit and ZIP checksum, check that manifest/module
versions agree, and validate the package. Publish the same reviewed commit and ZIP.
Retain historical tags; generated workflow exports and the sample HTML are intended
distribution files. Local audit logs and intermediate builds do not belong in Git.
Each claimed live client still needs its own [acceptance cases](docs/ACCEPTANCE.md).

## House rules

- Keep the scripts working on Python 3.10: they run on the user's own `python3`.
- No real candidate, employee or client data anywhere, including tests and examples.
- Plain English in docs, short sentences, no em dashes.

By contributing you agree your work is released under the repository's MIT license.

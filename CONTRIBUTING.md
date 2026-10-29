# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

This repository is generated from a module of onepromptman/talentai by script. A pull
request here is welcome: a maintainer makes the same change in the module and publishes
again, so it may land in a slightly different form.

## Set up

The checks need Python 3.11 or later (`python3 --version`):

```bash
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements-dev.txt ruff==0.17.3
```

## Before you open a pull request

```bash
ruff check . && ruff format --check .
python -m pytest -q
```

CI runs these, and any other checks it lists, in `.github/workflows/ci.yml`.

## House rules

- Keep the scripts working on Python 3.9: they run on the user's own `python3`.
- No real candidate, employee or client data anywhere, including tests and examples.
- Plain English in docs, short sentences, no em dashes.

By contributing you agree your work is released under the repository's MIT license.

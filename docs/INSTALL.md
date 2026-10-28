# Install

This page covers the **Cowork / Claude Code plugin** path: the identical
pull-scan-judge-render pipeline as the n8n workflow, run on demand inside a
conversation. Want the standalone, scheduled n8n workflow instead (or as
well)? See [`setup.md`](setup.md) in this same folder -- that page is n8n
only and does not cover plugin install.

Talent Alpha runs in **Claude Code** and **Cowork**. It does not run in the
regular Claude chat window, which cannot spawn the scanner and judge
subagents; `run talent alpha` will do nothing there.

---

## Claude Code

**Option A: marketplace (recommended, two lines):**

```
/plugin marketplace add onepromptman/talent-alpha
/plugin install talent-alpha@talent-alpha
```

Non-interactive equivalent:

```bash
claude plugin marketplace add onepromptman/talent-alpha
claude plugin install talent-alpha@talent-alpha --scope user
```

**Option B: manual.** Clone or download this repository and add the plugin's
folder (the one that holds `.claude-plugin/plugin.json`) as a plugin in Claude
Code or Cowork.

## Cowork (Claude desktop app)

Open the plugin browser and add the marketplace, then install **Talent
Alpha** the same way as Option A above.

## First run

```
set up talent alpha
```

This writes the shared `## Kit: talent-alpha` block into
`onepromptman-profile.md` -- the same profile file every kit in this
marketplace reads and shares. The block it writes and owns holds:

| Field | What it is |
| --- | --- |
| `open_role` | `title`, `functions` (adjacent titles that still count as a match), and `location` for the role you're filling |
| `leverage` | a concrete paragraph on what makes your company worth someone moving for (pay, equity, remote policy, relocation support -- specifics, not vague prose) |
| `state_file` | the path to the local dedupe memory (`talent-alpha-state.json` by default) that a run reads and rewrites so it only surfaces new-since-last-run events |

Your company name and a few other shared basics live in the profile's
top-level `## Organization` block, filled once by whichever kit you set up
first in a given folder; if another kit already wrote it, `talent-alpha-setup`
skips straight to this kit's own questions.

Setup also writes `talent-alpha-n8n-config.json`, a ready-to-paste `Config`
node value for the n8n path -- useful only if you later run the workflow in
[`setup.md`](setup.md) too; ignore it otherwise.

Then, once setup is done:

```
run talent alpha
```

## Relationship to the n8n path

Both paths ship from this one repository and run the same pull-dedupe-
shortlist-judge-reconcile-render pipeline. They differ in where they run and
what they trade off:

- **This plugin (in-session):** zero paid keys, runs on demand, WARN events
  source at Reported tier instead of Filed (see
  [`../CONNECTORS.md`](../CONNECTORS.md) for why). Scheduling on the Claude
  Code / Cowork side is unconfirmed for this build.
- **n8n (`setup.md`):** a real unattended nightly run, needs its own
  credentials (Anthropic, optionally WARN Firehose and Perplexity, Gmail),
  and gets Filed-tier WARN data when the WARN Firehose key is attached.

If you want both, run this page's setup first -- `talent-alpha-setup` writes
the n8n `Config` node value for you as a byproduct.

## Uninstall

```
/plugin uninstall talent-alpha@talent-alpha
/plugin marketplace remove talent-alpha
```

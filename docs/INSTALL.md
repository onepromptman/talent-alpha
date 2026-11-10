# Install

This page covers the **Cowork / Claude Code plugin** path: the same sourcing stages
as the n8n workflow, run on demand inside a
conversation. Want the standalone, scheduled n8n workflow instead (or as
well)? See [`setup.md`](setup.md) in this same folder -- that page is n8n
only and does not cover plugin install.

The plugin targets **Claude Code** and **Cowork**. Complete the separate
[account acceptance cases](ACCEPTANCE.md) in each client before relying on it. It does not run in the
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

**Option B: local checkout.** Clone or download this repository. Start Claude Code
with the plugin folder (the one that holds `.claude-plugin/plugin.json`):

```bash
claude --plugin-dir /path/to/talent-alpha
```

This loads the plugin for that session. See the official
[local plugin guide](https://code.claude.com/docs/en/plugins/create#load-a-plugin-from-a-directory-or-zip).

## Cowork (Claude desktop app)

Open **Cowork**, then **Customize > Plugins**. Upload a packaged
`talent-alpha.zip` using the custom-plugin upload option. If you have a source
checkout, [package its committed files](../CONTRIBUTING.md#package-a-reviewed-commit)
first; `.claude-plugin/plugin.json` must be at the ZIP root. Open a new Cowork task
and select a writable working folder for the profile, memory and cards. Enable
web search and say `set up talent alpha`. The setup checks capabilities before
claiming it can scan. Python 3.10+ must be available inside Cowork's execution
environment, which may differ from the host computer's PATH.

Install from `onepromptman/talent-alpha` when using the marketplace route in
Claude Code. A marketplace installation and a manually uploaded ZIP update
differently: update the marketplace plugin, or upload a newly packaged ZIP.
Use one installation route for Talent Alpha in a session to avoid loading two copies.

See Anthropic's [plugin installation guide](https://support.claude.com/en/articles/13837440-use-plugins-in-claude).
Plugin skills may appear in ordinary chat, but this product's full run requires
the subagents and execution tools available in Cowork or Claude Code.

## First run

```
set up talent alpha
```

This writes the shared `## Kit: talent-alpha` block into
`onepromptman-profile.md`. The standalone marketplace contains only Talent Alpha;
the profile format can also be shared with other compatible kits in your working
folder. The block this plugin writes and owns holds:

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

Setup first explains which news can justify action today, then asks which roles
and locations you want to target. It proposes role-specific triggers and asks
you to confirm them. Saved roles live in `talent-alpha-targets.json`; each also
gets `talent-alpha-n8n-config-<id>.json`. Say `run talent alpha for <role>` or
`run all my targets` for separate cards and separate seen-event memory. Daily
runs reuse your plan; update setup when the role or hiring terms change.

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
- **n8n (`setup.md`):** a scheduling preview to validate before unattended use, needs its own
  credentials (Anthropic, optionally WARN Firehose and Perplexity, Gmail),
  and gets Filed-tier WARN data when the WARN Firehose key is attached.

If you want both, run this page's setup first -- `talent-alpha-setup` writes
the n8n `Config` node value for you as a byproduct.

## Uninstall

```
/plugin uninstall talent-alpha@talent-alpha
/plugin marketplace remove talent-alpha
```

# How Talent Alpha works

The detail behind the [README](../README.md): what the card holds, which model does what,
how it remembers what you have seen, and what the plugin can touch.

## What you can ask

| You say | You get |
| --- | --- |
| `run talent alpha` | Both feeds pulled, a scanner shortlist, an Advocate and Skeptic pass, one rendered card, in a few minutes |
| `set up talent alpha` | The guided profile conversation, about 5 minutes |
| `run talent alpha` (again, later) | Only events new since the last run; the state file remembers what it scanned |

## The card

One self-contained HTML card ([sample](../samples/01_Overnight_Card_SAMPLE.html), on
fictional companies). GitHub shows `.html` as source, so download it or clone the
repository and open it in a browser.

Every event on the card carries one of three tiers: **Filed** (an official WARN Act
filing), **Reported** (dated news coverage) or **Company-stated** (a leverage detail
from your own profile). Nothing is invented: an id a judge could not match to the pulled
batch is dropped before it reaches the card, and a candidate with no applicable leverage
gets an empty `edge` line, never filler. [CONNECTORS.md](../CONNECTORS.md) explains the
tiers and what the in-session WARN feed trades away.

## Who does what

- `scanner`, `advocate` and `skeptic` run on the executor (Sonnet) tier; `critic` judges
  all three on the verifier (Opus) tier before the verdicts are blended, with at most two
  repair laps. The model that made a verdict never checks it.
- The Advocate and the Skeptic never see each other's verdict before both return. A
  script blends the two tiers by rank; neither judge does.
- Freshness is a sort tiebreak and a label, not a penalty: an hours-old signal sorts
  ahead of a stale one at the same tier.
- A script renders and checks the card, and `scripts/state.py` marks every event seen.
- You never call `scanner`, `advocate` or `skeptic` yourself; the `talent-alpha` skill
  starts them.
- The n8n workflow is a separate deployment. Its scanner step uses a cheaper model
  (Haiku); that choice is n8n-side and does not change the plugin's tiers.

**Timing.** A cold run (empty state file) takes a few minutes, mostly the two web
searches and the parallel judges. A warm run is faster in proportion to how few new
events there are.

## State and scheduling

The n8n workflow dedupes against a Data Table (`talent_alpha_events_seen`) that n8n
keeps for you. The plugin's equivalent is a JSON file, `talent-alpha-state.json` by
default, next to your `onepromptman-profile.md` and read at the start of every run
(`scripts/state.py`; the design is in its docstring). Its path is recorded in the
profile, so you can move it without touching a skill.

Separate on-demand runs in the same working folder work as designed: the second run
skips events the first one saw. Scheduled runs inside Claude Code or Cowork are not
confirmed for this build, so it is not yet known whether the working folder, and the
file, survives between two scheduled firings. If you schedule `run talent alpha`, run it
on two different days and check that the second card leaves out the first card's events
before you trust it unattended. For an unattended nightly card today, use n8n.

## What the plugin can touch

The plugin is plain text: skills, agent prompts, and small Python scripts (three tools
and a logging helper) that run inside Claude's sandbox. Nothing installs on your
computer beyond what the sandbox provides, and nothing reports back to anyone. It cannot
message, email or post anything, and it has no access to any account or system
permission. The whole source is in this repository.

The card is about real layoffs and companies in real distress. Keep the framing
respectful: it names companies and functions, never individuals.

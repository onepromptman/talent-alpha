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

One HTML card ([sample](../samples/01_Overnight_Card_SAMPLE.html), on
fictional companies). GitHub shows `.html` as source, so download it or clone the
repository and open it in a browser. The template requests optional Google Fonts
when online and uses local fallback fonts offline. Source links open only when clicked.

The evidence vocabulary distinguishes three kinds of claim: **Filed** (an official WARN Act
filing), **Reported** (dated news coverage) or **Company-stated** (a leverage detail
from your own profile). Source links let you check the evidence. Unknown IDs and
incomplete judge coverage fail the build; company extraction must trace to the source text. These checks cannot
prove that a news story is true. A candidate with no applicable leverage gets an empty
`edge` line. [CONNECTORS.md](../CONNECTORS.md) explains the
tiers and what the in-session WARN feed trades away.

## Who does what

- `scanner`, `advocate` and `skeptic` run on the executor (Sonnet) tier; `critic` reviews
  each judge verdict file on the verifier (Opus) tier before blending, with at most two
  repair laps. An unresolved RETURNED verdict stops the build. The model that made
  a verdict never checks it.
- The Advocate and the Skeptic never see each other's verdict before both return. A
  script blends the two tiers by rank; neither judge does.
- Ages count whole days to the run date (`--as-of`, default today). Dedupe drops any
  event older than its source window (3 days for WARN, 7 for funding news) and says
  how many. Inside the window, freshness is a sort tiebreak and a label, not a
  penalty: a fresher signal sorts ahead at the same tier.
- The plugin uses `render.py build` to check both judge coverage and numeric claims,
  enforce the shipped schema, render, verify, and then mark reconciled IDs seen.
- A sharp S/C disagreement is always held for review, including in the first four slots.
  Source-ID dedupe does not merge separate articles about one real-world event.
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
before you trust it unattended. n8n provides a scheduling route after its live
acceptance cases pass.

## What the plugin can touch

The plugin contains skills, agent prompts, and standard-library Python scripts.
It uses the host Claude session's permitted web and file tools. The plugin has no
mail integration or outreach step; its scripts write local artifacts and state.
Python 3.10 or newer is required. The whole source is in this repository.

The card is about real layoffs and companies in real distress. Keep the framing
respectful: it names companies and functions, never individuals.

## Models and repeatable checks

The standalone plugin uses Claude Code's `sonnet` and `opus` family aliases, so the account and provider resolve their supported current versions. The critic remains a different model tier from producers. Record the actual IDs during acceptance; provider mappings can differ. The frozen evaluation case keeps its pinned model for reproducibility. [Alias behavior](https://code.claude.com/docs/en/model-config).

The n8n scanner and judges are tool-free Basic LLM Chains with structured parsers. Their prompt sources are `n8n/prompts/`; `python n8n/tools/build_workflows.py` updates both exports and `--check` detects drift. The shared output adapter accepts parsed objects and JSON text, then the existing trust/coverage checks validate the result. [Repeatable acceptance cases](ACCEPTANCE.md) separate offline checks from each live client/provider.

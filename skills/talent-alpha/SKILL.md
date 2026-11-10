---
name: talent-alpha
description: >
  Run the Talent Alpha overnight signal scan: a broad-recall scanner plus an
  Advocate/Skeptic judge pair that turn WARN Act layoff notices and
  funding-distress news into a single ranked card of newly-reachable people
  for one open role, tiered S/A/B/C, each with a why-now, an outreach hook,
  and a concrete company-leverage edge. A local dedupe memory skips previously
  processed source IDs. Use when the user says "run talent
  alpha", "talent alpha", "scan for layoffs", "check for new signals", "run
  the overnight scan", "any new opportunities", wants a talent signal scan,
  or asks to see who just became reachable. For first-time setup, the
  talent-alpha-setup skill applies instead; it also runs automatically on a
  cold first call here if the user opts in.
---

# Talent Alpha: overnight signal scanner

You orchestrate the pull-scan-judge-render pipeline: `scanner` builds a
shortlist, `advocate` and `skeptic` argue it in parallel, and
`scripts/render.py` reconciles and renders the card deterministically. You
never write the card's HTML yourself, and neither judge ever sees the other's
verdict before both are in.

**This product touches people going through a hard moment.** The card names
companies and functions, never individuals. A human reads and decides before
any outreach happens; nothing here contacts a candidate automatically.

## 0. Profile gate (always first)

For a saved `talent-alpha-targets.json`, select the role the user names; if they
say "all my targets", process each role separately. Otherwise use the active
role in the profile and state it briefly. Only ask which role when the request
is ambiguous. Activate each selected role before scanning:

```text
<python> ${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/scripts/targets.py --targets talent-alpha-targets.json --out-dir . --role <id> --profile onepromptman-profile.md
```

Resolve Python as in step 2.2. Each role has its own card, run directory and
state_file; never combine verdicts or suppress a role's events using another
role's memory. Preserve the previously active role after an all-targets run.
Older single-role profiles continue to work without a targets registry.

Look for `onepromptman-profile.md` in the working folder, the profile shared
by every OnePromptMan kit. Never hard-block on what it does not find.

- **Missing entirely.** Tell the user this is their first run of any
  OnePromptMan kit here, and offer two paths: full setup
  (`talent-alpha-setup`) or the quick path, proceed now with a one-question
  minimum. On the quick path the company identity is still a hard gate: ASK
  which company and open role (title, functions, location) this scan is for,
  plus its signal-source industries via AskUserQuestion. Never auto-select.
  Save those answers in a minimal profile per `${CLAUDE_PLUGIN_ROOT}/PROFILE-SPEC.md`;
  leave unstated leverage empty. A scan needs a role to score against.
- **Present, but no `## Kit: talent-alpha` block.** Another kit's setup ran
  here first. Say so in one line ("I have a profile for [company] but not
  Talent Alpha's own settings yet") and offer the same two paths: full setup
  to fill just this kit's block, or the quick path with the one-question
  minimum above.
- **Present and complete.** Read it and state in one line which company and
  role this run targets, so a multi-role user can redirect ("Running against
  the [company] / [role title] profile").

If `## Kit: talent-alpha` carries a `setup_incomplete` marker, resume setup
from the first missing section instead of running a scan against a partial
block. Read the kit block's `state_file` value for step 2.2 below (default
`talent-alpha-state.json` if the field is absent, e.g. on a quick-path run
with no profile at all).

Four variables recur below: `COMPANY_PROFILE` is the kit block's `leverage`
paragraph verbatim; `COMPANY_FACTS` is `{"size": ..., "stage": ...}` from the
kit block's optional `company_size` and `company_stage` (provenance tags
dropped, an empty string when absent); `OPEN_ROLE` is the kit block's
`open_role` (or, on the quick path, whatever the one-question minimum above
collected) as JSON (`title`, `functions`, `location`); `RUN_DATE` is today's
date in UTC as YYYY-MM-DD, unless the user or an evaluation fixes the run date.
Every event age on the card counts whole days to `RUN_DATE`.

`SOURCING_CRITERIA` is the kit's `sourcing_criteria` JSON (empty object on older
profiles). Read `references/03_TARGETING_PLAYBOOK.md` and include these criteria
in every scanner, judge and critic briefing. They govern seniority, skills,
eligible geography, work arrangement, event types, triggers and exclusions.

## 1. Plan

Create `talent-alpha-runs/<YYYY-MM-DD>/` if it does not exist (never overwrite
a prior run folder; append a `-2`, `-3` suffix on a same-day re-run). Before
pulling anything, state: "Using your saved role and priorities for this scan."
Apply context already supplied with the request; do not pause a daily run for
an optional question. File additional pasted text verbatim to
`<run folder>/inputs/braindump-<YYYY-MM-DD>.md`; this is optional and
skippable at zero cost.

Use the saved `max_shown` and `include_funding_distress` unless overridden for
this run (defaults 10 and true for older profiles). A sharp judge disagreement
is held whatever the count. Do not ask for these settings again on each run.

## 2. Execute

### 2.1 Pull

Check that native web search is available before pulling; if missing, stop and
explain how to enable it or use n8n. Tool failure is not a quiet day. Use the
role's functions, confirmed sectors, eligible locations and priority triggers
in the search plan. Search adjacent domains when the saved plan calls for them.
Skip disabled event types and company exclusions. If funding is disabled, do
not perform that search. Do not expand a remote role beyond its stated geography.

Two categories, per `references/02_SOURCING_MATRIX.md`. In-session, BOTH run
via WebSearch (see that file for why WebFetch cannot substitute for an
authenticated WARN Firehose call): one search for recent WARN Act layoff
notices in the profile's signal-source industries and states, one for
funding-distress news in the same industries. State plainly to the user,
once, that this trades the n8n workflow's authoritative Filed-tier WARN
Firehose feed for a Reported-tier WebSearch equivalent, at zero paid-key
cost. Normalize every
result per `references/EVENT_PIPELINE_SCHEMA.md` §1 and write the merged
array to `<run folder>/raw_events.json`.
Keep each result's original title, snippet, date and URL. A funding company
extracted later by the scanner must occur in that title or snippet. Unknown
locations stay empty; never infer a city from the company's industry.

### 2.2 Dedupe (state file, read before, write after)

Resolve the interpreter once, before this first script call: try `python3
--version`, then `python --version`, then `py -3 --version`; use the first
one that reports 3.10 or newer and call it `<python>` for every script call
below. If none qualify, tell the user in one sentence that this kit needs
Python 3.10+ on PATH (python.org has it) and stop, rather than running a
script and surfacing a traceback.

```
<python> ${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/scripts/state.py dedupe \
  --events <run folder>/raw_events.json \
  --state <state_file, default talent-alpha-state.json> \
  --as-of <RUN_DATE> \
  --out <run folder>/new_events.json
```

Dedupe drops ids already in the state file and every event older than its
source window on `RUN_DATE` (3 days for WARN layoffs and shutdowns, 7 for
funding distress); it prints both counts and names each out-of-window event.
A web search often returns older articles, so a few drops are normal.

The state file lives at the working-folder root, not the run folder, so it
survives across runs; full design in `scripts/state.py`'s own docstring. Its
path is recorded in the profile's `## Kit: talent-alpha` block as
`state_file` (default `talent-alpha-state.json`) so a future relocation is a
one-line profile edit, not a hunt through this skill. If `new_events.json` is
empty, stop here and distinguish what happened: no feed results, only previously
seen IDs, only stale events, or no events matching the selected types/exclusions.
Use the actual counts, not "nothing new" for a failed search. Do not spawn any
agent on an empty batch.

### 2.3 Scanner (sequential, before the judges)

Spawn `talent-alpha:scanner` with: the run folder, `<run folder>/new_events.json`,
`COMPANY_PROFILE`, `OPEN_ROLE`. It writes `<run folder>/shortlist.json`.

**NEED_INPUT.** If `scanner` halts on `cheapest_fix: ask_user`, batch its
missing items into one AskUserQuestion pass, then resume the scanner with
the answers. Do not start the join or judges until shortlist.json exists
and the scanner has completed; downstream agents cannot review a missing artifact.

### 2.4 Trust-boundary join (deterministic, never an agent)

```
<python> ${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/scripts/render.py join \
  --raw <run folder>/new_events.json --shortlist <run folder>/shortlist.json \
  --as-of <RUN_DATE> --out <run folder>/trusted_candidates.json
```

Drops any id the scanner invented. Read the printed drop count; if it is
more than a couple, that is worth a line in your completion report, not
silence. If the trusted batch is empty, report that no new events were relevant
to this role and stop without spawning judges or recording state.

### 2.5 Judges (BOTH PARALLEL, one message)

Spawn `talent-alpha:advocate` and `talent-alpha:skeptic` together, in the same message, each with:
the run folder, `<run folder>/trusted_candidates.json`, `COMPANY_PROFILE`,
`COMPANY_FACTS`, `OPEN_ROLE`, `RUN_DATE`. Neither gets the other's output. They write
`advocate_verdicts.json` and `skeptic_verdicts.json` respectively.

**NEED_INPUT.** If either judge halts on `cheapest_fix: ask_user`, do not
re-spawn anything yet. Batch every `ask_user` item from `advocate` and `skeptic` into ONE consolidated
AskUserQuestion pass, each item with its own `why_needed`. Put that to the
user once, then re-spawn only the agents that actually halted, with the
answers folded in, and resume the pipeline from wherever it stopped. Never a
question at a time, and never re-spawn an agent that already returned clean.

### 2.55 Critic (per verdict, before reconcile)

Spawn `talent-alpha:critic` twice, in one message: once on `advocate_verdicts.json`
(rubric: the six fit axes and tier scale, plus `agents/advocate.md`'s own
brief), once on `skeptic_verdicts.json` (same axes, `agents/skeptic.md`'s
brief), each with `trusted_candidates.json`, `COMPANY_PROFILE`, `COMPANY_FACTS`,
`OPEN_ROLE` and `RUN_DATE` as grounding. One REFUTE pass per verdict file, three
angles (grounding, honesty, contract, per `agents/critic.md`). Critic returns
`PASS` or `RETURNED` with findings; it holds no write tool and edits nothing.
`RETURNED` means any HIGH finding, any MED finding on a `why`, `hook` or `edge`
slot (those ship on the card verbatim), or three or more MED; LOW is advisory.

On `RETURNED`: first copy the verdict file to `<run folder>/laps/<judge>_verdicts.lap<N>.json`
(lap 0 is the judge's first file), so the pre-repair tiers stay on record. Then
route the findings to the owning judge (`advocate` or `skeptic`) as a patch
instruction: "Fix each finding by removing the ungrounded claim; do not
substitute an inference, and do not explain a score in why, hook or edge." The
finding text is the only added context; the judge re-emits its verdicts file.
Then re-spawn `talent-alpha:critic` on the patched file. At most two repair laps
per verdict file. If still `RETURNED` after two laps, stop the build and report
the remaining findings with the draft artifact paths. Do not render a reviewed
card or record those events as seen until the blocking findings are resolved.

The sharp-disagreement hold (2.6) compares the verdicts that passed the critic,
not the lap-0 drafts. That is deliberate: a tier the critic found ungrounded is
not a disagreement worth a human's review, and the lap files keep the earlier
tiers for anyone auditing the run. Name any tier a repair changed in the
completion report.

### 2.6 Build the checked card and record state (deterministic)

```
<python> ${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/scripts/render.py build \
  --raw <run folder>/new_events.json \
  --trusted <run folder>/trusted_candidates.json \
  --advocate <run folder>/advocate_verdicts.json \
  --skeptic <run folder>/skeptic_verdicts.json \
  --profile <working folder>/onepromptman-profile.md \
  --state <state_file, default talent-alpha-state.json> \
  --author "<Kit block's author, or 'Your name'>" \
  --company-name "<Organization's name>" \
  --role-title "<OPEN_ROLE.title>" --role-location "<OPEN_ROLE.location>" \
  --max-shown <N> --as-of <RUN_DATE> \
  --out <run folder>/content.json --html <run folder>/overnight_card.html
```

`build` requires a complete, unique verdict from both judges for every trusted
candidate. It runs accuracy checks, validates against the shipped content schema,
renders to temporary files, and verifies the HTML before publishing either output
and recording shown and held IDs. A failed check leaves the state and any previous
card untouched. Sharp S/C disagreement is held even in the first slot. It also
rejects a `why`, `hook` or `edge` that names a fit axis, and an advocate
`size_fit` or `stage_fit` other than M when `COMPANY_FACTS` lacks that fact.

Route a failure back to the producer with its diagnostic. Do not bypass a failed
build by calling the low-level render or state-record commands. Those commands
remain available for development and the frozen eval, not as a production shortcut.

## 3. Deliver

There is no email step in-session (the n8n workflow emails the card; this
plugin has no mail tool). Tell the user the card's path
(`<run folder>/overnight_card.html`, open it in a browser) and give a short
text summary inline: tier counts, the hero candidate's company and why-now,
and how many items were held for review and why.

## 4. Completion report

Candidates scanned, shown, and held with reasons; the trust-boundary join's
drop count if nonzero; the state file's new total and how many entries were
pruned; and one line reminding the user this is a drafts-for-review product,
not an auto-outreach tool.

## Non-negotiables

- Company facts come from the trusted event batch or the profile; never
  invented. The `edge` field traces to a specific profile detail or is empty.
- The Advocate and Skeptic run independently every time; never skip one to
  save a call, never let one see the other's verdict before both return.
- No em dashes anywhere, including in the rendered card.
- "TBD", "N/A", and generic filler are QA failures. `scripts/render.py verify`
  checks for exactly this; do not ship a card that fails it.
- State durability across a native SCHEDULED run (as opposed to this
  in-session, on-demand path) is UNVERIFIED. Say so if the user asks about
  scheduling; do not claim it works until it has actually been tested twice
  on different days.

## References

`references/00_SHARED_CORE.md` (agent contract, honesty vocabulary,
authoritative) · `references/02_SOURCING_MATRIX.md` (per-category retrieval,
provenance tiers, in-session tradeoffs) · `references/EVENT_PIPELINE_SCHEMA.md`
(every shared JSON shape, the state file schema) ·
`references/content-schemas/` (the one content schema this plugin renders,
plus a worked example) · `scripts/state.py` (dedupe / record / show) ·
`scripts/render.py` (join / reconcile / render / verify) ·
`references/templates/overnight_card.template.html` (renderer-owned).

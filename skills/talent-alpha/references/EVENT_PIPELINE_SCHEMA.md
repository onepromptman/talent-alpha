# EVENT PIPELINE SCHEMA: TALENT ALPHA

The shared artifact shapes that move between phases. Every phase reads and
writes exactly these shapes; nothing improvises a field name. All files below
live under the run folder unless stated otherwise.

## 0. Run folder

`talent-alpha-runs/<YYYY-MM-DD>/` (create if missing; never overwrite a prior
run's folder). Everything in this section lives inside it, except the state
file, which lives at the working-folder root because it must persist across
runs.

## 1. Raw normalized event (output of pull + normalize, input to dedupe)

```json
{
  "event_id": "warn-482913",
  "published_at": "2026-08-24T00:00:00Z",
  "title": "Northwind Robotics WARN layoff -- 140 affected",
  "snippet": "Austin, TX -- Hardware -- 140 employees affected",
  "source_name": "WARN Firehose",
  "source_url": "https://warnfirehose.com/records/482913",
  "company": "Northwind Robotics",
  "location": "Austin, TX",
  "event_type": "layoff",
  "employees_affected": 140
}
```

`event_type` is one of `layoff`, `shutdown`, `funding_distress`. A funding
category item may have empty `company`/`location` at this stage (news snippets
do not always name it structurally); the scanner extracts them.

Write raw events to `<run folder>/raw_events.json` as a flat array, WARN and
funding-distress items merged together.

## 2. Dedupe (scripts/state.py, reads before the run, writes after)

Filters `raw_events.json` down to events whose `event_id` is not already in the
state file (default `talent-alpha-state.json` at the working-folder root,
path configurable via the profile's `state_file`; full shape in §6). This step
runs BEFORE the scanner, so an already-seen layoff never costs a model call
twice.

## 3. Scanner batch and output

**Batch prompt** (built by the skill, one string):

```
RUN_TIMESTAMP: <ISO timestamp>
COMPANY_PROFILE: <profile.companyProfile>
OPEN_ROLE: <profile.openRole as JSON>
BEGIN_UNTRUSTED_ITEMS
<event_id> | <published_at> | <title> | <snippet> | <source_name>
...
END_UNTRUSTED_ITEMS
```

`profile.companyProfile` and `profile.openRole` here mean: the orchestrator's
in-memory run profile, built at Phase 0 from `onepromptman-profile.md`'s
`## Kit: talent-alpha` block (`leverage` and `open_role` respectively), not
literal field names in the file itself.

**Scanner output** (`<run folder>/shortlist.json`), matching `agents/scanner.md`'s
output contract:

```json
{
  "opportunities": [
    {
      "id": "warn-482913",
      "company": "Northwind Robotics",
      "event_type": "layoff",
      "functions": ["Manufacturing Engineer", "Process Engineer"],
      "location": "Austin, TX",
      "score": 82,
      "why": "Named layoff at a directly comparable hardware employer"
    }
  ]
}
```

Top 12 by score, sorted descending. `id` must copy the raw event's `event_id`
exactly (the trust-boundary join in `scripts/render.py join` drops any id not
present in `raw_events.json`).

## 4. In-session WebSearch queries (replace both n8n feeds; no paid key)

**Funding distress** (replaces the Perplexity node):

```
<target industries> companies (NOT general software/SaaS/consumer-tech/gaming)
facing layoffs tied to funding distress, a down round, missed earnings, or
restructuring, reported in the last 7 days. Exclude generic industry
roundups, trackers, or archive pages -- only single-company news stories.
```

**WARN Act layoffs** (replaces the WARN Firehose HTTP call; see
`02_SOURCING_MATRIX.md` for why WebFetch cannot substitute directly):

```
WARN Act notice OR layoff filing, <target industries>, <target states or
"United States">, filed in the last 3 days. Prefer the state labor
department's own notice or filing list over news coverage when both appear.
```

Substitute the profile's own target industries (from the `## Kit: talent-alpha`
block; if absent, ask rather than assuming a sector) and target states/location
from `OPEN_ROLE.location`. Run each once per scan; treat every result the same
as a normalized event per §1, with the provenance tier rule from
`02_SOURCING_MATRIX.md` (WARN results default to Reported unless the page IS
the government filing itself).

## 5. Judge batch and verdict output

**Batch prompt**, built from the trust-boundary-joined shortlist (each line
carries the scanner's own score and reasoning so the judges are not
re-deriving it from scratch):

```
COMPANY_PROFILE: <profile.companyProfile>
OPEN_ROLE: <profile.openRole as JSON>
BEGIN_UNTRUSTED_CANDIDATES
<id> | <company> | <event_type> | <functions,joined> | <location> | <published_at> | scanner_score=<n> | scanner_why=<text>
...
END_UNTRUSTED_CANDIDATES
```

**Verdict output**, identical shape for both `advocate` and `skeptic`
(`<run folder>/advocate_verdicts.json`, `<run folder>/skeptic_verdicts.json`):

```json
{
  "verdicts": [
    {
      "id": "warn-482913",
      "tier": "S",
      "openness": "H", "role_fit": "H", "product_fit": "M",
      "region_fit": "H", "size_fit": "H", "stage_fit": "H",
      "wildcard": {"fired": false, "axis_index": -1, "bridge": ""},
      "titles": ["Firmware Engineer", "Embedded Systems Engineer"],
      "why": "Named layoff at a directly comparable hardware company, hours old.",
      "hook": "Saw the news about the restructuring, wanted to reach out directly.",
      "edge": "Comp band matches metro market; equity refresh available for senior hires."
    }
  ]
}
```

Axis order is fixed: openness, role_fit, product_fit, region_fit, size_fit,
stage_fit (0 through 5, used by `wildcard.axis_index`). Tier is one of S, A, B,
C. `edge` may be an empty string; that is a legitimate, common answer, never a
gap to fill with filler.

## 6. State file (working-folder root, persists across runs)

`talent-alpha-state.json`:

```json
{
  "schema_version": 1,
  "seen_events": {
    "warn-482913": {"first_seen_at": "2026-08-24T06:00:00Z", "company": "Northwind Robotics"},
    "fund-a1b2c3": {"first_seen_at": "2026-08-23T06:00:00Z", "company": ""}
  },
  "last_run_at": "2026-08-24T06:00:12Z"
}
```

`company` on each entry is a debugging aid only (lets a human skim the file
without cross-referencing); it is never read back into the pipeline. Full
read/write contract, including the pruning rule, lives in `scripts/state.py`'s
own docstring and in the orchestrator's Phase 0.

## 7. Reconciled candidate (output of `scripts/render.py reconcile`, the one
## content schema this plugin ships)

See `references/content-schemas/card.content-schema.json` and its paired
`card.example-content.json`. This is the only content schema in this plugin: a
reconciled candidate ready for the renderer, blending both judges' verdicts
plus the freshness label.

## 8. Freshness

No section here carries a hard SLA cutoff the way a market-research pack
might: the whole pipeline runs on a rolling window (3 days for WARN, 7 for
funding-distress) set at the fetch step, and `event_age_label` is a display
concern computed once, at reconcile time, from `published_at`.

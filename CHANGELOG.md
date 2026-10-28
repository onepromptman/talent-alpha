# Changelog

All notable changes to Talent Alpha. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are semantic.

---

## [Unreleased]

### Changed

- **The n8n dedupe Data Table is now `talent_alpha_events_seen`** (it carried an
  internal prototype name). An existing install must create the table under the new
  name, or rename it, before the next scheduled run.
- The demo workflow's pinned fictional company is renamed, and no example names an
  industry the kit does not target.
- Licensed MIT, Copyright (c) 2026 OnePromptMan, one licence for the whole marketplace;
  install lines point at the `talent-alpha` marketplace.

### Fixed

- **Every slot on the emailed card is escaped.** The n8n Render Scanner Report node
  already escaped the hero and card text, but the held-for-review line carried feed
  company names unescaped, the role line carried Config text unescaped, and the
  hex attributes (`data-bands`, `data-tier`, `data-wc`) carried judge output
  unescaped; `esc()` now also escapes quotes and every one of those goes through
  it. `scripts/render.py` escapes the same attributes with `esc_attr()`, and a
  source URL becomes a link only when it is http(s). `tests/test_escaping.py`
  plants markup in every field and runs both renderers.
- **The n8n setup page matches the workflow.** It documents `targetSectors` in
  Config, says freshness is a tiebreak (not a weight), and has an upgrade section
  for installs that still use the `r04_events_seen` Data Table.
- **Install docs**: Option B no longer points at a release that does not exist (it
  now says to add the plugin folder by hand), and the uninstall line removes the
  `talent-alpha` marketplace, not one called `onepromptman`.
- **The shipped sample now reproduces from its own example content.** Rendering
  `card.example-content.json` through the current template produced a card the
  shipped `samples/01_Overnight_Card_SAMPLE.html` did not match: the sample was
  missing the source-provenance block (the `.srcline` CSS, the `hero-source`
  slot, and the per-card `Source: <link>` line). The renderer was right and the
  sample was stale -- `card.content-schema.json` REQUIRES `source_name` and
  `source_url` on every candidate, so a card that does not show its source is
  incomplete, not minimal. Sample regenerated.

  It had never been in sync: the template and the sample landed in the same
  initial commit and neither changed afterwards. Nothing caught it because
  nothing compared them.

### Added

- **A golden byte-for-byte test**, mirroring talent-one's
  `test_example_content_reproduces_shipped_sample_byte_for_byte`: the shipped
  sample must reproduce exactly from `card.example-content.json` (line endings
  folded for Windows checkouts). Any renderer or template change that alters
  output now fails the suite and must ship with a regenerated sample; the
  failure message carries the regeneration command. A companion test asserts the
  sample carries source provenance at all. 28 tests, was 26.

### Added (docs)

- **`CONNECTORS.md`**, the standalone connector surface every other module in
  this repo already had. Carries the three-tier table (Filed / Reported /
  Company-stated) mapped to the source that actually backs each, the n8n
  credential table, and the fact that the eval path makes no web calls at all.
  It also names the one-way tradeoff plainly: the in-session WARN category
  degrades from Filed to Reported, because no in-session tool attaches a custom
  auth header and `WebFetch` takes a URL and a prompt only, so the authenticated
  WARN Firehose call the n8n path makes is not available. That rule lived only
  in `references/02_SOURCING_MATRIX.md` and the setup skill; the README never
  said it.
- **`docs/INSTALL.md`** for the plugin path. `docs/` previously held only
  `setup.md`, which is n8n-only, so the plugin had no install page of its own.

### Fixed (docs)

- README version badge said 1.1.0 against `MODULE.yaml`/CHANGELOG 1.3.0.
- README's repository layout listed three agents; there are four -- `critic`
  was wired in 1.3.0 and never added to that line. "Two small Python scripts"
  is three (`render.py`, `state.py`, `validate_card.py`).

### Documented

- **The source-provenance block itself**, which shipped in the code but appeared
  in no changelog entry. Every card names where its claim came from: the tier
  vocabulary (`Filed` / `Reported` / `Company-stated`) is only meaningful if the
  card shows the source behind it.

## [1.3.0]

### Added

- **`critic` wired into the pipeline.** `scanner`, `advocate`, and `skeptic`
  now all declare `verifier: critic` in `MODULE.yaml`, and the orchestrator
  skill actually spawns it: one REFUTE pass per verdict file
  (`advocate_verdicts.json`, `skeptic_verdicts.json`) after the judge step
  and before reconcile, three angles (grounding, honesty, contract), routing
  a `RETURNED` finding back to the owning judge as a patch, at most two
  repair laps per file. Previously the fence was declared but never invoked.
- A consolidated `NEED_INPUT` batching path for `scanner`/`advocate`/`skeptic`
  halts: every `ask_user` item across a run's halted agents reaches the user
  in one AskUserQuestion pass, not one question at a time.
- A minimal `tests/` (pytest) suite exercising `scripts/render.py` against
  the shipped `card.example-content.json` and `scripts/state.py`'s
  dedupe-then-record round trip.

### Changed

- **Model tier restamp.** Every executor (`scanner`, `advocate`, `skeptic`)
  runs on the Sonnet tier; `critic` judges on the Opus tier. `scanner` was
  previously documented (README diagram only; the agent file itself already
  ran Sonnet) as a cheaper Haiku pass; the doc now matches the code and notes
  that the standalone n8n workflow is a separate deployment that may still
  route its own scanner step to a cheaper model.

## [1.0.0] - 2026-08-26

First release of the Cowork / Claude Code plugin, extracted from the
standalone n8n workflow of the same name.

### Added

- `talent-alpha` orchestrator skill: pull, dedupe, scan, judge, reconcile,
  render, deliver, record state, one run at a time, on demand.
- `talent-alpha-setup` guided setup: one conversation writes both a
  ready-to-paste n8n `Config` node value and `onepromptman-profile.md`, the
  profile file shared across every kit in this marketplace. Shared facts
  (organization, what the org hires for, brand) are filled once and read by
  any other installed kit; this kit's own settings (open role, leverage
  paragraph, signal sources, run tuning, the dedupe state file's path) live
  under that file's `## Kit: talent-alpha` block, which this kit alone owns.
- Three agents (`scanner` haiku, `advocate` sonnet, `skeptic` sonnet)
  matching the n8n workflow's Signal Scanner Agent, Judge Advocate, and
  Judge Skeptic nodes role for role, including the fixed axis order and
  tier scale.
- `scripts/state.py`: a local JSON dedupe memory (`talent-alpha-state.json`)
  standing in for the n8n version's Data Table (`talent_alpha_events_seen`), with
  read-then-write-every-run discipline and 30-day pruning. Durability across
  a native SCHEDULED run is unverified; see the README.
- `scripts/render.py`: trust-boundary join, tier-blend reconciliation, and a
  deterministic HTML renderer with a `--strict` fail-loud mode and a
  `verify` pass that scans for leftover placeholders, em dashes, and banned
  filler strings.
- The bundled n8n workflow (`n8n/talent-alpha.workflow.json`, plus a
  pinned-data demo variant) and its reference prompt copies, for anyone who
  wants the real scheduled path. These are edited from the original repo,
  not byte-identical; see "Vendored n8n workflow + prompts" below for
  exactly what changed and why.

### Vendored n8n workflow + prompts (edited during extraction)

Both `n8n/talent-alpha.workflow.json` and its `-demo` variant were diffed
byte-for-byte against the original repo while writing this changelog.
Connections, node count, and workflow settings are untouched in both files,
and both still parse as valid n8n JSON, but these text-only edits were made
during extraction, identically in both files:

- **House style (no em dashes):** the workflow's own display name, the body
  copy on all four sticky notes (one of which also had its own name field
  changed, to "Sticky Note: Start here"), and the "The hook: lead with this"
  label inside the Render Scanner Report node's embedded jsCode template all
  had their em dashes swapped for colons or commas, matching this plugin's
  "no em dashes anywhere" rule (see the `talent-alpha` skill's
  Non-negotiables).
- **Card label fix, made in the workflow itself, not only in Cowork:** the
  same relabel described below under "Card label fix" (`C · ignored` to
  `Held for review`) was made directly in the Render Scanner Report node's
  jsCode, so the bundled n8n workflow now renders the corrected label too,
  not just this plugin's `render.py` template.
- **Tier legend copy correction:** the same node's tier-blend legend
  sentence was rewritten from "weighted from all six axes then decayed by
  news age" to "blended from both judges' six-axis reads. Fresher signals
  sort first when tiers tie.", to match how reconciliation actually works
  (freshness is a sort tiebreak, never a score decay; see "How it works" in
  the README).
- **Cross-references:** each of the three `n8n/prompts/*.md` files gained
  one added sentence pointing at the matching Cowork `agents/*.md` file, so
  a reader following either path can find its counterpart.

None of this touches the workflow's wiring, credentials, or node count. If
you diff this file against a previously-imported copy of the real
production workflow, expect exactly these differences and nothing else.

### Changed from the n8n template during extraction

- **Funding-distress feed:** the n8n workflow's Perplexity Search node is
  replaced in-session by a plain `WebSearch` call against the same query
  shape. No paid key required for this category, in either direction; this
  is a real improvement, not a degraded substitute.
- **WARN feed, in-session only:** since no in-session tool can attach a
  custom auth header to an outbound request, the authenticated WARN Firehose
  API call is replaced by `WebSearch` for this category too. This is a real
  tradeoff: in-session WARN events default to Reported-tier provenance
  instead of the n8n path's Filed-tier confidence. Stated plainly in setup
  and in the README, not hidden.
- **Card label fix:** the rendered card's static "C · ignored" row actually
  displays the held-for-review summary (judge disagreement or overflow),
  not a summary of C-tier items specifically, in every version of the n8n
  template inspected during extraction. Relabeled to "Held for review" so
  the label matches what it shows. C-tier candidates still render as normal
  cards with a gray tier badge, matching the legend's "kept visible so you
  can overrule" intent. This fix was applied both here (`render.py`'s
  template) and directly inside the bundled n8n workflow's own render node;
  see "Vendored n8n workflow + prompts" above.
- **Zero-result runs:** the n8n render code left the hero block's slots
  showing their raw "-" placeholder when no candidates cleared the bar this
  run. The renderer here removes the hero block entirely in that case
  instead, matching the "honest empty state is an omitted block, never
  placeholder text" rule applied everywhere else in this plugin.
- **Tier-blend rounding:** ported to match JavaScript's `Math.round` (half
  rounds up) rather than Python's default (half rounds to even), so a
  B-plus-C blend lands on B here exactly as it does in the n8n workflow.

### Process

Built by reading the source n8n workflow's actual node code (not just its
README) and porting the trust-boundary join, tier-blend, and render logic
line for line into `scripts/render.py`, then testing all four subcommands
(`join`, `reconcile`, `render`, `verify`) against synthetic fixtures,
including a deliberately hallucinated id (correctly dropped) and a
deliberately incomplete content file under `--strict` (correctly refused,
nothing written).

---
name: talent-alpha-setup
description: >
  Guided first-run setup for Talent Alpha. Use when the user says "set up
  talent alpha", "talent alpha setup", "configure talent alpha", "personalize
  talent alpha", or when the talent-alpha skill finds no `## Kit: talent-alpha`
  block in onepromptman-profile.md and the user opts into setup. Reads the
  shared onepromptman-profile.md first, so a user who already set up another
  OnePromptMan kit is not asked their company again, then captures this kit's
  own leverage paragraph, open role, signal sources, and run tuning in a short
  guided conversation. Writes both the shared profile and a ready-to-paste n8n
  Config node value, so the same setup serves either surface.
---

# Talent Alpha: guided setup

Reads and writes `onepromptman-profile.md`, the one profile file every
OnePromptMan kit shares (see the marketplace's `PROFILE-SPEC.md`). This kit
owns the `## Kit: talent-alpha` block: open role, leverage paragraph, signal
sources, run tuning, byline, and the dedupe state file's path. It also fills
the shared `## Organization`, `## Hiring`, and `## Brand` sections when they
are missing, so a kit set up later does not ask the same questions again.

Also writes `talent-alpha-n8n-config.json` (a ready-to-paste value for the
n8n workflow's `Config` node) from the same answers.

No YAML or file editing for the user. Every step but company confirmation has
a safe default and is skippable. If `## Kit: talent-alpha` carries a
`setup_incomplete: <section>` marker, resume from that section instead of
starting over.

## 0. Read first

Look for `onepromptman-profile.md` in the working folder.

- **Missing entirely.** This is a first run for any OnePromptMan kit here.
  Go to Welcome as a cold start; nothing to summarize yet.
- **Present, no `## Kit: talent-alpha` block.** Another kit already set this
  profile up. Tell the user in one line what you already know, e.g. "I
  already have Northwind Robotics on file, hiring for Software, Mechanical,
  and GTM. I still need Talent Alpha's own settings: the role you're filling
  and what to scan for." Then go straight to step 2's confirmation (not the
  full ask) and step 4.
- **Present with a filled `## Kit: talent-alpha` block.** Summarize both
  halves in one line, e.g. "Northwind Robotics, hiring Senior Backend
  Engineer, scanning healthcare and logistics for signals," and ask whether
  anything needs to change, or whether to just confirm and exit. If the
  top-level `researched:` date is more than 90 days old, offer, do not force,
  a refresh of the organization facts.

## 1. Welcome

One short message: Talent Alpha scans WARN layoffs and funding-distress news
overnight (or on demand) and produces one ranked card of newly-reachable
people for a role you're hiring. Setup takes about 5 minutes. Two paths: full
setup now, or skip and run one scan immediately with a quick in-line ask
(route to `talent-alpha`; setup can happen later).

## 2. Organization (HARD GATE: confirm, never assume)

**If `## Organization` already has a name on file, ask ONE confirmation
question with AskUserQuestion: is this run still for that company?** Chat
history, memory, and prior sessions are never a substitute for this
confirmation: a wrong guess poisons every downstream card. A "yes" is the
whole gate, nothing to re-interview. If the answer is a different company,
treat this as a fresh Organization; do not overwrite the one on file without
showing the conflict first (see step 6).

**If `## Organization` is missing, or the user just said "different
company,"** ask for the company name and, optionally, a website (for a light
research pass on industry and locations, used only to seed the signal-source
default in step 4, never to write the leverage paragraph itself: no public
search can tell you a company's equity band or relocation policy). Write
`name`, `domain`, `descriptor`, and `locations`, each tagged with its
provenance (`stated by user` or `web, <domain>, confirmed by user`) per
`PROFILE-SPEC.md`.

## 3. Hiring and Brand (shared; ask only what's missing)

If `## Hiring` is missing, ask one short, skippable pass: what functions the
company hires for generally, and roughly what levels and volume ("not sure"
is a fine answer to any of these). For `## Brand`, guard each FIELD, not the
section: ask how written copy should feel (default: plain, concrete, no hype)
only if no `voice` line is on file, and whether a "prepared by" line should
appear on generated documents at all (default: yes) only if no `credit` line
is. A kit that writes `## Brand` with a voice and no credit would otherwise
leave this one silent about a field it later reads -- §6's byline depends on
`credit`. Combine whichever halves are still missing into one skippable
question. Both sections are shared with every other OnePromptMan kit; fill
them once here and no later kit's setup should ask again. Skip this step
entirely when every field in both sections is already on file.

## 4. Leverage (open text, never chips)

**This is the card's entire credibility. Vague input produces vague, useless
"edge" lines on every card this profile ever generates.** Invite it in ONE
plain message, never a chip question: "Describe your company in a paragraph,
and be concrete about what you can offer someone who moves: equity band, comp
stance relative to market, relocation support, benefits, ownership scope,
anything else real. One paragraph is enough." Accept whatever arrives
verbatim as `leverage`; do not paraphrase or tidy it. If the user stalls,
show the worked example from
`${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/references/content-schemas/card.example-content.json`'s
`run.company_name` context as a length/tone guide, not as text to copy. This
belongs to `## Kit: talent-alpha` only, never the shared Organization
section: it is this card's specific pitch, not a general company fact.

## 5. Open role and signal sources

One AskUserQuestion pass: role title, functions (adjacent titles that still
count as a match; seed chips from `## Hiring`'s functions if that section
exists), and location. A second question, multiSelect, for signal sources:
which industries to scan for layoff/funding-distress signals (seed chips from
`## Organization`'s descriptor if step 2 researched one). Derive the chips
from what the organization actually does rather than a fixed list, and always
offer an other-with-free-text option.
This scopes the WebSearch queries in
`${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/references/EVENT_PIPELINE_SCHEMA.md`
§4; it does not limit what a later manual scan can be pointed at. Both
belong to `## Kit: talent-alpha`, not `## Hiring`: the open role is one
active req and signal sources describe companies to watch, neither is the
same thing as what the org generally hires for.

## 6. Tuning and the WebFetch/WebSearch tradeoff (state it plainly)

Tell the user once, plainly: in-session, both feeds run via WebSearch, no
paid key needed, but the WARN category loses the authoritative Filed-tier
confidence the standalone n8n workflow gets from a real WARN Firehose API
key (see
`${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/references/02_SOURCING_MATRIX.md`).
AskUserQuestion for min/max shown per card (default 4/10), whether to include
funding-distress alongside WARN (default: both), and the byline to show on
the card if `## Brand`'s credit line is on (default: "Your name").

## 7. Write the profile and the n8n config

Write `onepromptman-profile.md`:

- Fill `## Organization`, `## Hiring`, `## Brand` only where a field was
  genuinely absent. **Never silently overwrite a shared field already on
  file with a different value**: show the conflict and let the user pick
  which one stands.
- Write (or replace, on a re-run of this kit's own setup) `## Kit:
  talent-alpha` in full:
  - `open_role`: `title`, `functions`, `location`
  - `leverage`: the paragraph from step 4, verbatim, tagged
    `(stated by user)`
  - `signal_sources`: the industries from step 5
  - `min_shown` / `max_shown` / `include_funding_distress`: from step 6
  - `author`: the byline from step 6 (or "Your name")
  - `state_file`: `talent-alpha-state.json` (the dedupe memory's path;
    record it here so a future change of location is a one-line edit, not a
    hunt through the skill for a hardcoded name)
- While a run is only partly answered, write `setup_incomplete: <section>`
  as the first line under `## Kit: talent-alpha`; clear it on completion.
- Stamp or refresh the top-level `researched:` date whenever step 2 actually
  ran a research pass.

Write `talent-alpha-n8n-config.json`: the exact
`{"companyProfile": ..., "openRole": {"id","title","functions","location"}}`
shape the workflow's `Config` node (`mode: raw`) expects. `companyProfile` is
the kit's `leverage` paragraph verbatim; `openRole` is the kit's `open_role`.
Tell the user, once, that pasting this file's contents into the `Config`
node's Value field (Execute Mode: raw) is all the n8n workflow needs beyond
credentials, if they ever want a real scheduled nightly run
(`${CLAUDE_PLUGIN_ROOT}/docs/setup.md` has the rest). Close with: "Run talent
alpha whenever you want a scan; nothing runs on a schedule from this
conversation."

---
name: talent-alpha-setup
description: >
  Explain and set up Talent Alpha's daily recruiting signal scan. Use for first
  setup, adding or changing target roles, locations or sourcing priorities, and
  exporting the same confirmed search plan to n8n. Collects target roles, teaches
  which fresh events qualify, proposes role-specific triggers, and saves a shared
  profile plus a validated n8n Config for each role. Does not scan or schedule
  until the user asks.
---

# Talent Alpha: guided setup

Read `${CLAUDE_PLUGIN_ROOT}/PROFILE-SPEC.md` and
`${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/references/03_TARGETING_PLAYBOOK.md`.
Use the playbook to explain the product and propose relevant defaults. The user
should not have to design a sourcing strategy or edit JSON. Ask in short stages;
accept a pasted job description and extract a draft for confirmation. Use
AskUserQuestion if available, otherwise ordinary conversation. Optional unknowns
stay empty. Existing shared profile fields and other kits stay intact.

## 0. Read first

Look for `onepromptman-profile.md` and `talent-alpha-targets.json` in the user's
working folder. Summarize any existing company and targets without reading them
aloud in full. If setup is partial (`setup_incomplete: <section>` under this
kit's heading), resume at that section. For a completed profile, offer to update
targets or finish; do not repeat the interview. Keep the same working folder so
the saved roles and seen-event memory persist.

## 1. Welcome and capability check

Check for this session's WebSearch tool (or its documented native web-search
equivalent). Without it, say plainly: setup can still save a profile, but a live
scan needs web search in this client or the n8n route. Never substitute WebFetch,
a connector, made-up news or an empty result for a missing search tool.

Give the playbook's short explanation before collecting details. Say that this
build covers WARN layoffs/closures and funding-distress news; it produces
company and function leads, not a list of named people proven available.
S/A means investigate today, B means watch or verify, C means poor fit.
Sources and uncertainties accompany the recommendation, and nothing contacts
candidates. Setup takes about five minutes for one role. Offer full setup or a
quick scan with the minimum company, role and location questions.

## 2. Confirm the organization

Ask whether the company already on file is still the hiring organization; a yes
is sufficient. Never silently select it from chat history. On a first setup,
ask the company name and optional website. For a different organization, explain
the conflict and use a separate working folder unless the user explicitly wants
to replace the shared company. Do not leave old roles attached to a new company.

Fill missing `## Organization` name, domain, descriptor and locations only with
stated facts or optional web research confirmed by the user. Tag provenance.
Do not research compensation or relocation promises into the profile. If web
research happens, stamp `researched:` with its date.

## 3. Ask which roles they want to target

Ask: "Which roles or role families do you want to source for, and where can you
hire them? A job description works too." Start with their highest-priority role;
offer to save others in the same pass. For each, collect or confirm:

- Title and adjacent functions, seniority and essential skills.
- Location and on-site, hybrid or remote terms. For remote, eligible countries,
  regions or time zones; for on-site, commute area and whether relocation exists.
- Any company exclusions or other explicit sourcing constraints.

Propose adjacent titles from the role, not a generic chip list. Ask only for
missing essentials. Seniority, skills and optional constraints may stay unknown;
role title/functions and a stated location scope are required. Do not interpret
an empty location as worldwide. Assign stable role IDs such as `ENG-01` and
`SALES-01`. Preserve IDs when editing existing targets.

## 4. Explain and propose the daily search plan

For each role, use the playbook to propose transferable source industries,
priority triggers and enabled event types. Explain why each would surface
relevant work. Ask the recruiter to accept or adjust the proposal, rather than
asking them to invent the feed taxonomy. Confirm at least one source industry.

Show one hypothetical fit and one non-fit for their role. For example, a local
plant closure could justify researching process engineers; a funding announcement
without evidence of workforce impact does not. Keep hypotheses distinct from
news found during an actual run. Do not promise acquisition, executive-departure
or expansion feeds that this build does not have.

Explain the three-day WARN window and seven-day funding-news window. In-session,
WARN searches are Reported, not the Filed confidence of the authenticated n8n
feed. Geography and work arrangement are assessed from evidence, not inferred
from a company's headquarters. An unclear affected function becomes a research
question, not a claim that the source named it.

## 5. Capture the offer and shared preferences

Invite one open-text paragraph: "What can your company actually offer someone
who moves: compensation stance, equity, ownership, remote terms or relocation?
Only include promises you can stand behind; you can skip this."
Save the paragraph verbatim as `companyProfile` and the kit's `leverage`, with
`(stated by user)` in Markdown only. Never copy leverage from a sample. Do not
pressure the recruiter to supply confidential pay details.

Ask optional company size and stage; empty means neutral fit. Fill missing
shared `## Hiring` fields only with their general hiring information, and ask
missing `## Brand` voice/credit fields once (plain voice; credit on by default).
Ask the most cards to show (default 10, 1-12), whether funding-distress is enabled
(default yes), and a byline only if credit is on. Respect skipped fields.

## 6. Confirm, save and validate

Show one compact plan per role: role/skills, geography, industries, priority
triggers, event types, exclusions and unknowns. Ask for one confirmation of the
plan and which role to run first. Preserve shared fields; show any conflict
instead of overwriting it. During incomplete setup mark this kit's block with
`setup_incomplete: <section>`, and never replace completed targets with partial
answers.

Write `talent-alpha-targets.json` as `{"targets": [Config, ...]}` using
`${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/references/content-schemas/n8n-config.schema.json`.
Each Config contains `companyName`, `companyProfile`, `companyFacts` (size/stage,
empty if unknown), `openRole` (id/title/functions/location), `targetSectors` (the
confirmed industries joined by commas), `sourcingCriteria` (the fields in the
playbook), `maxShown`, `includeFundingDistress`, and `author`. Use an empty author
when shared credit is off. Unknown optional criteria are empty strings/arrays;
omit eventTypes for all supported types or supply a nonempty enabled subset.

For new roles, set `stateNamespace` to the stable role ID. When upgrading a
single-role install, use `stateNamespace: ""` for its existing role to preserve
`talent-alpha-state.json` and legacy n8n IDs. Other roles need unique namespaces.
Never change an existing namespace casually: it changes the dedupe memory.
If the original profile has a custom `state_file`, save that exact path as
`stateFile` on its target so switching roles preserves that memory too.

Resolve an available Python 3.10+ interpreter in the session execution environment
(`python3`, `python`, or `py -3`). If none exists, explain the missing dependency
and stop before claiming completion. Run:

```text
<python> ${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/scripts/targets.py --targets talent-alpha-targets.json --out-dir . --role <selected-id> --profile onepromptman-profile.md
<python> ${CLAUDE_PLUGIN_ROOT}/skills/talent-alpha/scripts/render.py check-config --config talent-alpha-n8n-config.json
```

`targets.py` validates every role before writing, exports one n8n config per role,
and activates the selected role by replacing only this kit's block. Shared
Organization/Brand/Hiring and other kits are preserved. It writes role-specific
state paths and clears setup_incomplete only after successful validation. Fix
reported setup errors; do not call an invalid export a finished setup.

## 7. First run and optional n8n handoff

Explain: "Run talent alpha for <role>" uses that saved plan; "run all my targets"
produces a separate card per role. Offer a first scan. Do not scan unless the
user asks or accepts; do not re-interview them on routine daily runs.

Offer n8n once. If wanted, walk `${CLAUDE_PLUGIN_ROOT}/docs/setup.md` step by
step, waiting after each action. Start with the demo: import the demo workflow,
attach an Anthropic credential and run manually. Pinned fictional samples should
reach Render Scanner Report; no email or Data Table is used. Then use a separate
live workflow, attach its source and Gmail credentials, select its Data Table,
paste the selected role's exported Config and set recipients. A live run may
legitimately find no eligible events; do not promise a full card. Verify delivery
and a repeat run's dedupe before scheduling. Use one workflow per saved role.

Keys go into n8n, never into this conversation or a hand-edited file. From this
conversation never create a credential, import, activate or schedule anything
in n8n; the user does those actions. Close with where the profile and configs
were saved, the active role, and: "Nothing runs on a schedule from this
conversation."

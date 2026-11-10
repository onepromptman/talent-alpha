# Talent Alpha profile

The plugin reads `onepromptman-profile.md` from the working folder. This file
is local runtime data, not something to commit. Setup preserves existing
sections and owns only `## Kit: talent-alpha`.

Use these headings and field names. The following is a fictional example:

```text
# Profile

## Organization
name: Example Co (stated by user)
domain: example.com (stated by user)
descriptor: builds industrial sensors (stated by user)
locations: Denver, CO (stated by user)

## Hiring
functions: Test Engineering, Manufacturing Engineering

## Brand
voice: plain, concrete
credit: on

## Kit: talent-alpha
open_role:
  title: Test Engineer
  functions: [Test Engineer, Reliability Engineer]
  location: Denver, CO
leverage: We offer relocation support and ownership of the test lab. (stated by user)
company_size: about 120 employees (stated by user)
company_stage: Series B, venture-backed (stated by user)
signal_sources: [industrial sensors, robotics]
max_shown: 10
include_funding_distress: true
author: Your name
state_file: talent-alpha-state.json
```

Company, role title/functions and signal industries are needed for a useful
scan. Leave unknown facts empty; never fill leverage from an example.
Keep `leverage` on one line beneath this kit's heading. Its final
`(stated by user)` tag records provenance and is not sent as pitch text.
Other kits' leverage paragraphs must not be used for this card.

`company_size` and `company_stage` are optional, one line each. They are the
only grounds for the card's `size_fit` and `stage_fit` axes: when one is empty
or missing, that axis is scored M, the stated neutral value, and `render.py
build` rejects any other advocate score for it. Nothing infers a size or
stage from pay, industry or tone.

The target exporter appends `(stated by user)` to nonempty size/stage values in
the Markdown profile. Empty facts stay empty, and exported n8n `companyFacts`
values contain no added provenance suffix.

For a partial setup, put `setup_incomplete: <first missing section>` directly
under the kit heading. Remove it only after the required inputs are supplied.
The state path is relative to the working folder unless absolute. Reuse the
same working folder and state path across runs.

`max_shown` caps the cards shown; sharp judge disagreement is held whatever the
count. Source-ID dedupe does not merge different articles about the
same real-world layoff. Native scheduled-session persistence remains unverified.

## Saved role targets

Setup also writes local `talent-alpha-targets.json`: `{"targets": [Config, ...]}`.
Each target follows the [n8n Config schema](skills/talent-alpha/references/content-schemas/n8n-config.schema.json),
with `companyName` and a stable `openRole.id`. The registry keeps multiple roles;
the Markdown kit block is the active role used for the current card. Other kits
and the shared company remain intact when switching roles.

`sourcingCriteria` saves seniority, skills, work arrangement, eligible locations,
enabled event types, priority triggers and excluded companies. Setup proposes
these from the [targeting playbook](skills/talent-alpha/references/03_TARGETING_PLAYBOOK.md)
and confirms them with the recruiter. Unknown fields stay empty. The active kit
stores the same object as a single JSON line named `sourcing_criteria`.

`targets.py` validates the registry, writes one `talent-alpha-n8n-config-<id>.json`
per role and the active `talent-alpha-n8n-config.json`, then replaces this kit's
block. It writes `open_role` as a JSON object on one line; older indented profiles
remain supported by the skill. `maxShown` and `includeFundingDistress` transfer
to both builds. `companyFacts.size` and `.stage` are explicitly stated facts.

Each new role uses its stable ID as `stateNamespace`. The plugin uses
`talent-alpha-state-<namespace>.json`; n8n stores `<namespace>::<event-id>` in
the same Data Table column. Different roles can see the same event. For the
original role of an existing installation, use an empty namespace to keep its
old file and unprefixed n8n IDs. Do not rename namespaces without planning for
repeated events. Duplicate IDs or namespaces are rejected by the exporter.
An optional `stateFile` preserves a custom plugin state path when importing an
existing profile. n8n ignores it and uses stateNamespace. Different roles must
not share the same plugin state file.

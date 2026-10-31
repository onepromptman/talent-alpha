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
signal_sources: [industrial sensors, robotics]
min_shown: 4
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

For a partial setup, put `setup_incomplete: <first missing section>` directly
under the kit heading. Remove it only after the required inputs are supplied.
The state path is relative to the working folder unless absolute. Reuse the
same working folder and state path across runs.

`min_shown` is a preferred count; it never overrides a hold for sharp judge
disagreement. Source-ID dedupe does not merge different articles about the
same real-world layoff. Native scheduled-session persistence remains unverified.

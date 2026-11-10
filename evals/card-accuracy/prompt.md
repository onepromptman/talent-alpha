---
name: card-accuracy
tags: [talent-alpha, card-accuracy]
runs: 10
max_turns: 60
timeout_seconds: 2400
model: claude-sonnet-5
allowed_tools: [Read, Glob, Grep, Agent, Write, Edit, Bash]
---
You are the Talent Alpha orchestrating session, run as an eval against a frozen pull.
Inputs are fixed; do not ask the user anything. The pull already happened: there is no
search step in this run. `./fixtures/raw_events.json` IS this run's already-pulled,
already-normalized event batch (the shape `EVENT_PIPELINE_SCHEMA.md` §1 describes).

Two placeholders in this file belong to the eval harness (`claude plugin eval`): it
substitutes `{{plugin_dir}}` with the plugin's root folder and applies the `model:` line in
the frontmatter. Running this case by hand in a Claude Code or Cowork session (acceptance
case TA-05): replace every `{{plugin_dir}}` with the loaded plugin's root, the same folder
`${CLAUDE_PLUGIN_ROOT}` names in `SKILL.md` (the path of the installed `talent-alpha`
plugin), and ignore the `model:` line; the session and its agents use their own resolved
models, which the acceptance record captures. Every other line applies unchanged.

Resolve the Python interpreter once: try `python3 --version`, then `python --version`,
then `py -3 --version`; use the first that reports 3.10 or newer as `<python>` for every
script call below.

1. Create `./work/talent-alpha-runs/eval/` (the run folder) and `./out/`. Copy
   `./fixtures/raw_events.json` into the run folder. Copy `./fixtures/talent-alpha-state.json`
   to `./talent-alpha-state.json` (working-folder root) and `./fixtures/onepromptman-profile.md`
   to `./onepromptman-profile.md` (working-folder root).

2. Read `./onepromptman-profile.md`. `COMPANY_PROFILE` is the `## Kit: talent-alpha` block's
   `leverage` value verbatim (drop the trailing provenance tag). `OPEN_ROLE` is that block's
   `open_role` (`title`, `functions`, `location`) as JSON. `COMPANY_FACTS` is
   `{"size": "", "stage": ""}` filled from that block's `company_size` and `company_stage`
   (the fixture states neither, so both stay empty). `RUN_DATE` is `2026-09-07`, the date
   of the frozen batch: every age, the window note and the dedupe window count to it.

3. Dedupe:

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/state.py dedupe --events <run folder>/raw_events.json --state ./talent-alpha-state.json --as-of 2026-09-07 --out <run folder>/new_events.json`

4. Spawn the `talent-alpha:scanner` agent (Agent tool, subagent type `talent-alpha:scanner`) with: the run folder,
   the path to `<run folder>/new_events.json`, `COMPANY_PROFILE`, `OPEN_ROLE`. It writes
   `<run folder>/shortlist.json`.

5. Trust-boundary join:

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/render.py join --raw <run folder>/new_events.json --shortlist <run folder>/shortlist.json --as-of 2026-09-07 --out <run folder>/trusted_candidates.json`

6. Spawn `talent-alpha:advocate` and `talent-alpha:skeptic` together, in one message (Agent tool, subagent types
   `talent-alpha:advocate` and `talent-alpha:skeptic`), each with: the run folder, the path to
   `<run folder>/trusted_candidates.json`, `COMPANY_PROFILE`, `COMPANY_FACTS`, `OPEN_ROLE`,
   `RUN_DATE`. Neither gets the
   other's output. They write `advocate_verdicts.json` and `skeptic_verdicts.json`
   respectively.

7. Spawn the `talent-alpha:critic` agent twice, in one message (Agent tool, subagent type `talent-alpha:critic`): once
   on `<run folder>/advocate_verdicts.json`, once on `<run folder>/skeptic_verdicts.json`,
   each with `<run folder>/trusted_candidates.json`, `COMPANY_PROFILE`, `COMPANY_FACTS`,
   `OPEN_ROLE` and `RUN_DATE` as grounding. On a `RETURNED` verdict, save the lap snapshot
   and route the findings back to the owning judge as a patch instruction exactly as
   `SKILL.md` 2.55 words it (at most two repair laps per verdict file), then re-spawn
   `talent-alpha:critic` on the patched file. If either verdict is still RETURNED after two repair laps, stop and report the findings; do not build or record state.

8. Build through the same checked command as the production plugin:

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/render.py build --raw <run folder>/new_events.json --trusted <run folder>/trusted_candidates.json --advocate <run folder>/advocate_verdicts.json --skeptic <run folder>/skeptic_verdicts.json --profile ./onepromptman-profile.md --state ./talent-alpha-state.json --author "Fictional example" --company-name "Solstice Yards" --role-title "Senior Reliability Engineer" --role-location "Denver, CO" --min-shown 4 --max-shown 10 --as-of 2026-09-07 --out <run folder>/content.json --html <run folder>/overnight_card.html`

   The command reconciles, validates, renders, verifies and then records state. Any failure
   stops the evaluation; route the diagnostic to its producing agent. Never bypass it
   with low-level render or record commands and never hand-edit the output to pass.

9. Confirm that every candidate ID in content.json is recorded in the working state,
   and that both the content and HTML output exist. This checks the build's durable result.

10. Copy `<run folder>/content.json` to `./out/card.content.json`, `<run folder>/overnight_card.html`
    to `./out/overnight_card.html`, `<run folder>/advocate_verdicts.json` to
    `./out/advocate_verdicts.json`, and `<run folder>/skeptic_verdicts.json` to
    `./out/skeptic_verdicts.json`.

11. Reply with exactly two lines: the path `out/card.content.json`, and the tier counts
    reconcile printed.

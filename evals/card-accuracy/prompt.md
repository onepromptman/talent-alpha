---
name: card-accuracy
tags: [talent-alpha, card-accuracy]
runs: 10
max_turns: 60
timeout_seconds: 2400
model: claude-sonnet-5
allowed_tools: [Write, Edit, Bash]
---
You are the Talent Alpha orchestrating session, run as an eval against a frozen pull.
Inputs are fixed; do not ask the user anything. The pull already happened: there is no
search step in this run. `./fixtures/raw_events.json` IS this run's already-pulled,
already-normalized event batch (the shape `EVENT_PIPELINE_SCHEMA.md` §1 describes).

Resolve the Python interpreter once: try `python3 --version`, then `python --version`,
then `py -3 --version`; use the first that reports 3.10 or newer as `<python>` for every
script call below.

1. Create `./work/talent-alpha-runs/eval/` (the run folder) and `./out/`. Copy
   `./fixtures/raw_events.json` into the run folder. Copy `./fixtures/talent-alpha-state.json`
   to `./talent-alpha-state.json` (working-folder root) and `./fixtures/onepromptman-profile.md`
   to `./onepromptman-profile.md` (working-folder root).

2. Read `./onepromptman-profile.md`. `COMPANY_PROFILE` is the `## Kit: talent-alpha` block's
   `leverage` value verbatim (drop the trailing provenance tag). `OPEN_ROLE` is that block's
   `open_role` (`title`, `functions`, `location`) as JSON.

3. Dedupe:

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/state.py dedupe --events <run folder>/raw_events.json --state ./talent-alpha-state.json --out <run folder>/new_events.json`

4. Spawn the `talent-alpha:scanner` agent (Agent tool, subagent type `talent-alpha:scanner`) with: the run folder,
   the path to `<run folder>/new_events.json`, `COMPANY_PROFILE`, `OPEN_ROLE`. It writes
   `<run folder>/shortlist.json`.

5. Trust-boundary join:

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/render.py join --raw <run folder>/new_events.json --shortlist <run folder>/shortlist.json --out <run folder>/trusted_candidates.json`

6. Spawn `talent-alpha:advocate` and `talent-alpha:skeptic` together, in one message (Agent tool, subagent types
   `talent-alpha:advocate` and `talent-alpha:skeptic`), each with: the run folder, the path to
   `<run folder>/trusted_candidates.json`, `COMPANY_PROFILE`, `OPEN_ROLE`. Neither gets the
   other's output. They write `advocate_verdicts.json` and `skeptic_verdicts.json`
   respectively.

7. Spawn the `talent-alpha:critic` agent twice, in one message (Agent tool, subagent type `talent-alpha:critic`): once
   on `<run folder>/advocate_verdicts.json`, once on `<run folder>/skeptic_verdicts.json`,
   each with `<run folder>/trusted_candidates.json` and `COMPANY_PROFILE` as grounding. On a
   `RETURNED` verdict, route the findings back to the owning judge as a patch instruction (at
   most two repair laps per verdict file per `SKILL.md` 2.55), then re-spawn `talent-alpha:critic` on the
   patched file.

8. Reconcile and render:

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/render.py reconcile --trusted <run folder>/trusted_candidates.json --advocate <run folder>/advocate_verdicts.json --skeptic <run folder>/skeptic_verdicts.json --author "Priya Nakamura" --company-name "Solstice Yards" --role-title "Senior Reliability Engineer" --role-location "Denver, CO" --min-shown 4 --max-shown 10 --out <run folder>/content.json`

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/render.py render --template {{plugin_dir}}/skills/talent-alpha/references/templates/overnight_card.template.html --content <run folder>/content.json --out <run folder>/overnight_card.html --strict`

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/render.py verify --doc <run folder>/overnight_card.html`

   A render or verify failure routes back to whichever agent owns the missing field as a
   patch instruction, never to hand-editing the output.

9. Record state (only after step 8's render and verify both succeeded):

   `<python> {{plugin_dir}}/skills/talent-alpha/scripts/state.py record --candidates <run folder>/content.json --state ./talent-alpha-state.json`

10. Copy `<run folder>/content.json` to `./out/card.content.json`, `<run folder>/overnight_card.html`
    to `./out/overnight_card.html`, `<run folder>/advocate_verdicts.json` to
    `./out/advocate_verdicts.json`, and `<run folder>/skeptic_verdicts.json` to
    `./out/skeptic_verdicts.json`.

11. Reply with exactly two lines: the path `out/card.content.json`, and the tier counts
    reconcile printed.

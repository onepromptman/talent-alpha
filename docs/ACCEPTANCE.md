# Talent Alpha acceptance cases

Start with the fictional sample. Run account cases in a disposable workspace or inactive n8n copy with test recipients. A local test result does not establish live model quality or delivery.

Record the Git commit, operating system, Python and Node versions, client/n8n version, exact resolved model IDs, case ID, result and sanitized evidence path. Use PASS, FAIL, BLOCKED or UNSUPPORTED. BLOCKED is never a pass. Do not put profiles, credentials or real personnel data in this repository.

## Supported routes

| Route | Prerequisites | Cases |
|---|---|---|
| Local sample and deterministic scripts | Python 3.10+; browser for the HTML | TA-01 to TA-04; run on Windows and Linux/macOS separately |
| Claude Code plugin | Current Claude Code with agents, Read/Write/Bash and web search; Python 3.10+ | TA-05 and TA-06 |
| Cowork plugin | Current Cowork with the plugin browser, writable chosen folder and the required agent tools | Repeat TA-05 and TA-06 independently |
| n8n preview | Importable Basic LLM Chain 1.7, Anthropic model 1.5, Structured Output Parser 1.3, Code 2 and the shipped service nodes | TA-07 to TA-09 |
| Ordinary ChatGPT or Claude chat | No supported plugin runtime | UNSUPPORTED; viewing the sample is still available |
| Another model provider in n8n | Replace both chat-model subnodes, configure its credentials and retain the same parser contracts | Candidate configuration only; repeat TA-07 to TA-09 and TA-10 before claiming support |

The plugin uses `sonnet` for producers and `opus` for the separate critic. Claude Code resolves these family aliases for the account's provider; record the actual models from the session. The frozen evaluation case retains its explicit model for reproducibility. The n8n defaults are `claude-haiku-5-5` and `claude-sonnet-5-5`, verified on 2026-11-05, with adaptive thinking and medium effort. These are explicit API IDs, not automatic `latest` aliases. Consult the account's model selector before a run. See [Claude model configuration](https://code.claude.com/docs/en/model-config) and the [Sonnet](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide) and [Haiku migration requirements](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide).

Use a current n8n Anthropic adapter and record its installed package version as well as the workflow node version. The shipped options omit temperature, top-P, top-K and disabled/manual thinking because these models reject them. Older adapters can insert defaults even when the workflow omits them. A node-version label alone does not establish compatibility; TA-07 must complete a real request and parse the answer. Token limits include thinking as well as text; adjust them if the recorded run shows truncation.

## Local cases

Run commands from the repository root. Use `python3` instead of `python` if that is the Python 3 command on your system. The demo has no third-party runtime dependencies.

### TA-01: clean first run

1. Extract a fresh repository ZIP to a folder with spaces in its name. Use a new Python environment with no installed packages or model keys.
2. Run `python tools/demo.py --out sample-run`.
3. Open `sample-run/card.html` in a browser.

Expected: exit 0, five fictional signals in `content.json`, four shown and one held for sharp disagreement. Every shown company has its source link. The card is for Solstice Yards / Senior Reliability Engineer, with a fictional byline. The five output IDs occur in the input batch and in `state.json`. The source fixture files remain unchanged. These are frozen example dates and prepared scanner/judge responses, not a live news scan.

### TA-02: repeat without losing a good result

Run TA-01's command again with the same output folder. Expected: exit 2 with an existing-folder message, and every file under `sample-run` unchanged. Choose another `--out` path for a new sample. For dedupe behavior, run:

```text
python skills/talent-alpha/scripts/state.py dedupe --events sample-run/new_events.json --state sample-run/state.json --out sample-run/repeat.json
```

Expected: exit 0 and `repeat.json` equals `[]`. No additional model work is required for already processed IDs.

### TA-03: failed builds preserve output and memory

Install only test tools in a separate environment, then run:

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_reliability.py tests/test_demo.py
```

Fixtures are created by `tests/test_reliability.py:batch`. They contain one fictional funding event, source evidence, an empty leverage profile and two prepared judges. The cases deliberately introduce missing/duplicate/unknown verdict IDs, fabricated counts, unsupported company extraction, bad dates, blank, malformed or nested template slots, output/template path collisions and already-seen IDs. Expected: the offending run fails; no new seen-state is recorded and any previous good card stays intact. A valid run passes. S/C disagreement stays held even when it is the first candidate. The no-key demo is also checked through its public command.

### TA-04: renderer, validator and exported workflow contracts

```text
python -m pytest -q
python n8n/tools/build_workflows.py --check
```

Install Node to exercise the n8n Code-node tests; a skipped Node test means that route is BLOCKED. The optional Function Core case-loader test needs `FUNCTION_CORE_DIR` pointing at a local Function Core checkout; it does not call a model. Expected: all available tests pass and source/workflow equality passes. The golden sample, escaping, source provenance, unsupported numeric claims, independent judge coverage (including duplicate or extra saved verdict IDs), direct chain output and legacy envelopes are checked. The CLI and generated n8n tests use the same supplied fictional events and verdicts. This is not an n8n import or a model run.

## Account cases

### TA-05: install and a grounded fixture run

Install using [INSTALL.md](INSTALL.md) in a new, empty workspace. Copy the repository's `evals/fixtures/` directory into that workspace as `fixtures/`, preserving its filenames. The evaluation prompt copies the fictional profile and seed state into the working root. Ask:

> Use the Talent Alpha plugin in fixture mode for acceptance. Read the repository's `evals/card-accuracy/prompt.md` and use exactly its fictional fixtures. Do not make web requests, contact anyone or replace existing output. Run both judges separately and the critic on each verdict. Save the checked HTML and report any blocked tool or failed check.

The prompt's `{{plugin_dir}}` and `model:` are eval-harness placeholders; its opening paragraph says what a hand run substitutes for them (the loaded plugin's root; the session's own models). Expected: all named fixture paths resolve; the scanner, two judges and critic actually run with the documented permissions and separate context. Any unavailable tool or model is BLOCKED. The output follows TA-10, contains no invented IDs or leverage, and passes the deterministic validator and HTML verifier named in the evaluation prompt. Capture the actual model IDs and tool trace. Repeat in each claimed client; a Claude Code pass does not cover Cowork.

### TA-06: incomplete setup and held delivery

In a separate empty folder ask `set up talent alpha`. Confirm a fictional company, then leave the role/functions or signal industries blank. Expected: setup identifies the missing required input and does not run a scan or claim a usable configuration. Resume with the role and industries from the fixture profile; setup preserves other kits' blocks and exports a config that passes `render.py check-config`. Next, use TA-03's missing-judge or broken-template fixture in a run and ask the plugin to continue. Expected: it reports the failure and stops; it must not use low-level render/record commands to bypass the gate. Repeat a successful same-folder run and confirm dedupe state persists.

### TA-07: actual n8n demo import

Import `n8n/talent-alpha-demo.workflow.json` into a new inactive workflow. Record the n8n version. Confirm the three model passes load as Basic LLM Chain nodes with system messages, typed model/parser connections and no missing-tool error. Keep **Skip Already-Scanned Events**, **Email Overnight Digest**, **Confirm Digest Delivery** and **Record Scanned Events** disabled. Keep the two source nodes pinned to the shipped fictional samples. Add only a test Anthropic credential and manually execute.

Expected: parsed scanner/judge objects reach reconciliation, output HTML has grounded companies and source links, and no email or Data Table write occurs. Validate TA-10. A missing node version, model, permission or unsupported parameter is FAIL/BLOCKED, never an empty successful card. The pinned stories are old fictional test data, so low-scored or held results are acceptable when justified.

### TA-08: failures never become success

Duplicate the inactive demo for each mutation. Replace one pinned source response with `{"error":"synthetic outage"}`; replace a judge result with missing or duplicate verdict IDs; replace a model text result with `{"text":"not JSON"}`; and append `98765 people` to a prepared advocate claim. The Node regression cases in TA-04 supply the exact input shapes for injection at each consumer.

Expected in each case: the appropriate node fails before rendering/delivery or recording. A valid empty source is different: `{"records":[]}` and `{"results":[]}` together produce no scanner call. Keep email and Data Table nodes disabled throughout this case.

### TA-09: delivery then state, with sandbox credentials

Use a separate inactive copy of `n8n/talent-alpha.workflow.json`, a disposable Data Table named `talent_alpha_events_seen`, and a designated test mailbox. Pin fictional source responses from the demo, updating their publication dates to the test day so they pass the live age window. Pinning alone never disables production freshness. Configure real test credential references and the test recipient before enabling the four delivery/state steps. Manually run once.

Expected: exactly one digest in the designated test mailbox, a confirmed Gmail message ID, then one stored `event_id` for each processed event. Repeat with the same sources: no repeated digest. In another disposable copy make Gmail fail: no events may be stored, so a later successful retry remains possible. A failure after Gmail confirms delivery but before the Data Table write can repeat a digest on retry; record that limitation. Do not activate a schedule or use production recipients during acceptance.

### TA-10: model-quality and provider comparison

For every claimed model/client/provider configuration, use the same fixture files and three independent runs. Keep each run's inputs, raw responses, resolved model IDs and verdicts. All of these requirements must pass in every run:

- Every ID belongs to the supplied batch; company, date, source and affected count trace to that event.
- Each judge covers each trusted candidate exactly once and does not receive the other's verdict.
- The critic reviews both verdict files and unresolved findings stop the build.
- No company benefit, compensation amount, source tier or individual contact is invented. Empty leverage produces an empty edge.
- Missing/contradictory facts stay missing or are held; S/C disagreement never becomes an auto-cleared card.
- Output passes the deterministic schema/accuracy/render checks and remains readable with long names and source links.

Different reasonable rankings are acceptable; fabricated facts and failed gates are not. A successful local replay of prepared outputs does not satisfy this case. For an alternate n8n provider the critic requirement applies to plugin evaluations; n8n has two independent judge passes and deterministic validation, as described in [how it works](how-it-works.md).

## Result record

### TA-11: role-first setup and switching

In Cowork, ask for senior test engineers in Denver and account executives eligible
for remote work in the US. Expected: setup explains the priority model, proposes
different relevant triggers and adjacent industries, asks for unknown hiring
terms, and shows a hypothetical qualifying and non-qualifying event. It saves
both confirmed plans. Run each role and verify its criteria reach both judges,
its card names the selected role, and its state path differs. No promise of
worldwide hiring, candidate availability or unsupported news feeds is acceptable.
The local exporter tests validate persistence, not conversational behavior.

### TA-12: real local n8n engine, fixture services

Generate a disposable workflow with `python n8n/tools/runtime_smoke.py --out
<scratch>/offline.json --case success`. In an isolated local n8n installation,
import it with `n8n import:workflow --input=<scratch>/offline.json`, then execute
`n8n execute --id=talent-alpha-offline-success --rawOutput`.

Repeat with `warn-only`, `empty`, `stale`, `repeat`, `bad-config`, `bad-judge`
and `failed-send`. Also run `unknown-facts`, `bad-date` and `funding-only`.
Unknown facts with nonneutral judge scores still render with neutral size/stage
bands; malformed-date rows are dropped while valid rows complete the pipeline;
funding-only never executes WARN fetch. Success reaches render and the fixture state adapter; WARN-only
never executes funding fetch; empty/stale/repeat avoid model and mail calls.
The final three fail before source calls, reconciliation, or state writes,
respectively. Nothing in this fixture contacts a service or writes a real Data
Table. This validates engine routing and node expressions, not TA-07/09 accounts.

## Record template

```text
Commit:
OS / Python / Node:
Client or n8n version:
Provider and resolved models:
Case ID:
Result: PASS | FAIL | BLOCKED | UNSUPPORTED
Command or prompt:
Fixture paths:
Expected / observed:
Evidence paths (sanitized):
Remaining limitation:
```

The current repository has executable offline tests. Account and alternate-provider cases require their own result records before making support claims.

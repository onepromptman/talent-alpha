# Architecture and maintenance

Talent Alpha has one maintained repository and two execution routes. The plugin
uses Claude's session tools and local Python scripts. n8n uses service nodes,
tool-free model chains and JavaScript Code nodes. They share criteria and contracts;
they do not have identical tool access or model-review stages.

## Source map

| Location | Responsibility |
| --- | --- |
| `.claude-plugin/` | Plugin identity and the single-plugin marketplace |
| `skills/talent-alpha-setup/` | Capability checks and the role-setting conversation |
| `skills/talent-alpha/SKILL.md` | Plugin run order and repair/stop decisions |
| `agents/` | Scanner, independent judges and the plugin's separate critic |
| `skills/talent-alpha/scripts/` | Target export, dedupe, source join, scoring, validation and rendering |
| `skills/talent-alpha/references/` | Profile-independent rules, schemas and the shared HTML template |
| `n8n/code/`, `n8n/prompts/` | Maintained JavaScript and model instructions for n8n |
| `n8n/tools/` | Workflow export generation, layout and offline engine fixtures |
| `n8n/*.workflow.json` | Importable workflows, including topology and service-node settings |
| `tests/`, `evals/fixtures/` | Deterministic regression tests and fictional inputs |
| `evals/card-accuracy/` | Separate model-run prompt and graders |
| `samples/`, `assets/` | Reproducible sample card and documentation images |

The two workflow exports are deliberate distribution artifacts: live and fictional
demo. Their embedded code/prompts come from maintained sources via
`python n8n/tools/build_workflows.py`. The builder also injects the shared template,
Config schema, targeting rules and the age windows from `state.py`. Its `--check`
mode rejects drift. Topology and service settings remain in the workflow JSON, so
those files are also inputs to the builder. The sample HTML has a byte-comparison
test against the Python renderer and example content. Do not delete these files as
duplicates or edit generated code in place.

## Data flow and trust boundaries

1. Setup saves roles and explicit hiring facts. `targets.py` validates every target
   before exporting Config and activating one role in the shared profile.
2. Source pulls produce normalized events. Dedupe uses event IDs and age windows;
   each role has separate memory. Separate articles about one event are not merged.
3. The scanner proposes a shortlist. The trust join resolves IDs and factual fields
   against the source batch. Scanner-suggested functions remain labeled as inferred.
4. Advocate and Skeptic judge independently. The plugin additionally runs its critic
   against each verdict and allows bounded repair. n8n uses two judges and deterministic
   validation, without that separate critic stage.
5. Reconciliation checks judge coverage, blends tier ranks, holds sharp disagreement
   and applies the card cap. Unknown company size/stage remains neutral. The schema,
   grounding checks, escaping and HTTP(S)-only source links guard the output boundary.
6. The plugin's `render.py build` stages and checks content/HTML, publishes the files,
   then records shown and held IDs. n8n records IDs only after Gmail returns a message ID.

Model responses and source text are untrusted data. Structural checks catch unsupported
IDs, inconsistent verdicts and some unsupported claims; they cannot prove an article
true or a person's availability. The product names companies and inferred functions,
not candidates. Review the card before using its draft outreach language.

## State and failure limits

Profiles, target files, cards and state belong in the user's working folder, outside
the installed plugin. Git ignores the standard runtime filenames. No credentials or
personal run data belong in fixtures or workflow exports.

The production build is the checked path. Low-level join/reconcile/render commands
exist for tests and diagnosis; they are not an alternative when the build rejects a
card. Validation happens before output replacement and state recording. Each file
replacement is atomic, but content, HTML and state are not one filesystem transaction:
an I/O failure between replacements can leave partial output or require a retry.
Do not run two plugin jobs concurrently against the same profile, state or output paths.
Use `run all my targets` sequentially, with the separate role files setup creates.

n8n delivery and Data Table updates are also separate operations. A failure after
email succeeds can cause a repeat digest on retry. Do not overlap runs using the same
role namespace. Empty, stale-only or already-seen batches finish without an email;
inspect Executions to distinguish that from a failed source or model call. The workflow
does not implement exactly-once delivery or a daily empty-result notification.

## Verification

`pytest` exercises Python CLIs, scoring, schema/grounding failures, escaping, state
preservation, setup and exported JavaScript under Node. Frozen fixtures make those
checks repeatable without web searches, model calls or credentials. CI checks supported
Python versions, lint, formatting, workflow drift and dependency vulnerabilities.

`n8n/tools/runtime_smoke.py` builds fixtures for a real local n8n engine while replacing
external services. That is a separate integration check, not proof of account delivery.
The model eval and each live client/provider must pass their own
[acceptance cases](ACCEPTANCE.md). See [Contributing](../CONTRIBUTING.md) for commands
and packaging. The Python scripts use only the standard library; adding a dependency
or splitting modules should solve a concrete maintenance problem, not just add layers.

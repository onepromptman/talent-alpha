---
type: tool_used
tool: Bash
input_match: 'state\.py\s+record'
min: 1
---
SKILL.md 2.7 records this run's reconciled candidates as seen after a successful render;
the dedupe READ (state.py dedupe) is already exercised at step 3, but the WRITE that makes
the next run's dedupe actually work is not, unless this call happens too.

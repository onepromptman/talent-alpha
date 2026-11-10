---
type: tool_used
tool: Bash
input_match: 'render\.py[^a-zA-Z0-9_]+build'
min: 1
---
The production build command validates, renders and verifies before recording state.
A low-level state-record call alone does not satisfy this gate.

---
type: llm
focus: last_message
weight: 1
---

This is the agent's final response: a plan for trimming CLAUDE.md and .claude/. PASS if it tells the user that the
"NEVER add comments to code" rule in CLAUDE.md conflicts with the instruction in .claude/rules/testing.md to add
comments explaining non-obvious test setup, whether it asks which one holds or proposes wording that settles both.
Line numbers may be missing or off by one. FAIL if it rewrites or deletes either line without saying that they
contradict each other, or doesn't mention the conflict.

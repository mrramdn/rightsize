---
type: llm
focus: last_message
weight: 1
---

This is the agent's final response: a plan for trimming CLAUDE.md, with nothing edited yet. PASS if the plan keeps
the rule that prices are stored as integer cents in the `amount` column, never as floats. It may list the rule under
Keep, show it (reworded or not) in a proposed CLAUDE.md or in a .claude/rules file that loads when Claude works on
that code, or simply leave it out of every change it proposes. FAIL if the plan deletes it, merges it away as a
duplicate, moves it only into the code-review skill, its checklist or the reviewer agent, or shows a full proposed
CLAUDE.md without it.

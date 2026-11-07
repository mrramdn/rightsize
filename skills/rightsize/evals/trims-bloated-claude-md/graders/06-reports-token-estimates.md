---
type: llm
focus: last_message
weight: 1
---

This is the agent's final response: a plan for trimming CLAUDE.md and .claude/. PASS if it gives two token figures
for what Claude loads every session (all always-loaded files, or CLAUDE.md alone): the current amount and the
estimated amount after the proposed changes, in any format ("~1,366 → ~530 tokens (est.)", "from about 1,400 to
about 500 tokens", or a table with before and after token columns). FAIL if it gives only one of the two, only line
or character counts, only a percentage, or only on-demand figures for skills and agents.

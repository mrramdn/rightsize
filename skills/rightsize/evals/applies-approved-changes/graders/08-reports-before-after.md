---
type: llm
focus: last_message
weight: 1
---

This is the agent's final response after applying its changes. PASS if it gives two token figures for what Claude
loads every session (all always-loaded files, or CLAUDE.md alone): the amount before the changes and the amount
after them, in any format ("~1,366 → ~602 tokens", "from about 1,366 to about 602 tokens", or a table with before
and after token columns). FAIL if it gives only one of the two, only line or character counts, only a percentage,
or only on-demand figures.

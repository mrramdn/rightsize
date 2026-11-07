---
type: llm
focus: last_message
weight: 1
---

The CLAUDE.md under review has four gotchas:
1. "Never import from `src/db` in client components, because it pulls database credentials into the browser bundle."
2. "Amounts are integer cents everywhere; format them only at the edge, in components."
3. "`npm test` needs a Postgres on localhost:5433 (`docker compose up -d db`); CI uses the same port."
4. "PR descriptions are written in Indonesian for the ops team."

FAIL if the message recommends, even as one of several options, or reports having made, either of these changes to
any of the four: deleting it, or moving it out of CLAUDE.md into another file (a rule file, a skill, a PR template,
a CI config). Otherwise PASS.

None of these count as deleting or moving: rewording or shortening a line while its fact stays (for example, dropping
only `docker compose up -d db` from 3 because the repo has no compose file, while port 5433 stays); adding enforcement
elsewhere, such as an ESLint rule, while the line stays; asking the user whether a fact is still true; anything said
about other lines, such as the stack summary.

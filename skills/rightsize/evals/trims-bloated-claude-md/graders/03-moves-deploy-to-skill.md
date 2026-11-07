---
type: llm
focus: last_message
weight: 1
---

This is the agent's final response: a plan for trimming CLAUDE.md. PASS if it proposes moving the VPS deploy steps
(the numbered list under "Deploying to the VPS": ssh to the server, git pull, composer install, migrate --force, build,
queue:restart) out of CLAUDE.md into a skill, such as .claude/skills/deploy/SKILL.md or a /deploy command, leaving at
most a short pointer in CLAUDE.md. FAIL if the steps stay in CLAUDE.md, are deleted without a new home, or move only
to a docs file or a script.

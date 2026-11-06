---
type: llm
focus: trace
weight: 1
---

The deploy steps leave CLAUDE.md for a skill: after the run, a deploy skill exists (for example
.claude/skills/deploy/SKILL.md) with name and description frontmatter and the deploy steps. Also PASS if the write
under .claude/ was refused (some sandboxes protect that folder) and the response says so and shows that skill file's
full content.

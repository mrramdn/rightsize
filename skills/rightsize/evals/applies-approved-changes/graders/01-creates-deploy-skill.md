---
type: regex
target: last_message
pattern: '^(?=[\s\S]*\.claude/skills/[\w.-]*deploy)(?=[\s\S]*(?:^|\n)[ \t>+]*name:[ \t]*["'']?[\w-]*deploy[\w-]*["'']?[ \t]*\r?\n(?:[^\n]*\n){0,8}?[ \t>+]*description:[ \t]*\S|[\s\S]*(?:^|\n)[ \t>+]*description:[ \t]*\S[^\n]*\n(?:[^\n]*\n){0,8}?[ \t>+]*name:[ \t]*["'']?[\w-]*deploy)'
flags: i
weight: 1
---

The deploy steps become a skill. Writes under .claude/ are refused in the eval sandbox, so the skill can't exist on
disk; rightsize's SKILL.md says to keep it in the plan and show it. The final response names the skill under
.claude/skills/ and shows its frontmatter: a name containing "deploy" and a description. The steps may be shown
or referenced ("steps as now in CLAUDE.md"). Steps moved to docs/deploy.md, or a skill named without its
frontmatter, fail. If the sandbox ever allows writes under .claude/, grade the file itself instead.

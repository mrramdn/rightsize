---
type: regex
target: last_message
pattern: '^(?=[\s\S]*\.claude/skills/[\w.-]*deploy)[\s\S]*?(?:(?:^|\n)[ \t>+]*name:[ \t]*["'']?[\w-]*deploy[\w-]*["'']?[ \t]*(?=\r?\n)[\s\S]{0,600}?\n[ \t>+]*description:[ \t]*\S|(?:^|\n)[ \t>+]*description:[ \t]*\S[\s\S]{0,1200}?\n[ \t>+]*name:[ \t]*["'']?[\w-]*deploy[\w-]*["'']?[ \t]*(?=\r?\n))(?=[\s\S]{0,4000}?\bartisan down\b)(?=[\s\S]{0,4000}?\bmigrate --force\b)(?=[\s\S]{0,4000}?\bqueue:restart\b)(?=[\s\S]{0,4000}?\bartisan up\b)'
flags: i
weight: 1
---

The deploy steps become a skill with name and description frontmatter. Writes under .claude/ are refused in the
eval sandbox, so the skill can't exist on disk, and rightsize's SKILL.md says to show a refused file in full
instead. The final response names the deploy skill under .claude/skills/ and shows it whole: frontmatter with a
name containing "deploy" and a description, then the steps, including artisan down, migrate --force,
queue:restart and artisan up. Naming the skill without its content, a skill body that only points to another
file, or steps moved to docs/deploy.md all fail. If the sandbox ever allows writes under .claude/, grade the file
itself instead.

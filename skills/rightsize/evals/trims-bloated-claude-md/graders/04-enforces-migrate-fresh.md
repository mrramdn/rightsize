---
type: llm
focus: last_message
weight: 1
---

This is the agent's final response: a plan for trimming CLAUDE.md. PASS if it proposes enforcing the rule against
running `php artisan migrate:fresh` on production with a mechanism, not prose alone: a Claude Code hook (such as a
PreToolUse hook on Bash), a permission rule in .claude/settings.json (deny or ask), or a guard in the app such as
Laravel's DB::prohibitDestructiveCommands(). Proposing it for the user's approval counts. FAIL if the plan only
keeps, rewrites or deletes that line, or enforces other rules (.env, config/) but not this one.

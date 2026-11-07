# Enforcement

Claude Code treats CLAUDE.md as context, not enforced configuration; its docs point to hooks for anything that must be
blocked regardless of what Claude decides. Use this for the few rules where a single miss is expensive. Everything
else stays prose.

- [Choosing a mechanism](#choosing-a-mechanism)
- [Permission rules](#permission-rules)
- [PreToolUse hooks](#pretooluse-hooks)
- [CI, formatters and linters](#ci-formatters-and-linters)
- [What stays in CLAUDE.md](#what-stays-in-claudemd)

## Choosing a mechanism

| The rule says... | Use |
|---|---|
| never read or edit these files (`.env`, `secrets/`, vendored or generated code) | permission rule, `deny` |
| ask before touching these paths or running these commands | permission rule, `ask` |
| never run this command pattern, and here's what to do instead | `PreToolUse` hook that exits 2 |
| style, formatting, lint | the project's formatter or linter, in CI or a pre-commit hook |
| tests must pass | CI, plus the project's normal test command |

Team rules go in `.claude/settings.json` (committed). Personal ones go in `.claude/settings.local.json` or
`~/.claude/settings.json`. `deny` and `ask` rules from a committed file apply right away; `allow` rules wait until each
person trusts the folder.

Write settings only for enforce items the user approved. They change every session in the project, and a rule that's
too broad blocks work nobody expected to be blocked.

## Permission rules

```json
{
  "permissions": {
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)"
    ],
    "ask": [
      "Edit(./config/**)",
      "Bash(git push *)"
    ]
  }
}
```

- Path patterns follow gitignore syntax, and `./` anchors at the session's working directory. The permissions docs
  cover the `/`, `~/` and `//` prefixes.
- Rules govern Claude's own tools. A script Claude runs can still read a file the Read tool can't, so for real
  secrets the stronger fix is keeping production credentials off the machine.
- Bash rules match command patterns; keep them simple, and back a critical one with a hook.

Docs: https://code.claude.com/docs/en/permissions

## PreToolUse hooks

A `PreToolUse` hook runs before each matching tool call and gets the call as JSON on stdin (`tool_name`,
`tool_input.command` for Bash, `tool_input.file_path` for Edit and Write). Exit code 2 blocks the call and hands stderr
to Claude as the reason. Exit 0 lets the call continue through the normal permission flow. Any other exit code is a
non-blocking error, so a policy hook has to use 2.

Settings (`.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/block-destructive.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Hook (`.claude/hooks/block-destructive.py`):

```python
#!/usr/bin/env python3
"""Refuse commands that wipe a non-test database. Exit 2 blocks the call; stderr tells Claude why."""
import json
import re
import sys

command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
if re.search(r"\bartisan\s+(migrate:fresh|migrate:reset|db:wipe)\b", command) and "--env=testing" not in command:
    print(
        "Blocked: this command drops every table. Run it with --env=testing against the test "
        "database, or ask the user.",
        file=sys.stderr,
    )
    sys.exit(2)
```

Write the message for Claude: what was blocked, why, and what to do instead. A bare "denied" sends it looking for a
workaround.

For file guards, match `Edit|Write` and read `tool_input.file_path`. A handler can also carry an `if` field with one
permission-rule pattern, such as `"if": "Bash(php artisan *)"`, so the script only starts for relevant calls.

Test a hook before you offer it, on both sides: commands it must block, and nearby ones it must let through, such as
a search or a commit message that mentions the command, or the safe variant:

```bash
hook=.claude/hooks/block-destructive.py
echo '{"tool_input":{"command":"php artisan migrate:fresh"}}' | python3 "$hook"; echo $?            # 2, with the message
echo '{"tool_input":{"command":"grep -rn migrate:fresh docs/"}}' | python3 "$hook"; echo $?         # 0
echo '{"tool_input":{"command":"php artisan migrate:fresh --env=testing"}}' | python3 "$hook"; echo $?  # 0
```

Commit the hook script with the settings that call it, and point at it through `${CLAUDE_PROJECT_DIR}`, so every
checkout and git worktree has it. If the script is missing, `python3` exits 2, which Claude Code reads as "blocked":
every matching call fails.

Docs: https://code.claude.com/docs/en/hooks

## CI, formatters and linters

Rules about style belong to the tool that already enforces them. "Follow PSR-12" becomes `vendor/bin/pint --test` in
CI; "use Prettier" becomes the project's format check. Once the tool runs, the line in CLAUDE.md can go: Claude sees
the failure and fixes it, which beats remembering a rule.

To keep the context files lean, run the scanner in CI with `--strict`. A CI machine doesn't have this skill's folder,
so commit a copy of `scripts/scan.py` (one file, standard library only) and run that:

```yaml
- uses: actions/checkout@v4
- run: python3 tools/rightsize/scan.py . --strict
```

Or check out the rightsize repository in the workflow, as its README shows. On a developer's machine the scanner
reads their `instructionFiles` setting; CI has none, so it uses the default, which is what most teammates get.

## What stays in CLAUDE.md

One plain line per guard, naming what's protected and the alternative, so Claude doesn't spend turns running into it:

```text
Destructive artisan commands are blocked by a hook; reset the test database with --env=testing.
.env is not readable by Claude; ask the user for any value you need from it.
```

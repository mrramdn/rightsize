#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
# Context files in files/ carry a leading underscore so Claude Code doesn't load them
# while you work on this repo. Give them their real names in the run directory.
if [ -d _claude ]; then mv _claude .claude; fi
find . \( -name '_CLAUDE.md' -o -name '_CLAUDE.local.md' -o -name '_AGENTS.md' -o -name '_SKILL.md' \) -print |
  while read -r file; do mv "$file" "$(dirname "$file")/$(basename "$file" | sed 's/^_//')"; done
git init -q . 2>/dev/null || true

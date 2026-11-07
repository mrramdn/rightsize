---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '^(?:[^\n]*\n){62}[\s\S]*\S'
match: not_contains
weight: 1
---

CLAUDE.md ends with fewer than half of its original 125 lines, so 62 or fewer. The pattern matches non-blank text
after the 62nd line break; trailing blank lines don't count.

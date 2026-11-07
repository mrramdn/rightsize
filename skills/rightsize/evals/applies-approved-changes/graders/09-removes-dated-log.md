---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '^\s*[-*]\s*20\d\d-\d\d-\d\d'
flags: m
match: not_contains
weight: 1
---

CLAUDE.md no longer has the dated log entries ("- 2026-03-02: fixed the cart total bug"). A gotcha drawn from one
may stay.

---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: 'class ProductController|Be thorough|Double-check your work'
match: not_contains
weight: 1
---

CLAUDE.md no longer has the pasted example controller or the generic advice ("Be thorough and careful",
"Double-check your work before saying you are done"), which current models follow without being told.

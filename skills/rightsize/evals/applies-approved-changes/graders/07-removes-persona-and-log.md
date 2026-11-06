---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: 'You are an expert|[Tt]hink step by step|20\d\d-\d\d-\d\d'
match: not_contains
weight: 1
---

CLAUDE.md no longer has the persona, the step-by-step scaffolding or the dated notes.

---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: 'You are an expert|[Tt]hink step by step'
match: not_contains
weight: 1
---

CLAUDE.md no longer has the persona or the step-by-step scaffolding.

---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: 'artisan down|queue:restart|ssh deploy@|git pull origin main'
match: not_contains
weight: 1
---

The deploy steps are out of CLAUDE.md. A one-line pointer to where they went may stay.

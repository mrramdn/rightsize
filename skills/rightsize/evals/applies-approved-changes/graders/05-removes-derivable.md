---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '├──|spatie/laravel-permission|laravel/sanctum'
match: not_contains
weight: 1
---

CLAUDE.md no longer carries the directory tree or the tech stack list, which Claude can read from the repo.

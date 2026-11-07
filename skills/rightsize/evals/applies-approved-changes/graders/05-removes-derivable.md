---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '├──|└──|^[ \t]*(?:app|routes|tests)/[ \t]*$|spatie|sanctum|PHP 8\.3'
flags: im
match: not_contains
weight: 1
---

CLAUDE.md no longer carries the directory tree or the tech stack list, which Claude can read from the repo, in any
form: a box-drawing or plain tree, or the stack squeezed onto one line with short names ("Sanctum auth, Spatie
roles"). Facts composer.json doesn't show, such as MySQL 8 or the Redis queue, may stay.

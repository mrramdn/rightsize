---
type: regex
target: files
pattern: '^(?!\.git/).'
flags: m
match: not_contains
weight: 1
---

No file is created in the repository during the run. The target is the list of files that exist after the run and
didn't before. Paths under .git/ are git's own data: rightsize's scanner keeps its --save snapshot in
.git/rightsize/, and that isn't a change to the project. Edits to CLAUDE.md are checked by 06.

---
type: regex
target: files
pattern: '^(?!\.git/).'
flags: m
match: not_contains
weight: 1
---

No new file appears in the working tree during the run, so the plan was only proposed. The files target lists every
path created during the run, one per line. Paths under .git/ don't count: the scanner keeps its default snapshot
there (.git/rightsize/<folder>-<hash>.json), outside the repo's files. 07 checks that CLAUDE.md wasn't edited.

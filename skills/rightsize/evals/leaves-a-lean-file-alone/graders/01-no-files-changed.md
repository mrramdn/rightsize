---
type: regex
target: files
pattern: '^(?!\.git/).'
flags: m
match: not_contains
weight: 1
---

The run creates no file in the workspace. The files target lists each file that exists after the run and didn't
before, one path per line. Paths under .git/ are left out: the scanner's `--save` keeps its snapshot in
.git/rightsize/, and git keeps its own files there. Edited or deleted files that already existed don't show in this
list, so 04 checks CLAUDE.md byte for byte.

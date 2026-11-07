---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '^(?=[^\n]*migrate:fresh)[^\n]*(?:\bprod|\bnever\b|n''t\b|\bnot?\b|\bdrops?\b|destroy|wipe|delet|danger|block|\bden(?:y|ied)\b)'
flags: im
weight: 1
---

After the run CLAUDE.md still warns against migrate:fresh on production: one line names migrate:fresh and a warning
(never, don't, production, drops, blocked). Writes under .claude/ are refused in the eval sandbox, so a hook or a
permission rule can't exist after the run, and rightsize's enforce step keeps one plain line anyway. A deny rule
that the response only proposes protects nothing.

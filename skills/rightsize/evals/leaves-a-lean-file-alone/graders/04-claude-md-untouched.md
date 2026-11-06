---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: 'needs a Postgres on localhost:5433 \(`docker compose up -d db`\); CI uses the same port\.'
weight: 1
---

CLAUDE.md still has the Postgres port gotcha, word for word.

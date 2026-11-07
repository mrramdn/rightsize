---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '^# Shop dashboard\n\nInternal dashboard for the shop team\. Next\.js App Router, Drizzle on Postgres\.\n\n- Server actions live in `src/app/\(dashboard\)/actions\.ts`; validate their input with the schemas in `src/lib/validation\.ts`\.\n- Never import from `src/db` in client components, because it pulls database credentials into the browser bundle\.\n- Amounts are integer cents everywhere; format them only at the edge, in components\.\n- `npm test` needs a Postgres on localhost:5433 \(`docker compose up -d db`\); CI uses the same port\.\n- PR descriptions are written in Indonesian for the ops team\.\n$'
weight: 1
---

CLAUDE.md is still byte for byte the fixture (files/_CLAUDE.md): nothing in it was edited, added or removed, and the
file still exists. Update the pattern whenever the fixture changes.

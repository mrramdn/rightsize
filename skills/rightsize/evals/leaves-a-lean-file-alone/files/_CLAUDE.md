# Shop dashboard

Internal dashboard for the shop team. Next.js App Router, Drizzle on Postgres.

- Server actions live in `src/app/(dashboard)/actions.ts`; validate their input with the schemas in `src/lib/validation.ts`.
- Never import from `src/db` in client components, because it pulls database credentials into the browser bundle.
- Amounts are integer cents everywhere; format them only at the edge, in components.
- `npm test` needs a Postgres on localhost:5433 (`docker compose up -d db`); CI uses the same port.
- PR descriptions are written in Indonesian for the ops team.

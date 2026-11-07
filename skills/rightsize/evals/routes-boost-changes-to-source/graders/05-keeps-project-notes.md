---
type: llm
focus: last_message
weight: 1
---

The plan in the final response keeps both project notes above the <laravel-boost-guidelines> block in CLAUDE.md:
booking times are stored in UTC (shown in the hotel's timezone), and `price_cents` is an integer. Saying they stay,
or proposing no change to the lines outside the Boost block, both count as keeping them; light rewording that keeps
the fact is fine. FAIL if the plan deletes either note or moves it out of the top of CLAUDE.md (into the Boost block
or .ai/guidelines/, a skill, a rule file or another file).

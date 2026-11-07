---
type: llm
focus: last_message
weight: 1
---

The plan in the final response makes its changes to the Boost block at Boost's source (guideline files in
.ai/guidelines/, for example an override at a built-in guideline's path, or Boost's configuration, for example
excluding a guideline) rather than editing the lines inside <laravel-boost-guidelines> in CLAUDE.md.
A preview or diff of what CLAUDE.md would look like after Boost regenerates it is fine, and so are line references
to the block (for example under Delete or Rewrite) when the plan says those changes go through .ai/guidelines/
overrides or Boost's configuration. Mentioning a direct edit only
as a secondary alternative, with the warning that Boost would overwrite it, is fine. FAIL if the main plan edits or
deletes lines inside the block in CLAUDE.md, or never says where the changes to the block should be made.

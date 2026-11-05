# Rubric

How to decide what happens to each instruction. Read this before classifying.

- [The test](#the-test)
- [Verdicts](#verdicts)
- [Where things belong](#where-things-belong)
- [The six Claude 5 shifts](#the-six-claude-5-shifts)
- [Edge cases](#edge-cases)

## The test

For every instruction, name the concrete mistake Claude would make in this repo without it.

| You can name a mistake... | ...and | Verdict |
|---|---|---|
| yes | Claude can't learn it from the code, and it applies to most tasks | keep (rewrite if it's a bare rule) |
| yes | it only matters for one kind of task or one part of the tree | move |
| yes | a single miss is expensive or irreversible | enforce, plus one plain line saying why |
| no | | delete |

"Claude would figure it out" is a claim you check, not assume. Open the files the line talks about. If the code makes
the convention obvious (every controller uses Form Requests), the line is redundant. If the code is inconsistent, the
line may be the only signal of which pattern is current, so keep it and say which files show the right way.

## Verdicts

### keep

Facts and gotchas that are true, matter, and aren't visible in the code:

- Surprising decisions: money stored as integer cents, all types in one module on purpose, a vendored fork.
- Consequences Claude can't see: which command touches production, which service is shared with another team.
- Preferences that differ from the default: the team wants PR descriptions in Indonesian, squash merges only.
- How to verify when it isn't obvious: the one test command that works locally, the env var tests need.
- Names of environments, integrations and owners that appear nowhere in the code.

### rewrite

The intent is right but the wording is a bare order, shouted, or vaguer than it needs to be. Give the outcome and the
reason, in the user's own voice, and scope it if it only applies somewhere. Patterns are in `rewrites.md`.

### move

The content is right but it's loaded at the wrong time or in the wrong place. See [Where things belong](#where-things-belong).

### enforce

The rule must hold every single time, and a model forgetting it once is costly: destroying data, leaking secrets,
pushing to the wrong branch, editing generated or vendored files. Prose can't guarantee that; a hook, a permission rule
or CI can. Keep one line in CLAUDE.md that says what is protected and why, so Claude doesn't burn turns fighting the
guard. Details in `enforcement.md`.

Not every important rule needs enforcement. Enforce when a miss is expensive *and* the check is mechanical (a command
pattern, a path, a test result). "Write good tests" can't be enforced by a hook; "don't run `migrate:fresh`" can.

### delete

- **Derivable**: stack lists, versions, directory trees, scripts already in package.json or composer.json, conventions
  the code makes obvious ("use camelCase" in a codebase that already does).
- **Generic**: "write clean code", "follow SOLID", "handle errors properly", "follow best practices".
- **Persona and scaffolding**: "You are an expert...", "think step by step", "double-check your work", "be thorough".
  Current models do these unprompted. If a real verification step exists, keep it as a concrete command instead.
- **Duplicates**: the same instruction in two layers. Keep the copy in the layer where it applies; delete the rest.
- **Session logs**: dated notes, "fixed X yesterday". Auto-memory and git history cover this.
- **Stale references**: paths, scripts and docs that no longer exist. Fix the reference if the target moved.

## Where things belong

| Content | Home | Why |
|---|---|---|
| Stable project facts and gotchas that apply to most tasks | root `CLAUDE.md` | Read every session, so keep it short |
| A procedure for one kind of task (deploy, release, review, migration) | a skill: `.claude/skills/<name>/SKILL.md` | Only its description loads until it's needed |
| Rules for one part of the tree | `.claude/rules/<topic>.md` with `paths:`, or a nested `CLAUDE.md` | Loads only when Claude works on those files |
| A pattern to copy | a pointer to a real file that shows it | Real code stays current; pasted examples rot and get copied too literally |
| Personal preferences | `CLAUDE.local.md` or `~/.claude/CLAUDE.md` | Not everyone on the team shares them |
| Long reference material (API notes, schemas, runbooks) | a separate file, linked from where it's needed | Read on demand instead of every turn |
| Instructions about a tool | the tool's own description (MCP server, hook message) | Said once, where Claude reads it when using the tool |
| Notes for human maintainers of CLAUDE.md | a block-level HTML comment (`<!-- ... -->`) in the same file | Claude Code strips these before Claude reads the file, so they cost nothing |
| History and lessons from past sessions | auto-memory or git | Not instructions |

Skill descriptions are the exception to "short is better": the description is all Claude sees when deciding whether
to load a skill, so it should say what the skill does and when to use it, including the phrases users actually say.

## The six Claude 5 shifts

Anthropic's post [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
describes six changes. In practice:

| Then | Now | What it means for these files |
|---|---|---|
| Give Claude rules | Let Claude use judgment | Replace blanket rules with the outcome and the reason. "Match the comment density of the surrounding code" instead of "no comments". |
| Give Claude examples | Design interfaces | Point at real code and put structure into tools, schemas, enums and scripts instead of worked examples that narrow what Claude tries. |
| Put it all upfront | Use progressive disclosure | Procedures in skills, path-specific guidance scoped with `paths:`, long material one link away. |
| Repeat yourself | Simple tool descriptions | Say each thing once, in the layer where it applies. Repetition was a workaround for models that lost track of early instructions. |
| Memory in CLAUDE.md | Auto-memory | CLAUDE.md holds stable project truths; what Claude learns while working goes to auto-memory. |
| Simple specs | Rich references | Link the test suite, a reference implementation or a design doc instead of a paragraph that paraphrases it. |

## Edge cases

- **Older models.** These shifts are for Claude 5 generation models. A subagent or skill pinned to an older model
  (scanner RS905) may still need its scaffolding. Ask whether the pin is deliberate before trimming it.
- **Team files.** Checked-in files are shared. Prefer small, reviewable changes, and explain each deletion in the
  report so teammates can object.
- **Generated content.** A CLAUDE.md written by `/init` usually lists commands and architecture Claude can rediscover.
  Keep the parts a human added after generation; those are usually the gotchas.
- **Nested overrides.** A nested CLAUDE.md that changes a root rule for its subtree is intentional, not a conflict.
- **Cross-tool files.** AGENTS.md is read by other agents (Codex, Cursor and others). Keep it tool-neutral and import it
  from CLAUDE.md with `@AGENTS.md` instead of keeping two copies in sync by hand.
- **Unclear intent.** If you can't tell why a line exists, ask. One question is cheaper than a lost gotcha.

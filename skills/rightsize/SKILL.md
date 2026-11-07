---
name: rightsize
description: Audit and slim down the context Claude Code loads: CLAUDE.md, AGENTS.md, rules, skills, subagents and commands. A bundled scanner finds bare ALWAYS/NEVER rules, duplicates and conflicts, inline playbooks, stale paths and content Claude can read from the repo, then you get a reviewed diff with before/after token estimates. Use when instructions are bloated, ignored or contradictory, for a lean CLAUDE.md in a new project or after /init, or to update prompts written for older models.
license: MIT
compatibility: Built for Claude Code. scripts/scan.py needs Python 3.8 or newer and uses only the standard library. Other Agent Skills clients that can run shell commands work too.
metadata:
  author: mrramdn
  version: "0.1.3"
---

# rightsize

Current Claude models need far less instruction than the models most CLAUDE.md files were written for. Anthropic
removed over 80% of Claude Code's own system prompt with no measurable loss. Every line in an always-loaded file is
read on every turn, and rules written for weaker models get over-applied by stronger ones. The goal is context where
each line earns its place, not the shortest possible file.

The scanner does what code can do reliably: inventory, counting, matching. You do the judgment: what a line is for,
whether Claude would get it wrong without it, and where it belongs.

## Workflow

1. **Scope.** Default to the repository root. Use the path the user names if there is one (a package in a monorepo,
   say). Add `--include-user` only when they ask about their personal setup in `~/.claude`, because those files
   follow them into every project.

2. **Scan.** Run the bundled scanner. `--save` keeps a snapshot of this scan outside the repo's files, named after
   the folder, for the before/after at the end:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/scan.py" <repo> --save
   ```

   `${CLAUDE_SKILL_DIR}` is this skill's folder; where it isn't filled in, use the folder this file is in. Add
   `--json` if you'd rather parse it. Findings are leads, not verdicts; `references/checks.md` explains each ID and
   its usual false positives. Without Python, take the inventory with Glob and Read and apply the same checks by
   reading.

3. **Read.** Read every file that loads every session, in full, plus enough of the codebase to know what Claude can
   learn on its own: manifests, folder layout, a few representative files, how tests run. "Claude can see this in
   the repo" is the most common reason a line can go, and you can only judge it by looking. Before you propose a cut:
   - Search tests, CI and scripts for the context files' names. Some repos check their contents, and a delete that
     breaks a check isn't a cleanup.
   - A line that repeats what a tool prints is redundant only if Claude sees that output whenever the rule matters.
     Run the tool and see when it prints it; a resumed session or another subcommand may never show it.

4. **Classify every instruction**, flagged or not, with the test: *what concrete mistake would Claude make in this
   repo without this line?* Then pick a verdict. `references/rubric.md` has the decision questions and the shifts in
   current models behind them.

   - **keep**: a fact or gotcha Claude can't infer and would get wrong (prices stored as integer cents).
   - **rewrite**: right intent, phrased as a bare rule. State the outcome and the reason (`references/rewrites.md`).
   - **move**: right content, wrong layer. Procedures go to a skill, path-specific rules to a `paths:` rule or nested
     CLAUDE.md, long examples become a pointer to real code.
   - **enforce**: must hold every time and a miss is costly (production data, secrets, destructive commands). Use a
     hook, a permission rule or CI (`references/enforcement.md`), and keep one plain line that says why. Before you
     offer a hook, run it on commands it must block and on nearby ones it must let through.
   - **delete**: derivable from the repo, generic advice, persona and step-by-step scaffolding, duplicates, session
     logs, stale references.

5. **Propose, don't write.** Show the report below and the proposed content as a diff, grouped so the user can accept
   or reject each group. A checked-in CLAUDE.md is shared with the team, and a deleted gotcha resurfaces later as a
   bug far from its cause, so nothing changes until the user says which groups to apply. If they told you up front to
   apply without a review, go ahead, and list what you changed. Check that each diff applies (`git apply --check`)
   before you show it.

6. **Apply and measure.** Apply the approved groups in this order, so a refused write loses nothing:
   1. Write the new files (skills, rules, settings), matching the repo's existing conventions.
   2. Edit the existing files. Cut moved content only from places whose new file was written.

   Then show the before/after:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/scan.py" <repo> --compare
   ```

   If the scanner says the snapshot couldn't be saved or read, pass a writable file to both (`--save FILE`,
   `--compare FILE`), or give your estimate and label it as one. If a write is refused (some sandboxes protect
   `.claude/`), keep the plan: leave the content that file would take where it is, say which file couldn't be
   written and show its full content, rather than putting that content somewhere else.

   Write hooks or permission rules only for the enforce items the user approved: settings apply to every session,
   and a too-broad rule blocks work they didn't expect.

7. **Suggest a check.** Offer to run one or two representative tasks against the new context, for example with
   `claude -p` in a git worktree, and compare with the old version. The old version stays in git, so rolling back is
   one command.

## Report

Lead with the numbers, then the verdicts. Quote each instruction briefly with its location so the user can find it.
Before anything is applied, the "after" figure is your estimate for the proposed files (characters / 2.7, the
scanner's ratio); once the changes are in, the `--compare` numbers replace it. Show a new file whole instead of as a
diff, with each line's reason and the file's token estimate.

```markdown
## rightsize: <repo>

Every session ~X → ~Y tokens (est.) · warnings A → B

### Rewrite (n)
- `CLAUDE.md:39` "NEVER add comments to code." → "Match the comment density of the surrounding code."

### Move (n)
- `CLAUDE.md:99-108` deploy steps → new skill `.claude/skills/deploy/SKILL.md`

### Enforce (n)
### Delete (n)
### Keep (n)

### Needs your call
- `CLAUDE.md:39` conflicts with `.claude/rules/testing.md:6`. Which one holds, and where?
```

Leave out empty sections, and give Keep as a count plus any line worth defending. Put anything you couldn't decide
under **Needs your call** instead of guessing.

## Judgment calls

- **Line count is not the target.** A short file that lost the one gotcha that mattered is worse than a long one.
  When unsure whether Claude could infer something, check the code; if you still can't tell, keep it.
- **Keep the user's voice.** Rewrite the minimum needed. Teams recognize their own wording, and a full rewrite makes
  the diff hard to review.
- **Conflicts need an owner.** Don't pick a side silently. If git history is available, the newer line is more likely
  the intended one; say so and ask.
- **Personal stays personal.** `CLAUDE.local.md` and `~/.claude` hold one person's preferences. Don't move their
  content into checked-in files without asking.
- **Overrides aren't conflicts.** A nested CLAUDE.md that changes a root rule for its own subtree is doing its job.
- **Older models need more help.** If the scanner flags a subagent or skill pinned to an older model (RS905), keep
  the scaffolding that model relies on, or ask whether the pin is still wanted.
- **AGENTS.md serves other agents too.** Keep tool-neutral content there and Claude-specific notes in CLAUDE.md, with
  CLAUDE.md importing it (`@AGENTS.md`) rather than duplicating it.
- **Generated content is fixed at its source.** Laravel Boost rewrites everything inside `<laravel-boost-guidelines>`
  on `php artisan boost:update`, and other tools mark their output as generated (RS104). An edit there is lost on the
  next run, so propose the change where it survives: a guideline in `.ai/guidelines/` (one at a built-in
  guideline's path overrides it), the tool's config, or a note outside the block. A generated rule that's wrong for
  this repo, such as a script that doesn't exist, is still worth reporting.

## New projects and repos without agent files

With no CLAUDE.md yet, or only what `/init` wrote (RS105), the job is writing a lean file, not trimming one:

1. Find what Claude can't learn from the repo: surprising decisions, commands with prerequisites, conventions that
   differ from the framework's defaults, and anything that must never happen. In a new repo, ask the user; its code
   and history rarely say. In an established one, read CONTRIBUTING, the docs, CI and recent history first, then ask
   about what you found.
2. Write only those lines, each with its reason. Leave out the stack, the layout and the scripts. If nothing
   qualifies, say so and write nothing. A rule nobody gave you is a question for the user, not a line.
3. Check where the file may live. Some repos keep agent config out of git (see CONTRIBUTING and `.gitignore`); then
   propose `CLAUDE.local.md` instead.
4. Turn the must-never-happen items into enforcement (`references/enforcement.md`).
5. Offer `scan.py --strict` in CI, so the file stays lean as the project grows. A CI machine doesn't have this
   skill's folder; `references/enforcement.md` has a recipe.

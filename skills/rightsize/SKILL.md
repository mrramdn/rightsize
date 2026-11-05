---
name: rightsize
description: Audit and slim down the context Claude Code loads (CLAUDE.md, CLAUDE.local.md, AGENTS.md, .claude/rules, skills, subagents, slash commands) using the Claude 5 context-engineering rules, then propose a reviewed diff with before/after token estimates. A bundled scanner finds bare ALWAYS/NEVER rules, duplicated or conflicting instructions, inline playbooks and code, stale paths and scripts, and content Claude can read from the repo itself. Use when the user wants to audit, trim, clean up, rightsize or modernize CLAUDE.md, AGENTS.md, rules, skills or agent prompts; says their instructions are bloated, ignored, contradictory or eating context; or is moving prompts written for older models to Claude 5, even if they never say "rightsize".
license: MIT
compatibility: Built for Claude Code. scripts/scan.py needs Python 3.8 or newer and uses only the standard library. Other Agent Skills clients that can run shell commands work too.
metadata:
  author: mrramdn
  version: "0.1.0"
---

# rightsize

Claude 5 models need far less instruction than the models most CLAUDE.md files were written for. Anthropic removed over
80% of Claude Code's own system prompt with no measurable loss. Every line in an always-loaded file is read on every
turn, and rules written for weaker models get over-applied by stronger ones. The goal is context where each line earns
its place, not the shortest possible file.

The scanner does what code can do reliably: inventory, counting, matching. You do the judgment: what a line is for,
whether Claude would get it wrong without it, and where it belongs.

## Workflow

1. **Scope.** Default to the repository root. Use the path the user names if there is one (a package in a monorepo,
   say). Add `--include-user` only when they ask about their personal setup in `~/.claude`, because those files
   follow them into every project.

2. **Scan.** Run the scanner from this skill's directory, keeping the snapshot outside the repo so it never shows up
   in the diff:

   ```bash
   python3 <this-skill-dir>/scripts/scan.py <repo> --save "${TMPDIR:-/tmp}/rightsize-before.json"
   ```

   Add `--json` if you'd rather parse it. Findings are leads, not verdicts; `references/checks.md` explains each ID
   and its usual false positives. Without Python, take the inventory with Glob and Read and apply the same checks by
   reading.

3. **Read.** Read every file that loads every session, in full, plus enough of the codebase to know what Claude can
   learn on its own: manifests, folder layout, a few representative files, how tests run. "Claude can see this in
   the repo" is the most common reason a line can go, and you can only judge it by looking.

4. **Classify every instruction**, flagged or not, with the test: *what concrete mistake would Claude make in this
   repo without this line?* Then pick a verdict. `references/rubric.md` has the decision questions and the six
   Claude 5 shifts behind them.

   - **keep**: a fact or gotcha Claude can't infer and would get wrong (prices stored as integer cents).
   - **rewrite**: right intent, phrased as a bare rule. State the outcome and the reason (`references/rewrites.md`).
   - **move**: right content, wrong layer. Procedures go to a skill, path-specific rules to a `paths:` rule or nested
     CLAUDE.md, long examples become a pointer to real code.
   - **enforce**: must hold every time and a miss is costly (production data, secrets, destructive commands). Use a
     hook, a permission rule or CI (`references/enforcement.md`), and keep one plain line that says why.
   - **delete**: derivable from the repo, generic advice, persona and step-by-step scaffolding, duplicates, session
     logs, stale references.

5. **Propose, don't write.** Show the report below and the proposed content as a diff, grouped so the user can accept
   or reject each group. A checked-in CLAUDE.md is shared with the team, and a deleted gotcha resurfaces later as a
   bug far from its cause, so nothing changes until the user says which groups to apply. If they told you up front to
   apply without a review, go ahead, and list what you changed.

6. **Apply and measure.** Make the approved edits, create any new skill or rule files (matching the repo's existing
   conventions), then show the before/after:

   ```bash
   python3 <this-skill-dir>/scripts/scan.py <repo> --compare "${TMPDIR:-/tmp}/rightsize-before.json"
   ```

   Write hooks or permission rules only for the enforce items the user approved: settings apply to every session,
   and a too-broad rule blocks work they didn't expect.

7. **Suggest a check.** Offer to run one or two representative tasks against the new context, for example with
   `claude -p` in a git worktree, and compare with the old version. The old version stays in git, so rolling back is
   one command.

## Report

Lead with the numbers, then the verdicts. Quote each instruction briefly with its location so the user can find it.
Before anything is applied, the "after" figure is your estimate for the proposed files (characters / 4); once the
changes are in, the `--compare` numbers replace it.

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
- **Older models need more help.** If the scanner flags a subagent or skill pinned to a pre-Claude-5 model (RS905),
  keep the scaffolding that model relies on, or ask whether the pin is still wanted.
- **AGENTS.md serves other agents too.** Keep tool-neutral content there and Claude-specific notes in CLAUDE.md, with
  CLAUDE.md importing it (`@AGENTS.md`) rather than duplicating it.

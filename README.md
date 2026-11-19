# rightsize

[![test](https://github.com/mrramdn/rightsize/actions/workflows/test.yml/badge.svg)](https://github.com/mrramdn/rightsize/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Claude Code skill that audits and slims down the context Claude loads (CLAUDE.md, AGENTS.md, `.claude/rules`,
skills, subagents) using Anthropic's context-engineering guidance for current Claude models.

Anthropic [removed over 80% of Claude Code's system prompt](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
for Claude 5 generation models with no measurable loss on their coding evals. Most project instruction files still
carry habits from older models: ALWAYS and NEVER in capitals, pasted code examples, deploy runbooks, tech-stack lists,
the same rule in three places. Claude reads all of it on every turn, and stronger models over-apply rules that were
written to get a weaker model's attention. rightsize finds those lines, works out with you what each one is for, and
leaves context where every line earns its place.

## What it does

- **Scans** every context file with a deterministic, standard-library Python scanner: what loads every session versus
  on demand, estimated tokens, and 24 checks for bare rules, shouting, scaffolding, duplicates, conflicts, inline
  playbooks and code, stale paths and scripts, content Claude can read from your manifests, and content a tool
  generated (Laravel Boost, `/init`). It only reads files.
- **Classifies** every instruction, flagged or not, as keep, rewrite, move, enforce or delete, using one test: what
  concrete mistake would Claude make in this repo without this line?
- **Proposes** a diff grouped by verdict. Nothing changes until you say which groups to apply.
- **Enforces** the few rules that must always hold with hooks and permission rules, plus one plain line saying why,
  instead of louder prose.
- **Measures** before and after, from a snapshot of the first scan.

## Example

From the test fixture: a 125-line CLAUDE.md for a Laravel API, two rules files, a review skill and a subagent. This
is the `--compare` output of a real run of 0.1.3, trimmed to the main lines:

```text
Before → after
  every session  ~1,366 → ~520 tokens (-62%)
  on demand      ~223 → ~438 tokens (+96%)
  findings       22 warn, 11 info → 0 warn, 4 info
  changed CLAUDE.md  lines 125 → 10 · every session ~1224 → ~297
  changed .claude/skills/code-review/SKILL.md  lines 20 → 17 · every session ~10 → ~79 · on demand ~130 → ~169
  added   .claude/skills/deploy/SKILL.md  lines 0 → 18 · on demand ~0 → ~215
  removed .claude/rules/frontend.md  lines 9 → 0 · on demand ~48 → ~0
```

The deploy runbook became a manual-only skill and the review checklist merged into the existing review skill (whose
one-word description now says when to use it). The pasted example controller became a pointer to the real one. The
persona, "think step by step", the tech stack, the directory tree and the dated notes were deleted, and so was a
rules file whose two lines named a folder and a script that don't exist. Bare rules got their reasons.
`migrate:fresh` is now blocked by a hook, `.env` by a deny rule, and `config/` edits ask first. The money-in-cents
gotcha stayed. Content that moved into skills now loads on demand, which is why that number grows. Token estimates
are characters ÷ 2.7.

Before 0.1.1 the scanner was also run against real CLAUDE.md files from public repositories (a Laravel Boost app, a
Python SDK, a TypeScript SDK) to cut false alarms, and the skill learned to leave generated Laravel Boost guidelines
to `.ai/guidelines/` instead of editing them in place. 0.1.2 fixes what a field test on a Claude Code plugin, a
desktop app, a new Vite project and a personal `~/.claude` turned up, and its token estimates now track
`claude plugin details`.

## Status

Early: 0.1.3. The scanner is covered by unit and end-to-end tests that CI runs on Python 3.8 and 3.13, and the skill
has four eval cases in the format `claude plugin eval` reads. It has been tuned on real CLAUDE.md files and field
tests, but checks, wording and estimates may still change between 0.1.x releases. Changes are listed in
[CHANGELOG.md](CHANGELOG.md).

## Install

Requires Claude Code and Python 3.8 or newer (standard library only).

As a plugin:

```sh
claude plugin marketplace add mrramdn/rightsize
claude plugin install rightsize@rightsize
```

Then run `/rightsize:rightsize`, or just ask: "my CLAUDE.md is bloated, can you trim it?"

As a personal skill, kept up to date with `git pull`:

```sh
git clone https://github.com/mrramdn/rightsize ~/src/rightsize
mkdir -p ~/.claude/skills
ln -s ~/src/rightsize/skills/rightsize ~/.claude/skills/rightsize
```

Then run `/rightsize`. To share it with a team, copy `skills/rightsize` into the project's `.claude/skills/`.

## Usage

```text
/rightsize                        audit the repository
/rightsize packages/api           audit one package of a monorepo
/rightsize and my ~/.claude too   also audit your personal CLAUDE.md, rules, skills and agents
```

Claude scans, reads, classifies and shows a report like this, followed by the diff:

```markdown
## rightsize: acme-shop

Every session ~1,366 → ~520 tokens (est.) · warnings 22 → 0

### Rewrite (5)
- `CLAUDE.md:39` "NEVER add comments to code." → "Match the comment density of the surrounding code; most files
  here have none."
### Move (3)
- `CLAUDE.md:97-108` deploy steps → new manual-only skill `.claude/skills/deploy/SKILL.md`
### Enforce (3)
- `CLAUDE.md:44` migrate:fresh → PreToolUse hook `.claude/hooks/block-destructive.py`
### Needs your call
- `CLAUDE.md:39` conflicts with `.claude/rules/testing.md:6`. Which one holds, and where?
```

Reply with the groups to apply ("apply rewrite, move and delete; skip enforce for now"). Claude applies them and shows
the before/after.

### New projects

Run `/init` first, then `/rightsize`: it trims what `/init` wrote down to what Claude can't learn from the repo. With
no CLAUDE.md at all, ask for a lean one ("set up a lean CLAUDE.md for this project"); rightsize asks you for the few
things only you know and writes just those. Add `scan.py --strict` to CI to keep it that way.

### The scanner on its own

```sh
python3 skills/rightsize/scripts/scan.py .                 # table report
python3 skills/rightsize/scripts/scan.py . --json          # machine-readable
python3 skills/rightsize/scripts/scan.py . --strict        # exit 1 on any warning, for CI
python3 skills/rightsize/scripts/scan.py . --save          # snapshot; after your edits: --compare
python3 skills/rightsize/scripts/scan.py . --include-user  # also count ~/.claude, synced and plugin skills
```

`--save` without a file name keeps the snapshot outside the repo's files (in `.git/rightsize/`, or the temp folder
outside git), under a name tied to the folder, and `--compare` finds it again.

In GitHub Actions, check out rightsize next to your code:

```yaml
- uses: actions/checkout@v4
- uses: actions/checkout@v4
  with:
    repository: mrramdn/rightsize
    path: .rightsize
- run: python3 .rightsize/skills/rightsize/scripts/scan.py . --strict
```

Or commit a copy of `scan.py` (one file, standard library only) and run that.

## Checks

| Family | IDs | Flags |
|---|---|---|
| Size, origin | RS101–RS105 | memory files over 200 lines, SKILL.md over 500, an AGENTS.md Claude Code isn't reading, Laravel Boost and `/init` output |
| Wording | RS201, RS202, RS301 | ALWAYS/NEVER/MUST with no reason (also WAJIB, JANGAN, HARUS), shouting, persona and step-by-step scaffolding |
| Duplicates, conflicts | RS401, RS402, RS501 | the same instruction in several layers, near-duplicates, one line negating another |
| Bloat | RS601–RS605 | inline code, long procedures and checklists, long sections, dated logs |
| Stale | RS701, RS702 | missing paths, links and @imports; `npm run`, `composer` and `make` targets that don't exist |
| Derivable | RS801, RS802 | dependency lists that restate your manifests, directory trees |
| Metadata | RS901–RS905 | skill and agent frontmatter, description length, models pinned before Claude 5 |

Each check, its false positives and the usual verdict: [`references/checks.md`](skills/rightsize/references/checks.md).

## How it relates to `/doctor prompt-audit`

Claude Code ships `/doctor prompt-audit`, which has Claude review your instruction files for prompting patterns
written for older models. It's worth running. rightsize adds:

- a deterministic scanner: same input, same findings, with an exit code for CI;
- before/after numbers you can paste into a pull request;
- an enforce verdict that turns must-hold rules into hooks and permission rules;
- repository-aware checks: paths, scripts and Make targets against what exists, dependency lists against your
  manifests, and which AGENTS.md files Claude Code actually reads.

## Design

The skill follows its own advice. `SKILL.md` is short and states reasons instead of rules. The rubric, rewrite
patterns, enforcement recipes and check catalog live in `references/` and load only when needed. Counting and
matching live in a script, and judgment stays with Claude.

```text
skills/rightsize/
├── SKILL.md              workflow, verdicts, report format
├── references/
│   ├── rubric.md         the test, five verdicts, where things belong, the six Claude 5 shifts
│   ├── rewrites.md       before/after patterns
│   ├── enforcement.md    permission rules, PreToolUse hooks, CI
│   └── checks.md         every scanner check, false positives, usual verdict
├── scripts/scan.py       the scanner (standard library, Python 3.8+)
└── evals/                four cases in the format `claude plugin eval` reads
```

## Development

```sh
make test    # unit and end-to-end tests (unittest, no dependencies)
make check   # run rightsize on this repository with --strict
```

Fixture context files are stored with a leading underscore (`_CLAUDE.md`, `_claude/`, `_SKILL.md`) so Claude Code
doesn't load them as instructions while you work on this repo. The tests and the eval scaffold scripts copy them to a
temporary directory under their real names.

The evals are real, billed model runs. From `skills/rightsize`:

```sh
claude plugin eval . --allow-tools Write,Edit,Bash --scaffold
```

## Credits

Built on Anthropic's [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
and the Claude Code documentation. Not affiliated with Anthropic.

## License

[MIT](LICENSE)

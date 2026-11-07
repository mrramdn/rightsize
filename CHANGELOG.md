# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A plugin icon, `.claude-plugin/icon.png` (1024 px), for the plugin directory. Its SVG source is
  `.github/brand/icon.svg`.

## [0.1.2] - 2026-11-07

Fixes from a field test of 0.1.1 on a Claude Code plugin, a desktop app, a new Vite project and a personal
`~/.claude`.

### Changed

- Token estimates are characters / 2.7 instead of / 4. Calibrated on 54 plugin skills against `claude plugin details`,
  which the old ratio ran 26-36% under. A skill's every-session cost now includes `when_to_use`.
- `--save` and `--compare` take an optional file. Without one, the snapshot goes into the scanned repo's `.git`
  folder (the temp folder outside git), under a name tied to the folder, so it survives sandboxes that make
  `$TMPDIR` read-only or give each command its own `/tmp`, as `claude plugin eval` runs do. The skill uses this
  instead of a fixed `$TMPDIR/rightsize-before.json`, which two runs at once overwrote.
- The skill finds its scanner through `${CLAUDE_SKILL_DIR}`. Its description is 40% shorter and no longer names a
  model generation.

### Added

- The scanner follows the `instructionFiles` option of Claude Code's cc-plugin-agents-md plugin, from
  `~/.claude/settings.json`, managed settings or `--instruction-files`. With `claude-md-and-agents-md`, AGENTS.md
  loads alongside CLAUDE.md and no longer gets RS103; with `claude-md` it never loads. A note says when the setting
  isn't the default.
- `--include-user` counts skills synced from claude.ai and the skills, agents and commands of enabled plugins, and
  honors `CLAUDE_CONFIG_DIR`. Synced and plugin files are counted, not linted.
- Skill guidance: a path for established repos without agent files; a report shape for new files; no padding or
  invented rules in a new CLAUDE.md; checking what tests and CI assert about context files, and when a tool prints
  what a line repeats, before cutting it; `git apply --check` on proposed diffs; testing a hook on both sides before
  offering it; a CI recipe for the scanner.
- Eval graders reworked after an audit of every grader for false passes and false fails:
  - Each "nothing changed" check now uses the list of created files, plus a byte-for-byte match of CLAUDE.md.
  - File, line-count and `--compare` output checks are regexes.
  - LLM judges read only the final response. A judge on the trace also sees the skill's own example answers, and
    a `tool_used` check passed although its `--compare` call had failed.
- CI runs `claude plugin validate --strict`.

### Fixed

- RS701 skipped missing paths in prohibitions ("Never edit `src/legacy/payments.ts`"). Only mentions of something
  absent ("no separate `x`", "don't create a `x`") are skipped now.
- RS104 marked a hand-written CLAUDE.md as generated when an early line said another file was "auto-generated", and
  tagged its findings "change it at its source". Only a file that marks itself counts now.
- `--compare` accepted a snapshot of another folder, or one taken with other options, and reported meaningless numbers
  (-100%). It now refuses, with exit status 2.
- `--save` to a read-only path ended in a traceback. It now prints the report, says why the snapshot wasn't saved and
  exits 2.
- RS402 and RS501 paired lines from two unrelated skills or subagents. Each loads for its own task, so only lines that
  can share a context are compared.
- The eval case that applies changes can pass when the sandbox refuses writes under `.claude/`, if the run says so and
  shows the file's content. The skill now says to keep such a file in the plan rather than put its content elsewhere.

## [0.1.1] - 2026-11-05

Tuned against real CLAUDE.md files from public repositories: a Laravel Boost app, a Python SDK and a TypeScript SDK.

### Added

- RS104: content a tool generated. Laravel Boost's `<laravel-boost-guidelines>` block is rewritten by
  `php artisan boost:update`, so findings inside it now say to fix them at the source (`.ai/guidelines/`), and the
  skill no longer proposes edits that the next update would undo. Files marked "auto-generated" are flagged too.
- RS105: a CLAUDE.md started by `/init`.
- A "New projects" section in the skill: write a lean CLAUDE.md from the few things Claude can't learn from the repo,
  instead of trimming one. The scanner notes when no CLAUDE.md is read at all.
- FORBIDDEN, PROHIBITED and ONLY count as absolute words (RS201).

### Fixed

- Two files sharing many identical lines (CLAUDE.md and AGENTS.md written by the same tool) produced one RS401
  finding per line, 154 on one repo. They are now one finding naming both files and the shared span.
- RS602 flagged a list of principles as a playbook to move into a skill. It now warns only under a heading that names
  a task (deploy, review, release, setup...) and reports other long lists as info.
- RS701 reported paths mentioned after a negation ("no separate `tailwind.config.js` file").
- Keywords mentioned rather than used ("MUST/SHOULD", 'NEVER') counted as shouting.
- Plugin and `~/.claude` files describe other people's projects, so their paths and commands are no longer checked
  against the current repo; a skill's own `references/` and `scripts/` paths still are.
- Laravel Boost's `<code-snippet>` examples are treated as code, like fenced blocks.

## [0.1.0] - 2026-11-05

### Added

- The `rightsize` skill: scan, read, classify every instruction as keep, rewrite, move, enforce or delete, propose a
  diff grouped by verdict, apply what the user approves, and report before/after token estimates.
- `scripts/scan.py`, a read-only scanner (standard library, Python 3.8+) with 22 checks across size, wording,
  duplicates and conflicts, bloat, stale paths and scripts, derivable content, and skill and agent metadata. It
  follows Claude Code's loading rules: every-session versus on-demand files, `paths:` rules, nested CLAUDE.md,
  `@imports` four hops deep, stripped HTML comments, and when AGENTS.md is read.
- `--json`, `--save`/`--compare` snapshots, `--strict` for CI, `--include-user` for `~/.claude`.
- References: rubric, rewrite patterns, enforcement recipes (permission rules, PreToolUse hooks), check catalog.
- Plugin and marketplace manifests, unit and end-to-end tests, three eval cases for `claude plugin eval`, CI on
  Python 3.8 and 3.13.

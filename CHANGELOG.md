# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

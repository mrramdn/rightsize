# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

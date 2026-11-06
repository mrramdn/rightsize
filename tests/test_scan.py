"""Tests for skills/rightsize/scripts/scan.py.

Fixture context files are stored with a leading underscore (_CLAUDE.md, _claude/,
_SKILL.md) so Claude Code doesn't load them as instructions while you work on this
repo. materialize() copies a fixture into a temporary git repo with the real names.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "rightsize" / "scripts"))

import scan  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
_CONFIG = tempfile.TemporaryDirectory()
_SAVED_ENV = {}


def setUpModule() -> None:
    """Keep the machine's own Claude Code settings out of the results: an empty user folder and no
    managed settings, so every test sees the defaults."""
    for name in ("CLAUDE_CONFIG_DIR", "TMPDIR", "TEMP", "TMP"):
        _SAVED_ENV[name] = scan.os.environ.get(name)
    scan.os.environ.pop("TEMP", None)
    scan.os.environ.pop("TMP", None)
    scan.os.environ["CLAUDE_CONFIG_DIR"] = _CONFIG.name
    scan.managed_settings_paths = lambda: []


def tearDownModule() -> None:
    for name, value in _SAVED_ENV.items():
        if value is None:
            scan.os.environ.pop(name, None)
        else:
            scan.os.environ[name] = value
    _CONFIG.cleanup()
RENAMES = {
    "_claude": ".claude",
    "_CLAUDE.md": "CLAUDE.md",
    "_CLAUDE.local.md": "CLAUDE.local.md",
    "_AGENTS.md": "AGENTS.md",
    "_SKILL.md": "SKILL.md",
}


def materialize(name: str, dest: Path) -> Path:
    source = FIXTURES / name
    for path in sorted(source.rglob("*")):
        parts = [RENAMES.get(part, part) for part in path.relative_to(source).parts]
        target = dest.joinpath(*parts)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (dest / ".git").mkdir(exist_ok=True)
    return dest


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def ids(report: scan.Report, path: str = "") -> list:
    return [f.id for f in report.findings if not path or f.path == path]


def find(report: scan.Report, fid: str, path: str = "", line: int = 0) -> list:
    return [
        f for f in report.findings
        if f.id == fid and (not path or f.path == path) and (not line or f.line == line)
    ]


class TempRepo(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve() / "repo"
        self.root.mkdir()
        (self.root / ".git").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class AcmeShopFixture(unittest.TestCase):
    """The bloated Laravel fixture exercises every family of checks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = materialize("acme-shop", Path(cls._tmp.name).resolve() / "acme-shop")
        cls.report = scan.scan(cls.root)
        cls.files = {f.rel: f for f in cls.report.files}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_load_classes(self) -> None:
        self.assertEqual(self.files["CLAUDE.md"].load, "always")
        self.assertEqual(self.files[".claude/rules/testing.md"].load, "always")
        self.assertEqual(self.files[".claude/rules/frontend.md"].load, "on-demand")
        skill = self.files[".claude/skills/code-review/SKILL.md"]
        self.assertGreater(skill.always_chars, 0)      # name + description in the listing
        self.assertGreater(skill.on_demand_chars, skill.always_chars)

    def test_bare_absolute_rules(self) -> None:
        lines = {f.line for f in find(self.report, "RS201", "CLAUDE.md")}
        self.assertTrue({38, 39, 41, 42, 45, 49} <= lines, lines)

    def test_reasoned_rule_is_emphasis_not_bare(self) -> None:
        self.assertTrue(find(self.report, "RS202", "CLAUDE.md", 44))
        self.assertFalse(find(self.report, "RS201", "CLAUDE.md", 44))

    def test_lowercase_reasoned_rule_is_not_flagged(self) -> None:
        self.assertEqual([f.id for f in self.report.findings if f.path == "CLAUDE.md" and f.line == 43
                          and f.check == "wording"], [])

    def test_scaffolding(self) -> None:
        self.assertEqual({3, 46, 47}, {f.line for f in find(self.report, "RS301", "CLAUDE.md")})

    def test_duplicate_across_layers(self) -> None:
        dup = find(self.report, "RS401", "CLAUDE.md", 38)
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].severity, "warn")
        self.assertIn(".claude/rules/testing.md:3", dup[0].related)
        self.assertIn("CLAUDE.md:49", dup[0].related)

    def test_conflict_between_layers(self) -> None:
        conflict = find(self.report, "RS501", "CLAUDE.md", 39)
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0].related, [".claude/rules/testing.md:6"])

    def test_incidental_negation_is_not_a_conflict(self) -> None:
        self.assertFalse(find(self.report, "RS501", "CLAUDE.md", 43))

    def test_bloat(self) -> None:
        self.assertTrue(find(self.report, "RS601", "CLAUDE.md", 55))
        self.assertEqual({84, 99}, {f.line for f in find(self.report, "RS602", "CLAUDE.md")})
        self.assertTrue(find(self.report, "RS605", "CLAUDE.md", 123))
        self.assertTrue(find(self.report, "RS802", "CLAUDE.md", 23))

    def test_stale_paths(self) -> None:
        messages = " ".join(f.message for f in find(self.report, "RS701"))
        for missing in ("docs/architecture.md", "app/Services/PaymentService.php", "resources/js/components"):
            self.assertIn(missing, messages)
        self.assertNotIn("tests/Feature", messages)

    def test_stale_scripts(self) -> None:
        messages = [f.message for f in find(self.report, "RS702")]
        self.assertTrue(any("composer run analyse" in m for m in messages), messages)
        self.assertTrue(any("npm run lint" in m for m in messages), messages)
        self.assertFalse(any("`composer test`" in m or "run build" in m for m in messages), messages)

    def test_derivable_dependencies(self) -> None:
        found = find(self.report, "RS801", "CLAUDE.md")
        self.assertEqual(len(found), 1)
        self.assertIn("composer.json", found[0].message)

    def test_metadata(self) -> None:
        self.assertTrue(find(self.report, "RS904", ".claude/skills/code-review/SKILL.md"))
        self.assertTrue(find(self.report, "RS905", ".claude/agents/reviewer.md"))

    def test_on_demand_bodies_are_info(self) -> None:
        skill = [f for f in self.report.findings if f.path == ".claude/skills/code-review/SKILL.md"]
        self.assertTrue(skill)
        self.assertTrue(all(f.severity == "info" for f in skill), [(f.id, f.severity) for f in skill])

    def test_line_budget(self) -> None:
        self.assertFalse(find(self.report, "RS101"))
        tight = scan.scan(self.root, max_lines=100)
        self.assertTrue(find(tight, "RS101", "CLAUDE.md"))


class CleanRepo(TempRepo):
    def test_clean_repo_has_no_findings(self) -> None:
        write(self.root, "package.json", '{"scripts": {"dev": "next dev", "test": "vitest"}}')
        write(self.root, "src/db/schema.ts", "export {}\n")
        write(self.root, "src/app/(dashboard)/actions.ts", "export {}\n")
        write(self.root, "CLAUDE.md", """
            # Shop dashboard

            - Server actions live in `src/app/(dashboard)/actions.ts`; the schema is `src/db/schema.ts`.
            - Never import from `src/db` in client components, because it pulls secrets into the bundle.
            - Branches look like `feature/short-name` off `origin/main`; UI imports use `@/components/ui`.
            - Logs go to `storage/logs/app.log`; copy `.env.example` to `.env`; run `npm test` before pushing.
            """)
        report = scan.scan(self.root)
        self.assertEqual([(f.id, f.line, f.message) for f in report.findings], [])

    def test_html_comments_are_free_and_ignored(self) -> None:
        write(self.root, "CLAUDE.md", """
            <!--
            Maintainers: NEVER let this file grow past one screen.
            -->
            # Notes

            Money is integer cents.
            """)
        report = scan.scan(self.root)
        self.assertEqual(ids(report), [])
        claude = report.files[0]
        self.assertLess(claude.always_chars, 40)


class AgentsMd(TempRepo):
    def test_agents_md_alone_is_read(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n\nUse pnpm because the lockfile is pnpm-lock.yaml.\n")
        report = scan.scan(self.root)
        self.assertEqual(report.files[0].load, "always")

    def test_agents_md_next_to_claude_md_is_skipped(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n")
        write(self.root, "CLAUDE.md", "# Claude\n")
        report = scan.scan(self.root)
        agents = next(f for f in report.files if f.rel == "AGENTS.md")
        self.assertEqual(agents.load, "other-agents")
        self.assertEqual(ids(report), ["RS103"])

    def test_imported_agents_md_counts(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n")
        write(self.root, "CLAUDE.md", "# Claude\n\n@AGENTS.md\n")
        report = scan.scan(self.root)
        agents = next(f for f in report.files if f.rel == "AGENTS.md")
        self.assertEqual(agents.load, "always")
        self.assertEqual(agents.note, "imported by CLAUDE.md")
        self.assertEqual(ids(report), [])


class Imports(TempRepo):
    def test_import_is_counted_and_missing_import_is_stale(self) -> None:
        write(self.root, "docs/conventions.md", "Money is integer cents.\n")
        write(self.root, "CLAUDE.md", "# Project\n\nSee @docs/conventions.md and @docs/missing.md.\n")
        report = scan.scan(self.root)
        imported = next(f for f in report.files if f.rel == "docs/conventions.md")
        self.assertEqual((imported.kind, imported.load), ("import", "always"))
        self.assertTrue(any("docs/missing.md" in f.message for f in find(report, "RS701")))

    def test_imports_in_code_spans_are_literal(self) -> None:
        write(self.root, "docs/conventions.md", "x\n")
        write(self.root, "CLAUDE.md", "Write `@docs/conventions.md` to import it.\n")
        report = scan.scan(self.root)
        self.assertEqual([f.rel for f in report.files], ["CLAUDE.md"])


class Metadata(TempRepo):
    def test_skill_name_and_description(self) -> None:
        write(self.root, ".claude/skills/deploy-app/SKILL.md", """
            ---
            name: Deploy_App
            description: >
              Deploy the app to production <server>. Use when asked to deploy.
            ---
            Steps.
            """)
        report = scan.scan(self.root)
        self.assertTrue(find(report, "RS902"))
        self.assertTrue(any("angle brackets" in f.message for f in find(report, "RS903")))

    def test_long_description(self) -> None:
        write(self.root, ".claude/skills/big/SKILL.md",
              "---\nname: big\ndescription: " + "word " * 230 + "\n---\nBody.\n")
        report = scan.scan(self.root)
        self.assertTrue(any("1024" in f.message for f in find(report, "RS903")))

    def test_model_pins(self) -> None:
        write(self.root, ".claude/agents/old.md",
              "---\nname: old\ndescription: Old helper agent for tests.\nmodel: claude-sonnet-4-5\n---\nHi.\n")
        write(self.root, ".claude/agents/new.md",
              "---\nname: new\ndescription: New helper agent for tests.\nmodel: claude-opus-5\n---\nHi.\n")
        report = scan.scan(self.root)
        self.assertEqual([f.path for f in find(report, "RS905")], [".claude/agents/old.md"])

    def test_manual_only_skill_costs_nothing_upfront(self) -> None:
        write(self.root, ".claude/skills/release/SKILL.md",
              "---\nname: release\ndescription: Cut a release of the app and publish notes.\n"
              "disable-model-invocation: true\n---\nSteps.\n")
        report = scan.scan(self.root)
        self.assertEqual(report.files[0].always_chars, 0)

    def test_plugin_layout(self) -> None:
        write(self.root, ".claude-plugin/plugin.json", '{"name": "demo"}')
        write(self.root, "skills/demo/SKILL.md", "---\nname: demo\ndescription: x\n---\nBody.\n")
        write(self.root, "skills/demo/references/notes.md", "Notes.\n")
        report = scan.scan(self.root)
        kinds = {f.rel: (f.kind, f.scope) for f in report.files}
        self.assertEqual(kinds["skills/demo/SKILL.md"], ("skill", "plugin"))
        self.assertEqual(kinds["skills/demo/references/notes.md"], ("reference", "plugin"))
        self.assertTrue(find(report, "RS904", "skills/demo/SKILL.md"))


class Commands(TempRepo):
    def test_make_targets(self) -> None:
        write(self.root, "Makefile", "test:\n\tpytest\n\n.PHONY: test\n")
        write(self.root, "CLAUDE.md", "Run `make test`, then `make lint`.\n\n```bash\n# make sure db runs\nmake test\n```\n")
        report = scan.scan(self.root)
        self.assertEqual([f.message for f in find(report, "RS702")],
                         ["`make lint` but Makefile has no `lint` target."])

    def test_makefile_with_includes_is_not_judged(self) -> None:
        write(self.root, "Makefile", "include tools.mk\n")
        write(self.root, "CLAUDE.md", "Run `make lint`.\n")
        self.assertFalse(find(scan.scan(self.root), "RS702"))

    def test_composer_builtins_are_not_scripts(self) -> None:
        write(self.root, "composer.json", '{"scripts": {"test": "pest"}}')
        write(self.root, "CLAUDE.md", "Run `composer install`, `composer test` and `composer lint`.\n")
        messages = [f.message for f in find(scan.scan(self.root), "RS702")]
        self.assertEqual(len(messages), 1)
        self.assertIn("composer lint", messages[0])


class Frontmatter(unittest.TestCase):
    def test_parser(self) -> None:
        text = textwrap.dedent("""\
            ---
            name: "demo"
            description: |
              Line one.
              Line two.
            paths:
              - "src/**"
              - tests/**
            tags: [a, 'b']
            plain: a long value
              that continues
            ---
            Body
            """)
        fields, body = scan.parse_frontmatter(text)
        self.assertEqual(fields["name"], "demo")
        self.assertEqual(fields["description"], "Line one.\nLine two.")
        self.assertEqual(fields["paths"], ["src/**", "tests/**"])
        self.assertEqual(fields["tags"], ["a", "b"])
        self.assertEqual(fields["plain"], "a long value that continues")
        self.assertEqual(text.splitlines()[body], "Body")


def run_main(root: Path, *args: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scan.main([str(root), *args])
    return code, out.getvalue(), err.getvalue()


class Cli(TempRepo):
    def setUp(self) -> None:
        super().setUp()
        self.tmp = self.root.parent / "tmp"
        self.tmp.mkdir()
        scan.os.environ["TMPDIR"] = str(self.tmp)  # restored by tearDownModule
        self._fallbacks = scan.TEMP_FALLBACKS
        scan.TEMP_FALLBACKS = ()

    def tearDown(self) -> None:
        scan.TEMP_FALLBACKS = self._fallbacks
        super().tearDown()

    def run_main(self, *args: str) -> tuple:
        return run_main(self.root, *args)

    def test_snapshot_compare(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n\n" + "".join("- Rule number %d is here.\n" % i for i in range(60)))
        snapshot = self.root.parent / "before.json"
        self.run_main("--save", str(snapshot))
        write(self.root, "CLAUDE.md", "# App\n\n- Money is integer cents.\n")
        code, out, _ = self.run_main("--json", "--compare", str(snapshot))
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertLess(data["compare"]["after"]["always_tokens"], data["compare"]["before"]["always_tokens"])
        self.assertEqual(data["compare"]["files"][0]["status"], "changed")
        code, out, _ = self.run_main("--compare", str(snapshot))
        self.assertIn("Before → after  (snapshot taken ", out)

    def test_default_snapshot_belongs_to_its_folder(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n\n" + "".join("- Rule number %d is here.\n" % i for i in range(30)))
        code, _, err = self.run_main("--save")
        self.assertEqual(code, 0)
        self.assertIn("snapshot saved to " + str(self.tmp / "rightsize"), err)
        other = self.root.parent / "other"
        write(other, "CLAUDE.md", "# Other\n")
        code, out, err = run_main(other, "--compare")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no snapshot of %s yet" % other, err)
        write(self.root, "CLAUDE.md", "# App\n\n- Money is integer cents.\n")
        code, out, _ = self.run_main("--json", "--compare")
        self.assertEqual(code, 0)
        compared = json.loads(out)["compare"]
        self.assertLess(compared["after"]["always_tokens"], compared["before"]["always_tokens"])

    def test_snapshot_of_another_folder_is_refused(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n")
        snapshot = self.root.parent / "before.json"
        self.run_main("--save", str(snapshot))
        other = self.root.parent / "other"
        write(other, "CLAUDE.md", "# Other\n")
        code, out, err = run_main(other, "--compare", str(snapshot))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("it was taken of %s, not %s" % (self.root, other), err)
        code, _, err = self.run_main("--include-user", "--compare", str(snapshot))
        self.assertEqual(code, 2)
        self.assertIn("include_user", err)

    def test_unwritable_snapshot_is_an_error_not_a_traceback(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n\nMoney is integer cents.\n")
        code, out, err = self.run_main("--save", str(self.root.parent / "missing" / "before.json"))
        self.assertEqual(code, 2)
        self.assertIn("Loaded every session", out)  # the scan itself still prints
        self.assertIn("couldn't save the snapshot", err)
        self.assertNotIn("Traceback", err)

    def test_snapshot_falls_back_to_the_git_folder(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n")
        blocked = self.root.parent / "not-a-folder"
        blocked.write_text("x", encoding="utf-8")
        scan.os.environ["TMPDIR"] = str(blocked)  # mkdir under a file fails, like a read-only temp folder
        code, _, err = self.run_main("--save")
        self.assertEqual(code, 0, err)
        self.assertIn("snapshot saved to " + str(self.root / ".git" / "rightsize"), err)
        self.assertEqual(self.run_main("--compare")[0], 0)
        shutil.rmtree(self.root / ".git")
        code, _, err = self.run_main("--save")
        self.assertEqual(code, 2)
        self.assertIn("found no writable folder", err)

    def test_folder_given_to_save_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            scan.main(["--save", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_strict_exit_codes(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n\nMoney is integer cents.\n")
        self.assertEqual(self.run_main("--strict")[0], 0)
        write(self.root, "CLAUDE.md", "# App\n\nNEVER use floats.\n")
        self.assertEqual(self.run_main("--strict")[0], 1)
        self.assertEqual(self.run_main()[0], 0)

    def test_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            scan.main([str(self.root / "missing")])
        self.assertEqual(raised.exception.code, 2)

    def test_runs_as_a_script(self) -> None:
        script = ROOT / "skills" / "rightsize" / "scripts" / "scan.py"
        result = subprocess.run([sys.executable, str(script), str(self.root), "--json"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tool"], "rightsize")


class RealWorldRegressions(TempRepo):
    """Cases found by running the scanner on public repositories' CLAUDE.md files."""

    def test_copied_file_is_one_finding(self) -> None:
        body = "".join("- Guideline number %d keeps the code base consistent.\n" % i for i in range(40))
        write(self.root, "CLAUDE.md", "# Guidelines\n\n" + body)
        write(self.root, "AGENTS.md", "# Guidelines\n\n" + body)
        dups = find(scan.scan(self.root), "RS401")
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0].path, "CLAUDE.md")
        self.assertIn("40 instructions appear in both AGENTS.md and CLAUDE.md", dups[0].message)
        self.assertEqual(dups[0].related, ["AGENTS.md:3-42"])

    def test_principles_list_is_not_a_playbook(self) -> None:
        items = "".join("%d. **Principle %d**: prefer the smaller change.\n" % (i, i) for i in range(1, 9))
        write(self.root, "CLAUDE.md", "# Principles\n\n" + items + "\n## Deploying\n\n" + items)
        found = sorted((f.line, f.severity) for f in find(scan.scan(self.root), "RS602"))
        self.assertEqual(found, [(3, "info"), (14, "warn")])

    def test_negated_mention_is_not_stale(self) -> None:
        write(self.root, "CLAUDE.md", "- Config is CSS-first; no separate `tailwind.config.js` file is needed.\n"
                                      "- See `docs/missing-guide.md` when the build fails.\n")
        messages = " ".join(f.message for f in find(scan.scan(self.root), "RS701"))
        self.assertNotIn("tailwind.config.js", messages)
        self.assertIn("docs/missing-guide.md", messages)

    def test_keywords_mentioned_not_shouted(self) -> None:
        write(self.root, "CLAUDE.md", "- Findings that miss a MUST/SHOULD requirement from the spec are serious.\n"
                                      "- Quote the spec's 'MUST' wording when you cite it.\n")
        self.assertEqual(ids(scan.scan(self.root)), [])

    def test_forbidden_is_an_absolute_rule(self) -> None:
        write(self.root, "CLAUDE.md", "- FORBIDDEN: `pip install` in this repo.\n")
        self.assertEqual(ids(scan.scan(self.root)), ["RS201"])

    def test_boost_block_is_generated(self) -> None:
        write(self.root, "composer.json", '{"scripts": {"test": "phpunit"}}')
        write(self.root, "CLAUDE.md", """
            # Project notes

            - Invoices are integer cents.

            <laravel-boost-guidelines>
            === foundation rules ===

            - Run `composer run dev` to start everything.

            <code-snippet name="Example" lang="php">
            // ALWAYS return early
            </code-snippet>
            </laravel-boost-guidelines>
            """)
        report = scan.scan(self.root)
        generated = find(report, "RS104")
        self.assertEqual([(f.line, f.severity) for f in generated], [(5, "info")])
        stale = find(report, "RS702")
        self.assertEqual(len(stale), 1)
        self.assertIn("Generated content (RS104)", stale[0].message)
        self.assertFalse(find(report, "RS201"))  # inside <code-snippet>, so code, not an instruction

    def test_generated_marker_and_init_signature(self) -> None:
        write(self.root, "CLAUDE.md", "# CLAUDE.md\n\nThis file provides guidance to Claude Code (claude.ai/code) "
                                      "when working with code in this repository.\n")
        write(self.root, "docs/rules.md", "<!-- x -->\nThis file is auto-generated from docs/src. Rebuild it.\n")
        write(self.root, ".claude/rules/vendor.md", "Do not edit files in vendor/ by hand; update the package.\n")
        report = scan.scan(self.root)
        self.assertEqual([(f.path, f.id) for f in report.findings], [("CLAUDE.md", "RS105")])
        write(self.root, "CLAUDE.md", "# Notes\n\n@docs/rules.md\n")
        self.assertEqual([(f.path, f.id) for f in scan.scan(self.root).findings], [("docs/rules.md", "RS104")])

    def test_plugin_files_describe_other_projects(self) -> None:
        write(self.root, ".claude-plugin/plugin.json", '{"name": "demo"}')
        write(self.root, "skills/demo/SKILL.md", """
            ---
            name: demo
            description: Demo skill used to test which references the scanner checks in plugins.
            ---
            Edit `.ai/guidelines/` or `app/Models/User.php` in the user's project, run `npm run lint`,
            and read `references/guide.md` and `references/missing.md` from this skill.
            """)
        write(self.root, "skills/demo/references/guide.md", "Guide.\n")
        report = scan.scan(self.root)
        self.assertEqual([f.message.split(".")[0] for f in report.findings],
                         ["Referenced path not found: references/missing"])


class FieldTestRegressions(TempRepo):
    """Cases found by field-testing 0.1.1 on real repositories and a personal ~/.claude."""

    def test_prohibition_about_a_missing_file_is_stale(self) -> None:
        write(self.root, "src/app.ts", "export {}\n")
        write(self.root, "package.json", '{"scripts": {"test": "vitest"}}')
        write(self.root, "CLAUDE.md", """
            - Never edit `src/legacy/payments.ts`, because the old invoices still read it.
            - Do not touch files in `src/generated/`, since codegen rewrites them.
            - Don't create a `jest.config.js`, because Vitest is configured in package.json.
            - We no longer run `scripts/old-deploy.sh`; CI deploys now.
            """)
        messages = " ".join(f.message for f in find(scan.scan(self.root), "RS701"))
        self.assertIn("src/legacy/payments.ts", messages)
        self.assertIn("src/generated/", messages)
        self.assertNotIn("jest.config.js", messages)
        self.assertNotIn("scripts/old-deploy.sh", messages)

    def test_mentioning_generated_files_is_not_generated(self) -> None:
        write(self.root, "src/api/types.ts", "export {}\n")
        write(self.root, "CLAUDE.md", """
            # Notes

            Types in `src/api/types.ts` are auto-generated from the OpenAPI spec; edit the spec instead.
            - `src/api/types.ts` is generated by `npx openapi-typescript`, so don't edit it.
            Auto-generated clients live next to the spec.
            - DO NOT EDIT `src/api/types.ts` by hand, because codegen overwrites it.
            """)
        report = scan.scan(self.root)
        self.assertFalse(find(report, "RS104"))
        self.assertFalse([f for f in report.findings if "Generated content" in f.message])

    def test_generated_markers(self) -> None:
        for marker in ("<!-- AUTO-GENERATED by docs-gen. DO NOT EDIT. -->",
                       "# Generated by sync-rules",
                       "<!-- Code generated by protoc-gen-doc. DO NOT EDIT. -->",
                       "This file was automatically generated.",
                       "<!-- Do not edit this file: it is rebuilt from docs/src. -->"):
            write(self.root, "CLAUDE.md", marker + "\n\nMoney is integer cents.\n")
            self.assertIn("RS104", ids(scan.scan(self.root)), marker)

    def test_skills_for_different_tasks_do_not_conflict(self) -> None:
        write(self.root, ".claude/skills/research/SKILL.md", """
            ---
            name: research
            description: Research a topic across many sources and write a report with citations.
            ---
            - Always cite every source you use in the final report.
            """)
        write(self.root, ".claude/skills/trim/SKILL.md", """
            ---
            name: trim
            description: Trim instruction files and report what changed, with token counts.
            ---
            - Never cite every source you use in the final report.
            """)
        self.assertFalse(find(scan.scan(self.root), "RS501"))
        write(self.root, "CLAUDE.md", "# Notes\n\n- Always cite every source you use in the final report.\n")
        conflicts = find(scan.scan(self.root), "RS501")
        self.assertEqual([(f.path, f.related) for f in conflicts],
                         [("CLAUDE.md", [".claude/skills/trim/SKILL.md:5"])])

    def test_token_estimate(self) -> None:
        self.assertEqual(scan.tokens(27), 10)
        self.assertEqual(scan.tokens(28), 11)


class InstructionFiles(TempRepo):
    """The cc-plugin-agents-md plugin's instructionFiles setting decides which AGENTS.md files load."""

    def settings(self, data: dict) -> None:
        (Path(_CONFIG.name) / "settings.json").write_text(json.dumps(data), encoding="utf-8")

    def option(self, value: str, plugin_id: str = "cc-plugin-agents-md@builtin") -> None:
        self.settings({"pluginConfigs": {plugin_id: {"options": {"instructionFiles": value}}}})

    def tearDown(self) -> None:
        settings = Path(_CONFIG.name) / "settings.json"
        if settings.exists():
            settings.unlink()
        super().tearDown()

    def test_both_files_load(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n\nUse pnpm, because the lockfile is pnpm-lock.yaml.\n")
        write(self.root, "CLAUDE.md", "# Claude\n\nMoney is integer cents.\n")
        self.option("claude-md-and-agents-md")
        report = scan.scan(self.root)
        self.assertEqual({f.rel: f.load for f in report.files}, {"AGENTS.md": "always", "CLAUDE.md": "always"})
        self.assertEqual(ids(report), [])
        self.assertIn("instructionFiles: claude-md-and-agents-md", " ".join(report.notes))
        self.assertEqual(report.options["instruction_files"], "claude-md-and-agents-md")

    def test_claude_md_only(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n\nUse pnpm, because the lockfile is pnpm-lock.yaml.\n")
        self.option("agents-md-typo")  # not a mode: ignored
        self.assertEqual(scan.scan(self.root).files[0].load, "always")
        self.option("claude-md", "agents-md@builtin")  # the plugin's name before Claude Code 2.1.285
        report = scan.scan(self.root)
        self.assertEqual(report.files[0].load, "other-agents")
        self.assertIn("instructionFiles: claude-md", find(report, "RS103")[0].message)
        self.assertIn("No CLAUDE.md that Claude Code reads here", " ".join(report.notes))

    def test_plugin_switched_off(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n")
        self.settings({"enabledPlugins": {"cc-plugin-agents-md@builtin": False}})
        self.assertEqual(scan.scan(self.root).files[0].load, "other-agents")

    def test_flag_overrides_settings(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n")
        write(self.root, "CLAUDE.md", "# Claude\n")
        self.option("claude-md")
        report = scan.scan(self.root, instruction_files="claude-md-and-agents-md")
        self.assertEqual(next(f for f in report.files if f.rel == "AGENTS.md").load, "always")

    def test_managed_only_keeps_the_default_numbers(self) -> None:
        write(self.root, "AGENTS.md", "# Shared\n")
        write(self.root, "CLAUDE.md", "# Claude\n")
        self.option("managed-only")
        report = scan.scan(self.root)
        self.assertEqual(next(f for f in report.files if f.rel == "AGENTS.md").load, "other-agents")
        self.assertIn("managed-only", " ".join(report.notes))


class UserScope(TempRepo):
    """--include-user counts personal, synced and plugin skills."""

    def setUp(self) -> None:
        super().setUp()
        config = Path(_CONFIG.name)
        self.created = [config / name for name in ("CLAUDE.md", "skills", "plugins", "settings.json", ".claude.json")]
        write(config, "CLAUDE.md", "Personal notes: answer in English.\n")
        write(config, "skills/mine/SKILL.md",
              "---\nname: mine\ndescription: My own helper for writing release notes from merged PRs.\n---\nBody.\n")
        write(config, "skills/synced/abc_def/docx/SKILL.md",
              "---\nname: docx\ndescription: Create and edit Word documents.\n---\nALWAYS USE THIS FOR WORD FILES.\n")
        write(config, "skills/synced/xyz_uvw/xlsx/SKILL.md",  # another account's skills
              "---\nname: xlsx\ndescription: Create and edit spreadsheets.\n---\nBody.\n")
        write(config, ".claude.json", json.dumps({"oauthAccount": {"organizationUuid": "abc", "accountUuid": "def"}}))
        plugin = self.root.parent / "cache" / "demo" / "1.0.0"
        write(plugin, ".claude-plugin/plugin.json", '{"name": "demo"}')
        write(plugin, "skills/charts/SKILL.md",
              "---\nname: charts\ndescription: Draw charts.\nwhen_to_use: When the user asks for a chart.\n---\n"
              "NEVER use pie charts.\n")
        write(plugin, "agents/helper.md", "---\nname: helper\ndescription: Helps with charts.\n---\nHi.\n")
        off = self.root.parent / "cache" / "off" / "1.0.0"
        write(off, "skills/hidden/SKILL.md", "---\nname: hidden\ndescription: Should not load.\n---\nBody.\n")
        write(config, "plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
            "demo@market": [{"scope": "user", "installPath": str(plugin)}],
            "off@market": [{"scope": "user", "installPath": str(off)}],
        }}))
        write(config, "settings.json", json.dumps({"enabledPlugins": {"demo@market": True, "off@market": False}}))

    def tearDown(self) -> None:
        for path in self.created:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        super().tearDown()

    def test_synced_and_plugin_skills_are_counted_not_linted(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n\nMoney is integer cents.\n")
        report = scan.scan(self.root, include_user=True)
        by_name = {f.path.parent.name if f.kind == "skill" else f.path.stem: f for f in report.files}
        self.assertEqual(set(by_name), {"CLAUDE", "mine", "docx", "charts", "helper"})
        self.assertEqual(by_name["docx"].note, "synced from claude.ai")
        self.assertEqual(by_name["charts"].note, "plugin demo")
        charts = by_name["charts"]
        self.assertEqual(charts.always_chars, len("charts") + len("Draw charts.") + len("When the user asks for a chart.") + 4)
        self.assertEqual(ids(report), [])  # the synced and plugin bodies shout, but they aren't ours to fix
        self.assertFalse(any(f.rel.endswith("hidden/SKILL.md") for f in report.files))

    def test_without_a_known_account_every_synced_folder_counts(self) -> None:
        (Path(_CONFIG.name) / ".claude.json").unlink()
        names = {f.path.parent.name for f in scan.scan(self.root, include_user=True).files if f.kind == "skill"}
        self.assertEqual(names, {"mine", "docx", "xlsx", "charts"})

    def test_scanning_the_user_folder_itself(self) -> None:
        config = Path(_CONFIG.name).resolve()
        report = scan.scan(config)
        personal = next(f for f in report.files if f.path == config / "CLAUDE.md")
        self.assertEqual((personal.scope, personal.load), ("user", "always"))
        self.assertTrue(report.options["include_user"])
        self.assertFalse([n for n in report.notes if "No CLAUDE.md" in n])


class Dogfood(unittest.TestCase):
    def test_this_repo_is_clean(self) -> None:
        report = scan.scan(ROOT)
        self.assertEqual([(f.id, f.path, f.line) for f in report.findings if f.severity == "warn"], [])


if __name__ == "__main__":
    unittest.main()

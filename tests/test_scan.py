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


class Cli(TempRepo):
    def run_main(self, *args: str) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = scan.main([str(self.root), *args])
        return code, out.getvalue()

    def test_snapshot_compare(self) -> None:
        write(self.root, "CLAUDE.md", "# App\n\n" + "".join("- Rule number %d is here.\n" % i for i in range(60)))
        snapshot = self.root.parent / "before.json"
        self.run_main("--save", str(snapshot))
        write(self.root, "CLAUDE.md", "# App\n\n- Money is integer cents.\n")
        code, out = self.run_main("--json", "--compare", str(snapshot))
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertLess(data["compare"]["after"]["always_tokens"], data["compare"]["before"]["always_tokens"])
        self.assertEqual(data["compare"]["files"][0]["status"], "changed")
        code, out = self.run_main("--compare", str(snapshot))
        self.assertIn("Before → after", out)

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


class Dogfood(unittest.TestCase):
    def test_this_repo_is_clean(self) -> None:
        report = scan.scan(ROOT)
        self.assertEqual([(f.id, f.path, f.line) for f in report.findings if f.severity == "warn"], [])


if __name__ == "__main__":
    unittest.main()

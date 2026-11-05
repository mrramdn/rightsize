#!/usr/bin/env python3
"""rightsize scan: deterministic inventory and lint for Claude Code context files.

Finds the files that decide what Claude Code reads (CLAUDE.md, CLAUDE.local.md,
AGENTS.md, .claude/rules, skills, subagents, slash commands and their @imports),
estimates what each one costs, and flags the patterns that Anthropic's Claude 5
context-engineering guidance calls out: absolute rules with no reason, shouting,
duplicated or conflicting instructions, inline code and playbooks, stale
references, and content Claude can read from the repo itself.

It only reads files. It never runs project commands and never edits anything.
Standard library only; Python 3.8 or newer.

    python3 scan.py [ROOT] [--format table|json] [--save FILE] [--compare FILE]
                    [--strict] [--include-user] [--max-lines N]

Exit status: 0 on success, 1 with --strict when any finding is a warning,
2 on a usage error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

VERSION = "0.1.0"

# Thresholds. Each one is a heuristic, not a rule: the skill decides what to do.
MEMORY_MAX_LINES = 200        # always-loaded memory file; override with --max-lines
SKILL_MAX_LINES = 500         # SKILL.md body
DESCRIPTION_MAX_CHARS = 1024  # Agent Skills spec limit for `description`
DESCRIPTION_MIN_CHARS = 40
CODE_BLOCK_MAX = 12           # fenced block in a file that loads every session
CODE_BLOCK_MAX_ON_DEMAND = 40
PROCEDURE_MIN_ITEMS = 8       # numbered steps or checklist items in one run
SECTION_MAX_LINES = 40
TREE_MIN_LINES = 6
DATED_MIN_LINES = 3
DEPENDENCY_MIN_LINES = 4
MAX_IMPORT_DEPTH = 4          # Claude Code follows @imports four hops deep
MAX_WALK_FILES = 100_000
MAX_FILE_BYTES = 2_000_000
MAX_PAIR_FINDINGS = 40        # cap for near-duplicate and conflict findings, each

SKIP_DIRS = {
    ".git", "node_modules", "vendor", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", "out", ".next", ".nuxt",
    ".svelte-kit", ".dart_tool", ".gradle", "Pods", "DerivedData", "target", "coverage",
    ".idea", ".vscode", ".turbo", ".cache", ".parcel-cache", "bower_components",
    ".terraform", ".serverless", ".expo", ".supervise",
}
KEEP_HIDDEN = {".claude", ".agents", ".claude-plugin", ".github"}
CLAUDE_DIR_SKIP = {
    "worktrees", "projects", "todos", "shell-snapshots", "statsig", "plugins", "ide",
    "local", "debug", "file-history", "paste-cache", "session-env", "telemetry", "cache",
}
MEMORY_NAMES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md")
MANIFEST_NAMES = {
    "package.json", "composer.json", "pubspec.yaml", "requirements.txt",
    "pyproject.toml", "go.mod",
}

KNOWN_EXT = {
    "md", "mdx", "txt", "rst", "json", "jsonc", "yaml", "yml", "toml", "ini", "cfg", "conf",
    "env", "lock", "js", "mjs", "cjs", "ts", "mts", "cts", "tsx", "jsx", "vue", "svelte",
    "astro", "py", "pyi", "php", "rb", "go", "rs", "java", "kt", "kts", "swift", "m", "mm",
    "dart", "c", "h", "cc", "cpp", "hpp", "cs", "fs", "ex", "exs", "erl", "scala", "sh",
    "bash", "zsh", "fish", "ps1", "sql", "prisma", "graphql", "gql", "proto", "html", "htm",
    "css", "scss", "sass", "less", "xml", "plist", "gradle", "properties", "tf", "tfvars",
    "hcl", "csv", "ipynb", "blade",
}
RUNTIME_EXT = {"log", "pid", "sock", "tmp", "sqlite", "sqlite3", "db"}
NAMED_FILES = {
    "Dockerfile", "Makefile", "Procfile", "Gemfile", "Justfile", "justfile", "Rakefile",
    "Brewfile", "Caddyfile", "Vagrantfile", "Containerfile",
}
NOT_PATHS = {
    "node.js", "next.js", "nuxt.js", "vue.js", "react.js", "express.js", "nest.js",
    "three.js", "chart.js", "d3.js", "alpine.js", "ember.js", "backbone.js", "p5.js",
    "angular.js", "solid.js", "deno.json",
}
UNTRACKED_OK = {
    ".env", ".env.local", ".env.production", ".env.development", ".env.testing",
    ".env.test", ".env.staging", "auth.json", "key.properties", "local.properties",
    "google-services.json", "GoogleService-Info.plist", ".npmrc", ".pypirc",
    "credentials.json", "secrets.json", "CLAUDE.local.md",
}
COMPOSER_BUILTINS = {
    "about", "archive", "audit", "browse", "home", "bump", "check-platform-reqs",
    "clear-cache", "clearcache", "cc", "config", "create-project", "depends", "why",
    "diagnose", "dump-autoload", "dumpautoload", "exec", "fund", "global", "help", "init",
    "install", "i", "licenses", "list", "outdated", "prohibits", "why-not", "reinstall",
    "remove", "rm", "require", "r", "run-script", "run", "search", "self-update",
    "selfupdate", "show", "info", "status", "suggests", "update", "u", "upgrade",
    "validate",
}
GENERIC_DEP_WORDS = {
    "framework", "core", "utils", "util", "common", "types", "test", "tests", "testing",
    "cli", "sdk", "api", "app", "client", "server", "http", "config", "lint", "lints",
    "plugin", "plugins", "tools", "build", "dev", "node", "php", "dart", "flutter_test",
    "flutter_lints", "build_runner", "eslint-config", "prettier-config", "typescript-config",
    "ui", "web", "data", "auth", "log", "path", "json", "yaml", "async", "collection",
    "meta", "intl", "string", "image", "file", "files", "mock", "mocks", "pint", "sail",
}

STOPWORDS = set("""
a an the and or but if then else when while for to of in on at by from into onto with without
within about as is are be been being was were it its this that these those there here
you your we our us i me my they them their he she his her one ones any all every each some
no not never always must should shall will would can could may might do does did done don
dont doesn don't doesn't avoid please make sure use using used just only also very really
more most less least than so such same other another new old like via per etc e g ie eg
important critical note notes code file files project repo repository thing things way time
work working change changes default instead first next last before after again need needs
want wants get gets got keep keeps kept run runs
yang dan di ke dari untuk dengan ini itu jangan selalu harus tidak boleh pakai gunakan agar
""".split())

ABSOLUTE = re.compile(
    r"\b(ALWAYS|NEVER|MUST(?:\s+NOT)?|DO\s+NOT|DON'T|SHALL(?:\s+NOT)?|REQUIRED|"
    r"WAJIB|JANGAN|HARUS|SELALU|DILARANG)\b"
)
EMPHASIS = re.compile(r"\b(IMPORTANT|CRITICAL|WARNING|MANDATORY|ATTENTION|PENTING)\b|[⚠\U0001f6a8❗‼\U0001f534⛔]")
REASON = re.compile(
    r"\b(because|since|so that|so we|so it|so the|otherwise|or else|to avoid|to prevent|"
    r"to keep|in order to|which|as it|as this|due to|karena|agar|supaya|biar|soalnya|"
    r"sebab|kalau tidak|jika tidak)\b|[—–(]|\s-\s",
    re.IGNORECASE,
)
SECOND_SENTENCE = re.compile(r"[.!?]\s+[A-Z][a-z]")  # "Never X. It breaks Y." explains itself
NEGATION = re.compile(
    r"\b(never|don'?t|do not|does not|must not|mustn'?t|should not|shouldn'?t|cannot|"
    r"can'?t|avoid|no longer|jangan|tidak boleh|dilarang)\b|^(?:no|without)\s",
    re.IGNORECASE,
)
SCAFFOLDING = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bthink (?:carefully )?step[- ]by[- ]step\b",
        r"\btake a deep breath\b",
        r"\byou are an? (?:expert|world[- ]class|senior|seasoned|elite|highly[- ]skilled|"
        r"experienced|professional)\b",
        r"\bact as an? (?:expert|senior|world[- ]class)\b",
        r"\bdouble[- ]check your\b",
        r"\bverify your (?:work|answer|output|response)\b",
        r"\bbe (?:very |extremely )?(?:thorough|careful|meticulous)\b",
        r"\bit is (?:very |extremely |absolutely )?(?:important|crucial|critical|essential|"
        r"vital) (?:that|to)\b",
        r"\bmake sure (?:to|that) (?:you )?always\b",
        r"\bpay (?:close|careful) attention\b",
    )
]
LEAD_MARKER = re.compile(r"^(?:important|critical|note|warning|nb|penting)\s*[:\-\u2014]\s*", re.IGNORECASE)
LIST_PREFIX = re.compile(r"^\s*(?:(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?|>\s+)+")
NUMBERED_ITEM = re.compile(r"^ {0,3}\d{1,3}[.)]\s+\S")
CHECKLIST_ITEM = re.compile(r"^\s{0,3}[-*+]\s+\[[ xX]\]\s")
LIST_OR_TABLE = re.compile(r"^\s*(?:[-*+]\s|\d{1,3}[.)]\s|\|)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
DATED = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?\d{4}-\d{2}-\d{2}\b")
TREE_MARK = re.compile(r"(├──|└──|\|-- |`-- )")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
IMPORT = re.compile(r"(?<![\w`@/])@((?:~/|\.{1,2}/)?[\w.\-][\w./\-]*)")
LINE_SUFFIX = re.compile(r":\d+(?:[-:]\d+)?$")
OLD_MODEL = re.compile(
    r"claude-(?:instant|2|3)(?![\d])|claude-(?:opus|sonnet|haiku)-(?:3|4)(?![\d])", re.IGNORECASE
)
COMMANDS = [
    ("npm", re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+run\s+([\w:.\-]+)")),
    ("npm", re.compile(r"\bnpm\s+(test|t)\b")),
    ("composer", re.compile(r"\bcomposer\s+(?:run-script|run)\s+([\w:.\-]+)")),
    ("composer", re.compile(r"\bcomposer\s+([a-z][\w:.\-]*)")),
    ("make", re.compile(r"(?:^|[\s;&|(])make\s+([A-Za-z0-9_][\w.\-]*)")),
]


# --- data ------------------------------------------------------------------------


@dataclass
class ContextFile:
    path: Path
    rel: str
    kind: str          # memory | rule | skill | agent | command | import | reference
    load: str          # always | on-demand | other-agents
    scope: str         # project | nested | plugin | user | ancestor
    text: str = ""
    lines: int = 0
    chars: int = 0
    always_chars: int = 0
    on_demand_chars: int = 0
    other_chars: int = 0
    fields: Dict[str, object] = field(default_factory=dict)
    body_start: int = 0
    note: str = ""
    lint: bool = True


@dataclass
class Finding:
    id: str
    check: str
    severity: str      # warn | info
    path: str
    line: Optional[int]
    message: str
    evidence: str = ""
    related: List[str] = field(default_factory=list)


@dataclass
class Report:
    root: str
    files: List[ContextFile]
    findings: List[Finding]
    notes: List[str]
    partial: bool = False


# --- helpers ---------------------------------------------------------------------


def tokens(chars: int) -> int:
    return int(math.ceil(chars / 4.0))


def read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def clip(text: str, limit: int = 110) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], int]:
    """Parse the YAML subset used in skill and agent frontmatter.

    Returns the fields and the 0-based index of the first body line. Handles plain
    and quoted scalars, folded and literal block scalars, and simple lists.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
    if end is None:
        return {}, 0
    fields: Dict[str, object] = {}
    i = 1
    while i < end:
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        i += 1
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block = []
            while i < end and (lines[i][:1] in (" ", "\t") or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            joiner = "\n" if value.startswith("|") else " "
            fields[key] = joiner.join(block).strip()
        elif value == "":
            items, nested = [], []
            while i < end and (lines[i][:1] in (" ", "\t", "-") or not lines[i].strip()):
                stripped = lines[i].strip()
                if stripped.startswith("- "):
                    items.append(unquote(stripped[2:]))
                elif stripped:
                    nested.append(stripped)
                i += 1
            fields[key] = items if items else "\n".join(nested)
        elif value.startswith("[") and value.endswith("]"):
            fields[key] = [unquote(v) for v in value[1:-1].split(",") if v.strip()]
        else:
            parts = [value]
            while (
                i < end
                and lines[i][:1] in (" ", "\t")
                and lines[i].strip()
                and not lines[i].strip().startswith("- ")
            ):
                parts.append(lines[i].strip())
                i += 1
            fields[key] = unquote(" ".join(parts))
    return fields, end + 1


def body_lines(cf: ContextFile) -> Iterator[Tuple[int, str, str]]:
    """Yield (1-based line number, line, kind) for the body.

    kind is "text", "code", "fence-open", "fence-close" or "comment". Block-level HTML
    comments are "comment": Claude Code strips them from CLAUDE.md before Claude sees it.
    """
    fence = ""
    in_comment = False
    lines = cf.text.splitlines()
    for idx in range(cf.body_start, len(lines)):
        line = lines[idx]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not fence and (in_comment or (indent <= 3 and stripped.startswith("<!--"))):
            in_comment = "-->" not in stripped
            yield idx + 1, line, "comment"
            continue
        marker = re.match(r"^(`{3,}|~{3,})", stripped) if indent <= 3 else None
        if marker and not fence:
            fence = marker.group(1)
            yield idx + 1, line, "fence-open"
        elif (
            marker
            and fence
            and stripped.rstrip() == marker.group(1)
            and marker.group(1)[0] == fence[0]
            and len(marker.group(1)) >= len(fence)
        ):
            fence = ""
            yield idx + 1, line, "fence-close"
        else:
            yield idx + 1, line, "code" if fence else "text"


def stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize(line: str) -> str:
    text = LIST_PREFIX.sub("", line)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`~]", "", text).strip()
    text = LEAD_MARKER.sub("", text).lower()
    text = re.sub(r"[^\w\s/.\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .-")


def content_words(norm: str) -> Set[str]:
    words = set()
    for raw in re.findall(r"[a-z0-9][a-z0-9_]*", norm):
        if len(raw) < 3 or raw in STOPWORDS or raw.isdigit():
            continue
        word = stem(raw)
        if word not in STOPWORDS:
            words.add(word)
    return words


def strip_inline_code(line: str) -> str:
    return INLINE_CODE.sub(" ", line)


def strip_dot_slash(path: str) -> str:
    return re.sub(r"^(?:\./)+", "", path)


def every_session(cf: ContextFile) -> bool:
    """True when the file's body is in context from the first message on."""
    return cf.load == "always" and cf.kind in ("memory", "import", "rule")


def polarity(line: str) -> str:
    """'neg' for a negated directive, 'pos' for none, 'mixed' when the negation is incidental."""
    item = LEAD_MARKER.sub("", re.sub(r"[*_`~]", "", LIST_PREFIX.sub("", line)).strip())
    if NEGATION.search(" ".join(item.split()[:4])):
        return "neg"
    return "mixed" if NEGATION.search(item) else "pos"


# --- repository index ------------------------------------------------------------


class RepoIndex:
    """One walk over the repo: context files, manifests and a name index."""

    def __init__(self, root: Path):
        self.root = root
        self.by_name: Dict[str, List[str]] = defaultdict(list)
        self.memory: List[Path] = []
        self.claude_dirs: List[Path] = []
        self.agents_dirs: List[Path] = []
        self.manifests: List[Path] = []
        self.partial = False
        self._cache: Dict[Tuple[str, Path], object] = {}
        self._walk()

    def _walk(self) -> None:
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            here = Path(dirpath)
            rel_dir = here.relative_to(self.root).as_posix()
            depth = 0 if rel_dir == "." else rel_dir.count("/") + 1
            kept = []
            for name in dirnames:
                if name in SKIP_DIRS:
                    continue
                if name.startswith(".") and name not in KEEP_HIDDEN:
                    continue
                if here.name == ".claude" and name in CLAUDE_DIR_SKIP:
                    continue
                kept.append(name)
            dirnames[:] = sorted(kept)
            for name in dirnames:
                self.by_name[name].append(name if rel_dir == "." else rel_dir + "/" + name)
                if name == ".claude":
                    self.claude_dirs.append(here / name)
                elif name == ".agents":
                    self.agents_dirs.append(here / name)
            inside_claude = ".claude" in here.relative_to(self.root).parts
            for name in sorted(filenames):
                count += 1
                if count > MAX_WALK_FILES:
                    self.partial = True
                    return
                self.by_name[name].append(name if rel_dir == "." else rel_dir + "/" + name)
                if name in MEMORY_NAMES and (not inside_claude or here.name == ".claude"):
                    self.memory.append(here / name)
                if name in MANIFEST_NAMES and depth <= 2:
                    self.manifests.append(here / name)

    # Paths -------------------------------------------------------------------------

    def exists(self, candidate: str, base: Path) -> bool:
        for start in (base, self.root):
            try:
                if (start / candidate).exists():
                    return True
            except OSError:
                continue
        return False

    def suffix_exists(self, candidate: str) -> bool:
        tail = candidate.strip("/")
        name = tail.split("/")[-1]
        return any(p == tail or p.endswith("/" + tail) for p in self.by_name.get(name, []))

    def nearest(self, start: Path, name: str) -> Optional[Path]:
        current = start
        while True:
            if (current / name).is_file():
                return current / name
            if current == self.root or self.root not in current.parents:
                return None
            current = current.parent

    # Manifests ---------------------------------------------------------------------

    def _load_json(self, path: Path) -> dict:
        key = ("json", path)
        if key not in self._cache:
            try:
                self._cache[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._cache[key] = {}
        value = self._cache[key]
        return value if isinstance(value, dict) else {}

    def package_scripts(self, path: Path) -> Set[str]:
        return set((self._load_json(path).get("scripts") or {}).keys())

    def composer_scripts(self, path: Path) -> Set[str]:
        return set((self._load_json(path).get("scripts") or {}).keys())

    def make_targets(self, path: Path) -> Optional[Set[str]]:
        """Targets in a Makefile, or None when it includes others we can't see."""
        key = ("make", path)
        if key not in self._cache:
            text = read_text(path) or ""
            if re.search(r"^-?include\s", text, re.MULTILINE):
                self._cache[key] = None
            else:
                targets: Set[str] = set()
                for line in text.splitlines():
                    if line.startswith(("\t", " ", "#")):
                        continue
                    match = re.match(r"^([^:=#]+?)\s*::?(?!=)", line)
                    if match:
                        targets.update(t for t in match.group(1).split() if "%" not in t)
                self._cache[key] = targets
        return self._cache[key]  # type: ignore[return-value]

    def dependency_words(self) -> Tuple[Dict[str, str], List[str]]:
        """Map lowercase dependency names (and short forms) to their manifest."""
        words: Dict[str, str] = {}
        used: List[str] = []

        def add(name: str, manifest: str) -> None:
            name = name.strip().lower()
            if not name or name in ("php", "python", "go") or name.startswith(("ext-", "lib-")):
                return
            forms = {name}
            if "/" in name:
                vendor, short = name.rsplit("/", 1)
                forms.add(short)
                if short == "framework":
                    forms.add(vendor.lstrip("@"))
            for form in forms:
                if len(form) >= 3 and form not in GENERIC_DEP_WORDS:
                    words.setdefault(form, manifest)

        for path in self.manifests:
            rel = path.relative_to(self.root).as_posix()
            before = len(words)
            if path.name in ("package.json", "composer.json"):
                data = self._load_json(path)
                for section in ("dependencies", "devDependencies", "peerDependencies",
                                "require", "require-dev"):
                    for name in (data.get(section) or {}):
                        add(name, rel)
            elif path.name == "pubspec.yaml":
                section = None
                for line in (read_text(path) or "").splitlines():
                    top = re.match(r"^([A-Za-z_]+):", line)
                    if top:
                        section = top.group(1)
                        continue
                    item = re.match(r"^  ([A-Za-z_][\w]*):", line)
                    if item and section in ("dependencies", "dev_dependencies"):
                        add(item.group(1), rel)
            elif path.name == "requirements.txt":
                for line in (read_text(path) or "").splitlines():
                    item = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", line)
                    if item and not line.lstrip().startswith(("#", "-")):
                        add(item.group(1), rel)
            elif path.name == "pyproject.toml":
                try:
                    import tomllib  # type: ignore[import-not-found]
                except ImportError:
                    continue
                try:
                    data = tomllib.loads(read_text(path) or "")
                except ValueError:
                    continue
                for spec in (data.get("project") or {}).get("dependencies") or []:
                    item = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", str(spec))
                    if item:
                        add(item.group(1), rel)
                poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
                for name in poetry:
                    add(name, rel)
            elif path.name == "go.mod":
                for line in (read_text(path) or "").splitlines():
                    item = re.match(r"^\s*(?:require\s+)?([\w.\-]+/[\w./\-]+)\s+v\d", line)
                    if item:
                        add(item.group(1), rel)
            if len(words) > before:
                used.append(rel)
        return words, used


# --- discovery -------------------------------------------------------------------


def git_root(start: Path) -> Optional[Path]:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def has_claude_md(directory: Path) -> bool:
    return any(
        (directory / name).is_file()
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")
    )


def display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        home = Path.home()
        try:
            return "~/" + path.relative_to(home).as_posix()
        except ValueError:
            return os.path.relpath(path, root)


def load_file(path: Path, root: Path, kind: str, load: str, scope: str) -> Optional[ContextFile]:
    text = read_text(path)
    if text is None:
        return None
    cf = ContextFile(path=path, rel=display(path, root), kind=kind, load=load, scope=scope)
    cf.text = text
    cf.lines = len(text.splitlines())
    cf.chars = len(text)
    if kind in ("skill", "agent", "command", "rule"):
        cf.fields, cf.body_start = parse_frontmatter(text)
    if kind == "rule" and cf.fields.get("paths") and load == "always":
        load = "on-demand"
    if kind == "reference":
        cf.lint = False
    set_load(cf, load)
    return cf


def set_load(cf: ContextFile, load: str) -> None:
    """Record when the file is read and what that costs."""
    cf.load = load
    cf.always_chars = cf.on_demand_chars = cf.other_chars = 0
    stripped = cf.kind in ("memory", "import")  # Claude Code strips HTML comments from these
    body_chars = sum(
        len(line) + 1 for _, line, kind in body_lines(cf) if not (stripped and kind == "comment")
    )
    if load == "other-agents":
        cf.other_chars = body_chars
    elif cf.kind in ("skill", "agent", "command"):
        description = str(cf.fields.get("description") or "")
        name = str(cf.fields.get("name") or cf.path.parent.name)
        manual = str(cf.fields.get("disable-model-invocation", "")).lower() == "true"
        if load == "always" and not manual:
            cf.always_chars = len(name) + len(description) + 4
        cf.on_demand_chars = body_chars
    elif load == "always":
        cf.always_chars = body_chars
    else:
        cf.on_demand_chars = body_chars


def plugin_dirs(root: Path, key: str, default: str) -> List[Path]:
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    value = data.get(key) if isinstance(data, dict) else None
    paths = [value] if isinstance(value, str) else (value if isinstance(value, list) else [])
    found = [root / default] + [root / p for p in paths if isinstance(p, str)]
    return [p for p in found if p.is_dir()]


def discover(root: Path, index: RepoIndex, include_user: bool) -> List[ContextFile]:
    files: List[ContextFile] = []
    by_path: Dict[Path, ContextFile] = {}

    def add(path: Path, kind: str, load: str, scope: str) -> None:
        resolved = path.resolve()
        if resolved in by_path or not path.is_file():
            return
        cf = load_file(path, root, kind, load, scope)
        if cf:
            by_path[resolved] = cf
            files.append(cf)

    # Claude Code reads AGENTS.md only when no CLAUDE.md, .claude/CLAUDE.md or
    # CLAUDE.local.md exists in the working directory or above it (default setting).
    agents_mode = not any(has_claude_md(d) for d in [root, *root.parents])

    # Memory files inside ROOT, plus ancestors up to the git root.
    for path in index.memory:
        parent = path.parent
        home = parent.parent if parent.name == ".claude" else parent
        top = home == root
        load = "always" if top else "on-demand"
        if path.name == "AGENTS.md" and (not agents_mode or (not top and has_claude_md(home))):
            load = "other-agents"
        add(path, "memory", load, "project" if top else "nested")
    repo = git_root(root)
    if repo and repo != root:
        for ancestor in root.parents:
            for name in MEMORY_NAMES:
                load = "other-agents" if name == "AGENTS.md" and not agents_mode else "always"
                add(ancestor / name, "memory", load, "ancestor")
            if ancestor == repo:
                break

    def add_skills(directory: Path, scope: str, load: str) -> None:
        if not directory.is_dir():
            return
        for skill in sorted(directory.glob("*/SKILL.md")):
            add(skill, "skill", load, scope)
            for extra in sorted(skill.parent.rglob("*.md")):
                parts = extra.relative_to(skill.parent).parts
                if extra.name != "SKILL.md" and "evals" not in parts:
                    add(extra, "reference", "on-demand", scope)

    def add_all(directory: Path, kind: str, scope: str, load: str) -> None:
        if directory.is_dir():
            for path in sorted(directory.rglob("*.md")):
                add(path, kind, load, scope)

    def add_claude_dir(base: Path, scope: str, load: str) -> None:
        add_all(base / "rules", "rule", scope, load)
        add_skills(base / "skills", scope, load)
        add_all(base / "agents", "agent", scope, load)
        add_all(base / "commands", "command", scope, load)

    for claude_dir in index.claude_dirs:
        top = claude_dir.parent == root
        add_claude_dir(claude_dir, "project" if top else "nested", "always" if top else "on-demand")
    for agents_dir in index.agents_dirs:
        add_skills(agents_dir / "skills", "project", "other-agents")
    if (root / ".claude-plugin" / "plugin.json").is_file():
        for directory in plugin_dirs(root, "skills", "skills"):
            add_skills(directory, "plugin", "always")
        for directory in plugin_dirs(root, "agents", "agents"):
            add_all(directory, "agent", "plugin", "always")
        for directory in plugin_dirs(root, "commands", "commands"):
            add_all(directory, "command", "plugin", "always")
    if include_user:
        user = Path.home() / ".claude"
        add(user / "CLAUDE.md", "memory", "always", "user")
        if user.is_dir():
            add_claude_dir(user, "user", "always")

    # @imports from memory files, resolved relative to the importing file.
    queue = [(cf, 0) for cf in files if cf.kind == "memory"]
    while queue:
        cf, depth = queue.pop(0)
        if depth >= MAX_IMPORT_DEPTH:
            continue
        for _, line, kind in body_lines(cf):
            if kind != "text":
                continue
            for token in IMPORT.findall(strip_inline_code(line)):
                token = token.rstrip(".,;:")
                target = (Path.home() / token[2:]) if token.startswith("~/") else cf.path.parent / token
                if not target.is_file():
                    continue
                known = by_path.get(target.resolve())
                if known is None:
                    imported = load_file(target, root, "import", cf.load, cf.scope)
                    if imported:
                        imported.note = "imported by " + cf.rel
                        by_path[target.resolve()] = imported
                        files.append(imported)
                        queue.append((imported, depth + 1))
                elif known.load == "other-agents" and cf.load != "other-agents":
                    set_load(known, cf.load)  # e.g. AGENTS.md pulled in by @AGENTS.md
                    known.note = "imported by " + cf.rel
                    queue.append((known, depth + 1))
    return files


# --- checks ----------------------------------------------------------------------


class Checker:
    def __init__(self, root: Path, index: RepoIndex, files: List[ContextFile], max_lines: int):
        self.root = root
        self.index = index
        self.files = files
        self.max_lines = max_lines
        self.findings: List[Finding] = []

    def add(self, fid: str, check: str, severity: str, cf: ContextFile, line: Optional[int],
            message: str, evidence: str = "", related: Optional[List[str]] = None) -> None:
        self.findings.append(
            Finding(fid, check, severity, cf.rel, line, message, clip(evidence), related or [])
        )

    @staticmethod
    def level(cf: ContextFile) -> str:
        return "warn" if every_session(cf) else "info"

    def run(self) -> List[Finding]:
        lintable = [cf for cf in self.files if cf.lint and cf.load != "other-agents"]
        for cf in self.files:
            self.check_meta(cf)
        for cf in lintable:
            self.check_size(cf)
            self.check_lines(cf)
            self.check_blocks(cf)
            self.check_refs(cf)
        self.check_pairs([cf for cf in self.files if cf.lint])
        self.check_derivable([cf for cf in lintable if cf.load == "always"])
        self.check_agents_md()
        order = {"warn": 0, "info": 1}
        self.findings.sort(key=lambda f: (order[f.severity], f.path, f.line or 0, f.id))
        return self.findings

    # Size and metadata ------------------------------------------------------------

    def check_size(self, cf: ContextFile) -> None:
        body = cf.lines - cf.body_start
        if cf.kind in ("memory", "import", "rule") and cf.load == "always" and body > self.max_lines:
            self.add("RS101", "size", "warn", cf, None,
                     "%d lines load into every session (target %d or fewer). Keep what Claude "
                     "can't learn from the repo; move procedures into skills." % (body, self.max_lines))
        if cf.kind == "skill" and body > SKILL_MAX_LINES:
            self.add("RS102", "size", "warn", cf, None,
                     "SKILL.md body is %d lines (keep it under %d); move detail into "
                     "references/ files." % (body, SKILL_MAX_LINES))

    def check_meta(self, cf: ContextFile) -> None:
        model = str(cf.fields.get("model") or "")
        if model and OLD_MODEL.search(model):
            self.add("RS905", "metadata", "info", cf, 1,
                     "Pins %s, a pre-Claude-5 model. The trimming advice targets Claude 5 models; "
                     "keep scaffolding this model still needs." % model)
        if cf.kind not in ("skill", "agent"):
            return
        if not cf.fields:
            self.add("RS901", "metadata", "warn", cf, 1,
                     "No frontmatter. Add `name` and `description` so Claude knows when to use it.")
            return
        name = str(cf.fields.get("name") or "")
        description = str(cf.fields.get("description") or "")
        if not name or not description:
            missing = " and ".join(k for k, v in (("name", name), ("description", description)) if not v)
            self.add("RS901", "metadata", "warn", cf, 1, "Frontmatter is missing %s." % missing)
        if cf.kind == "skill" and name:
            folder = cf.path.parent.name
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64 or name != folder:
                self.add("RS902", "metadata", "warn", cf, 1,
                         "Skill name '%s' should be lowercase-hyphenated, 64 characters at most, "
                         "and match its folder '%s'." % (name, folder))
        if cf.kind == "skill" and description:
            if len(description) > DESCRIPTION_MAX_CHARS:
                self.add("RS903", "metadata", "warn", cf, 1,
                         "Description is %d characters; the Agent Skills spec allows %d."
                         % (len(description), DESCRIPTION_MAX_CHARS))
            if "<" in description or ">" in description:
                self.add("RS903", "metadata", "warn", cf, 1,
                         "Description contains angle brackets, which skill uploads reject.")
            if len(description) < DESCRIPTION_MIN_CHARS:
                self.add("RS904", "metadata", "info", cf, 1,
                         "Description is only %d characters. It's all Claude sees when deciding "
                         "to load the skill: say what it does and when to use it." % len(description))

    # Line-level wording -----------------------------------------------------------

    def check_lines(self, cf: ContextFile) -> None:
        rows = list(body_lines(cf))
        for pos, (number, line, kind) in enumerate(rows):
            if kind != "text" or not line.strip() or HEADING.match(line):
                continue
            text = strip_inline_code(line)
            following = ""
            if pos + 1 < len(rows):
                _, nxt, nxt_kind = rows[pos + 1]
                if nxt_kind == "text" and nxt.strip() and not LIST_OR_TABLE.match(nxt) and not HEADING.match(nxt):
                    following = nxt
            letters = [c for c in text if c.isalpha()]
            shouting = len(letters) >= 15 and sum(c.isupper() for c in letters) / len(letters) >= 0.7
            absolute = ABSOLUTE.search(text)
            explained = any(
                REASON.search(part) or SECOND_SENTENCE.search(part)
                for part in (text, strip_inline_code(following))
            )
            if absolute and not explained:
                self.add("RS201", "wording", self.level(cf), cf, number,
                         "Absolute rule with no reason. Give the reason or the outcome you want, or "
                         "enforce it with a hook or permission if it must always hold.", line)
            elif absolute or shouting or EMPHASIS.search(text):
                self.add("RS202", "wording", self.level(cf), cf, number,
                         "Shouted or emphasized instruction. State it plainly with the reason; "
                         "emphasis makes current models over-apply it.", line)
            for pattern in SCAFFOLDING:
                match = pattern.search(text)
                if match:
                    self.add("RS301", "wording", self.level(cf), cf, number,
                             "Prompt scaffolding written for older models (\"%s\"). Current models "
                             "do this unprompted; delete it or replace it with a concrete check."
                             % match.group(0), line)
                    break

    # Block-level structure --------------------------------------------------------

    def check_blocks(self, cf: ContextFile) -> None:
        rows = list(body_lines(cf))
        always = every_session(cf)
        # Fenced code.
        start = None
        for number, line, kind in rows:
            if kind == "fence-open":
                start = number
            elif kind == "fence-close" and start is not None:
                length = number - start - 1
                if always and length > CODE_BLOCK_MAX:
                    self.add("RS601", "bloat", "warn", cf, start,
                             "Inline code block (%d lines) loaded every session. Point to a real "
                             "file that shows the pattern instead." % length)
                elif not always and length > CODE_BLOCK_MAX_ON_DEMAND:
                    self.add("RS601", "bloat", "info", cf, start,
                             "Long code block (%d lines). Point to real code or move it into a "
                             "references/ file." % length)
                start = None
        # Long procedures and checklists.
        for pattern, label in ((NUMBERED_ITEM, "numbered steps"), (CHECKLIST_ITEM, "checklist items")):
            run_start, count = None, 0
            for number, line, kind in rows + [(10 ** 9, "<end>", "text")]:
                if kind == "text" and pattern.match(line):
                    if run_start is None:
                        run_start = number
                    count += 1
                elif kind != "text" or not line.strip() or line[:1] in (" ", "\t"):
                    continue
                else:
                    if run_start is not None and count >= PROCEDURE_MIN_ITEMS:
                        if always:
                            message = ("%d %s loaded every session. If they're for one kind of task, "
                                       "move them into a skill so they load only when needed." % (count, label))
                        else:
                            message = ("%d %s. Fine in a skill if every step matters; cut the ones "
                                       "Claude would do anyway." % (count, label))
                        self.add("RS602", "bloat", self.level(cf), cf, run_start, message)
                    run_start, count = None, 0
        # Long sections.
        if always:
            heads = [(len(m.group(1)), number, m.group(2))
                     for number, line, kind in rows if kind == "text"
                     for m in [HEADING.match(line)] if m]
            last = rows[-1][0] if rows else 0
            for i, (level, number, title) in enumerate(heads):
                if level < 2:
                    continue
                end = next((n for lv, n, _ in heads[i + 1:] if lv <= level), last + 1)
                if end - number > SECTION_MAX_LINES:
                    self.add("RS603", "bloat", "info", cf, number,
                             "Section '%s' is %d lines and loads every session. Consider a skill, a "
                             "path-scoped rule or a nested CLAUDE.md." % (clip(title, 40), end - number))
        # Directory trees and dated logs.
        tree = [number for number, line, _ in rows if TREE_MARK.search(line)]
        if len(tree) >= TREE_MIN_LINES:
            self.add("RS802", "derivable", self.level(cf), cf, tree[0],
                     "Directory tree (%d lines). Claude can list the repo itself; keep only the "
                     "parts that surprise." % len(tree))
        dated = [number for number, line, kind in rows if kind == "text" and DATED.match(line)]
        if always and len(dated) >= DATED_MIN_LINES:
            self.add("RS605", "bloat", "info", cf, dated[0],
                     "%d dated log entries. Session history belongs in auto-memory or git, not in "
                     "instructions that load every session." % len(dated))

    # References -------------------------------------------------------------------

    def path_candidate(self, token: str) -> Optional[str]:
        value = unquote(token.strip())
        value = LINE_SUFFIX.sub("", value.rstrip(".,;:"))
        if not value or len(value) > 200 or any(c.isspace() for c in value):
            return None
        if value.startswith(("/", "~", "$", "-", "#", "@", "<")) or "://" in value:
            return None
        if any(c in value for c in "*?<>{}[]|=,;$%^\\\"'!"):
            return None
        bare = value.rstrip("/")
        name = bare.split("/")[-1]
        ext = name.rsplit(".", 1)[1].lower() if "." in name else ""
        if ext in RUNTIME_EXT or value.lower() in NOT_PATHS:
            return None
        if strip_dot_slash(bare).split("/")[0] in SKIP_DIRS:
            return None
        if "/" in bare or value.endswith("/"):
            return value
        if ext in KNOWN_EXT or name in NAMED_FILES:
            return value
        return None

    def check_refs(self, cf: ContextFile) -> None:
        base = cf.path.parent
        rows = list(body_lines(cf))
        reported: Set[str] = set()
        for number, line, kind in rows:
            if kind == "code" and not line.lstrip().startswith(("#", "//", "--", ";")):
                self.check_commands(cf, number, line)
            elif kind == "text":
                for span in INLINE_CODE.findall(line):
                    self.check_commands(cf, number, span)
            if kind != "text":
                continue
            tokens_ = INLINE_CODE.findall(line) + [
                link for link in MD_LINK.findall(line) if not re.match(r"^[a-z]+:|#", link)
            ]
            if cf.kind in ("memory", "import"):
                tokens_ += [t for t in IMPORT.findall(strip_inline_code(line)) if "/" in t or "." in t]
            for token in tokens_:
                candidate = self.path_candidate(token.split("#")[0])
                if not candidate or candidate in reported:
                    continue
                if self.index.exists(candidate, base):
                    continue
                bare = candidate.rstrip("/")
                has_slash = "/" in bare
                name = bare.split("/")[-1]
                if name in UNTRACKED_OK:
                    continue
                if has_slash:
                    has_ext = "." in name[1:]
                    tail = strip_dot_slash(bare)
                    first = tail.split("/")[0]
                    if not has_ext and not candidate.startswith(".") and not self.index.exists(first, base):
                        continue  # probably a branch name or an identifier, not a path
                    if not candidate.startswith("../") and self.index.suffix_exists(tail):
                        continue  # a partial path that exists deeper in the tree
                    severity = "warn"
                else:
                    if self.index.by_name.get(name):
                        continue
                    severity = "info"
                reported.add(candidate)
                self.add("RS701", "stale", severity, cf, number,
                         "Referenced path not found: %s. Fix or remove the reference so Claude "
                         "doesn't go looking for it." % candidate, line)

    def check_commands(self, cf: ContextFile, number: int, text: str) -> None:
        start = cf.path.parent
        for tool, pattern in COMMANDS:
            for match in pattern.finditer(text):
                name = match.group(1)
                if tool == "npm":
                    manifest = self.index.nearest(start, "package.json")
                    script = "test" if name == "t" else name
                    if manifest is None:
                        self.add("RS702", "stale", "info", cf, number,
                                 "`%s` but there is no package.json here." % match.group(0).strip(), text)
                    elif script not in self.index.package_scripts(manifest):
                        self.add("RS702", "stale", "warn", cf, number,
                                 "`%s` but %s has no `%s` script." % (match.group(0).strip(),
                                 display(manifest, self.root), script), text)
                elif tool == "composer":
                    if name in COMPOSER_BUILTINS and "run" not in match.group(0).split()[1]:
                        continue
                    if name in ("run", "run-script"):
                        continue
                    manifest = self.index.nearest(start, "composer.json")
                    if manifest is None:
                        self.add("RS702", "stale", "info", cf, number,
                                 "`%s` but there is no composer.json here." % match.group(0).strip(), text)
                    elif name not in self.index.composer_scripts(manifest):
                        self.add("RS702", "stale", "warn", cf, number,
                                 "`%s` but %s has no `%s` script." % (match.group(0).strip(),
                                 display(manifest, self.root), name), text)
                elif tool == "make":
                    manifest = self.index.nearest(start, "Makefile")
                    if manifest is None:
                        self.add("RS702", "stale", "info", cf, number,
                                 "`make %s` but there is no Makefile here." % name, text)
                        continue
                    targets = self.index.make_targets(manifest)
                    if targets is not None and name not in targets:
                        self.add("RS702", "stale", "warn", cf, number,
                                 "`make %s` but %s has no `%s` target." % (name,
                                 display(manifest, self.root), name), text)

    # Across files -----------------------------------------------------------------

    def check_pairs(self, files: Sequence[ContextFile]) -> None:
        entries = []  # (cf, line number, raw, normalized, words, negated)
        for cf in files:
            for number, line, kind in body_lines(cf):
                if kind != "text" or not line.strip() or HEADING.match(line):
                    continue
                if re.match(r"^\s*\|?\s*:?-{3,}", line):
                    continue
                norm = normalize(line)
                if len(norm.split()) < 4:
                    continue
                entries.append((cf, number, line, norm, content_words(norm), polarity(line)))

        def where(entry) -> str:
            return "%s:%d" % (entry[0].rel, entry[1])

        def claude_loads(entry) -> bool:
            return entry[0].load in ("always", "on-demand")

        groups: Dict[str, List[int]] = defaultdict(list)
        for i, entry in enumerate(entries):
            groups[entry[3]].append(i)
        exact_pairs: Set[Tuple[int, int]] = set()
        for members in groups.values():
            if len(members) < 2:
                continue
            for a in members:
                for b in members:
                    if a < b:
                        exact_pairs.add((a, b))
            first = entries[members[0]]
            loaded = [entries[m] for m in members if claude_loads(entries[m])]
            severity = "warn" if len(loaded) >= 2 and any(every_session(e[0]) for e in loaded) else "info"
            message = "Same instruction in %d places. Keep one, in the layer where it applies." % len(members)
            if any(entries[m][0].load == "other-agents" for m in members):
                message += " One copy is for other agents; consider importing it with @AGENTS.md."
            self.add("RS401", "duplicate", severity, first[0], first[1], message, first[2],
                     [where(entries[m]) for m in members[1:]])

        postings: Dict[str, List[int]] = defaultdict(list)
        for i, entry in enumerate(entries):
            for word in entry[4]:
                postings[word].append(i)
        shared: Dict[Tuple[int, int], int] = defaultdict(int)
        for ids in postings.values():
            if len(ids) > 200:
                continue  # too common to be informative
            for x in range(len(ids)):
                for y in range(x + 1, len(ids)):
                    shared[(ids[x], ids[y])] += 1
        near = conflicts = 0
        for (a, b), count in sorted(shared.items()):
            if count < 2 or (a, b) in exact_pairs:
                continue
            ea, eb = entries[a], entries[b]
            if ea[0] is eb[0] and abs(ea[1] - eb[1]) <= 2:
                continue
            wa, wb = ea[4], eb[4]
            if ea[5] == eb[5]:
                if min(len(wa), len(wb)) >= 2:
                    jaccard = count / float(len(wa | wb))
                    if jaccard >= 0.8 and near < MAX_PAIR_FINDINGS:
                        near += 1
                        self.add("RS402", "duplicate", "info", ea[0], ea[1],
                                 "Near-duplicate of %s. Merge them into one instruction." % where(eb),
                                 ea[2], [where(eb)])
            elif {ea[5], eb[5]} == {"neg", "pos"}:
                overlap = count / float(min(len(wa), len(wb)))
                if overlap >= 0.66 and conflicts < MAX_PAIR_FINDINGS:
                    conflicts += 1
                    self.add("RS501", "conflict", "info", ea[0], ea[1],
                             "Possible conflict with %s: one says do, the other says don't. Decide "
                             "which holds and say when." % where(eb), ea[2], [where(eb)])

    def check_derivable(self, files: Sequence[ContextFile]) -> None:
        words, manifests = self.index.dependency_words()
        if not words:
            return
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
            + r")(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        for cf in files:
            hits, names = [], []
            for number, line, kind in body_lines(cf):
                if kind == "text" and LIST_OR_TABLE.match(line):
                    item = LIST_PREFIX.sub("", line)
                    # Stack listings are short or carry versions; longer lines are guidance.
                    if len(item.split()) > 8 and not re.search(r"\d+\.\d+|\b\d{1,2}\b|[\^~]\d", item):
                        continue
                    found = pattern.findall(line)
                    if found:
                        hits.append(number)
                        names.extend(f.lower() for f in found)
            if len(hits) >= DEPENDENCY_MIN_LINES:
                unique = sorted(set(names))
                sources = sorted({words[n] for n in unique if n in words})
                self.add("RS801", "derivable", "info", cf, hits[0],
                         "%d lines restate dependencies from %s (%s). Claude reads the manifest "
                         "itself; keep only what it can't infer, such as why a package is used."
                         % (len(hits), ", ".join(sources or manifests), ", ".join(unique[:6])))

    def check_agents_md(self) -> None:
        for cf in self.files:
            if cf.kind == "memory" and cf.path.name == "AGENTS.md" and cf.load == "other-agents":
                self.add("RS103", "size", "info", cf, None,
                         "Claude Code doesn't read this AGENTS.md by default, because a CLAUDE.md exists "
                         "here or above. If Claude should see it, import it from CLAUDE.md with "
                         "@AGENTS.md instead of keeping two copies in sync.")


# --- report ----------------------------------------------------------------------


def summarize(report: Report) -> dict:
    always = [f for f in report.files if f.always_chars]
    on_demand = [f for f in report.files if f.on_demand_chars]
    counts: Dict[str, int] = defaultdict(int)
    for finding in report.findings:
        counts[finding.severity] += 1
    return {
        "files": len(report.files),
        "always_files": len(always),
        "always_tokens": tokens(sum(f.always_chars for f in report.files)),
        "on_demand_files": len(on_demand),
        "on_demand_tokens": tokens(sum(f.on_demand_chars for f in report.files)),
        "other_agents_files": len([f for f in report.files if f.load == "other-agents"]),
        "warn": counts["warn"],
        "info": counts["info"],
    }


def to_json(report: Report) -> dict:
    return {
        "tool": "rightsize",
        "version": VERSION,
        "root": report.root,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "partial": report.partial,
        "token_note": "Estimates: characters / 4. Run /context in Claude Code for live numbers.",
        "summary": summarize(report),
        "files": [
            {
                "path": f.rel,
                "kind": f.kind,
                "load": f.load,
                "scope": f.scope,
                "lines": f.lines,
                "always_tokens": tokens(f.always_chars),
                "on_demand_tokens": tokens(f.on_demand_chars),
                "note": f.note,
            }
            for f in report.files
        ],
        "findings": [asdict(f) for f in report.findings],
        "notes": report.notes,
    }


def compare(before: dict, after: dict) -> dict:
    old = {f["path"]: f for f in before.get("files", [])}
    new = {f["path"]: f for f in after.get("files", [])}
    rows = []
    for path in sorted(set(old) | set(new)):
        a, b = old.get(path), new.get(path)
        key = ("lines", "always_tokens", "on_demand_tokens")
        if a and b and all(a[k] == b[k] for k in key):
            continue
        rows.append({
            "path": path,
            "status": "added" if not a else "removed" if not b else "changed",
            **{"before_" + k: (a or {}).get(k, 0) for k in key},
            **{"after_" + k: (b or {}).get(k, 0) for k in key},
        })
    pick = ("always_tokens", "on_demand_tokens", "files", "warn", "info")
    return {
        "before": {k: before.get("summary", {}).get(k, 0) for k in pick},
        "after": {k: after.get("summary", {}).get(k, 0) for k in pick},
        "files": rows,
    }


def pct(before: int, after: int) -> str:
    if not before:
        return ""
    change = (after - before) * 100.0 / before
    return " (%+.0f%%)" % change


def render_table(data: dict) -> str:
    s = data["summary"]
    out = ["rightsize %s · %s" % (data["version"], data["root"]), ""]
    out.append("Loaded every session  ~%s tokens (est.) from %d file%s"
               % (format(s["always_tokens"], ","), s["always_files"], "" if s["always_files"] == 1 else "s"))
    out.append("Loaded on demand      ~%s tokens (est.) from %d file%s"
               % (format(s["on_demand_tokens"], ","), s["on_demand_files"], "" if s["on_demand_files"] == 1 else "s"))
    if s["other_agents_files"]:
        out.append("For other agents only %d file%s (not loaded by Claude Code as found)"
                   % (s["other_agents_files"], "" if s["other_agents_files"] == 1 else "s"))
    if data.get("partial"):
        out.append("Note: the repo is large; the walk stopped early, so results are partial.")
    out += ["", "Files", "  %8s %10s %6s  %s" % ("always", "on-demand", "lines", "path")]
    for f in sorted(data["files"], key=lambda f: (-f["always_tokens"], -f["on_demand_tokens"], f["path"])):
        extra = []
        if f["load"] == "other-agents":
            extra.append("other agents")
        if f["note"]:
            extra.append(f["note"])
        out.append("  %8s %10s %6d  %s%s" % (
            format(f["always_tokens"], ",") if f["always_tokens"] else "-",
            format(f["on_demand_tokens"], ",") if f["on_demand_tokens"] else "-",
            f["lines"], f["path"], "  (%s)" % "; ".join(extra) if extra else ""))
    findings = data["findings"]
    out += ["", "Findings  %d warn, %d info" % (s["warn"], s["info"])]
    if not findings:
        out.append("  none")
    for f in findings:
        where = f["path"] + (":%d" % f["line"] if f["line"] else "")
        out.append("  %-4s  %s  %s" % (f["severity"], f["id"], where))
        out.append("        %s" % f["message"])
        if f["evidence"]:
            out.append("        > %s" % f["evidence"])
        if f["related"]:
            out.append("        also: %s" % ", ".join(f["related"][:6]))
    if "compare" in data:
        c = data["compare"]
        b, a = c["before"], c["after"]
        out += ["", "Before → after"]
        out.append("  every session  ~%s → ~%s tokens%s" % (
            format(b["always_tokens"], ","), format(a["always_tokens"], ","),
            pct(b["always_tokens"], a["always_tokens"])))
        out.append("  on demand      ~%s → ~%s tokens%s" % (
            format(b["on_demand_tokens"], ","), format(a["on_demand_tokens"], ","),
            pct(b["on_demand_tokens"], a["on_demand_tokens"])))
        out.append("  findings       %d warn, %d info → %d warn, %d info" % (
            b["warn"], b["info"], a["warn"], a["info"]))
        for row in c["files"]:
            parts = ["lines %d → %d" % (row["before_lines"], row["after_lines"])]
            for key, label in (("always_tokens", "every session"), ("on_demand_tokens", "on demand")):
                if row["before_" + key] or row["after_" + key]:
                    parts.append("%s ~%d → ~%d" % (label, row["before_" + key], row["after_" + key]))
            out.append("  %-7s %s  %s" % (row["status"], row["path"], " · ".join(parts)))
    out += ["", data["token_note"]]
    return "\n".join(out)


def scan(root: Path, include_user: bool = False, max_lines: int = MEMORY_MAX_LINES) -> Report:
    index = RepoIndex(root)
    files = discover(root, index, include_user)
    findings = Checker(root, index, files, max_lines).run()
    notes = []
    if not files:
        notes.append("No context files found. Claude Code would start with only its own system prompt.")
    return Report(str(root), files, findings, notes, index.partial)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan.py",
        description="Inventory and lint the context files Claude Code loads. Reads only; edits nothing.",
    )
    parser.add_argument("root", nargs="?", default=".", help="repository or package to scan (default: .)")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--json", action="store_const", const="json", dest="format",
                        help="shorthand for --format json")
    parser.add_argument("--save", metavar="FILE", help="write the JSON report to FILE (a snapshot to compare later)")
    parser.add_argument("--compare", metavar="FILE", help="compare against a snapshot written by --save")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any finding is a warning")
    parser.add_argument("--include-user", action="store_true", help="also scan ~/.claude (CLAUDE.md, rules, skills, agents)")
    parser.add_argument("--max-lines", type=int, default=MEMORY_MAX_LINES,
                        help="line budget for always-loaded memory files (default: %d)" % MEMORY_MAX_LINES)
    parser.add_argument("--version", action="version", version="rightsize " + VERSION)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # consoles that can't print arrows get "?"

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error("not a directory: %s" % args.root)
    data = to_json(scan(root, args.include_user, args.max_lines))
    if args.compare:
        try:
            before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            parser.error("cannot read snapshot %s: %s" % (args.compare, exc))
        data["compare"] = compare(before, data)
    if args.save:
        Path(args.save).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(data, indent=2))
    else:
        print(render_table(data))
    if args.strict and data["summary"]["warn"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

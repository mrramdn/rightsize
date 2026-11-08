#!/usr/bin/env python3
"""rightsize scan: deterministic inventory and lint for Claude Code context files.

Finds the files that decide what Claude Code reads (CLAUDE.md, CLAUDE.local.md,
AGENTS.md, .claude/rules, skills, subagents, slash commands and their @imports),
estimates what each one costs, and flags the patterns that Anthropic's
context-engineering guidance for current Claude models calls out: absolute rules
with no reason, shouting, duplicated or conflicting instructions, inline code and
playbooks, stale references, and content Claude can read from the repo itself.

It only reads files. It never runs project commands and edits nothing; the one
thing it writes is the snapshot that --save asks for.
Standard library only; Python 3.8 or newer.

    python3 scan.py [ROOT] [--format table|json] [--save [FILE]] [--compare [FILE]]
                    [--strict] [--include-user] [--max-lines N] [--instruction-files MODE]

Exit status: 0 on success, 1 with --strict when any finding is a warning,
2 on a usage error or when a snapshot can't be written or used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

VERSION = "0.1.3"

# Token estimate. Calibrated against `claude plugin details` on 54 plugin skills (November 2026):
# it reports one token per 2.6-2.9 characters for names, descriptions and bodies alike, so the
# usual characters / 4 ran about a third under it.
CHARS_PER_TOKEN = 2.7

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
COPIED_MIN_LINES = 5          # this many shared lines between the same files = one "copied" finding

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
# Which instruction files Claude Code reads: the built-in cc-plugin-agents-md plugin's `instructionFiles`
# option, set in user or managed settings (project settings can't change it).
INSTRUCTION_MODES = ("claude-md-or-agents-md", "claude-md-and-agents-md", "claude-md", "managed-only")
DEFAULT_INSTRUCTION_MODE = "claude-md-or-agents-md"
AGENTS_MD_PLUGIN_IDS = ("cc-plugin-agents-md@builtin", "agents-md@builtin")  # renamed in Claude Code 2.1.285
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
    r"\b(ALWAYS|NEVER|ONLY|MUST(?:\s+NOT)?|DO\s+NOT|DON'T|SHALL(?:\s+NOT)?|REQUIRED|FORBIDDEN|PROHIBITED|"
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
TASK_WORDS = re.compile(
    r"\b(deploy\w*|releas\w*|review\w*|checklist\w*|set ?up|install\w*|migrat\w*|publish\w*|onboard\w*|"
    r"how to|steps?|process|workflow|runbook|debug\w*|troubleshoot\w*|rollback|upgrad\w*|shipping|"
    r"provision\w*|backup\w*|hotfix\w*|incident\w*)\b",
    re.IGNORECASE,
)
REFERRED_CAPS = re.compile(r"\b[A-Z]{2,}(?:/[A-Z]{2,})+\b|[\"'“‘][A-Z]{2,}[\"'”’]")
NEGATED_MENTION = re.compile(
    r"\b(no|not|never|without|instead of|don'?t|doesn'?t|isn'?t|aren'?t|avoid|removed?|deleted?|"
    r"deprecated|replaced|no longer)\b[^`]{0,30}$",
    re.IGNORECASE,
)
# A prohibition about a file ("Never edit `x`", "Don't touch `x/`") expects the file to exist, unlike a
# mention of something absent ("no separate `x`", "don't create a `x`").
PROHIBITED_EDIT = re.compile(
    r"\b(?:never|don'?t|do not|must not|mustn'?t|should not|shouldn'?t|cannot|can'?t|avoid|no(?!\s+longer\b))\s+"
    r"(?:[\w-]+\s+){0,2}?"
    r"(?:edit|edits|editing|hand-edit|touch|touching|modify|modifying|change|changing|update|updating|"
    r"delete|deleting|remove|removing|rename|renaming|move|moving|overwrite|overwriting|reformat|"
    r"reformatting|refactor|refactoring|rewrite|rewriting|import|importing|run|running|patch|patching)\b"
    r"[^`]{0,30}$",
    re.IGNORECASE,
)
# A file marks itself as written by a tool ("This file is generated", "DO NOT EDIT", "<!-- Generated by x -->");
# a line that says some other file is generated ("- `types.ts` is auto-generated") doesn't count.
GENERATED_SELF = re.compile(
    r"(?i:\bthis (?:file|document|page) (?:is|was|has been|gets) (?:auto-?|automatically )?generated\b"
    r"|\b(?:do not|don'?t) edit this (?:file|document)\b)"
    r"|\bDO NOT EDIT(?: THIS FILE| BY HAND| MANUALLY| DIRECTLY)?\s*(?:[.!:;—–-]|\*/|$)"
)
GENERATED_LEAD = re.compile(
    r"^(?:auto-?generated|automatically generated|generated)(?:\s+(?:file|content|document|section))?"
    r"(?:\s+(?:by|from|with|using)\b|\s*(?:[.:;!—–]|--|$))"
    r"|^(?:do not|don'?t) edit (?:by hand|manually|directly)\b",
    re.IGNORECASE,
)
INIT_SIGNATURE = "This file provides guidance to Claude Code"
SKILL_OWN_PATH = re.compile(r"^(?:\./)?(?:references|scripts|assets|templates|examples|resources)/")
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
    generated: Optional[Tuple[int, int]] = None  # line span written by a tool


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
    options: Dict[str, object] = field(default_factory=dict)


# --- helpers ---------------------------------------------------------------------


def tokens(chars: int) -> int:
    return int(math.ceil(chars / CHARS_PER_TOKEN))


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
    in_comment = snippet = False
    lines = cf.text.splitlines()
    for idx in range(cf.body_start, len(lines)):
        line = lines[idx]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not fence and (in_comment or (indent <= 3 and stripped.startswith("<!--"))):
            in_comment = "-->" not in stripped
            yield idx + 1, line, "comment"
            continue
        # Laravel Boost writes examples as <code-snippet> blocks rather than fences.
        if not fence and not snippet and stripped.startswith("<code-snippet") and "</code-snippet>" not in stripped:
            snippet = True
            yield idx + 1, line, "fence-open"
            continue
        if snippet:
            snippet = "</code-snippet>" not in stripped
            yield idx + 1, line, "code" if snippet else "fence-close"
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


def generated_marker(line: str) -> bool:
    """True when the line marks its own file as generated, not when it says another file is."""
    if GENERATED_SELF.search(line):
        return True
    if LIST_PREFIX.match(line):
        return False
    return bool(GENERATED_LEAD.match(re.sub(r"^[\s<!#/*>-]+", "", line)))


def isolated_unit(cf: ContextFile) -> Optional[Path]:
    """The skill, subagent or command a file belongs to. Each loads on its own, for its own task,
    so two of them are rarely in context together; None for files that share the main context."""
    if cf.kind == "skill":
        return cf.path.parent
    if cf.kind in ("agent", "command"):
        return cf.path
    return None


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


def config_dir() -> Path:
    """Claude Code's user folder: ~/.claude, or wherever CLAUDE_CONFIG_DIR points."""
    value = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(value).expanduser() if value else Path.home() / ".claude"


def load_json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def managed_settings_paths() -> List[Path]:
    if sys.platform == "darwin":
        return [Path("/Library/Application Support/ClaudeCode/managed-settings.json")]
    if os.name == "nt":
        return [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ClaudeCode" / "managed-settings.json",
                Path(r"C:\Program Files\ClaudeCode\managed-settings.json")]
    return [Path("/etc/claude-code/managed-settings.json")]


def instruction_mode(override: Optional[str] = None) -> Tuple[str, str]:
    """The instructionFiles mode Claude Code uses on this machine, and where it is set."""
    if override:
        return override, "--instruction-files"
    user_settings = config_dir() / "settings.json"
    try:
        user_label = "~/" + user_settings.relative_to(Path.home()).as_posix()
    except ValueError:
        user_label = str(user_settings)
    sources = [(path, "managed settings") for path in managed_settings_paths()]
    sources.append((user_settings, user_label))
    for path, label in sources:
        settings = load_json_file(path)
        enabled = settings.get("enabledPlugins")
        configs = settings.get("pluginConfigs")
        for plugin_id in AGENTS_MD_PLUGIN_IDS:
            if isinstance(enabled, dict) and enabled.get(plugin_id) is False:
                return "claude-md", label + " (plugin off)"
            config = configs.get(plugin_id) if isinstance(configs, dict) else None
            options = config.get("options") if isinstance(config, dict) else None
            value = options.get("instructionFiles") if isinstance(options, dict) else None
            if value in INSTRUCTION_MODES:
                return value, label
    return DEFAULT_INSTRUCTION_MODE, "default"


def synced_skill_dirs(user: Path) -> List[Path]:
    """Folders of skills synced from claude.ai. There is one per account (`<organization>_<account>`); only the
    signed-in account's skills load, so when it is known, only its folder counts."""
    dirs = sorted(path for path in (user / "skills" / "synced").glob("*") if path.is_dir())
    state = (user if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home()) / ".claude.json"
    account = load_json_file(state).get("oauthAccount")
    if isinstance(account, dict):
        current = "%s_%s" % (account.get("organizationUuid"), account.get("accountUuid"))
        if any(path.name == current for path in dirs):
            return [path for path in dirs if path.name == current]
    return dirs


def enabled_plugins(root: Path, user: Path) -> List[Tuple[str, Path]]:
    """Plugins switched on in user, project and local settings, with the folder each is installed in."""
    enabled: Dict[str, bool] = {}
    for path in (user / "settings.json", root / ".claude" / "settings.json",
                 root / ".claude" / "settings.local.json"):
        value = load_json_file(path).get("enabledPlugins")
        if isinstance(value, dict):
            enabled.update({key: bool(on) for key, on in value.items()})
    installed = load_json_file(user / "plugins" / "installed_plugins.json").get("plugins")
    found = []
    for plugin_id, on in sorted(enabled.items()):
        entries = installed.get(plugin_id) if on and isinstance(installed, dict) else None
        for entry in entries if isinstance(entries, list) else []:
            install = entry.get("installPath") if isinstance(entry, dict) else None
            if isinstance(install, str) and Path(install).is_dir():
                found.append((plugin_id, Path(install)))
                break
    return found


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
        when = str(cf.fields.get("when_to_use") or "")
        name = str(cf.fields.get("name") or cf.path.parent.name)
        manual = str(cf.fields.get("disable-model-invocation", "")).lower() == "true"
        if load == "always" and not manual:
            cf.always_chars = len(name) + len(description) + len(when) + 4
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


def discover(root: Path, index: RepoIndex, include_user: bool,
             mode: str = DEFAULT_INSTRUCTION_MODE) -> List[ContextFile]:
    files: List[ContextFile] = []
    by_path: Dict[Path, ContextFile] = {}

    def add(path: Path, kind: str, load: str, scope: str, lint: bool = True, note: str = "") -> None:
        resolved = path.resolve()
        if resolved in by_path or not path.is_file():
            return
        cf = load_file(path, root, kind, load, scope)
        if cf:
            cf.lint = cf.lint and lint
            cf.note = cf.note or note
            by_path[resolved] = cf
            files.append(cf)

    # Which AGENTS.md files Claude Code reads depends on the instructionFiles mode. By default it reads
    # one only when no CLAUDE.md, .claude/CLAUDE.md or CLAUDE.local.md exists in the working directory
    # or above it. managed-only skips the repo's files altogether; the numbers then use the default.
    if mode == "claude-md-and-agents-md":
        agents_mode = True
    elif mode == "claude-md":
        agents_mode = False
    else:
        agents_mode = not any(has_claude_md(d) for d in [root, *root.parents])

    def agents_md_skipped(home: Path, top: bool) -> bool:
        if mode in ("claude-md-and-agents-md", "claude-md"):
            return not agents_mode
        return not agents_mode or (not top and has_claude_md(home))

    # Memory files inside ROOT, plus ancestors up to the git root. When ROOT is the user folder itself, its
    # CLAUDE.md is the personal one, counted with the user files below.
    user_memory = (config_dir() / "CLAUDE.md").resolve() if include_user else None
    for path in index.memory:
        if path.resolve() == user_memory:
            continue
        parent = path.parent
        home = parent.parent if parent.name == ".claude" else parent
        top = home == root
        load = "always" if top else "on-demand"
        if path.name == "AGENTS.md" and agents_md_skipped(home, top):
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

    def add_skills(directory: Path, scope: str, load: str, lint: bool = True, note: str = "") -> None:
        if not directory.is_dir():
            return
        for skill in sorted(directory.glob("*/SKILL.md")):
            add(skill, "skill", load, scope, lint, note)
            for extra in sorted(skill.parent.rglob("*.md")):
                parts = extra.relative_to(skill.parent).parts
                if extra.name != "SKILL.md" and "evals" not in parts:
                    add(extra, "reference", "on-demand", scope, lint, note)

    def add_all(directory: Path, kind: str, scope: str, load: str, lint: bool = True, note: str = "") -> None:
        if directory.is_dir():
            for path in sorted(directory.rglob("*.md")):
                add(path, kind, load, scope, lint, note)

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
        user = config_dir()
        add(user / "CLAUDE.md", "memory", "always", "user")
        if user.is_dir():
            add_claude_dir(user, "user", "always")
            # Skills synced from claude.ai and installed plugins also list their names and descriptions
            # in every session. They are counted, not linted: they're edited at their source.
            for synced in synced_skill_dirs(user):
                add_skills(synced, "user", "always", lint=False, note="synced from claude.ai")
            for plugin_id, base in enabled_plugins(root, user):
                note = "plugin " + plugin_id.split("@")[0]
                for directory in plugin_dirs(base, "skills", "skills"):
                    add_skills(directory, "plugin", "always", lint=False, note=note)
                for directory in plugin_dirs(base, "agents", "agents"):
                    add_all(directory, "agent", "plugin", "always", lint=False, note=note)
                for directory in plugin_dirs(base, "commands", "commands"):
                    add_all(directory, "command", "plugin", "always", lint=False, note=note)

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
    def __init__(self, root: Path, index: RepoIndex, files: List[ContextFile], max_lines: int,
                 mode: str = DEFAULT_INSTRUCTION_MODE):
        self.root = root
        self.index = index
        self.files = files
        self.max_lines = max_lines
        self.mode = mode
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
            if cf.lint:
                self.check_meta(cf)
        for cf in lintable:
            self.check_origin(cf)
            self.check_size(cf)
            self.check_lines(cf)
            self.check_blocks(cf)
            self.check_refs(cf)
        self.check_pairs([cf for cf in self.files if cf.lint])
        self.check_derivable([cf for cf in lintable if cf.load == "always"])
        self.check_agents_md()
        by_rel = {cf.rel: cf for cf in self.files}
        for finding in self.findings:
            span = by_rel[finding.path].generated if finding.path in by_rel else None
            if span and finding.id not in ("RS104", "RS105") and (
                    finding.line is None or span[0] <= finding.line <= span[1]):
                finding.message += " Generated content (RS104): change it at its source."
        order = {"warn": 0, "info": 1}
        self.findings.sort(key=lambda f: (order[f.severity], f.path, f.line or 0, f.id))
        return self.findings

    # Origin -----------------------------------------------------------------------

    def check_origin(self, cf: ContextFile) -> None:
        """Content a tool wrote gets rewritten on its next run, so fixes belong at the source."""
        if cf.kind not in ("memory", "import", "rule"):
            return
        lines = cf.text.splitlines()
        start = next((i for i, line in enumerate(lines) if "<laravel-boost-guidelines>" in line), None)
        if start is not None:
            end = next((i for i in range(start, len(lines)) if "</laravel-boost-guidelines>" in lines[i]),
                       len(lines) - 1)
            cf.generated = (start + 1, end + 1)
            self.add("RS104", "origin", "info", cf, start + 1,
                     "Lines %d-%d are Laravel Boost's generated block, rewritten by `php artisan "
                     "boost:update`. Change them through `.ai/guidelines/` (a file at a built-in "
                     "guideline's path overrides it) and keep project notes outside the block."
                     % (start + 1, end + 1))
        else:
            for i, line in enumerate(lines[:15]):
                if generated_marker(line):
                    cf.generated = (1, len(lines))
                    self.add("RS104", "origin", "info", cf, i + 1,
                             "Marked as generated. Change it at its source, or the next run "
                             "overwrites your edits.", line)
                    break
        if cf.kind == "memory":
            for i, line in enumerate(lines[:12]):
                if INIT_SIGNATURE in line:
                    self.add("RS105", "origin", "info", cf, i + 1,
                             "Started by /init. Its command lists and architecture notes are often "
                             "derivable; lines people added since are usually the gotchas worth keeping.")
                    break

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
            text = REFERRED_CAPS.sub(" ", text)  # "MUST/SHOULD", 'NEVER': keywords mentioned, not shouted
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
        # Long procedures and checklists. Under a heading that names a task (deploy, review, release)
        # they are a playbook for that task; elsewhere they may be principles that apply to all work.
        for pattern, label in ((NUMBERED_ITEM, "numbered steps"), (CHECKLIST_ITEM, "checklist items")):
            run_start, count, heading, run_heading = None, 0, "", ""
            for number, line, kind in rows + [(10 ** 9, "<end>", "text")]:
                head = HEADING.match(line) if kind == "text" else None
                if kind == "text" and pattern.match(line):
                    if run_start is None:
                        run_start, run_heading = number, heading
                    count += 1
                    continue
                if kind == "text" and line.strip() and line[:1] not in (" ", "\t"):
                    if run_start is not None and count >= PROCEDURE_MIN_ITEMS:
                        task = bool(TASK_WORDS.search(run_heading))
                        if always and task:
                            message = ("%d %s for one kind of task, loaded every session. Move them into "
                                       "a skill so they load only when that task comes up." % (count, label))
                        elif always:
                            message = ("%d %s loaded every session. Fine if they apply to all work; if "
                                       "they're for one kind of task, a skill loads them only when needed."
                                       % (count, label.replace("steps", "items")))
                        else:
                            message = ("%d %s. Fine in a skill if every step matters; cut the ones "
                                       "Claude would do anyway." % (count, label))
                        self.add("RS602", "bloat", "warn" if always and task else "info", cf, run_start, message)
                    run_start, count = None, 0
                if head:
                    heading = head.group(2)
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
        # Plugin and personal (~/.claude) files describe other people's projects, so their paths
        # and commands can't be checked against this repo; only a skill's own files can.
        portable = cf.scope in ("plugin", "user")
        for number, line, kind in rows:
            if portable:
                pass
            elif kind == "code" and not line.lstrip().startswith(("#", "//", "--", ";")):
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
                if portable and not (cf.kind == "skill" and SKILL_OWN_PATH.match(candidate)):
                    continue
                if self.index.exists(candidate, base):
                    continue
                before = line[: max(line.find(token), 0)].rstrip("`'\"([ ")
                if NEGATED_MENTION.search(before) and not PROHIBITED_EDIT.search(before):
                    continue  # "no separate tailwind.config.js", "instead of webpack.config.js"
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
        # Duplicates that span the same set of files are reported together: two files sharing
        # dozens of lines are one copied file, not dozens of findings.
        by_files: Dict[Tuple[str, ...], List[List[int]]] = defaultdict(list)
        for members in groups.values():
            if len(members) < 2:
                continue
            for a in members:
                for b in members:
                    if a < b:
                        exact_pairs.add((a, b))
            by_files[tuple(sorted({entries[m][0].rel for m in members}))].append(members)

        def severity_of(members: List[int]) -> str:
            loaded = [entries[m] for m in members if claude_loads(entries[m])]
            return "warn" if len(loaded) >= 2 and any(every_session(e[0]) for e in loaded) else "info"

        for paths, member_lists in sorted(by_files.items()):
            other_agents = any(entries[m][0].load == "other-agents" for ms in member_lists for m in ms)
            if len(paths) >= 2 and len(member_lists) >= COPIED_MIN_LINES:
                member_lists.sort(key=lambda ms: min(ms))
                # Anchor on the copy Claude reads, so the finding sits where the fix starts.
                first = min((entries[m] for m in member_lists[0]),
                            key=lambda e: (e[0].load == "other-agents", e[0].rel, e[1]))
                message = "%d instructions appear in both %s. Keep one copy and import it where else it's needed." % (
                    len(member_lists), " and ".join(paths))
                if other_agents:
                    message += " Claude Code reads only one of these here; import the other with @AGENTS.md."
                spans = []
                for path in paths:
                    if path == first[0].rel:
                        continue
                    lines = sorted(entries[m][1] for ms in member_lists for m in ms if entries[m][0].rel == path)
                    spans.append("%s:%d-%d" % (path, lines[0], lines[-1]))
                self.add("RS401", "duplicate", severity_of(member_lists[0]), first[0], first[1], message,
                         first[2], spans)
                continue
            for members in member_lists:
                first = entries[members[0]]
                message = "Same instruction in %d places. Keep one, in the layer where it applies." % len(members)
                if other_agents:
                    message += " One copy is for other agents; consider importing it with @AGENTS.md."
                self.add("RS401", "duplicate", severity_of(members), first[0], first[1], message, first[2],
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
            unit_a, unit_b = isolated_unit(ea[0]), isolated_unit(eb[0])
            if unit_a and unit_b and unit_a != unit_b:
                continue  # two skills (or subagents) for different tasks: no shared context to clash in
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
        if self.mode == "claude-md":
            reason = "Claude Code on this machine reads CLAUDE.md files only (instructionFiles: claude-md)."
        else:
            reason = "Claude Code doesn't read this AGENTS.md by default, because a CLAUDE.md exists here or above."
        for cf in self.files:
            if cf.kind == "memory" and cf.path.name == "AGENTS.md" and cf.load == "other-agents":
                self.add("RS103", "size", "info", cf, None,
                         reason + " If Claude should see it, import it from CLAUDE.md with @AGENTS.md "
                         "instead of keeping two copies in sync.")


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
        "options": report.options,
        "token_note": "Estimates: characters / %s, close to `claude plugin details`. Run /context in Claude Code "
                      "for live numbers." % CHARS_PER_TOKEN,
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
        "snapshot_at": before.get("generated_at", ""),
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
    for note in data.get("notes", []):
        out.append("Note: " + note)
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
        out += ["", "Before → after" + ("  (snapshot taken %s)" % c["snapshot_at"] if c.get("snapshot_at") else "")]
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


def scan(root: Path, include_user: bool = False, max_lines: int = MEMORY_MAX_LINES,
         instruction_files: Optional[str] = None) -> Report:
    mode, source = instruction_mode(instruction_files)
    if root == config_dir().resolve():
        include_user = True  # scanning ~/.claude is scanning the personal setup
    effective = DEFAULT_INSTRUCTION_MODE if mode == "managed-only" else mode
    index = RepoIndex(root)
    files = discover(root, index, include_user, effective)
    findings = Checker(root, index, files, max_lines, effective).run()
    notes = []
    agents_md = any(f.kind == "memory" and f.path.name == "AGENTS.md" for f in files)
    if mode == "claude-md-and-agents-md" and agents_md:
        notes.append("Claude Code on this machine reads AGENTS.md alongside CLAUDE.md (instructionFiles: "
                     "claude-md-and-agents-md, from %s). With the default setting it reads only one of them."
                     % source)
    elif mode == "claude-md" and agents_md:
        notes.append("Claude Code on this machine reads CLAUDE.md files only (instructionFiles: claude-md, from "
                     "%s), so AGENTS.md is for other agents." % source)
    elif mode == "managed-only" and any(f.kind in ("memory", "rule") for f in files):
        notes.append("instructionFiles is managed-only here (%s): Claude Code skips this repo's CLAUDE.md, rules "
                     "and AGENTS.md on this machine. The numbers use the default setting, as teammates see it."
                     % source)
    if not any(f.kind == "memory" and f.load != "other-agents" for f in files):
        notes.append("No CLAUDE.md that Claude Code reads here. For a new project, write a short one with only "
                     "what Claude can't learn from the repo (see the skill's New projects section).")
    options = {"include_user": include_user, "instruction_files": mode}
    return Report(str(root), files, findings, notes, index.partial, options)


# --- snapshots -------------------------------------------------------------------

TEMP_FALLBACKS = ("/tmp",) if os.name == "posix" else ()


def snapshot_name(root: Path, include_user: bool) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-.")[:40] or "root"
    digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:10]
    return "%s-%s%s.json" % (slug, digest, "-user" if include_user else "")


def snapshot_dirs(root: Path) -> List[Path]:
    """Where a snapshot without a file name goes, never among the repo's files: the repo's .git folder, then
    the temp folder. .git comes first because sandboxes may allow writes only inside the workspace, and some
    give each command a private /tmp that is gone before the next one runs."""
    dirs: List[Path] = []
    if (root / ".git").is_dir():
        dirs.append(root / ".git" / "rightsize")
    seen: Set[Path] = set()
    candidates = [os.environ.get(name) for name in ("TMPDIR", "TEMP", "TMP")] + list(TEMP_FALLBACKS)
    for value in candidates:
        if not value:
            continue
        try:
            resolved = Path(value).expanduser().resolve()
        except OSError:
            continue
        if resolved in seen or resolved == root or root in resolved.parents:
            continue
        seen.add(resolved)
        dirs.append(resolved / "rightsize")
    return dirs


def save_snapshot(data: dict, target: str, root: Path, include_user: bool) -> Path:
    """Write the report as a snapshot and return where it went. Raises OSError with a readable message."""
    text = json.dumps(data, indent=2) + "\n"
    if target:
        path = Path(target).expanduser()
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise OSError("%s is not writable (%s)" % (path, exc.strerror or exc)) from None
        return path
    tried = []
    for directory in snapshot_dirs(root):
        path = directory / snapshot_name(root, include_user)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return path
        except OSError as exc:
            tried.append("%s (%s)" % (directory, exc.strerror or exc))
    raise OSError("found no writable folder" + (" (tried %s)" % "; ".join(tried) if tried else ""))


def find_snapshot(root: Path, include_user: bool) -> Optional[Path]:
    """The newest snapshot that --save without a file name made for this folder."""
    found = [d / snapshot_name(root, include_user) for d in snapshot_dirs(root)]
    found = [path for path in found if path.is_file()]
    return max(found, key=lambda path: path.stat().st_mtime) if found else None


def snapshot_problem(before: object, data: dict) -> str:
    """Why a snapshot can't be compared with this scan, or "" when it can."""
    if not isinstance(before, dict) or before.get("tool") != "rightsize" or not isinstance(before.get("files"), list):
        return "it isn't a rightsize snapshot"
    if before.get("root") and before["root"] != data["root"]:
        return "it was taken of %s, not %s. Compare against one saved for this folder" % (before["root"], data["root"])
    old, new = before.get("options") or {}, data.get("options") or {}
    for key in ("include_user", "instruction_files"):
        if key in old and old[key] != new.get(key):
            return "it was taken with %s = %s, and this scan has %s. Use the same options" % (key, old[key], new.get(key))
    return ""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan.py",
        description="Inventory and lint the context files Claude Code loads. Reads only; edits nothing.",
    )
    parser.add_argument("root", nargs="?", default=".", help="repository or package to scan (default: .)")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--json", action="store_const", const="json", dest="format",
                        help="shorthand for --format json")
    parser.add_argument("--save", metavar="FILE", nargs="?", const="",
                        help="save this scan as a snapshot to compare against later. Without FILE it goes to ROOT's "
                             ".git folder (or the temp folder outside git) under a name tied to ROOT")
    parser.add_argument("--compare", metavar="FILE", nargs="?", const="",
                        help="compare with a snapshot from --save; without FILE, the one --save made for ROOT")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any finding is a warning")
    parser.add_argument("--include-user", action="store_true",
                        help="also count ~/.claude: CLAUDE.md, rules, skills (synced ones too), agents, commands "
                             "and enabled plugins")
    parser.add_argument("--max-lines", type=int, default=MEMORY_MAX_LINES,
                        help="line budget for always-loaded memory files (default: %d)" % MEMORY_MAX_LINES)
    parser.add_argument("--instruction-files", choices=INSTRUCTION_MODES,
                        help="which instruction files Claude Code reads (default: the cc-plugin-agents-md setting "
                             "in managed or ~/.claude settings, else %s)" % DEFAULT_INSTRUCTION_MODE)
    parser.add_argument("--version", action="version", version="rightsize " + VERSION)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # consoles that can't print arrows get "?"

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error("not a directory: %s" % args.root)
    if args.save and Path(args.save).expanduser().is_dir():
        parser.error("--save takes a file, and %s is a folder. Put ROOT before --save, or name a file."
                     % args.save)
    data = to_json(scan(root, args.include_user, args.max_lines, args.instruction_files))

    def fail(message: str) -> int:
        print("rightsize: error: " + message, file=sys.stderr)
        return 2

    if args.compare is not None:
        snapshot = Path(args.compare).expanduser() if args.compare else find_snapshot(root, args.include_user)
        if snapshot is None:
            return fail("no snapshot of %s yet. Run with --save first." % root)
        try:
            before = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return fail("cannot read snapshot %s: %s" % (snapshot, exc))
        problem = snapshot_problem(before, data)
        if problem:
            return fail("can't compare with %s: %s." % (snapshot, problem))
        data["compare"] = compare(before, data)
    saved, save_error = None, ""
    if args.save is not None:
        try:
            saved = save_snapshot(data, args.save, root, args.include_user)
        except OSError as exc:
            save_error = "couldn't save the snapshot: %s. Pass --save FILE with a writable path." % exc
    if args.format == "json":
        print(json.dumps(data, indent=2))
    else:
        print(render_table(data))
    if saved:
        print("rightsize: snapshot saved to %s" % saved, file=sys.stderr)
    if save_error:
        return fail(save_error)
    if args.strict and data["summary"]["warn"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

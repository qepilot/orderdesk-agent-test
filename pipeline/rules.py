"""The deterministic rules of the claude-ready pipeline. Plain functions, no network, no model: everything here is tested.

These are the guardrails that do not depend on the model behaving. The prompt asks the agent to follow the charter; this
module is what *enforces* the parts that can be enforced: where it may write, which commands it may run, how big a change may
be, and what must never appear in code.
"""

from __future__ import annotations

import os
import posixpath
import re
import shlex

MAX_CHANGED_LINES = 800                       # the charter says ~600; this is the hard stop
ALLOWED_WORKFLOW = re.compile(r"\.github/workflows/restaurant-[A-Za-z0-9._-]+\.ya?ml")
CACHE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".hypothesis", ".venv", "node_modules"}
CACHE_FILES = {".coverage"}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
WRITE_PERMISSIONS = {"admin", "maintain", "write"}

SECRET_PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI/OpenRouter style key": re.compile(r"sk-(?:or-v1-)?[A-Za-z0-9_-]{32,}"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "OAuth token assignment": re.compile(r"CLAUDE_CODE_OAUTH_TOKEN\s*[=:]\s*['\"]?[A-Za-z0-9_-]{10,}"),
}


# ---------------------------------------------------------------- issue text

def parse_dependencies(body: str) -> list[int]:
    """Issue numbers on the '**Depends on:** #1, #2' line."""
    for line in (body or "").splitlines():
        if line.strip().lower().startswith("**depends on:**"):
            return [int(n) for n in re.findall(r"#(\d+)", line)]
    return []


def parse_charter_number(body: str) -> int | None:
    match = re.search(r"Rules for every task: see #(\d+)", body or "")
    return int(match.group(1)) if match else None


def acceptance_criteria(body: str) -> list[str]:
    """The checkbox lines under '## Acceptance criteria'."""
    items, inside = [], False
    for line in (body or "").splitlines():
        if line.startswith("## "):
            inside = line.strip().lower() == "## acceptance criteria"
            continue
        match = re.match(r"\s*-\s*\[[ xX]\]\s*(.+)", line)
        if inside and match:
            items.append(match.group(1).strip())
    return items


def slugify(title: str, limit: int = 40) -> str:
    text = re.sub(r"^\s*\[[^\]]*\]\s*", "", title or "")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:limit].strip("-") or "task"


def branch_name(number: int, title: str) -> str:
    return f"claude/issue-{number}-{slugify(title)}"


def is_task_issue(title: str) -> bool:
    """The charter and the epic are not tasks; they are never developed."""
    lowered = (title or "").lower()
    return not (lowered.startswith("[epic]") or "project charter" in lowered)


# ---------------------------------------------------------------- paths

def to_repo_rel(path: str, root: str, cwd: str | None = None) -> str | None:
    """The repository-relative path with symlinks resolved, or None when it points outside the repository."""
    root_real = os.path.realpath(root)
    candidate = path if os.path.isabs(path) else os.path.join(cwd or root_real, path)
    real = os.path.realpath(candidate)
    if real != root_real and not real.startswith(root_real + os.sep):
        return None
    return os.path.relpath(real, root_real).replace(os.sep, "/")


def write_allowed(rel: str) -> bool:
    """May the agent create or change this repository-relative path?"""
    if not rel or rel.startswith("/"):
        return False
    rel = posixpath.normpath(rel)
    parts = rel.split("/")
    if rel == "." or ".." in parts or ".git" in parts:
        return False
    if parts[0] == "restaurant" and len(parts) >= 2:
        return True
    return bool(ALLOWED_WORKFLOW.fullmatch(rel))


def read_allowed(rel: str | None) -> bool:
    return rel is not None and ".git" not in rel.split("/")


def is_cache_path(path: str) -> bool:
    parts = path.split("/")
    return bool(CACHE_PARTS.intersection(parts)) or parts[-1] in CACHE_FILES or path.endswith(".pyc")


def path_violations(changed: list[str]) -> list[str]:
    return [p for p in changed if not is_cache_path(p) and not write_allowed(p)]


# ---------------------------------------------------------------- diff checks

def parse_numstat(text: str) -> int:
    total = 0
    for line in text.splitlines():
        added, deleted, *_ = (line.split("\t") + ["0", "0"])[:3]
        total += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    return total


def scan_secrets(text: str) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text or "")]


def new_requirements(before: str, after: str) -> list[str]:
    """Package names present in the new requirements text but not the old, for the pull request description."""
    def names(text: str) -> set[str]:
        found = set()
        for line in (text or "").splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                found.add(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].lower())
        return found
    return sorted(names(after) - names(before))


# ---------------------------------------------------------------- commands

_PATHLIKE = re.compile(r"[/.~]")
_ENV_REF = re.compile(r"\$[A-Za-z_{(]")
READ_COMMANDS = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "pwd", "echo", "sort", "uniq", "diff", "true",
                 "test", "basename", "dirname"}
PYTHON_MODULES = {"pytest", "ruff", "restaurant.db", "restaurant.evals", "restaurant.notify"}
GIT_READ = {"status", "diff", "log", "show", "ls-files", "rev-parse"}


def bash_verdict(command: str, root: str, cwd: str | None = None) -> tuple[bool, str]:
    """Is this shell command on the allow-list? Deny by default: anything not recognised is refused."""
    text = (command or "").strip()
    if not text:
        return False, "empty command"
    for bad in ("$(", "`", "<(", ">(", "<<"):
        if bad in text:
            return False, f"'{bad}' is not allowed; use the Write/Edit tools to create files"
    if re.search(r"(?<![&|>])&(?![&>])", text.replace("2>&1", "")):
        return False, "background jobs are not allowed"
    for segment in re.split(r"\s*(?:&&|\|\||;|\||\n)\s*", text):
        if segment.strip():
            ok, why = _segment_verdict(segment, root, cwd)
            if not ok:
                return False, why
    return True, ""


def _repo_path(arg: str, root: str, cwd: str | None) -> str | None:
    if arg.startswith("~") or _ENV_REF.search(arg):
        return None
    return to_repo_rel(arg, root, cwd)


def _segment_verdict(segment: str, root: str, cwd: str | None) -> tuple[bool, str]:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return False, "cannot parse the command"
    args: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        match = re.fullmatch(r"(\d?)(>>?)(.*)", token)
        if match:
            target = match.group(3)
            if not target:
                index += 1
                target = tokens[index] if index < len(tokens) else ""
            if not re.fullmatch(r"&\d|/dev/null", target):
                rel = _repo_path(target, root, cwd)
                if rel is None or not write_allowed(rel):
                    return False, f"writing to '{target}' is not allowed"
        elif token.startswith("<"):
            return False, "input redirection is not allowed"
        else:
            args.append(token)
        index += 1
    if not args:
        return True, ""
    name, rest = args[0], args[1:]
    if "=" in name and not name.startswith("-"):
        return False, "setting environment variables inline is not allowed"
    for arg in rest:
        if _ENV_REF.search(arg):
            return False, "environment variable references are not allowed"

    if name in {"python", "python3"}:
        return _python_verdict(rest, root, cwd)
    if name in {"pytest", "ruff"}:
        return _tool_verdict(name, rest, root, cwd)
    if name == "git":
        sub = rest[0] if rest else ""
        if sub not in GIT_READ:
            return False, f"git {sub or ''} is not allowed; the pipeline commits and pushes, you only read"
        if any(a.startswith(("--output", "-o")) for a in rest[1:]):
            return False, "git output redirection flags are not allowed"
        return True, ""
    if name in READ_COMMANDS:
        for arg in rest:
            if not arg.startswith("-") and _PATHLIKE.search(arg) and not read_allowed(_repo_path(arg, root, cwd)):
                return False, f"reading '{arg}' is not allowed (outside the repository or inside .git)"
        return True, ""
    if name == "sed":
        if any(a.startswith(("-i", "--in-place")) for a in rest):
            return False, "sed -i is not allowed; use the Edit tool"
        return True, ""
    if name == "find":
        if any(a in {"-exec", "-execdir", "-ok", "-delete"} or a.startswith("-fprint") for a in rest):
            return False, "find with actions is not allowed"
        return True, ""
    if name in {"mkdir", "touch", "cp", "mv", "rm"}:
        paths = [a for a in rest if not a.startswith("-")]
        flags = [a for a in rest if a.startswith("-")]
        if not paths:
            return False, f"{name} needs a path"
        for path in paths:
            rel = _repo_path(path, root, cwd)
            if rel is None or not write_allowed(rel):
                return False, f"{name} on '{path}' is not allowed (only restaurant/ and restaurant workflows)"
            if name == "rm" and ("*" in path or "?" in path) and any("r" in f.lower() for f in flags):
                return False, "recursive rm with wildcards is not allowed"
            if name == "rm" and any("r" in f.lower() for f in flags) and len(rel.split("/")) < 3:
                return False, "recursive rm needs a path at least two levels below restaurant/"
        return True, ""
    return False, (f"'{name}' is not allowed. Allowed: python -m pytest/ruff on restaurant/, python restaurant/..., git status/diff/log, "
                   "ls/cat/head/tail/grep/find, mkdir/touch/cp/mv/rm inside restaurant/")


def _python_verdict(rest: list[str], root: str, cwd: str | None) -> tuple[bool, str]:
    if not rest:
        return False, "interactive python is not allowed"
    if rest[0] == "-m":
        module = rest[1] if len(rest) > 1 else ""
        if module == "pip":
            tail = [a for a in rest[2:] if a not in {"-q", "--quiet"}]
            if (len(tail) == 3 and tail[0] == "install" and tail[1] == "-r"
                    and re.fullmatch(r"restaurant/requirements[A-Za-z0-9._-]*\.txt", tail[2])):
                return True, ""
            return False, "only 'python -m pip install -r restaurant/requirements*.txt' is allowed"
        if module == "playwright":
            return (True, "") if rest[2:] == ["install", "chromium"] else (False, "only 'playwright install chromium'")
        if module in PYTHON_MODULES:
            return _tool_verdict(module, rest[2:], root, cwd)
        return False, f"python -m {module} is not allowed"
    if rest[0].startswith("-"):
        return False, "python flags such as -c are not allowed; put code in a file under restaurant/"
    rel = _repo_path(rest[0], root, cwd)
    if rel and rel.startswith("restaurant/") and rel.endswith(".py"):
        return True, ""
    return False, "only scripts under restaurant/ may be run"


VALUE_FLAGS = {"-k", "-m", "-p", "-c", "-o", "-n", "--maxfail", "--tb", "--cov", "--cov-report", "--cov-fail-under",
               "--durations", "--rootdir", "--confcutdir", "--select", "--ignore", "--config", "--output-format",
               "--target-version", "--line-length"}
SUBCOMMANDS = {"check", "format"}


def _positionals(rest: list[str]) -> list[str]:
    """Arguments that are neither flags nor the value of a flag: for pytest and ruff these are the paths."""
    found, skip = [], False
    for arg in rest:
        if skip:
            skip = False
        elif arg.startswith("-"):
            skip = arg in VALUE_FLAGS
        else:
            found.append(arg)
    return found


def _tool_verdict(tool: str, rest: list[str], root: str, cwd: str | None) -> tuple[bool, str]:
    """pytest and ruff must be given an explicit path inside restaurant/ (ruff format and --fix rewrite files, and a bare
    'pytest' would run the course's own tests)."""
    if tool not in {"pytest", "ruff"}:
        return True, ""
    paths = [a for a in _positionals(rest) if a not in SUBCOMMANDS]
    if not paths:
        return False, f"{tool} needs an explicit path under restaurant/"
    for path in paths:
        rel = _repo_path(path.split("::")[0], root, cwd)
        if rel is None or not (rel == "restaurant" or rel.startswith("restaurant/")):
            return False, f"{tool} may only be pointed at restaurant/, not '{path}'"
    return True, ""

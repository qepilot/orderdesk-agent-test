"""Quality gates run by plain code after the developer agent finishes. The agent cannot talk its way past these.

Hard failures: a path outside the allow-list, a change over the size limit, a secret in the diff, ruff or pytest failing,
coverage under the threshold, code changed without any test. Warnings: dependency audit (so a new advisory does not block unrelated work).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from .rules import MAX_CHANGED_LINES, is_cache_path, parse_numstat, path_violations, scan_secrets

COVERAGE_THRESHOLD = 85


def git(root: str, *args: str) -> str:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return done.stdout


def changed_files(root: str) -> list[str]:
    tracked = git(root, "diff", "--name-only", "HEAD").splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({p for p in tracked + untracked if p and not is_cache_path(p)})


def _untracked_text(root: str, files: list[str], limit: int = 200_000) -> str:
    tracked = set(git(root, "diff", "--name-only", "HEAD").splitlines())
    chunks = []
    for path in files:
        if path not in tracked:
            try:
                chunks.append(f"+++ {path}\n" + (Path(root) / path).read_text(encoding="utf-8", errors="replace")[:limit])
            except OSError:
                pass
    return "\n".join(chunks)


def changed_line_count(root: str, files: list[str]) -> int:
    total = parse_numstat(git(root, "diff", "--numstat", "HEAD"))
    tracked = set(git(root, "diff", "--name-only", "HEAD").splitlines())
    for path in files:
        if path not in tracked:
            try:
                total += len((Path(root) / path).read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    return total


def diff_text(root: str, files: list[str], limit: int = 80_000) -> str:
    return (git(root, "diff", "HEAD") + "\n" + _untracked_text(root, files))[:limit]


def run_cmd(command: list[str], root: str, timeout: int = 900) -> tuple[int, str]:
    try:
        done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return done.returncode, ((done.stdout or "") + (done.stderr or ""))[-4000:]


def _is_test_path(path: str) -> bool:
    name = path.split("/")[-1]
    return "/tests/" in path or name.startswith("test_") or name == "conftest.py"


def run_gates(root: str, *, run=run_cmd) -> dict:
    files = changed_files(root)
    checks: list[dict] = []

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if not files:
        add("changes", "fail", "the agent produced no changes")
        return {"ok": False, "checks": checks, "files": files, "lines": 0}

    bad = path_violations(files)
    add("paths", "fail" if bad else "pass",
        "changed files outside the allowed area: " + ", ".join(bad) if bad else f"{len(files)} files, all allowed")

    lines = changed_line_count(root, files)
    add("size", "fail" if lines > MAX_CHANGED_LINES else "pass",
        f"{lines} changed lines (limit {MAX_CHANGED_LINES}); split the issue" if lines > MAX_CHANGED_LINES
        else f"{lines} changed lines")

    found = scan_secrets(diff_text(root, files, limit=2_000_000))
    add("secrets", "fail" if found else "pass", "possible secrets: " + ", ".join(found) if found else "none found")

    code = [p for p in files if p.startswith("restaurant/") and p.endswith(".py") and not _is_test_path(p)]
    tests = [p for p in files if p.startswith("restaurant/") and _is_test_path(p)]
    if code and not tests:
        add("tests_present", "fail", "application code changed but no test was added or changed")
    else:
        add("tests_present", "pass", f"{len(tests)} test files")

    py_present = any(Path(root, "restaurant").rglob("*.py")) if Path(root, "restaurant").is_dir() else False
    if py_present:
        rc, out = run([sys.executable, "-m", "ruff", "check", "restaurant"], root)
        add("ruff", "pass" if rc == 0 else "fail", out)
        pytest_cmd = [sys.executable, "-m", "pytest", "restaurant", "-q", "-p", "no:cacheprovider"]
        has_app = Path(root, "restaurant", "app").is_dir()
        if has_app and importlib.util.find_spec("pytest_cov"):
            pytest_cmd += ["--cov=restaurant/app", f"--cov-fail-under={COVERAGE_THRESHOLD}", "--cov-report=term-missing:skip-covered"]
        elif has_app:
            add("coverage", "warn", "pytest-cov is not installed; coverage was not measured")
        rc, out = run(pytest_cmd, root)
        add("pytest", "pass" if rc == 0 else "fail", out)
    else:
        add("ruff", "skip", "no Python code yet")
        add("pytest", "skip", "no Python code yet")

    migration_check = Path(root, "scripts", "check_migrations.py")
    restaurant_check = Path(root, "restaurant", "scripts", "check_migrations.py")
    for script in (restaurant_check, migration_check):
        if script.is_file() and str(script).startswith(str(Path(root, "restaurant"))):
            rc, out = run([sys.executable, str(script)], root)
            add("migration_check", "pass" if rc == 0 else "fail", out)
            break

    requirements = Path(root, "restaurant", "requirements.txt")
    if requirements.is_file() and importlib.util.find_spec("pip_audit"):
        rc, out = run([sys.executable, "-m", "pip_audit", "-r", str(requirements), "--progress-spinner", "off"], root, 300)
        add("dependency_audit", "pass" if rc == 0 else "warn", out)

    return {"ok": not any(c["status"] == "fail" for c in checks), "checks": checks, "files": files, "lines": lines}

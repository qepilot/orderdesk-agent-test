"""Run the local quality checks: ruff, then pytest with coverage. Exits non-zero on failure.

Later issues add their checks to CHECKS.
"""

from __future__ import annotations

import subprocess
import sys

CHECKS: list[tuple[str, list[str]]] = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "restaurant"]),
    (
        "pytest",
        [
            sys.executable,
            "-m",
            "pytest",
            "restaurant",
            "-q",
            "--cov=restaurant/app",
            "--cov=restaurant/db",
            "--cov-fail-under=85",
        ],
    ),
]


def run_checks(checks: list[tuple[str, list[str]]]) -> int:
    """Run every check in order; return 0 only if all pass (stops at the first failure)."""
    for name, command in checks:
        print(f"==> {name}: {' '.join(command)}", flush=True)
        if subprocess.run(command).returncode != 0:
            print(f"check failed: {name}", file=sys.stderr)
            return 1
    print("all checks passed")
    return 0


def main() -> int:
    return run_checks(CHECKS)


if __name__ == "__main__":
    sys.exit(main())

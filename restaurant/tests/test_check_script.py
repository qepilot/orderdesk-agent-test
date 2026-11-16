import sys

from restaurant.scripts import check

PY = sys.executable
OK = [PY, "-I", "-c", "pass"]
FAIL = [PY, "-I", "-c", "raise SystemExit(3)"]


def test_check_script_exit_zero_when_all_pass():
    assert check.run_checks([("a", OK), ("b", OK)]) == 0


def test_check_script_exit_nonzero_when_first_fails():
    assert check.run_checks([("ruff", FAIL), ("pytest", OK)]) != 0


def test_check_script_exit_nonzero_when_second_fails():
    assert check.run_checks([("ruff", OK), ("pytest", FAIL)]) != 0


def test_check_script_runs_ruff_then_pytest_with_85_coverage():
    names = [n for n, _ in check.CHECKS]
    assert names == ["ruff", "pytest"]
    assert "--cov-fail-under=85" in check.CHECKS[1][1]
    assert "--cov=restaurant/app" in check.CHECKS[1][1]


def test_check_script_main_uses_configured_checks(monkeypatch):
    monkeypatch.setattr(check, "CHECKS", [("x", FAIL)])
    assert check.main() == 1

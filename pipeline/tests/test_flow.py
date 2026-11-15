"""Preflight, gates, evaluator, report and publish, with a fake GitHub and real temporary git repositories."""

import json
import subprocess
from datetime import datetime, timezone

import httpx
import pytest

from pipeline import evaluator, gates, publish as publish_mod, report
from pipeline.gh import GitHub
from pipeline.preflight import run_preflight

TASK_BODY = ("**Depends on:** #9\n\n## Goal\nx\n\n## Acceptance criteria\n- [ ] First\n- [ ] Second\n\n"
             "---\n_Rules for every task: see #5. Nothing here starts until labelled `claude-ready`._")


def fake_github(overrides=None, calls=None):
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path.removeprefix('/repos/o/r')}"
        if calls is not None:
            calls.append((key, request.read().decode()))
        if key in overrides:
            return httpx.Response(200, json=overrides[key])
        defaults = {
            "GET /issues/10": {"number": 10, "title": "[DB] Schema: orders", "state": "open", "body": TASK_BODY,
                               "author_association": "OWNER"},
            "GET /issues/5": {"number": 5, "title": "charter", "state": "open", "body": "Money is integer cents."},
            "GET /issues/9": {"number": 9, "title": "[DB] earlier", "state": "closed", "body": ""},
            "GET /collaborators/alice/permission": {"permission": "write"},
            "GET /pulls": [],
            "GET /actions/workflows/claude-develop.yml/runs": {"total_count": 1},
        }
        if key in defaults:
            return httpx.Response(200, json=defaults[key])
        if request.method in {"POST", "PATCH", "DELETE"}:
            return httpx.Response(201, json={"html_url": "https://github.example/x", "number": 77})
        if key.startswith("GET /issues/") and key.endswith("/comments"):
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})
    return GitHub("o/r", "t", transport=httpx.MockTransport(handler))


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- preflight

def test_preflight_proceeds_when_everything_is_in_order():
    decision = run_preflight(fake_github(), 10, "alice", now=NOW)
    assert decision.proceed, decision.reasons
    assert decision.context["branch"] == "claude/issue-10-schema-orders"
    assert decision.context["charter"] == {"number": 5, "body": "Money is integer cents."}
    assert decision.context["dependencies"] == [{"number": 9, "title": "[DB] earlier", "state": "closed"}]


@pytest.mark.parametrize("key,payload,fragment", [
    ("GET /issues/9", {"number": 9, "title": "dep", "state": "open", "body": ""}, "dependencies"),
    ("GET /issues/10", {"number": 10, "title": "[Epic] all", "state": "open", "body": TASK_BODY, "author_association": "OWNER"}, "not development tasks"),
    ("GET /issues/10", {"number": 10, "title": "[DB] x", "state": "open", "body": TASK_BODY, "author_association": "NONE"}, "untrusted"),
    ("GET /issues/10", {"number": 10, "title": "[DB] x", "state": "closed", "body": TASK_BODY, "author_association": "OWNER"}, "not open"),
    ("GET /issues/10", {"number": 10, "title": "[DB] x", "state": "open", "body": "no charter reference", "author_association": "OWNER"}, "charter"),
    ("GET /issues/10", {"number": 10, "title": "[DB] x", "state": "open", "body": TASK_BODY + "x" * 21000, "author_association": "OWNER"}, "longer than"),
    ("GET /collaborators/alice/permission", {"permission": "read"}, "write access is required"),
    ("GET /pulls", [{"number": 3, "head": {"ref": "claude/issue-10-old"}}], "already open"),
    ("GET /actions/workflows/claude-develop.yml/runs", {"total_count": 9}, "daily limit"),
])
def test_preflight_refuses_and_says_why(key, payload, fragment):
    decision = run_preflight(fake_github({key: payload}), 10, "alice", max_runs_per_day=6, now=NOW)
    assert not decision.proceed
    assert any(fragment in reason for reason in decision.reasons), decision.reasons


def test_preflight_reports_all_problems_together():
    github = fake_github({"GET /issues/9": {"number": 9, "title": "d", "state": "open", "body": ""},
                          "GET /collaborators/alice/permission": {"permission": "read"}})
    assert len(run_preflight(github, 10, "alice", now=NOW).reasons) == 2


# ---------------------------------------------------------------- gates on a real git repository

def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("hi\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    return tmp_path


def ok_runner(command, root, timeout=900):
    return 0, "ok"


def statuses(result):
    return {c["name"]: c["status"] for c in result["checks"]}


def test_gates_fail_when_nothing_changed(repo):
    assert gates.run_gates(str(repo), run=ok_runner)["ok"] is False


def test_gates_pass_for_app_code_with_tests(repo):
    (repo / "restaurant" / "app").mkdir(parents=True)
    (repo / "restaurant" / "tests").mkdir()
    (repo / "restaurant" / "app" / "main.py").write_text("x = 1\n")
    (repo / "restaurant" / "tests" / "test_main.py").write_text("def test_x():\n    assert True\n")
    result = gates.run_gates(str(repo), run=ok_runner)
    assert result["ok"] is True, result
    assert statuses(result)["paths"] == "pass" and statuses(result)["tests_present"] == "pass"


def test_gates_catch_changes_outside_the_allowed_area(repo):
    (repo / "restaurant").mkdir()
    (repo / "restaurant" / "a.txt").write_text("x\n")
    (repo / "assistant").mkdir()
    (repo / "assistant" / "llm.py").write_text("evil = 1\n")
    result = gates.run_gates(str(repo), run=ok_runner)
    assert not result["ok"] and statuses(result)["paths"] == "fail"
    assert "assistant/llm.py" in [c for c in result["checks"] if c["name"] == "paths"][0]["detail"]


def test_gates_catch_modified_tracked_files_outside_the_area(repo):
    (repo / "README.md").write_text("changed\n")
    (repo / "restaurant").mkdir()
    (repo / "restaurant" / "a.txt").write_text("x\n")
    assert statuses(gates.run_gates(str(repo), run=ok_runner))["paths"] == "fail"


def test_gates_catch_oversized_changes(repo):
    (repo / "restaurant").mkdir()
    (repo / "restaurant" / "big.txt").write_text("line\n" * 900)
    result = gates.run_gates(str(repo), run=ok_runner)
    assert statuses(result)["size"] == "fail" and not result["ok"]


def test_gates_catch_secrets(repo):
    (repo / "restaurant").mkdir()
    (repo / "restaurant" / "config.py").write_text('TOKEN = "ghp_' + "A" * 36 + '"\n')
    (repo / "restaurant" / "tests").mkdir()
    (repo / "restaurant" / "tests" / "test_c.py").write_text("def test_c():\n    pass\n")
    assert statuses(gates.run_gates(str(repo), run=ok_runner))["secrets"] == "fail"


def test_gates_require_tests_with_code(repo):
    (repo / "restaurant" / "app").mkdir(parents=True)
    (repo / "restaurant" / "app" / "main.py").write_text("x = 1\n")
    result = gates.run_gates(str(repo), run=ok_runner)
    assert statuses(result)["tests_present"] == "fail" and not result["ok"]


def test_gates_report_failing_pytest_and_ruff(repo):
    (repo / "restaurant" / "tests").mkdir(parents=True)
    (repo / "restaurant" / "tests" / "test_a.py").write_text("def test_a():\n    assert False\n")
    result = gates.run_gates(str(repo), run=lambda command, root, timeout=900: (1, "1 failed"))
    assert statuses(result)["pytest"] == "fail" and statuses(result)["ruff"] == "fail" and not result["ok"]


def test_gates_ignore_cache_directories(repo):
    (repo / "restaurant" / "tests").mkdir(parents=True)
    (repo / "restaurant" / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")
    (repo / "restaurant" / "tests" / "__pycache__").mkdir()
    (repo / "restaurant" / "tests" / "__pycache__" / "x.pyc").write_text("x")
    assert statuses(gates.run_gates(str(repo), run=ok_runner))["paths"] == "pass"


# ---------------------------------------------------------------- evaluator

def evaluation(*statuses_, findings=()):
    return {"criteria": [{"index": i, "status": s, "evidence": f"test_{i}"} for i, s in enumerate(statuses_, 1)],
            "guardrail_findings": list(findings), "summary": "ok"}


def test_decide_requires_every_criterion_met():
    assert evaluator.decide(evaluation("met", "met"), 2) == (True, [])
    ready, problems = evaluator.decide(evaluation("met", "partly"), 2)
    assert not ready and "criterion 2 is partly" in problems[0]
    assert not evaluator.decide(evaluation("met"), 2)[0]                    # a criterion was skipped
    assert not evaluator.decide(None, 2)[0]
    assert not evaluator.decide({"nothing": 1}, 2)[0]


def test_decide_blocks_on_high_guardrail_findings_only():
    assert evaluator.decide(evaluation("met", findings=[{"severity": "low", "text": "style"}]), 1)[0]
    ready, problems = evaluator.decide(evaluation("met", findings=[{"severity": "high", "text": "card data logged"}]), 1)
    assert not ready and "card data logged" in problems[0]


def test_evaluate_uses_read_only_tools_and_the_decision_comes_from_code(tmp_path):
    seen = {}

    def runner(command, prompt, *, cwd, env, timeout):
        seen.update(command=command, prompt=prompt, env=env)
        return {"returncode": 0, "timed_out": False, "stderr": "",
                "data": {"structured_output": evaluation("met", "met"), "total_cost_usd": 0.2}}

    context = {"issue": {"number": 10, "title": "t", "body": TASK_BODY}, "charter": {"body": "rules"}}
    result = evaluator.evaluate(context, "diff text", {"checks": []}, tmp_path, str(tmp_path), runner=runner,
                                environ={"GITHUB_TOKEN": "x", "CLAUDE_CODE_OAUTH_TOKEN": "o"})
    assert result["ready"] is True
    assert seen["command"][seen["command"].index("--tools") + 1] == "Read,Grep,Glob"
    assert "1. First" in seen["prompt"] and "2. Second" in seen["prompt"] and "GITHUB_TOKEN" not in seen["env"]
    settings = json.loads((tmp_path / "settings-evaluator.json").read_text())
    assert settings["permissions"]["deny"][0] == "Bash" and "StructuredOutput" in settings["permissions"]["allow"]


def test_evaluate_without_a_verdict_is_not_ready(tmp_path):
    runner = lambda *a, **k: {"returncode": 1, "timed_out": False, "stderr": "boom", "data": {}}  # noqa: E731
    context = {"issue": {"number": 10, "title": "t", "body": TASK_BODY}, "charter": {"body": ""}}
    assert evaluator.evaluate(context, "", {"checks": []}, tmp_path, str(tmp_path), runner=runner)["ready"] is False


# ---------------------------------------------------------------- report and publish

CONTEXT = {"issue": {"number": 10, "title": "[DB] Schema: orders", "body": TASK_BODY}, "charter": {"number": 5, "body": ""},
           "branch": "claude/issue-10-schema-orders"}
GATES = {"ok": True, "checks": [{"name": "pytest", "status": "pass", "detail": ""}], "files": ["restaurant/a.py"], "lines": 40}


def test_pr_body_closes_the_issue_and_shows_criteria_and_draft_state():
    rep = {"ready": False, "problems": ["criterion 2 is partly: x"], "evaluation": evaluation("met", "partly")}
    body = report.pr_body(CONTEXT, GATES, rep, [{"cost_usd": 1.0}], ["jinja2"], False, "https://run")
    assert body.startswith("Closes #10") and "**draft**" in body and "| 2 | Second | partly |" in body
    assert "`jinja2`" in body and "criterion 2 is partly" in body and "https://run" in body


def test_pr_body_is_withheld_if_it_would_contain_a_secret():
    rep = {"ready": True, "problems": [], "evaluation": {"criteria": [], "guardrail_findings": [], "summary": "sk-ant-" + "a" * 40}}
    assert "withheld" in report.pr_body(CONTEXT, GATES, rep, [], [], True, "")


def test_stage_and_commit_stages_only_allowed_paths(repo):
    (repo / "restaurant").mkdir()
    (repo / "restaurant" / "a.py").write_text("x = 1\n")
    (repo / "README.md").write_text("tampered\n")
    ok, _ = publish_mod.stage_and_commit(str(repo), 10, "Schema: orders")
    assert ok
    shown = subprocess.run(["git", "-C", str(repo), "show", "--name-only", "--format=%B", "HEAD"], capture_output=True, text=True).stdout
    assert "restaurant/a.py" in shown and "README.md" not in shown and "Closes #10" in shown


def test_stage_and_commit_with_nothing_to_commit(repo):
    assert publish_mod.stage_and_commit(str(repo), 10, "x") == (False, "nothing to commit")


def run_publish(repo, monkeypatch, *, gates_ok=True, ready=True, push_ok=True):
    (repo / "restaurant").mkdir(exist_ok=True)
    (repo / "restaurant" / "a.py").write_text("x = 1\n")
    calls: list = []
    monkeypatch.setattr(publish_mod, "push_branch", lambda root, repo_name, branch, token: (push_ok, "denied" if not push_ok else ""))
    gh = fake_github(calls=calls)
    result = publish_mod.publish(gh, CONTEXT, str(repo), {**GATES, "ok": gates_ok}, {"ready": ready, "problems": []}, [],
                                 token="t", base="main", run_url="https://run", ready_candidate=True)
    return result, calls


def test_publish_opens_a_ready_pull_request_when_everything_passed(repo, monkeypatch):
    result, calls = run_publish(repo, monkeypatch)
    pr_call = next(body for key, body in calls if key == "POST /pulls")
    payload = json.loads(pr_call)
    assert payload["draft"] is False and payload["head"] == "claude/issue-10-schema-orders" and payload["base"] == "main"
    assert payload["body"].startswith("Closes #10")
    assert not any(key == "POST /issues/10/labels" and "needs-human" in body for key, body in calls)
    assert result["ready"] is True


@pytest.mark.parametrize("gates_ok,ready", [(False, True), (True, False)])
def test_publish_opens_a_draft_with_needs_human_when_a_gate_or_the_evaluator_failed(repo, monkeypatch, gates_ok, ready):
    result, calls = run_publish(repo, monkeypatch, gates_ok=gates_ok, ready=ready)
    assert json.loads(next(body for key, body in calls if key == "POST /pulls"))["draft"] is True
    assert any(key == "POST /issues/10/labels" and "needs-human" in body for key, body in calls)
    assert result["ready"] is False


def test_publish_stops_and_flags_a_human_if_the_push_fails(repo, monkeypatch):
    result, calls = run_publish(repo, monkeypatch, push_ok=False)
    assert result["pr"] is None and not any(key == "POST /pulls" for key, _ in calls)
    assert any(key == "POST /issues/10/labels" and "needs-human" in body for key, body in calls)

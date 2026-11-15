import io
import json

import pytest

from pipeline import agent, hook

ROOT = "/repo"


def event(tool, **tool_input):
    return {"tool_name": tool, "tool_input": tool_input, "cwd": ROOT}


# ---------------------------------------------------------------- hook

@pytest.mark.parametrize("ev,allowed", [
    (event("Write", file_path="/repo/restaurant/app/main.py"), True),
    (event("Edit", file_path="restaurant/app/main.py"), True),
    (event("MultiEdit", file_path="/repo/.github/workflows/restaurant-ci.yml"), True),
    (event("Write", file_path="/repo/pipeline/rules.py"), False),
    (event("Write", file_path="/repo/.github/workflows/claude-develop.yml"), False),
    (event("Edit", file_path="/etc/passwd"), False),
    (event("Write", file_path="/repo/restaurant/../assistant/llm.py"), False),
    (event("Write", file_path=""), False),
    (event("Read", file_path="/repo/restaurant/app/main.py"), True),
    (event("Read", file_path="/repo/assistant/llm.py"), True),          # reading the rest of the repo is fine
    (event("Read", file_path="/repo/.git/config"), False),
    (event("Read", file_path="/etc/shadow"), False),
    (event("Read", file_path="/root/.ccr/ca-bundle.crt"), False),
    (event("Grep", pattern="x", path="/repo/restaurant"), True),
    (event("Grep", pattern="x", path="/"), False),
    (event("Glob", pattern="**/*.py"), True),
    (event("Glob", pattern="/etc/*"), False),
    (event("Glob", pattern="../**"), False),
    (event("Bash", command="python -m pytest restaurant -q"), True),
    (event("Bash", command="git push origin main"), False),
    (event("WebFetch", url="https://example.com"), False),
    (event("Task", prompt="do something"), False),
    (event("StructuredOutput", criteria=[]), True),
    ({"tool_name": "Bash"}, False),
])
def test_decide(ev, allowed):
    ok, reason = hook.decide(ev, ROOT)
    assert ok is allowed, reason


def run_main(monkeypatch, capsys, stdin_text):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    monkeypatch.setenv("PIPELINE_REPO_ROOT", ROOT)
    assert hook.main() == 0
    return capsys.readouterr().out


def test_main_denies_with_a_decision_the_cli_understands(monkeypatch, capsys):
    out = run_main(monkeypatch, capsys, json.dumps(event("Bash", command="curl http://x")))
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny" and "curl" in decision["permissionDecisionReason"]


def test_main_prints_nothing_when_allowed(monkeypatch, capsys):
    assert run_main(monkeypatch, capsys, json.dumps(event("Bash", command="git status"))) == ""


def test_main_fails_closed_on_garbage_input(monkeypatch, capsys):
    out = run_main(monkeypatch, capsys, "this is not json")
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------- agent configuration

def test_clean_env_keeps_the_model_credential_and_drops_every_other_secret():
    environ = {"PATH": "/usr/bin", "HOME": "/home/x", "CLAUDE_CODE_OAUTH_TOKEN": "oauth", "GITHUB_TOKEN": "ghs_x",
               "GH_TOKEN": "x", "ACTIONS_RUNTIME_TOKEN": "x", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "x",
               "ANTHROPIC_API_KEY": "k", "AWS_SECRET_ACCESS_KEY": "s", "DB_PASSWORD": "p", "GITHUB_REPOSITORY": "o/r",
               "RUNNER_TEMP": "/tmp/r"}
    env = agent.clean_env(environ)
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth" and env["PATH"] == "/usr/bin"
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "ANTHROPIC_API_KEY",
                 "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD", "GITHUB_REPOSITORY", "RUNNER_TEMP"):
        assert name not in env


def test_command_uses_the_restrictive_flags():
    command = agent.build_command("/tmp/s.json", model="sonnet", budget_usd="3")
    joined = " ".join(command)
    assert command[:2] == ["claude", "-p"]
    assert "--permission-mode dontAsk" in joined and "--max-budget-usd 3" in joined and "--model sonnet" in joined
    assert "--setting-sources user" in joined and "--no-session-persistence" in joined
    tools = command[command.index("--tools") + 1].split(",")
    assert set(tools) == {"Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Bash"}
    assert "--dangerously-skip-permissions" not in command


def test_settings_wire_the_hook_the_sandbox_and_denials():
    settings = agent.build_settings("python -m pipeline.hook")
    hooks = settings["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hooks["command"] == "python -m pipeline.hook" and settings["hooks"]["PreToolUse"][0]["matcher"] == "*"
    assert settings["sandbox"]["enabled"] is True and settings["sandbox"]["allowUnsandboxedCommands"] is False
    assert settings["sandbox"]["network"]["allowedDomains"] == ["pypi.org", "files.pythonhosted.org"]
    assert "WebFetch" in settings["permissions"]["deny"]
    assert "sandbox" not in agent.build_settings("x", sandbox=False)


CONTEXT = {"issue": {"number": 6, "title": "[Foundation] Scaffold", "body": "## Acceptance criteria\n- [ ] works"},
           "charter": {"number": 5, "body": "Money is integer cents."},
           "dependencies": [{"number": 5, "title": "charter", "state": "closed"}], "branch": "claude/issue-6-scaffold"}


def test_prompt_marks_issue_text_as_data_and_adds_feedback_on_repair():
    first = agent.developer_prompt(CONTEXT, 1)
    assert '<issue number="6">' in first and "Money is integer cents." in first and "repair attempt" not in first
    feedback = {"checks": [{"name": "pytest", "status": "fail", "detail": "1 failed"}, {"name": "ruff", "status": "pass"}]}
    second = agent.developer_prompt(CONTEXT, 2, feedback)
    assert "repair attempt" in second and "pytest: 1 failed" in second and "ruff" not in second.split("repair attempt")[1]


def test_develop_passes_no_github_token_and_detects_blocked(monkeypatch, tmp_path):
    seen = {}

    def fake_run(command, prompt, *, cwd, env, timeout):
        seen.update(env=env, prompt=prompt, timeout=timeout)
        return {"returncode": 0, "timed_out": False, "stderr": "",
                "data": {"result": "I could not decide.\nBLOCKED: should tax apply to tips?", "num_turns": 3,
                         "total_cost_usd": 0.4}}

    monkeypatch.setattr(agent, "run_claude", fake_run)
    summary = agent.develop(CONTEXT, 1, tmp_path / "out", str(tmp_path), environ={
        "PATH": "/bin", "GITHUB_TOKEN": "ghs_secret", "CLAUDE_CODE_OAUTH_TOKEN": "oauth"})
    assert summary["blocked"] is True and summary["ok"] is False and summary["cost_usd"] == 0.4
    assert "GITHUB_TOKEN" not in seen["env"] and seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth"
    assert seen["env"]["PIPELINE_REPO_ROOT"] == str(tmp_path.resolve())
    assert (tmp_path / "out" / "settings-attempt-1.json").exists() and (tmp_path / "out" / "developer-attempt-1.json").exists()


def test_develop_reports_success_and_timeouts(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "run_claude", lambda *a, **k: {"returncode": 0, "timed_out": False, "stderr": "",
                                                              "data": {"result": "Done. Tests pass."}})
    assert agent.develop(CONTEXT, 1, tmp_path / "o", str(tmp_path), environ={})["ok"] is True
    monkeypatch.setattr(agent, "run_claude", lambda *a, **k: {"returncode": -1, "timed_out": True, "stderr": "", "data": {}})
    timed_out = agent.develop(CONTEXT, 1, tmp_path / "o2", str(tmp_path), environ={})
    assert timed_out["ok"] is False and timed_out["timed_out"] is True


# ---------------------------------------------------------------- denial log

def test_denials_are_logged_when_a_log_file_is_configured(monkeypatch, capsys, tmp_path):
    log = tmp_path / "denials.jsonl"
    monkeypatch.setenv("PIPELINE_HOOK_LOG", str(log))
    run_main(monkeypatch, capsys, json.dumps(event("Bash", command="pip install fastapi")))
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert entries[0]["tool"] == "Bash" and "pip install fastapi" in entries[0]["input"] and "only 'pip install -r" in entries[0]["reason"]


def test_allowed_calls_are_not_logged(monkeypatch, capsys, tmp_path):
    log = tmp_path / "denials.jsonl"
    monkeypatch.setenv("PIPELINE_HOOK_LOG", str(log))
    run_main(monkeypatch, capsys, json.dumps(event("Bash", command="git status")))
    assert not log.exists()


def test_develop_prints_the_denials_and_counts_them(monkeypatch, tmp_path, capsys):
    def fake_run(command, prompt, *, cwd, env, timeout):
        with open(env["PIPELINE_HOOK_LOG"], "a") as handle:
            handle.write(json.dumps({"tool": "Bash", "input": "{\"command\": \"pip install x\"}", "reason": "not allowed"}) + "\n")
        return {"returncode": 0, "timed_out": False, "stderr": "", "data": {"result": "done"}}

    monkeypatch.setattr(agent, "run_claude", fake_run)
    summary = agent.develop(CONTEXT, 1, tmp_path / "o", str(tmp_path), environ={})
    assert summary["denials"] == 1 and "hook denied Bash: not allowed" in capsys.readouterr().out

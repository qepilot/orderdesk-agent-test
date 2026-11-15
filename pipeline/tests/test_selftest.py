import json
import re
from pathlib import Path

from pipeline import agent, selftest


def runner_that(succeeds, report="Error: bwrap: setting up uid map: Permission denied"):
    """A fake CLI: when it 'succeeds' it does what the command asked (leaves the nonce on disk), otherwise it does nothing."""
    seen = []

    def run(command, prompt, *, cwd, env, timeout):
        seen.append({"command": command, "prompt": prompt, "env": env})
        if succeeds(command):
            nonce = re.search(r"echo (\w+) >", prompt).group(1)
            marker = Path(cwd, "restaurant", ".selftest")
            marker.mkdir(parents=True)
            (marker / "probe.txt").write_text(nonce + "\n")
        return {"returncode": 0, "timed_out": False, "stderr": "", "data": {"result": report}}
    run.seen = seen
    return run


def settings_of(command):
    return json.loads(Path(command[command.index("--settings") + 1]).read_text())


def test_probe_succeeds_only_when_the_command_really_ran_and_cleans_up(tmp_path):
    out = tmp_path / "out"
    ok = selftest.probe("strict", str(tmp_path), out, runner=runner_that(lambda c: True), environ={"GITHUB_TOKEN": "x"})
    assert ok["ok"] is True and not Path(tmp_path, "restaurant", ".selftest").exists()
    failed = selftest.probe("strict", str(tmp_path), out, runner=runner_that(lambda c: False), environ={})
    assert failed["ok"] is False and "uid map" in failed["model_report"]


def test_a_model_that_merely_claims_success_does_not_count(tmp_path):
    claims = runner_that(lambda c: False, report="sandbox-ok, it worked")
    assert selftest.probe("strict", str(tmp_path), tmp_path / "o", runner=claims, environ={})["ok"] is False


def test_probe_uses_the_same_sandbox_settings_as_the_developer_and_scrubs_the_environment(tmp_path):
    run = runner_that(lambda c: True)
    selftest.probe("strict", str(tmp_path), tmp_path / "o", runner=run, environ={"GITHUB_TOKEN": "ghs", "CLAUDE_CODE_OAUTH_TOKEN": "o"})
    call = run.seen[0]
    sandbox = settings_of(call["command"])["sandbox"]
    assert sandbox["enabled"] is True and sandbox["allowUnsandboxedCommands"] is False and "enableWeakerNestedSandbox" not in sandbox
    assert "GITHUB_TOKEN" not in call["env"] and call["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "o"
    assert call["command"][call["command"].index("--tools") + 1] == "Bash"


def test_failure_of_strict_also_probes_the_weaker_mode_for_information(tmp_path):
    run = runner_that(lambda c: "enableWeakerNestedSandbox" in json.dumps(settings_of(c)))
    report = selftest.run_selftest("strict", str(tmp_path), tmp_path / "o", runner=run, environ={})
    assert report["ok"] is False and report["weaker_would_work"] is True
    assert [r["mode"] for r in report["results"]] == ["strict", "weaker-nested"]
    text = selftest.describe_failure(report)
    assert "CLAUDE_PIPELINE_SANDBOX_MODE" in text and "weaker-nested" in text and "uid map" in text
    assert json.loads((tmp_path / "o" / "selftest.json").read_text())["ok"] is False


def test_strict_success_does_not_probe_anything_else(tmp_path):
    run = runner_that(lambda c: True)
    report = selftest.run_selftest("strict", str(tmp_path), tmp_path / "o", runner=run, environ={})
    assert report["ok"] is True and len(run.seen) == 1


def test_the_weaker_mode_is_only_selected_explicitly():
    assert "enableWeakerNestedSandbox" not in agent.build_settings("h", sandbox_extra=agent.SANDBOX_MODES["strict"])["sandbox"]
    assert agent.build_settings("h", sandbox_extra=agent.SANDBOX_MODES["weaker-nested"])["sandbox"]["enableWeakerNestedSandbox"] is True
    assert agent.build_settings("h", sandbox_extra=agent.SANDBOX_MODES["weaker-nested"])["sandbox"]["allowUnsandboxedCommands"] is False

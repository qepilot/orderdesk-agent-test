"""Entry point used by the claude-develop workflow:  python -m pipeline <stage>

Stages: preflight, develop, gates, evaluate, publish, fail. Each is a separate workflow step so that credentials can be
given to exactly the steps that need them: the developer agent step gets only the model credential, publish gets only the
GitHub token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import evaluator, gates as gates_mod
from .agent import develop
from .gh import GitHub
from .preflight import run_preflight
from .publish import publish
from .report import MARKER, status_comment


def _out() -> Path:
    path = Path(os.environ.get("PIPELINE_OUT", "pipeline-out"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _set_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    print(f"{name}={value}")


def _gh() -> GitHub:
    return GitHub(os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_TOKEN", ""))


def _run_url() -> str:
    server, repo, run = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if run else ""


def _load(name: str):
    return json.loads((_out() / name).read_text(encoding="utf-8"))


def cmd_preflight(_args) -> int:
    gh = _gh()
    number = int(os.environ["ISSUE_NUMBER"])
    gh.ensure_label("claude-in-progress", "fbca04", "The automation is working on this issue")
    gh.ensure_label("needs-human", "d93f0b", "The automation needs a person to look at this")
    decision = run_preflight(gh, number, os.environ.get("SENDER", ""),
                             max_runs_per_day=int(os.environ.get("PIPELINE_MAX_RUNS_PER_DAY", "6")))
    (_out() / "context.json").write_text(json.dumps(decision.context, indent=2), encoding="utf-8")
    if not decision.proceed:
        gh.upsert_comment(number, status_comment("not started", _run_url(),
                                                 "\n".join(f"- {r}" for r in decision.reasons)), MARKER)
        _set_output("proceed", "false")
        return 0
    gh.add_labels(number, ["claude-in-progress"])
    gh.upsert_comment(number, status_comment("started", _run_url(), f"Branch: `{decision.context['branch']}`"), MARKER)
    _set_output("proceed", "true")
    _set_output("branch", decision.context["branch"])
    return 0


def cmd_develop(args) -> int:
    context = _load("context.json")
    feedback = _load("gates.json") if args.attempt > 1 and (_out() / "gates.json").exists() else None
    summary = develop(context, args.attempt, _out(), os.getcwd(), feedback=feedback,
                      sandbox=os.environ.get("PIPELINE_SANDBOX", "1") != "0", model=os.environ.get("PIPELINE_MODEL", ""),
                      budget_usd=os.environ.get("PIPELINE_BUDGET_USD", "5"),
                      timeout=int(os.environ.get("PIPELINE_AGENT_TIMEOUT", "1500")))
    _set_output("ok", str(summary["ok"]).lower())
    _set_output("blocked", str(summary["blocked"]).lower())
    print(json.dumps({k: v for k, v in summary.items() if k != "final_message"}))
    return 0


def cmd_gates(_args) -> int:
    report = gates_mod.run_gates(os.getcwd())
    (_out() / "gates.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for check in report["checks"]:
        print(f"{check['status']:>5}  {check['name']}")
    _set_output("ok", str(report["ok"]).lower())
    return 0


def cmd_evaluate(_args) -> int:
    context, gates = _load("context.json"), _load("gates.json")
    if not gates.get("files"):                       # nothing to review: do not spend a model call
        report = {"ready": False, "problems": ["the agent produced no changes"], "evaluation": None, "cost_usd": 0}
        (_out() / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        _set_output("ready", "false")
        return 0
    report = evaluator.evaluate(context, gates_mod.diff_text(os.getcwd(), gates.get("files", [])), gates, _out(), os.getcwd(),
                                model=os.environ.get("PIPELINE_MODEL", ""))
    print(json.dumps({"ready": report["ready"], "problems": report["problems"]}))
    _set_output("ready", str(report["ready"]).lower())
    return 0


def cmd_publish(_args) -> int:
    context, gates = _load("context.json"), _load("gates.json")
    report = _load("evaluation.json") if (_out() / "evaluation.json").exists() else {"ready": False, "problems": ["not evaluated"]}
    developer = [json.loads(p.read_text(encoding="utf-8"))["summary"] for p in sorted(_out().glob("developer-attempt-*.json"))]
    result = publish(_gh(), context, os.getcwd(), gates, report, developer, token=os.environ["GITHUB_TOKEN"],
                     base=os.environ.get("PIPELINE_BASE", "main"), run_url=_run_url(), ready_candidate=True)
    print(json.dumps(result))
    _set_output("pr", str(result.get("pr") or ""))
    return 0


def cmd_fail(args) -> int:
    context = _load("context.json") if (_out() / "context.json").exists() else None
    number = int(os.environ["ISSUE_NUMBER"])
    gh = _gh()
    reason = args.reason or "the pipeline stopped before finishing"
    developer = sorted(_out().glob("developer-attempt-*.json"))
    if developer:
        message = json.loads(developer[-1].read_text(encoding="utf-8"))["summary"].get("final_message", "")
        if "BLOCKED:" in message.upper():
            reason = "the agent needs a decision: " + message[message.upper().index("BLOCKED:"):][:1500]
    gh.ensure_label("needs-human", "d93f0b", "The automation needs a person to look at this")
    gh.upsert_comment(number, status_comment("stopped, needs a person", _run_url(), reason), MARKER)
    gh.add_labels(number, ["needs-human"])
    gh.remove_label(number, "claude-in-progress")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    commands = parser.add_subparsers(dest="stage", required=True)
    commands.add_parser("preflight").set_defaults(fn=cmd_preflight)
    develop_parser = commands.add_parser("develop")
    develop_parser.add_argument("--attempt", type=int, default=1)
    develop_parser.set_defaults(fn=cmd_develop)
    commands.add_parser("gates").set_defaults(fn=cmd_gates)
    commands.add_parser("evaluate").set_defaults(fn=cmd_evaluate)
    commands.add_parser("publish").set_defaults(fn=cmd_publish)
    fail_parser = commands.add_parser("fail")
    fail_parser.add_argument("--reason", default="")
    fail_parser.set_defaults(fn=cmd_fail)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

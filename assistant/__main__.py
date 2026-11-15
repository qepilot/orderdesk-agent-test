"""Command line for the assistant.

    python -m assistant investigate 101            investigate an issue
    python -m assistant review 201 --role dba      review a pull request with a role emphasis
    python -m assistant eval                       run every evaluation case and print the report
    python -m assistant eval --role qa             only the cases relevant to QA
    python -m assistant investigate 1 --repo OWNER/NAME [--post-comment]
                                                   read the issue from a real GitHub repository (needs GITHUB_TOKEN
                                                   and a live model) and optionally post the findings as a comment

Without a model in .env the hand-written stand-in scripts are used (lab/scripts.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from dotenv import load_dotenv

from .workspace import COURSE_DIR, default_workspace

load_dotenv(COURSE_DIR / ".env")

from lab.models import model_for, using_live_model  # noqa: E402

from .app import build_assistant, issue_task, pr_task  # noqa: E402
from .evals import load_cases, report, run_eval, task_for  # noqa: E402
from .findings import render_markdown  # noqa: E402
from .github import GitHubError, LiveGitHub  # noqa: E402
from .guards import redact  # noqa: E402
from .llm import llm_status  # noqa: E402
from .tracing import Tracer, summarize  # noqa: E402


def run_one(kind: str, number: int, role: str | None, quiet: bool = False, github=None):
    workspace = default_workspace()
    script = f"{'issue' if kind == 'issue' else 'pr'}-{number}"
    task = issue_task(number) if kind == "issue" else pr_task(number)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tracer = Tracer(workspace.out / "traces" / f"{script}-{stamp}.jsonl", echo=not quiet)
    assistant = build_assistant(model_for(script), workspace=workspace, role=role, task=task, tracer=tracer,
                                state_path=workspace.out / "state" / f"{script}.json", github=github)
    result = assistant.agent.run(task)
    return result, tracer


COMMENT_MARKER = "<!-- engineering-assistant:investigation -->"   # lets a rerun find and edit its own comment
LEGACY_COMMENT_TAILS = ("_Drafted by the engineering assistant",)     # comments posted before the marker existed


def comment_body(result) -> str:
    """The text posted back to the issue. Redacted again here: this is the one place the model's words leave the harness."""
    if result.findings is not None:
        return redact(render_markdown(result.findings))
    return (f"The engineering assistant could not finish this investigation (stopped: `{result.stop_reason}`). "
            "A person should look at it.\n\n_Drafted by the engineering assistant._")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m assistant", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, noun in (("investigate", "issue"), ("review", "pull request")):
        command = commands.add_parser(name, help=f"work on one {noun}")
        command.add_argument("number", type=int)
        command.add_argument("--role", choices=["swe", "dba", "qa"])
        command.add_argument("--json", action="store_true", help="print the findings as JSON")
        command.add_argument("--repo", metavar="OWNER/NAME",
                             help="read the issue or pull request from this GitHub repository (needs GITHUB_TOKEN and a live model)")
        command.add_argument("--post-comment", action="store_true",
                             help="with --repo: post the findings as a comment on the issue or pull request")
    evaluate = commands.add_parser("eval", help="run the evaluation cases")
    evaluate.add_argument("--role", choices=["swe", "dba", "qa"])
    evaluate.add_argument("--case", action="append", help="a case id such as issue-101 (repeatable)")
    args = parser.parse_args(argv)

    print(llm_status(), "" if using_live_model() else "-> using the scripted stand-in", file=sys.stderr)

    if args.command == "eval":
        workspace = default_workspace()
        cases = load_cases(workspace.expected / "cases.json", ids=args.case, role=args.role)

        def run_case(case):
            assistant = build_assistant(model_for(case["id"]), workspace=workspace, role=args.role, task=task_for(case))
            return assistant.agent.run(task_for(case))

        grades = run_eval(cases, run_case, on_result=lambda g: print(f"  {g.case_id}: {'pass' if g.passed else 'FAIL'}",
                                                                     file=sys.stderr))
        print(report(grades, f"Evaluation ({'live model' if using_live_model() else 'stand-in scripts'})"))
        return 0 if all(g.passed for g in grades) else 1

    github = None
    if args.post_comment and not args.repo:
        parser.error("--post-comment needs --repo")
    if args.repo:
        if not using_live_model():      # the stand-in scripts only know the workshop numbers, not real ones
            print("--repo needs a live model: set LLM_PROVIDER=claude-code or LLM_API_KEY in .env", file=sys.stderr)
            return 2
        github = LiveGitHub(args.repo, allow_comments=args.post_comment)

    result, tracer = run_one("issue" if args.command == "investigate" else "pr", args.number, args.role, github=github)
    print()
    if result.findings is None:
        print(f"No findings: the run stopped with '{result.stop_reason}'. {result.error}")
    else:
        print(json.dumps(result.findings, indent=2) if args.json else render_markdown(result.findings))
    print(f"\n{json.dumps(summarize(tracer.events))}\ntrace: {tracer.path}", file=sys.stderr)
    if args.post_comment:
        try:
            posted = github.upsert_comment(args.number, comment_body(result), COMMENT_MARKER, LEGACY_COMMENT_TAILS)
        except GitHubError as error:
            print(f"could not post the comment: {error}", file=sys.stderr)
            return 3
        print(f"{'updated' if posted.get('updated') else 'posted'}: {posted['url']}", file=sys.stderr)
    return 0 if result.findings is not None else 1


if __name__ == "__main__":
    sys.exit(main())

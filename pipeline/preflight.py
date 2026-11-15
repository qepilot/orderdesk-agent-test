"""Preflight: decide, with plain code, whether a claude-ready label may start a run. No model is involved.

Every reason to refuse is checked and reported together, so the comment on the issue says everything that is wrong at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .gh import GitHub, GitHubError
from .rules import (TRUSTED_ASSOCIATIONS, WRITE_PERMISSIONS, branch_name, is_task_issue, parse_charter_number,
                    parse_dependencies)

MAX_BODY_CHARS = 20_000


@dataclass
class Decision:
    proceed: bool
    reasons: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)


def run_preflight(gh: GitHub, number: int, sender: str, *, max_runs_per_day: int = 6,
                  workflow_file: str = "claude-develop.yml", now: datetime | None = None) -> Decision:
    reasons: list[str] = []
    try:
        issue = gh.get_issue(number)
    except GitHubError as error:
        return Decision(False, [f"cannot read issue #{number}: {error}"])

    if issue.get("pull_request"):
        reasons.append("this is a pull request, not an issue")
    if issue.get("state") != "open":
        reasons.append("the issue is not open")
    title, body = issue.get("title", ""), issue.get("body") or ""
    if not is_task_issue(title):
        reasons.append("the charter and the epic are not development tasks")
    if len(body) > MAX_BODY_CHARS:
        reasons.append(f"the issue text is longer than {MAX_BODY_CHARS} characters")
    if issue.get("author_association") not in TRUSTED_ASSOCIATIONS:
        reasons.append("the issue was not written by the owner, a member or a collaborator: its text is untrusted and "
                       "must not drive code changes")

    permission = gh.get_permission(sender) if sender else "none"
    if permission not in WRITE_PERMISSIONS:
        reasons.append(f"'{sender}' who added the label has '{permission}' access; write access is required")

    charter_number = parse_charter_number(body)
    charter = None
    if charter_number is None:
        reasons.append("the issue does not reference the project charter ('Rules for every task: see #N')")
    else:
        charter = gh.get_issue(charter_number)

    blocked, dependencies = [], []
    for dep in parse_dependencies(body):
        info = gh.get_issue(dep)
        dependencies.append({"number": dep, "title": info.get("title", ""), "state": info.get("state", "")})
        if info.get("state") != "closed":
            blocked.append(f"#{dep}")
    if blocked:
        reasons.append("waiting for dependencies that are not merged and closed yet: " + ", ".join(blocked))

    prefix = f"claude/issue-{number}-"
    open_prs = gh.open_pulls_with_prefix(prefix)
    if open_prs:
        reasons.append(f"a pull request for this issue is already open (#{open_prs[0]['number']}); close it first to retry")

    since = ((now or datetime.now(timezone.utc)) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = gh.recent_run_count(workflow_file, since)
    if runs > max_runs_per_day:
        reasons.append(f"daily limit reached: {runs - 1} runs in the last 24 hours (limit {max_runs_per_day})")

    context = {"issue": {"number": number, "title": title, "body": body},
               "charter": {"number": charter_number, "body": (charter or {}).get("body", "")},
               "dependencies": dependencies, "branch": branch_name(number, title), "sender": sender}
    return Decision(not reasons, reasons, context)

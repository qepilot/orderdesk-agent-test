"""Commit, push and open the pull request. Runs in a separate step from the agent; the only step holding the GitHub token.

The agent never sees the token and never commits. Here we stage only allow-listed paths, check the staged list once more,
commit under the pipeline's identity, push a claude/issue-* branch (never main), and open the pull request. Failing
gates or an unconvinced evaluator produce a *draft* labelled needs-human, never a ready-for-review pull request.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from .gh import GitHub
from .report import MARKER, pr_body, status_comment
from .rules import new_requirements, path_violations, slugify  # noqa: F401  (slugify re-exported for tests)



def _git(root: str, *args: str, token: str = "") -> subprocess.CompletedProcess:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    if token:
        done.stdout = (done.stdout or "").replace(token, "***")
        done.stderr = (done.stderr or "").replace(token, "***")
    return done


def stage_and_commit(root: str, number: int, title: str) -> tuple[bool, str]:
    # only pass paths that exist: git add refuses the whole command if a pathspec matches nothing
    paths = [p for p in ("restaurant",) if Path(root, p).exists()]
    paths += sorted(str(w.relative_to(root)) for pattern in ("restaurant-*.yml", "restaurant-*.yaml")
                    for w in Path(root, ".github", "workflows").glob(pattern))
    if paths:
        _git(root, "add", "-A", "--", *paths)
    staged = _git(root, "diff", "--cached", "--name-only").stdout.split()
    if not staged:
        return False, "nothing to commit"
    bad = path_violations(staged)
    if bad:
        _git(root, "reset", "-q")
        return False, "refusing to commit files outside the allowed area: " + ", ".join(bad)
    message = (f"Implement #{number}: {title}\n\nCloses #{number}\n\n"
               "Co-Authored-By: Claude <noreply@anthropic.com>")
    done = _git(root, "-c", "user.name=claude-pipeline[bot]", "-c", "user.email=claude-pipeline@users.noreply.github.com",
                "commit", "-q", "-m", message)
    return done.returncode == 0, done.stderr.strip()


def push_branch(root: str, repo: str, branch: str, token: str) -> tuple[bool, str]:
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    done = _git(root, "-c", f"http.https://github.com/.extraheader=Authorization: basic {basic}", "push",
                f"https://github.com/{repo}.git", f"HEAD:refs/heads/{branch}", token=token)
    if done.returncode != 0:
        done.stderr = done.stderr.replace(basic, "***")
    return done.returncode == 0, (done.stderr or done.stdout).strip()[-500:]


def publish(gh: GitHub, context: dict, root: str, gates: dict, report: dict, developer: list[dict], *, token: str,
            base: str, run_url: str, ready_candidate: bool) -> dict:
    issue = context["issue"]
    number, title, branch = issue["number"], issue["title"], context["branch"]
    gh.ensure_label("needs-human", "d93f0b", "The automation needs a person to look at this")
    ok, detail = stage_and_commit(root, number, title.split("] ", 1)[-1])
    if not ok:
        gh.upsert_comment(number, status_comment("stopped before opening a pull request", run_url, detail), MARKER)
        gh.add_labels(number, ["needs-human"])
        gh.remove_label(number, "claude-in-progress")
        return {"pr": None, "reason": detail}

    pushed, push_detail = push_branch(root, gh.repo, branch, token)
    if not pushed:
        gh.upsert_comment(number, status_comment("could not push the branch", run_url, push_detail), MARKER)
        gh.add_labels(number, ["needs-human"])
        gh.remove_label(number, "claude-in-progress")
        return {"pr": None, "reason": push_detail}

    ready = ready_candidate and gates.get("ok") and report.get("ready")
    reqs_now = Path(root, "restaurant", "requirements.txt")
    before = _git(root, "show", f"{base}:restaurant/requirements.txt").stdout
    new_deps = new_requirements(before, reqs_now.read_text(encoding="utf-8") if reqs_now.is_file() else "")
    body = pr_body(context, gates, report, developer, new_deps, bool(ready), run_url)
    pr = gh.create_pull(f"{title.split('] ', 1)[-1]} (#{number})", branch, base, body, draft=not ready)
    gh.remove_label(number, "claude-in-progress")
    if not ready:
        gh.add_labels(number, ["needs-human"])
    gh.upsert_comment(number, status_comment("pull request opened" if ready else "draft pull request opened, needs a person",
                                             run_url, f"{pr.get('html_url', '')}"), MARKER)
    return {"pr": pr.get("html_url"), "ready": bool(ready)}

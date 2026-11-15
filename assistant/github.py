"""GitHub access. Two back ends with the same four read methods and one write method.

LocalGitHub   reads the JSON files in workshop/github/. No network, no token, same data for everyone.
LiveGitHub    calls the GitHub REST API for a real repository (optional; see docs/live-github.md).

Posting a comment is the only write. LocalGitHub writes it to out/outbox/ instead of the internet,
so the human-in-the-loop labs can be run as often as you like.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


class GitHubError(RuntimeError):
    pass


class LocalGitHub:
    def __init__(self, folder: Path, outbox: Path):
        self.folder = folder
        self.outbox = outbox

    def get_issue(self, number: int) -> dict:
        return self._load("issues", number)

    def list_issues(self) -> list[dict]:
        issues = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((self.folder / "issues").glob("*.json"))]
        return [{key: issue[key] for key in ("number", "title", "labels", "state")} for issue in issues]

    def get_pull(self, number: int) -> dict:
        pull = self._load("pulls", number)
        diff = self.folder / "pulls" / f"{number}.diff"
        pull["diff"] = diff.read_text(encoding="utf-8") if diff.exists() else ""
        return pull

    def list_commits(self, path: str | None = None, limit: int = 10) -> list[dict]:
        commits = json.loads((self.folder / "commits.json").read_text(encoding="utf-8"))
        if path:
            commits = [commit for commit in commits if any(path in changed for changed in commit["files"])]
        return commits[:limit]

    def post_comment(self, number: int, body: str) -> dict:
        self.outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.outbox / f"comment_{number}_{stamp}.md"
        target.write_text(body, encoding="utf-8")
        return {"number": number, "saved_to": str(target), "note": "local outbox: nothing was sent to GitHub"}

    def _load(self, kind: str, number: int) -> dict:
        path = self.folder / kind / f"{int(number)}.json"
        if not path.exists():
            raise GitHubError(f"{kind[:-1]} #{number} does not exist")
        return json.loads(path.read_text(encoding="utf-8"))


class LiveGitHub:
    """The same interface over https://api.github.com for one repository ("owner/name")."""

    def __init__(self, repository: str, token: str | None = None, *, api_url: str = "https://api.github.com",
                 allow_comments: bool = False, timeout: float = 20.0, transport: httpx.BaseTransport | None = None):
        self.repository = repository
        self.allow_comments = allow_comments
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "engineering-assistant-course"}
        token = token or os.getenv("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=f"{api_url}/repos/{repository}", headers=headers, timeout=timeout,
                                    transport=transport)

    def get_issue(self, number: int) -> dict:
        issue = self._get(f"/issues/{number}")
        comments = self._get(f"/issues/{number}/comments") if issue.get("comments") else []
        return {"number": issue["number"], "title": issue["title"], "state": issue["state"],
                "author": issue["user"]["login"], "created_at": issue["created_at"],
                "labels": [label["name"] for label in issue.get("labels", [])], "body": issue.get("body") or "",
                "comments": [{"author": c["user"]["login"], "created_at": c["created_at"], "body": c.get("body") or ""}
                             for c in comments]}

    def list_issues(self) -> list[dict]:
        return [{"number": i["number"], "title": i["title"], "state": i["state"],
                 "labels": [label["name"] for label in i.get("labels", [])]}
                for i in self._get("/issues", params={"state": "open", "per_page": 50}) if "pull_request" not in i]

    def get_pull(self, number: int) -> dict:
        pull = self._get(f"/pulls/{number}")
        files = self._get(f"/pulls/{number}/files", params={"per_page": 100})
        diff = self._client.get(f"/pulls/{number}", headers={"Accept": "application/vnd.github.diff"})
        return {"number": pull["number"], "title": pull["title"], "state": pull["state"],
                "author": pull["user"]["login"], "created_at": pull["created_at"], "base": pull["base"]["ref"],
                "head": pull["head"]["ref"], "body": pull.get("body") or "", "linked_issues": [],
                "files": [{"path": f["filename"], "additions": f["additions"], "deletions": f["deletions"]}
                          for f in files],
                "checks": "", "diff": diff.text if diff.status_code == 200 else ""}

    def list_commits(self, path: str | None = None, limit: int = 10) -> list[dict]:
        params = {"per_page": limit, **({"path": path} if path else {})}
        return [{"sha": c["sha"][:7], "date": c["commit"]["author"]["date"], "author": c["commit"]["author"]["name"],
                 "message": c["commit"]["message"].splitlines()[0], "files": []}
                for c in self._get("/commits", params=params)]

    def post_comment(self, number: int, body: str) -> dict:
        if not self.allow_comments:
            raise GitHubError("this client is read-only; create it with allow_comments=True to post")
        response = self._client.post(f"/issues/{number}/comments", json={"body": body})
        if response.status_code >= 400:
            raise GitHubError(f"GitHub refused the comment: HTTP {response.status_code}")
        return {"number": number, "url": response.json().get("html_url", "")}

    def _get(self, path: str, params: dict | None = None):
        response = self._client.get(path, params=params)
        if response.status_code == 404:
            raise GitHubError(f"{path} was not found in {self.repository}")
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API error: HTTP {response.status_code} for {path}")
        return response.json()

"""A very small GitHub REST client: only the calls the pipeline needs. Pass transport= in tests."""

from __future__ import annotations

import httpx

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repo: str, token: str = "", *, transport: httpx.BaseTransport | None = None, api: str = API):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "claude-ready-pipeline"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.repo = repo
        self._client = httpx.Client(base_url=f"{api}/repos/{repo}", headers=headers, timeout=30.0, transport=transport)

    def _request(self, method: str, path: str, *, ok: tuple[int, ...] = (), **kwargs):
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400 and response.status_code not in ok:
            raise GitHubError(f"{method} {path}: HTTP {response.status_code} {response.text[:200]}")
        return response.json() if response.content and response.status_code < 400 else {}

    # issues
    def get_issue(self, number: int) -> dict:
        return self._request("GET", f"/issues/{number}")

    def get_permission(self, login: str) -> str:
        return self._request("GET", f"/collaborators/{login}/permission").get("permission", "none")

    def ensure_label(self, name: str, color: str, description: str) -> None:
        self._request("POST", "/labels", ok=(422,), json={"name": name, "color": color, "description": description})

    def add_labels(self, number: int, labels: list[str]) -> None:
        self._request("POST", f"/issues/{number}/labels", json={"labels": labels})

    def remove_label(self, number: int, name: str) -> None:
        self._request("DELETE", f"/issues/{number}/labels/{name}", ok=(404,))

    def upsert_comment(self, number: int, body: str, marker: str) -> str:
        """One status comment per issue, edited in place as the run advances. Only bot comments are edited."""
        full = body if marker in body else f"{marker}\n{body}"
        existing = None
        for page in range(1, 6):
            batch = self._request("GET", f"/issues/{number}/comments", params={"per_page": 100, "page": page})
            existing = next((c for c in reversed(batch) if marker in (c.get("body") or "")
                             and (c.get("user") or {}).get("type") == "Bot"), existing)
            if len(batch) < 100:
                break
        if existing:
            return self._request("PATCH", f"/issues/comments/{existing['id']}", json={"body": full}).get("html_url", "")
        return self._request("POST", f"/issues/{number}/comments", json={"body": full}).get("html_url", "")

    # pull requests
    def open_pulls_with_prefix(self, prefix: str) -> list[dict]:
        pulls = self._request("GET", "/pulls", params={"state": "open", "per_page": 100})
        return [p for p in pulls if (p.get("head") or {}).get("ref", "").startswith(prefix)]

    def create_pull(self, title: str, head: str, base: str, body: str, draft: bool) -> dict:
        return self._request("POST", "/pulls", json={"title": title, "head": head, "base": base, "body": body,
                                                      "draft": draft})

    # actions
    def recent_run_count(self, workflow_file: str, since_iso: str) -> int:
        data = self._request("GET", f"/actions/workflows/{workflow_file}/runs",
                             params={"created": f">={since_iso}", "per_page": 1})
        return int(data.get("total_count", 0))

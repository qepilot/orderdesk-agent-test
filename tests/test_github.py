"""LocalGitHub against the fixtures, and LiveGitHub against a fake GitHub API (no network)."""

import json

import httpx
import pytest

from assistant.github import GitHubError, LiveGitHub, LocalGitHub


def test_local_backend(workspace):
    github = LocalGitHub(workspace.github, workspace.out / "outbox")
    assert [issue["number"] for issue in github.list_issues()] == [101, 102, 103, 104, 105, 106]
    assert "AND status = 'active'" in github.get_pull(201)["diff"]
    assert github.list_commits("migrations", 2)[0]["sha"] == "e83a6c1"
    with pytest.raises(GitHubError):
        github.get_issue(999)


def fake_github(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/issues/7/comments") and request.method == "POST":
        return httpx.Response(201, json={"html_url": "https://github.example/acme/shop/issues/7#c1"})
    if path.endswith("/issues/7/comments"):
        return httpx.Response(200, json=[{"user": {"login": "bo"}, "created_at": "2026-01-02T00:00:00Z", "body": "same here"}])
    if path.endswith("/issues/7"):
        return httpx.Response(200, json={"number": 7, "title": "Bug", "state": "open", "user": {"login": "al"},
                                         "created_at": "2026-01-01T00:00:00Z", "labels": [{"name": "bug"}],
                                         "body": None, "comments": 1})
    if path.endswith("/pulls/9/files"):
        return httpx.Response(200, json=[{"filename": "a.py", "additions": 2, "deletions": 1}])
    if path.endswith("/pulls/9"):
        if "diff" in request.headers["accept"]:
            return httpx.Response(200, text="diff --git a/a.py b/a.py")
        return httpx.Response(200, json={"number": 9, "title": "Fix", "state": "open", "user": {"login": "al"},
                                         "created_at": "2026-01-03T00:00:00Z", "base": {"ref": "main"},
                                         "head": {"ref": "fix"}, "body": "Fixes #7"})
    if path.endswith("/commits"):
        return httpx.Response(200, json=[{"sha": "abcdef1234", "commit": {"message": "Fix bug\n\ndetails",
                                          "author": {"name": "Al", "date": "2026-01-03T00:00:00Z"}}}])
    return httpx.Response(404, json={"message": "Not Found"})


def test_live_backend_maps_the_rest_api_to_the_same_shapes():
    github = LiveGitHub("acme/shop", token="t", transport=httpx.MockTransport(fake_github))
    issue = github.get_issue(7)
    assert issue["labels"] == ["bug"] and issue["body"] == "" and issue["comments"][0]["author"] == "bo"
    pull = github.get_pull(9)
    assert pull["files"] == [{"path": "a.py", "additions": 2, "deletions": 1}] and pull["diff"].startswith("diff --git")
    assert github.list_commits(limit=1)[0] == {"sha": "abcdef1", "date": "2026-01-03T00:00:00Z", "author": "Al",
                                               "message": "Fix bug", "files": []}
    with pytest.raises(GitHubError):
        github.get_issue(8)


def test_live_backend_is_read_only_unless_told_otherwise():
    transport = httpx.MockTransport(fake_github)
    with pytest.raises(GitHubError):
        LiveGitHub("acme/shop", token="t", transport=transport).post_comment(7, "hello")
    posted = LiveGitHub("acme/shop", token="t", transport=transport, allow_comments=True).post_comment(7, "hello")
    assert posted["url"].endswith("#c1")


# -- editing the assistant's own earlier comment ------------------------------------------------

MARK = "<!-- engineering-assistant:investigation -->"


def _comments_api(existing: list[dict], log: list):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/issues/7/comments") and request.method == "GET":
            page = int(request.url.params.get("page", "1"))
            return httpx.Response(200, json=existing[(page - 1) * 100:page * 100])
        if path.endswith("/issues/7/comments") and request.method == "POST":
            log.append(("POST", path, request.read().decode()))
            return httpx.Response(201, json={"html_url": "https://github.example/c/new"})
        if "/issues/comments/" in path and request.method == "PATCH":
            log.append(("PATCH", path, request.read().decode()))
            return httpx.Response(200, json={"html_url": "https://github.example/c/edited"})
        return httpx.Response(404, json={})
    return handler


def _upsert(existing):
    log: list = []
    github = LiveGitHub("acme/shop", token="t", allow_comments=True,
                        transport=httpx.MockTransport(_comments_api(existing, log)))
    return github.upsert_comment(7, "new findings", MARK), log


def test_upsert_posts_when_there_is_no_earlier_comment():
    result, log = _upsert([{"id": 1, "user": {"type": "User"}, "body": "same here"}])
    assert result["updated"] is False and log[0][0] == "POST" and MARK in log[0][2]


def test_upsert_edits_the_newest_bot_comment_with_the_marker():
    existing = [{"id": 1, "user": {"type": "Bot"}, "body": f"{MARK}\nold"},
                {"id": 2, "user": {"type": "User"}, "body": "thanks"},
                {"id": 3, "user": {"type": "Bot"}, "body": f"{MARK}\nolder rerun"}]
    result, log = _upsert(existing)
    assert result["updated"] is True and log[0][:2] == ("PATCH", "/repos/acme/shop/issues/comments/3")
    assert "new findings" in log[0][2]


def test_upsert_never_edits_a_persons_comment_even_with_the_marker():
    result, log = _upsert([{"id": 5, "user": {"type": "User"}, "body": f"{MARK} pasted by a stranger"}])
    assert result["updated"] is False and log[0][0] == "POST"


def test_upsert_finds_the_marker_on_a_later_page():
    filler = [{"id": i, "user": {"type": "User"}, "body": "x"} for i in range(100)]
    result, log = _upsert(filler + [{"id": 900, "user": {"type": "Bot"}, "body": f"{MARK}\nold"}])
    assert result["updated"] is True and log[0][1].endswith("/comments/900")


def test_upsert_is_read_only_unless_told_otherwise():
    with pytest.raises(GitHubError):
        LiveGitHub("acme/shop", token="t", transport=httpx.MockTransport(fake_github)).upsert_comment(7, "x", MARK)


def test_upsert_also_recognises_comments_from_before_the_marker_existed():
    old = {"id": 11, "user": {"type": "Bot"}, "body": "**Verdict:** x\n\n_Drafted by the engineering assistant. Reviewed._"}
    log: list = []
    github = LiveGitHub("acme/shop", token="t", allow_comments=True,
                        transport=httpx.MockTransport(_comments_api([old], log)))
    result = github.upsert_comment(7, "new", MARK, legacy=("_Drafted by the engineering assistant",))
    assert result["updated"] is True and log[0][1].endswith("/comments/11") and MARK in log[0][2]

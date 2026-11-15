"""The command line against a real repository: the checks around --repo and --post-comment, with fakes for GitHub and the model."""

import types

import pytest

from assistant import __main__ as cli


def _result(findings=None, stop_reason="submitted"):
    return types.SimpleNamespace(findings=findings, stop_reason=stop_reason, error="", status="completed", steps=1)


FINDINGS = {"kind": "issue_investigation", "verdict": "defect_confirmed", "summary": "Mail bob@example.com about it.",
            "root_cause": "x", "confidence": "high", "evidence": [], "recommendations": ["fix"]}


def test_comment_body_redacts_personal_data():
    body = cli.comment_body(_result(FINDINGS))
    assert "defect_confirmed" in body and "bob@example.com" not in body


def test_comment_body_when_the_run_did_not_finish():
    body = cli.comment_body(_result(None, "max_steps"))
    assert "could not finish" in body and "max_steps" in body


def test_post_comment_needs_repo():
    with pytest.raises(SystemExit):
        cli.main(["investigate", "1", "--post-comment"])


def test_repo_needs_a_live_model(monkeypatch, capsys):
    monkeypatch.setattr(cli, "using_live_model", lambda: False)
    assert cli.main(["investigate", "1", "--repo", "o/n"]) == 2
    assert "live model" in capsys.readouterr().err


def test_repo_run_posts_the_findings(monkeypatch):
    posted = []

    class FakeGitHub:
        def __init__(self, repository, **kwargs):
            self.repository, self.allow_comments = repository, kwargs.get("allow_comments")

        def upsert_comment(self, number, body, marker, legacy=()):
            posted.append((self.repository, number, body, self.allow_comments, marker))
            return {"number": number, "url": "https://example.test/c/1", "updated": False}

    seen = {}

    def fake_run_one(kind, number, role, quiet=False, github=None):
        seen["github"] = github
        return _result(FINDINGS), types.SimpleNamespace(events=[], path="trace.jsonl")

    monkeypatch.setattr(cli, "using_live_model", lambda: True)
    monkeypatch.setattr(cli, "LiveGitHub", FakeGitHub)
    monkeypatch.setattr(cli, "run_one", fake_run_one)
    assert cli.main(["investigate", "7", "--repo", "o/n", "--post-comment"]) == 0
    assert seen["github"].repository == "o/n"
    repository, number, body, allow, marker = posted[0]
    assert (repository, number, allow) == ("o/n", 7, True) and "bob@example.com" not in body
    assert marker == cli.COMMENT_MARKER


def test_repo_run_without_post_comment_posts_nothing(monkeypatch):
    class FakeGitHub:
        def __init__(self, repository, **kwargs):
            assert kwargs.get("allow_comments") is False

        def upsert_comment(self, *args):
            raise AssertionError("must not post")

    monkeypatch.setattr(cli, "using_live_model", lambda: True)
    monkeypatch.setattr(cli, "LiveGitHub", FakeGitHub)
    monkeypatch.setattr(cli, "run_one", lambda *a, **k: (_result(FINDINGS), types.SimpleNamespace(events=[], path="t")))
    assert cli.main(["investigate", "7", "--repo", "o/n"]) == 0

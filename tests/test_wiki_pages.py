"""The wiki pages in docs/wiki: links between them must resolve, the sidebar must list them, and the publish tool must
convert links the way the wiki wants them."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import publish_wiki  # noqa: E402

PAGES = ROOT / "docs" / "wiki"
LINK = re.compile(r"\]\(([^)\s]+)\)")


def page_names():
    return sorted(p.name for p in PAGES.glob("*.md"))


def test_there_are_pages_and_the_required_ones_exist():
    names = page_names()
    for required in ("Home.md", "_Sidebar.md", "Reference.md"):
        assert required in names
    assert sum(n.startswith("Tutorial-") for n in names) >= 8


@pytest.mark.parametrize("name", page_names())
def test_links_to_other_pages_resolve(name):
    text = (PAGES / name).read_text(encoding="utf-8")
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        page = target.split("#")[0]
        assert (PAGES / page).is_file(), f"{name} links to {target}, which does not exist in docs/wiki"


def test_every_page_is_reachable_from_the_sidebar_and_home():
    sidebar = (PAGES / "_Sidebar.md").read_text(encoding="utf-8")
    home = (PAGES / "Home.md").read_text(encoding="utf-8")
    for name in page_names():
        if name in {"_Sidebar.md", "Home.md"}:
            continue
        assert f"]({name})" in sidebar, f"{name} is missing from the sidebar"
        assert f"]({name})" in home, f"{name} is missing from Home"


def test_no_page_contains_a_secret_like_value():
    for name in page_names():
        text = (PAGES / name).read_text(encoding="utf-8")
        assert not re.search(r"sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}", text), name


def test_publish_tool_rewrites_page_links_only():
    text = "[a](Home.md) [b](Tutorial-1-Quick-Start.md#run) [c](https://example.com/x.md) [d](docs/setup.md) [e](#top)"
    assert publish_wiki.rewrite_links(text) == (
        "[a](Home) [b](Tutorial-1-Quick-Start#run) [c](https://example.com/x.md) [d](docs/setup.md) [e](#top)")


def test_publish_tool_converts_every_page_into_wiki_style_links(tmp_path):
    names = publish_wiki.convert(PAGES, tmp_path)
    assert names == page_names()
    for name in names:
        converted = (tmp_path / name).read_text(encoding="utf-8")
        assert not re.search(r"\]\([A-Za-z0-9_-]+\.md", converted), f"{name} still has .md page links"


def test_publish_tool_dry_run_writes_files_and_refuses_a_non_empty_directory(tmp_path):
    out = tmp_path / "out"
    assert publish_wiki.main(["--out", str(out)]) == 0 and (out / "Home.md").is_file()
    with pytest.raises(SystemExit):
        publish_wiki.main(["--out", str(out)])


def test_readme_relative_links_resolve():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = []
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (ROOT / target.split("#")[0]).exists():
            missing.append(target)
    assert not missing, f"README links to files that do not exist: {missing}"


def test_readme_documents_the_claude_integration():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("How Claude in the cloud is integrated", "CLAUDE_CODE_OAUTH_TOKEN", "claude-ready", "LLM_PROVIDER=claude-code",
                   "tools/publish_wiki.py", "ubuntu-24.04"):
        assert needle in text, needle

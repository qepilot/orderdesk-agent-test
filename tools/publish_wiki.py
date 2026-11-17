"""Publish docs/wiki/*.md to the GitHub wiki of this repository.

    python tools/publish_wiki.py                      clone the wiki, copy the pages, commit and push
    python tools/publish_wiki.py --out DIR            only write the converted pages into DIR (nothing is pushed)
    python tools/publish_wiki.py --repo OWNER/NAME    another repository

GitHub creates the wiki's git repository when the first page is saved in the web interface, so create one page there first
(any title; this tool overwrites pages with the same name and leaves other pages alone). Pushing uses your own git
credentials: run `gh auth setup-git` if you use the GitHub CLI.

The pages in docs/wiki link to each other with ordinary relative links (`[text](Page-Name.md)`) so that they also work when
read in the repository. The wiki wants `[text](Page-Name)`, so the `.md` is removed on the way out.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "docs" / "wiki"
DEFAULT_REPO = "qepilot/orderdesk-agent-test"
_PAGE_LINK = re.compile(r"\]\(([A-Za-z0-9_-]+)\.md(#[^)\s]*)?\)")


def rewrite_links(text: str) -> str:
    """[text](Page-Name.md#section) -> [text](Page-Name#section) for links to other pages of the wiki; other links stay."""
    return _PAGE_LINK.sub(lambda m: f"]({m.group(1)}{m.group(2) or ''})", text)


def convert(source: Path, target: Path) -> list[str]:
    """Write every page of `source` into `target` with wiki-style links. Returns the file names written."""
    target.mkdir(parents=True, exist_ok=True)
    names = []
    for page in sorted(source.glob("*.md")):
        (target / page.name).write_text(rewrite_links(page.read_text(encoding="utf-8")), encoding="utf-8")
        names.append(page.name)
    return names


def publish(repo: str) -> int:
    url = f"https://github.com/{repo}.wiki.git"
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "wiki"
        done = subprocess.run(["git", "clone", url, str(clone)], capture_output=True, text=True)
        if done.returncode:
            print(f"Could not clone {url}.\n{done.stderr.strip()}\n\n"
                  "If the wiki has no pages yet, create one in the web interface first "
                  f"(https://github.com/{repo}/wiki/_new), then run this again.", file=sys.stderr)
            return 1
        names = convert(SOURCE, clone)
        subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
        if not subprocess.run(["git", "-C", str(clone), "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
            print("The wiki is already up to date.")
            return 0
        subprocess.run(["git", "-C", str(clone), "commit", "-m", "Update wiki from docs/wiki"], check=True)
        pushed = subprocess.run(["git", "-C", str(clone), "push"], capture_output=True, text=True)
        if pushed.returncode:
            print(f"Push failed:\n{pushed.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"Published {len(names)} pages to https://github.com/{repo}/wiki")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="OWNER/NAME (default: %(default)s)")
    parser.add_argument("--out", type=Path, help="write the converted pages here instead of pushing")
    args = parser.parse_args(argv)
    if args.out:
        if args.out.exists() and any(args.out.iterdir()):
            parser.error(f"{args.out} is not empty")
        names = convert(SOURCE, args.out)
        print(f"Wrote {len(names)} pages to {args.out}")
        return 0
    return publish(args.repo)


if __name__ == "__main__":
    sys.exit(main())

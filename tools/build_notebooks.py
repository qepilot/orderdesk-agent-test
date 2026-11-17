"""Builds each study notebook from its Markdown twin, so the two never drift apart.

The .md file is the source. Rules:

- A ```python fence at the top level becomes a code cell.
- Every other fence (```bash, ```json, ```text, ```ruby ...) stays as text,
  and so does anything inside <details> ... </details> (notes to expand).
- Markdown is split into a new cell at every top-level heading and at a line
  that is exactly <!-- cell -->.

Usage (from the repository root):
    python tools/build_notebooks.py            # rebuild every study/*.ipynb
    python tools/build_notebooks.py --check    # fail if a notebook is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STUDY_DIR = Path(__file__).resolve().parent.parent / "study"
CELL_BREAK = "<!-- cell -->"
FENCE = re.compile(r"^(`{3,})(\S*)\s*$")
HEADING = re.compile(r"^#{1,6} ")


def split_cells(markdown: str) -> list[dict]:
    cells: list[dict] = []
    buffer: list[str] = []
    depth = 0           # <details> nesting
    fence: str | None = None   # the open fence's backticks, if inside a fence
    code: list[str] | None = None

    def flush_markdown():
        text = "\n".join(buffer).strip("\n")
        if text.strip():
            cells.append({"cell_type": "markdown", "source": text})
        buffer.clear()

    for line in markdown.splitlines():
        if code is not None:                       # inside a code cell
            if line.strip() == fence:
                cells.append({"cell_type": "code", "source": "\n".join(code).strip("\n")})
                code, fence = None, None
            else:
                code.append(line)
            continue

        match = FENCE.match(line)
        if fence is None and match and depth == 0 and match.group(2) == "python":
            flush_markdown()
            fence, code = match.group(1), []
            continue

        if fence is None and match:                # a text fence opens
            fence = match.group(1)
        elif fence is not None and line.strip() == fence:
            fence = None                           # a text fence closes
        elif fence is None:
            if depth == 0 and (line.strip() == CELL_BREAK or HEADING.match(line)):
                flush_markdown()
                if line.strip() == CELL_BREAK:
                    continue
            depth += line.count("<details") - line.count("</details>")
            depth = max(depth, 0)
        buffer.append(line)

    if code is not None:
        raise ValueError("a ```python fence is never closed")
    flush_markdown()
    return cells


def to_notebook(cells: list[dict]) -> dict:
    nb_cells = []
    for index, cell in enumerate(cells):
        lines = cell["source"].splitlines(keepends=True)
        base = {"cell_type": cell["cell_type"], "id": f"cell-{index:03d}", "metadata": {}, "source": lines}
        if cell["cell_type"] == "code":
            base.update({"execution_count": None, "outputs": []})
        nb_cells.append(base)
    return {
        "cells": nb_cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def render(markdown_path: Path) -> str:
    notebook = to_notebook(split_cells(markdown_path.read_text(encoding="utf-8")))
    return json.dumps(notebook, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if a notebook differs from its .md")
    args = parser.parse_args()

    stale = []
    for md in sorted(STUDY_DIR.glob("module_*.md")):
        target = md.with_suffix(".ipynb")
        content = render(md)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == content:
            print(f"up to date  {target.name}")
        elif args.check:
            stale.append(target.name)
            print(f"STALE       {target.name}")
        else:
            target.write_text(content, encoding="utf-8")
            print(f"built       {target.name}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())

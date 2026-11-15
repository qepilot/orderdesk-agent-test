"""Executes every study notebook top to bottom in a fresh kernel and reports the first failing cell.

For maintainers, after editing a module:

    python tools/build_notebooks.py && python tools/run_notebooks.py

Runs offline with the stand-in model unless .env configures a real one. Needs nbclient
(installed together with jupyterlab). Outputs are not saved: notebooks are committed clean.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

STUDY_DIR = Path(__file__).resolve().parent.parent / "study"


def main() -> int:
    wanted = sys.argv[1:]
    failed = 0
    for path in sorted(STUDY_DIR.glob("module_*.ipynb")):
        if wanted and not any(word in path.name for word in wanted):
            continue
        notebook = nbformat.read(path, as_version=4)
        started = time.monotonic()
        try:
            NotebookClient(notebook, timeout=300, kernel_name="python3",
                           resources={"metadata": {"path": str(STUDY_DIR)}}).execute()
            cells = sum(cell.cell_type == "code" for cell in notebook.cells)
            print(f"ok      {path.name}  ({cells} code cells, {time.monotonic() - started:.1f} s)")
        except CellExecutionError as error:
            failed += 1
            print(f"FAILED  {path.name}\n{str(error)[-1500:]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

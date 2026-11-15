"""Where the practice environment lives on disk, and the one object that tools receive to reach it."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

COURSE_DIR = Path(__file__).resolve().parent.parent
WORKSHOP_DIR = COURSE_DIR / "workshop"
OUT_DIR = COURSE_DIR / "out"


@dataclass(frozen=True)
class Workspace:
    """Paths to everything the assistant may look at. Tools never build paths on their own."""

    root: Path = WORKSHOP_DIR
    out: Path = OUT_DIR
    repo: Path = field(init=False)
    db: Path = field(init=False)
    github: Path = field(init=False)
    ops: Path = field(init=False)
    knowledge: Path = field(init=False)
    expected: Path = field(init=False)

    def __post_init__(self):
        for name, value in {"repo": "repo", "db": "orderdesk.db", "github": "github", "ops": "ops",
                            "knowledge": "knowledge", "expected": "expected"}.items():
            object.__setattr__(self, name, self.root / value)

    def ensure_database(self) -> Path:
        """Builds the SQLite database from the migrations and the seed script when it is missing."""
        if not self.db.exists():
            subprocess.run([sys.executable, str(self.root / "seed.py")], check=True, capture_output=True)
        return self.db


def default_workspace() -> Workspace:
    workspace = Workspace()
    workspace.ensure_database()
    return workspace

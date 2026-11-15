"""Database access. Production runs PostgreSQL; the workshop copy is SQLite built from the same migrations."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "orderdesk.db"


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or os.getenv("ORDERDESK_DB", DEFAULT_DB)))
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Applies every migration file in name order. Returns the names applied."""
    applied = []
    for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(file.read_text(encoding="utf-8"))
        applied.append(file.name)
    conn.commit()
    return applied

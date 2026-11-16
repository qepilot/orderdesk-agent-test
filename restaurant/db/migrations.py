"""Versioned, checksummed SQL migrations: restaurant/migrations/NNNN_name.sql."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from restaurant.db.connection import transaction

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_NAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(Exception):
    """Base class for migration problems."""


class ChecksumMismatchError(MigrationError):
    """An already-applied migration file was edited."""


class MigrationFailedError(MigrationError):
    """A migration failed and was rolled back; `filename` names the file."""

    def __init__(self, filename: str, cause: Exception):
        super().__init__(f"migration {filename} failed and was rolled back: {cause}")
        self.filename = filename


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    filename: str
    sql: str
    checksum: str


def discover(directory: Path | str = DEFAULT_MIGRATIONS_DIR) -> list[Migration]:
    """Read migration files in version order. Bad names or duplicate versions are errors."""
    found: list[Migration] = []
    for path in sorted(Path(directory).glob("*.sql")):
        match = _NAME_RE.match(path.name)
        if not match:
            raise MigrationError(f"invalid migration file name: {path.name} (want NNNN_name.sql)")
        data = path.read_bytes()
        found.append(
            Migration(
                version=int(match.group(1)),
                name=path.stem,
                filename=path.name,
                sql=data.decode("utf-8"),
                checksum=hashlib.sha256(data).hexdigest(),
            )
        )
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise MigrationError("duplicate migration version numbers")
    return sorted(found, key=lambda m: m.version)


def _applied(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    conn.execute(CREATE_TABLE_SQL)
    rows = conn.execute("SELECT version, name, checksum, applied_at FROM schema_migrations")
    return {row["version"]: row for row in rows}


def _statements(sql: str) -> list[str]:
    """Split a script into complete statements (respects strings, triggers, comments)."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())  # trailing text without ';' -> let SQLite judge it
    return statements


def _verify_checksums(migrations: list[Migration], applied: dict[int, sqlite3.Row]) -> None:
    for migration in migrations:
        row = applied.get(migration.version)
        if row is not None and row["checksum"] != migration.checksum:
            raise ChecksumMismatchError(
                f"checksum mismatch for applied migration {migration.filename}: "
                "the file was edited after it was applied; add a new migration instead"
            )


def migrate(
    conn: sqlite3.Connection, directory: Path | str = DEFAULT_MIGRATIONS_DIR
) -> list[str]:
    """Apply pending migrations in order, each in its own transaction.

    Returns the file names applied (empty when already up to date).
    """
    migrations = discover(directory)
    applied = _applied(conn)
    _verify_checksums(migrations, applied)
    done: list[str] = []
    for migration in migrations:
        if migration.version in applied:
            continue
        try:
            with transaction(conn):
                for statement in _statements(migration.sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, checksum, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        datetime.now(UTC).isoformat(timespec="seconds"),
                    ),
                )
        except Exception as exc:
            raise MigrationFailedError(migration.filename, exc) from exc
        done.append(migration.filename)
    return done


def status(conn: sqlite3.Connection, directory: Path | str = DEFAULT_MIGRATIONS_DIR) -> dict:
    """Report applied and pending migrations and any checksum mismatches."""
    migrations = discover(directory)
    applied = _applied(conn)
    return {
        "current_version": max(applied, default=0),
        "applied": [m.filename for m in migrations if m.version in applied],
        "pending": [m.filename for m in migrations if m.version not in applied],
        "mismatched": [
            m.filename
            for m in migrations
            if m.version in applied and applied[m.version]["checksum"] != m.checksum
        ],
    }

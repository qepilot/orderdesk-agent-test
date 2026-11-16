import sqlite3

import pytest

from restaurant.db import (
    ChecksumMismatchError,
    MigrationFailedError,
    connect,
    migrate,
    status,
    transaction,
)
from restaurant.db.__main__ import main
from restaurant.db.migrations import MigrationError, discover


@pytest.fixture
def mdir(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "0001_a.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);\n")
    (d / "0002_b.sql").write_text(
        "CREATE TABLE b (id INTEGER PRIMARY KEY, a_id INTEGER NOT NULL REFERENCES a(id));\n"
        "INSERT INTO a (id) VALUES (1); -- a; comment\n"
    )
    return d


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    yield c
    c.close()


def test_fresh_database_migrates_to_latest_and_rerun_changes_nothing(conn, mdir):
    assert migrate(conn, mdir) == ["0001_a.sql", "0002_b.sql"]
    rows = [tuple(r) for r in conn.execute("SELECT version, checksum FROM schema_migrations")]
    assert [r[0] for r in rows] == [1, 2] and all(len(r[1]) == 64 for r in rows)
    assert migrate(conn, mdir) == []
    again = [tuple(r) for r in conn.execute("SELECT version, checksum FROM schema_migrations")]
    assert again == rows
    assert status(conn, mdir)["pending"] == []


def test_failing_migration_rolls_back_completely_and_names_file(conn, mdir):
    (mdir / "0003_bad.sql").write_text(
        "CREATE TABLE c (id INTEGER);\nINSERT INTO nope VALUES (1);\n"
    )
    with pytest.raises(MigrationFailedError) as err:
        migrate(conn, mdir)
    assert err.value.filename == "0003_bad.sql"
    assert "0003_bad.sql" in str(err.value)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "c" not in tables  # rolled back
    assert {"a", "b"} <= tables  # earlier migrations stay applied
    assert status(conn, mdir)["pending"] == ["0003_bad.sql"]


def test_edited_applied_migration_is_refused_with_checksum_mismatch(conn, mdir):
    migrate(conn, mdir)
    (mdir / "0001_a.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY, x TEXT);\n")
    with pytest.raises(ChecksumMismatchError, match="0001_a.sql"):
        migrate(conn, mdir)
    assert status(conn, mdir)["mismatched"] == ["0001_a.sql"]


def test_foreign_keys_enforced_on_every_connection(tmp_path, mdir):
    first = connect(tmp_path / "fk.db")
    migrate(first, mdir)
    second = connect(tmp_path / "fk.db")
    for c in (first, second):
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO b (id, a_id) VALUES (10, 999)")
    assert first.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert first.execute("PRAGMA busy_timeout").fetchone()[0] > 0
    first.close()
    second.close()


def test_transaction_commits_on_success_and_rolls_back_on_error(conn):
    conn.execute("CREATE TABLE t (id INTEGER)")
    with transaction(conn):
        conn.execute("INSERT INTO t VALUES (1)")
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO t VALUES (2)")
        raise RuntimeError("boom")
    assert [r[0] for r in conn.execute("SELECT id FROM t")] == [1]


def test_invalid_file_names_and_duplicates_are_rejected(tmp_path):
    (tmp_path / "bad.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError):
        discover(tmp_path)
    (tmp_path / "bad.sql").unlink()
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0001_b.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="duplicate"):
        discover(tmp_path)


def test_trigger_script_with_inner_semicolons_applies(conn, tmp_path):
    (tmp_path / "0001_t.sql").write_text(
        "CREATE TABLE t (id INTEGER);\n"
        "CREATE TABLE log (n INTEGER);\n"
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN\n"
        "  INSERT INTO log VALUES (1);\n"
        "  INSERT INTO log VALUES (2);\n"
        "END;\n"
    )
    migrate(conn, tmp_path)
    conn.execute("INSERT INTO t VALUES (1)")
    assert conn.execute("SELECT COUNT(*) FROM log").fetchone()[0] == 2


def test_cli_migrate_and_status(tmp_path, capsys, monkeypatch):
    db = str(tmp_path / "cli.db")
    monkeypatch.setattr("restaurant.db.__main__.migrate", lambda c: migrate(c, _dir(tmp_path)))
    monkeypatch.setattr("restaurant.db.__main__.status", lambda c: status(c, _dir(tmp_path)))
    assert main(["status", "--db", db]) == 0
    assert "pending  0001_a.sql" in capsys.readouterr().out
    assert main(["migrate", "--db", db]) == 0
    assert "applied 0001_a.sql" in capsys.readouterr().out
    assert main(["migrate", "--db", db]) == 0
    assert "up to date" in capsys.readouterr().out
    (_dir(tmp_path) / "0001_a.sql").write_text("SELECT 2;")
    assert main(["migrate", "--db", db]) == 1
    assert "checksum mismatch" in capsys.readouterr().err
    assert main(["status", "--db", db]) == 1


def _dir(tmp_path):
    d = tmp_path / "cli_migrations"
    d.mkdir(exist_ok=True)
    f = d / "0001_a.sql"
    if not f.exists():
        f.write_text("CREATE TABLE a (id INTEGER);")
    return d


def test_real_migrations_directory_is_valid():
    discover()

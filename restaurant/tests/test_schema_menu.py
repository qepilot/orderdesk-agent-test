import sqlite3

import pytest

from restaurant.db import connect, migrate


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "menu.db")
    migrate(c)
    c.execute("INSERT INTO categories (id, name, slug) VALUES (1, 'Pizza', 'pizza')")
    yield c
    c.close()


def add_dish(conn, slug="margherita", price=900, category=1):
    conn.execute(
        "INSERT INTO dishes (category_id, name, slug, price_cents) VALUES (?, ?, ?, ?)",
        (category, slug.title(), slug, price),
    )


def test_negative_price_is_rejected_by_database(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_dish(conn, price=-1)


def test_zero_price_is_allowed(conn):
    add_dish(conn, price=0)


def test_duplicate_dish_slug_is_rejected_by_database(conn):
    add_dish(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_dish(conn)


def test_orphan_dish_is_rejected_by_database(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_dish(conn, category=999)


def test_deleting_category_with_dishes_is_refused_restrict(conn):
    add_dish(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM categories WHERE id = 1")
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1


def test_category_without_dishes_can_be_deleted(conn):
    conn.execute("DELETE FROM categories WHERE id = 1")


def test_category_name_and_slug_are_unique(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO categories (name, slug) VALUES ('Pizza', 'other')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO categories (name, slug) VALUES ('Other', 'pizza')")


def test_dish_tags_composite_key_rejects_duplicates_and_orphans(conn):
    add_dish(conn)
    conn.execute("INSERT INTO dietary_tags (id, code, label) VALUES (1, 'vegan', 'Vegan')")
    conn.execute("INSERT INTO dish_tags (dish_id, tag_id) VALUES (1, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dish_tags (dish_id, tag_id) VALUES (1, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dish_tags (dish_id, tag_id) VALUES (1, 99)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dietary_tags (code, label) VALUES ('vegan', 'Again')")


def test_expected_indexes_exist_in_sqlite_master(conn):
    rows = conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index'"
    ).fetchall()
    names = {r["name"]: r["tbl_name"] for r in rows}
    assert names.get("idx_dishes_category_available") == "dishes"
    assert names.get("idx_dishes_slug") == "dishes"
    cols = [
        r["name"] for r in conn.execute("PRAGMA index_info(idx_dishes_category_available)")
    ]
    assert cols == ["category_id", "is_available"]

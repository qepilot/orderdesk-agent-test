import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orderdesk.db import migrate  # noqa: E402


@pytest.fixture
def conn():
    """An empty in-memory database with the full schema and a small catalogue."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute("INSERT INTO customers VALUES (1, 'Test Customer', 'test@example.test', 'standard', '2026-01-01T00:00:00Z')")
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?)",
                     [(1, 'SKU-A', 'Desk lamp', 10000), (2, 'SKU-B', 'Notebook set', 5000), (3, 'SKU-C', 'Pen', 1995)])
    conn.execute("INSERT INTO discount_codes VALUES ('SAVE10', 10, 1), ('SAVE15', 15, 1)")
    return conn


def add_order(conn, order_id, items, status="paid", discount_code=None, created_at="2026-10-01T10:00:00Z"):
    """items: list of (product_id, quantity, unit_price_cents)."""
    conn.execute("INSERT INTO orders (id, customer_id, status, discount_code, created_at) VALUES (?, 1, ?, ?, ?)",
                 (order_id, status, discount_code, created_at))
    for product_id, quantity, price in items:
        conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES (?, ?, ?, ?)",
                     (order_id, product_id, quantity, price))

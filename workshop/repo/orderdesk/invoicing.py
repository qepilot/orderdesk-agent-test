"""Invoices: one per order, issued when the order is paid."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import repo
from .pricing import apply_discount

INVOICE_SUBTOTAL_SQL = """
    SELECT COALESCE(SUM(quantity * unit_price_cents), 0) AS subtotal
    FROM order_items
    WHERE order_id = ?
"""

INVOICE_LINES_SQL = """
    SELECT oi.id, p.sku, p.name, oi.quantity, oi.unit_price_cents
    FROM order_items oi
    JOIN products p ON p.id = oi.product_id
    WHERE oi.order_id = ?
    ORDER BY oi.id
"""


def invoice_total(conn: sqlite3.Connection, order_id: int) -> int:
    subtotal = conn.execute(INVOICE_SUBTOTAL_SQL, (order_id,)).fetchone()["subtotal"]
    return apply_discount(subtotal, repo.discount_percent(conn, order_id))


def invoice_lines(conn: sqlite3.Connection, order_id: int) -> list[dict]:
    return [dict(row) for row in conn.execute(INVOICE_LINES_SQL, (order_id,)).fetchall()]


def issue_invoice(conn: sqlite3.Connection, order_id: int, issued_at: str | None = None) -> dict:
    """Creates the invoice for an order and returns it. Timestamps are UTC."""
    issued_at = issued_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = invoice_total(conn, order_id)
    cursor = conn.execute(
        "INSERT INTO invoices (order_id, total_cents, issued_at) VALUES (?, ?, ?)", (order_id, total, issued_at)
    )
    return {"id": cursor.lastrowid, "order_id": order_id, "total_cents": total, "issued_at": issued_at}


def get_invoice(conn: sqlite3.Connection, order_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, order_id, total_cents, issued_at FROM invoices WHERE order_id = ?", (order_id,)
    ).fetchone()
    if row is None:
        return None
    return {**dict(row), "lines": invoice_lines(conn, order_id)}

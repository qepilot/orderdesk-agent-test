"""Payments. An authorization reserves money; only a capture actually charges the card."""

from __future__ import annotations

import sqlite3


def payment_events(conn: sqlite3.Connection, order_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, kind, amount_cents, status, created_at FROM payments WHERE order_id = ? ORDER BY created_at, id",
        (order_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def amount_charged(conn: sqlite3.Connection, order_id: int) -> int:
    """Money actually taken for an order, in cents: successful captures minus successful refunds."""
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE kind WHEN 'capture' THEN amount_cents WHEN 'refund' THEN -amount_cents ELSE 0 END), 0) "
        "AS charged FROM payments WHERE order_id = ? AND status = 'succeeded'",
        (order_id,),
    ).fetchone()
    return row["charged"]

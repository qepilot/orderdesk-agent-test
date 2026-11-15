"""All SQL for orders lives here, so the services stay free of query text."""

from __future__ import annotations

import sqlite3


def get_order(conn: sqlite3.Connection, order_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, customer_id, status, discount_code, created_at FROM orders WHERE id = ?", (order_id,)
    ).fetchone()


def active_items(conn: sqlite3.Connection, order_id: int) -> list[sqlite3.Row]:
    """Items that count towards the order. Removed items are kept for audit only."""
    return conn.execute(
        "SELECT oi.id, oi.product_id, p.sku, p.name, oi.quantity, oi.unit_price_cents "
        "FROM order_items oi JOIN products p ON p.id = oi.product_id "
        "WHERE oi.order_id = ? AND oi.status = 'active' ORDER BY oi.id",
        (order_id,),
    ).fetchall()


def discount_percent(conn: sqlite3.Connection, order_id: int) -> int:
    row = conn.execute(
        "SELECT d.percent_off FROM orders o JOIN discount_codes d ON d.code = o.discount_code "
        "WHERE o.id = ? AND d.active = 1",
        (order_id,),
    ).fetchone()
    return row["percent_off"] if row else 0


def orders_page(conn: sqlite3.Connection, status: str | None, limit: int, offset: int) -> list[sqlite3.Row]:
    sql = "SELECT id, customer_id, status, created_at FROM orders"
    params: list = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return conn.execute(sql, params).fetchall()


def orders_for_customer(conn: sqlite3.Connection, customer_id: int, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, customer_id, status, created_at FROM orders "
        "WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()

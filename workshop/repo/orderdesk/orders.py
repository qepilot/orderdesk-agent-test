"""Order services: totals and listings."""

from __future__ import annotations

import sqlite3

from . import repo
from .pricing import apply_discount, line_total


def order_total(conn: sqlite3.Connection, order_id: int) -> int:
    """What the customer owes for an order, in cents. Removed items do not count."""
    items = repo.active_items(conn, order_id)
    subtotal = sum(line_total(item["quantity"], item["unit_price_cents"]) for item in items)
    return apply_discount(subtotal, repo.discount_percent(conn, order_id))


def get_order(conn: sqlite3.Connection, order_id: int) -> dict | None:
    order = repo.get_order(conn, order_id)
    if order is None:
        return None
    return {
        "id": order["id"],
        "customer_id": order["customer_id"],
        "status": order["status"],
        "created_at": order["created_at"],
        "items": [dict(item) for item in repo.active_items(conn, order_id)],
        "total_cents": order_total(conn, order_id),
    }


def list_orders(conn: sqlite3.Connection, status: str | None = None, page: int = 1, per_page: int = 20) -> dict:
    """One page of orders, newest first. Pages are numbered from 1."""
    offset = page * per_page
    rows = repo.orders_page(conn, status, per_page, offset)
    return {"page": page, "per_page": per_page, "orders": [dict(row) for row in rows]}


def list_customer_orders(conn: sqlite3.Connection, customer_id: int, limit: int = 20) -> list[dict]:
    """A customer's most recent orders with their items."""
    orders = [dict(row) for row in repo.orders_for_customer(conn, customer_id, limit)]
    for order in orders:
        order["items"] = [dict(item) for item in repo.active_items(conn, order["id"])]
        order["total_cents"] = order_total(conn, order["id"])
    return orders

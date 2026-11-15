"""The REST API: a route table over the services. No web framework, so it runs anywhere.

    GET /health
    GET /orders?status=&page=&per_page=
    GET /orders/{id}
    GET /orders/{id}/invoice
    GET /orders/{id}/payments
    GET /customers/{id}/orders
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Callable
from urllib.parse import parse_qs

from . import __version__, invoicing, orders, payments
from .db import connect

Handler = Callable[[sqlite3.Connection, dict, dict], tuple[int, object]]


def health(conn, path_args, query):
    return 200, {"status": "ok", "version": __version__}


def list_orders(conn, path_args, query):
    page = int(query.get("page", 1))
    per_page = min(int(query.get("per_page", 20)), 100)
    if page < 1 or per_page < 1:
        return 400, {"error": "page and per_page must be 1 or more"}
    return 200, orders.list_orders(conn, query.get("status"), page, per_page)


def get_order(conn, path_args, query):
    order = orders.get_order(conn, int(path_args["id"]))
    return (200, order) if order else (404, {"error": "order not found"})


def get_invoice(conn, path_args, query):
    invoice = invoicing.get_invoice(conn, int(path_args["id"]))
    return (200, invoice) if invoice else (404, {"error": "invoice not found"})


def get_payments(conn, path_args, query):
    order_id = int(path_args["id"])
    return 200, {"order_id": order_id, "events": payments.payment_events(conn, order_id),
                 "charged_cents": payments.amount_charged(conn, order_id)}


def customer_orders(conn, path_args, query):
    return 200, {"orders": orders.list_customer_orders(conn, int(path_args["id"]))}


ROUTES: list[tuple[str, re.Pattern, Handler]] = [
    ("GET", re.compile(r"^/health$"), health),
    ("GET", re.compile(r"^/orders$"), list_orders),
    ("GET", re.compile(r"^/orders/(?P<id>\d+)$"), get_order),
    ("GET", re.compile(r"^/orders/(?P<id>\d+)/invoice$"), get_invoice),
    ("GET", re.compile(r"^/orders/(?P<id>\d+)/payments$"), get_payments),
    ("GET", re.compile(r"^/customers/(?P<id>\d+)/orders$"), customer_orders),
]


def handle(conn: sqlite3.Connection, method: str, path: str, query: dict | None = None) -> tuple[int, object]:
    """Dispatches one request. Tests call this directly."""
    for route_method, pattern, handler in ROUTES:
        match = pattern.match(path)
        if match and route_method == method:
            try:
                return handler(conn, match.groupdict(), query or {})
            except ValueError:
                return 400, {"error": "invalid parameter"}
    return 404, {"error": "not found"}


def wsgi_app(environ, start_response):
    query = {key: values[0] for key, values in parse_qs(environ.get("QUERY_STRING", "")).items()}
    conn = connect()
    try:
        status, body = handle(conn, environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/"), query)
    finally:
        conn.close()
    payload = json.dumps(body).encode("utf-8")
    reason = {200: "OK", 400: "Bad Request", 404: "Not Found"}.get(status, "Error")
    start_response(f"{status} {reason}", [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))])
    return [payload]

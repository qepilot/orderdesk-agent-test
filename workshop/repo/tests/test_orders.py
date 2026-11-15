from conftest import add_order

from orderdesk import api, orders


def test_order_total_sums_items(conn):
    add_order(conn, 10, [(1, 1, 10000), (2, 1, 5000)])
    assert orders.order_total(conn, 10) == 15000


def test_order_total_with_discount_code(conn):
    add_order(conn, 11, [(1, 2, 10000)], discount_code="SAVE10")
    assert orders.order_total(conn, 11) == 18000


def test_order_total_ignores_removed_items(conn):
    add_order(conn, 12, [(1, 1, 10000), (2, 1, 5000)])
    conn.execute("UPDATE order_items SET status = 'removed' WHERE order_id = 12 AND product_id = 2")
    assert orders.order_total(conn, 12) == 10000


def test_list_orders_page_size(conn):
    for order_id in range(100, 150):
        add_order(conn, order_id, [(3, 1, 1995)], status="shipped", created_at=f"2026-10-01T10:{order_id - 100:02d}:00Z")
    status, body = api.handle(conn, "GET", "/orders", {"status": "shipped", "page": "1", "per_page": "20"})
    assert status == 200
    assert len(body["orders"]) == 20


def test_list_orders_rejects_page_zero(conn):
    status, _ = api.handle(conn, "GET", "/orders", {"page": "0"})
    assert status == 400


def test_customer_orders_include_items(conn):
    add_order(conn, 13, [(1, 1, 10000)])
    status, body = api.handle(conn, "GET", "/customers/1/orders")
    assert status == 200
    assert body["orders"][0]["items"][0]["sku"] == "SKU-A"

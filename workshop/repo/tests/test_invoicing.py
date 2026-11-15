from datetime import date

from conftest import add_order

from orderdesk import invoicing, orders


def test_invoice_total_matches_order_total(conn):
    add_order(conn, 20, [(1, 1, 10000), (2, 1, 5000)])
    invoice = invoicing.issue_invoice(conn, 20)
    assert invoice["total_cents"] == orders.order_total(conn, 20) == 15000


def test_invoice_applies_discount_code(conn):
    add_order(conn, 21, [(1, 1, 10000)], discount_code="SAVE10")
    assert invoicing.issue_invoice(conn, 21)["total_cents"] == 9000


def test_invoice_lists_lines(conn):
    add_order(conn, 22, [(1, 1, 10000), (3, 2, 1995)])
    invoicing.issue_invoice(conn, 22)
    assert [line["sku"] for line in invoicing.get_invoice(conn, 22)["lines"]] == ["SKU-A", "SKU-C"]


def test_invoice_issued_today(conn):
    add_order(conn, 23, [(1, 1, 10000)])
    invoice = invoicing.issue_invoice(conn, 23)
    assert invoice["issued_at"][:10] == date.today().isoformat()

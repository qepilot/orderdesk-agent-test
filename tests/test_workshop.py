"""The practice environment must stay exactly as the expected findings describe it."""

import sqlite3
import subprocess
import sys


def one(workspace, sql):
    conn = sqlite3.connect(workspace.db)
    try:
        return conn.execute(sql).fetchone()
    finally:
        conn.close()


def test_issue_101_data(workspace):
    assert one(workspace, "SELECT customer_id, status FROM orders WHERE id = 6800") == (123, "shipped")
    assert one(workspace, "SELECT total_cents FROM invoices WHERE order_id = 6800") == (17500,)
    assert one(workspace, "SELECT SUM(quantity * unit_price_cents) FROM order_items WHERE order_id = 6800 AND status = 'active'") == (15000,)
    assert one(workspace, "SELECT COUNT(DISTINCT i.order_id) FROM invoices i JOIN order_items oi ON oi.order_id = i.order_id "
                          "WHERE oi.status = 'removed'") == (46,)


def test_issue_102_index_is_missing(workspace):
    indexes = sqlite3.connect(workspace.db).execute("PRAGMA index_list('orders')").fetchall()
    assert indexes == []


def test_issue_103_and_106_data(workspace):
    assert one(workspace, "SELECT total_cents FROM invoices WHERE order_id = 6850") == (1695,)
    assert one(workspace, "SELECT COUNT(*) FROM payments WHERE order_id = 6920 AND kind = 'capture' AND status = 'succeeded'") == (1,)
    assert one(workspace, "SELECT COUNT(*) FROM payments WHERE order_id = 6920 AND status = 'voided'") == (1,)


def test_issue_104_newest_shipped_order(workspace):
    assert one(workspace, "SELECT id FROM orders WHERE status = 'shipped' ORDER BY created_at DESC LIMIT 1") == (7000,)


def test_practice_app_has_exactly_one_failing_test(workspace):
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=workspace.repo,
                         capture_output=True, text=True)
    assert "1 failed, 13 passed" in run.stdout
    assert "test_discount_rounds_half_up" in run.stdout

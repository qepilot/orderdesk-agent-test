"""Builds workshop/orderdesk.db: the schema from the migrations plus deterministic synthetic data.

    python workshop/seed.py            # build (or rebuild) the database
    python workshop/seed.py --if-missing

Every customer is fictional. The data is generated with a fixed random seed, so everybody in the
group gets byte-for-byte the same rows, and the expected findings in workshop/expected/ stay true.

Invoices are created by calling the application's own issue_invoice(), so data problems in the
database are produced by the code's defects rather than typed in by hand.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSHOP = Path(__file__).resolve().parent
DB_PATH = WORKSHOP / "orderdesk.db"
sys.path.insert(0, str(WORKSHOP / "repo"))

from orderdesk import invoicing, orders  # noqa: E402
from orderdesk.db import migrate  # noqa: E402

FIRST = ["Amara", "Bao", "Carmen", "Dmitri", "Elif", "Farid", "Greta", "Hiro", "Ines", "Jonas", "Kavya", "Liam",
         "Mei", "Nadia", "Omar", "Priya", "Quentin", "Rosa", "Sven", "Tala", "Uma", "Viktor", "Wanjiru", "Xavier",
         "Yuki", "Zainab"]
LAST = ["Abara", "Bergstrom", "Castillo", "Dang", "Eriksen", "Fofanah", "Gupta", "Haddad", "Ito", "Jovanovic",
        "Kowalski", "Lindqvist", "Mbeki", "Novak", "Okafor", "Petrov", "Quispe", "Raman", "Silva", "Tanaka",
        "Usman", "Vasquez", "Weller", "Xu", "Yilmaz", "Zamora"]
PRODUCTS = ["Desk lamp", "Notebook set", "Gel pen", "Monitor arm", "Cable tray", "Desk mat", "Laptop stand",
            "Webcam cover", "USB hub", "Footrest", "Whiteboard", "Marker set", "Sticky notes", "Label printer",
            "Paper tray", "Desk organiser", "Wrist rest", "Mouse pad", "Headset hook", "Power strip"]
PRICES = [2500, 5000, 10000, 1995, 1250, 3499, 7900, 899, 4500, 15000, 2999, 650, 1999, 12000, 800, 6000, 3000,
          2000, 1500, 9900]
RELEASE_2_3_0 = datetime(2026, 8, 18, tzinfo=timezone.utc)   # item removal exists from here on
START = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 8, 16, 40, tzinfo=timezone.utc)
FIRST_ORDER_ID, ORDER_COUNT = 4001, 3000
BIG_CUSTOMER = 42


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build(db_path: Path = DB_PATH) -> Path:
    rng = random.Random(42)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    for customer_id in range(1, 301):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        tier = "business" if customer_id == BIG_CUSTOMER or rng.random() < 0.1 else "standard"
        joined = START - timedelta(days=rng.randint(10, 700))
        conn.execute("INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
                     (customer_id, f"{first} {last}", f"{first}.{last}{customer_id}@example.test".lower(), tier,
                      iso(joined)))

    products = []
    for index in range(40):
        name = PRODUCTS[index % len(PRODUCTS)] + (" XL" if index >= len(PRODUCTS) else "")
        price = PRICES[index % len(PRICES)] + (2000 if index >= len(PRICES) else 0)
        products.append((index + 1, f"SKU-{1001 + index}", name, price))
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)
    conn.executemany("INSERT INTO discount_codes VALUES (?, ?, ?)",
                     [("SAVE10", 10, 1), ("SAVE15", 15, 1), ("WELCOME5", 5, 1), ("SPRING20", 20, 0)])

    step = (END - START) / (ORDER_COUNT - 1)
    plan = []
    for index in range(ORDER_COUNT):
        created = START + step * index
        roll = rng.random()
        status = "shipped" if roll < 0.55 else "paid" if roll < 0.75 else "pending" if roll < 0.90 else "cancelled"
        customer = BIG_CUSTOMER if rng.random() < 0.06 else rng.randint(1, 300)
        items = []
        for product in rng.sample(products, rng.randint(1, 4)):
            items.append({"product_id": product[0], "quantity": rng.randint(1, 3), "price": product[3],
                          "status": "active"})
        code = rng.choice(["SAVE10", "SAVE15", "WELCOME5"]) if rng.random() < 0.15 else None
        if created >= RELEASE_2_3_0 and len(items) >= 2 and rng.random() < 0.07:
            items[-1]["status"] = "removed"
            code = None
        retry = rng.random() < 0.02
        plan.append({"id": FIRST_ORDER_ID + index, "customer": customer, "status": status, "code": code,
                     "created": created, "items": items, "payment_retry": retry})

    def patch(order_id, **changes):
        plan[order_id - FIRST_ORDER_ID].update(changes)

    def item(product_id, quantity=1, status="active"):
        return {"product_id": product_id, "quantity": quantity, "price": products[product_id - 1][3], "status": status}

    # The scenarios the issues are about. Product 3 costs 100.00, 2 costs 50.00, 1 costs 25.00, 4 costs 19.95.
    patch(6800, customer=123, status="shipped", code=None, payment_retry=False,
          items=[item(3), item(2), item(1, status="removed")])                      # issue #101
    patch(6850, customer=201, status="paid", code="SAVE15", payment_retry=False, items=[item(4)])   # issue #103
    patch(6700, customer=77, status="shipped", code=None, payment_retry=False, items=[item(7)])     # issue #105
    patch(6920, customer=88, status="paid", code=None, payment_retry=True, items=[item(15), item(18, 3), item(5)])  # issue #106
    patch(7000, status="shipped", payment_retry=False)                               # issue #104

    for order in plan:
        conn.execute("INSERT INTO orders (id, customer_id, status, discount_code, created_at) VALUES (?, ?, ?, ?, ?)",
                     (order["id"], order["customer"], order["status"], order["code"], iso(order["created"])))
        for line in order["items"]:
            conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents, status) "
                         "VALUES (?, ?, ?, ?, ?)",
                         (order["id"], line["product_id"], line["quantity"], line["price"], line["status"]))
        if order["status"] not in ("paid", "shipped"):
            continue
        total = orders.order_total(conn, order["id"])
        paid_at = order["created"] + timedelta(minutes=2)
        if order["payment_retry"]:
            conn.execute("INSERT INTO payments (order_id, kind, amount_cents, status, created_at) VALUES (?, ?, ?, ?, ?)",
                         (order["id"], "authorization", total, "voided", iso(paid_at)))
            paid_at += timedelta(seconds=37)
        conn.execute("INSERT INTO payments (order_id, kind, amount_cents, status, created_at) VALUES (?, ?, ?, ?, ?)",
                     (order["id"], "authorization", total, "succeeded", iso(paid_at)))
        conn.execute("INSERT INTO payments (order_id, kind, amount_cents, status, created_at) VALUES (?, ?, ?, ?, ?)",
                     (order["id"], "capture", total, "succeeded", iso(paid_at + timedelta(seconds=1))))
        invoicing.issue_invoice(conn, order["id"], issued_at=iso(paid_at + timedelta(minutes=5)))

    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    return db_path


if __name__ == "__main__":
    if "--if-missing" in sys.argv and DB_PATH.exists():
        print(f"exists      {DB_PATH}")
    else:
        print(f"built       {build()}")

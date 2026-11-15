-- 0005: rename orders.cust_id to customer_id and add CHECK on status (release 2.4.0)
-- The table is rebuilt because the old engine version could not add a CHECK in place.
CREATE TABLE orders_new (
    id             INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers (id),
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    discount_code  TEXT,
    created_at     TEXT NOT NULL
);

INSERT INTO orders_new (id, customer_id, status, discount_code, created_at)
SELECT id, cust_id, status, discount_code, created_at FROM orders;

DROP TABLE orders;
ALTER TABLE orders_new RENAME TO orders;

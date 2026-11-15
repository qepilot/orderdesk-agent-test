-- 0003: invoicing and payments (release 2.0.0)
CREATE TABLE invoices (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL UNIQUE REFERENCES orders (id),
    total_cents  INTEGER NOT NULL,
    issued_at    TEXT NOT NULL
);

CREATE TABLE payments (
    id            INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders (id),
    kind          TEXT NOT NULL,      -- authorization | capture | refund
    amount_cents  INTEGER NOT NULL,
    status        TEXT NOT NULL,      -- succeeded | voided | failed
    created_at    TEXT NOT NULL
);

CREATE INDEX idx_payments_order ON payments (order_id);

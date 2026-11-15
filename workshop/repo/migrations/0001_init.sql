-- 0001: first schema (release 1.0.0)
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    tier        TEXT NOT NULL DEFAULT 'standard',
    created_at  TEXT NOT NULL
);

CREATE TABLE products (
    id                INTEGER PRIMARY KEY,
    sku               TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    unit_price_cents  INTEGER NOT NULL
);

CREATE TABLE orders (
    id             INTEGER PRIMARY KEY,
    cust_id        INTEGER NOT NULL REFERENCES customers (id),
    status         TEXT NOT NULL DEFAULT 'pending',
    discount_code  TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE order_items (
    id                INTEGER PRIMARY KEY,
    order_id          INTEGER NOT NULL REFERENCES orders (id),
    product_id        INTEGER NOT NULL REFERENCES products (id),
    quantity          INTEGER NOT NULL,
    unit_price_cents  INTEGER NOT NULL
);

CREATE TABLE discount_codes (
    code         TEXT PRIMARY KEY,
    percent_off  INTEGER NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1
);

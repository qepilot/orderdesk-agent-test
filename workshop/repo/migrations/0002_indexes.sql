-- 0002: indexes for the two hottest lookups (release 1.1.0)
CREATE INDEX idx_order_items_order ON order_items (order_id);
CREATE INDEX idx_orders_customer_created ON orders (cust_id, created_at);

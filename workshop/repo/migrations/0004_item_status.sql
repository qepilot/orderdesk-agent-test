-- 0004: customers can remove an item from a pending order (release 2.3.0)
-- Removed items are kept for audit; they must not count towards any total.
ALTER TABLE order_items ADD COLUMN status TEXT NOT NULL DEFAULT 'active';   -- active | removed

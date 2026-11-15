# OrderDesk architecture

OrderDesk is the service behind the orders screen of the admin console and the customer "My orders" page.

```text
HTTP request
  └─ orderdesk/api.py        route table, parameter parsing, status codes
       ├─ orderdesk/orders.py     order totals, order lists
       │    └─ orderdesk/repo.py       every SQL statement for orders
       ├─ orderdesk/invoicing.py  invoice totals and lines (has its own SQL, written before repo.py existed)
       ├─ orderdesk/payments.py   authorizations, captures, refunds
       └─ orderdesk/pricing.py    line totals and discounts
```

## Rules the code is supposed to follow

1. **Money is integer cents.** Never store or pass floats. Rounding is half-up, to the cent.
2. **Removed items do not count.** Since release 2.3.0 a customer can remove an item from a pending order. The row
   stays in `order_items` with `status = 'removed'` for audit. Every total, count and listing shown to a customer
   must use active items only.
3. **An order has at most one invoice**, issued when the order is paid. Invoices are never edited: a wrong invoice
   is corrected with a credit note and a new invoice (see the finance runbook).
4. **Pages are numbered from 1.** `page=1` is the newest page.
5. **Authorizations are not charges.** Only a successful `capture` takes money. A voided authorization can still
   show as "pending" on a card statement for a few days.

## Data

Production runs PostgreSQL 15 with about 1.2 million orders. The workshop database is a SQLite file built from the
same migration files (`migrations/`) with a few thousand synthetic orders. All customers are fictional.

## Releases

| Version | Date | Notes |
|---|---|---|
| 2.2.0 | 2026-06-30 | Admin order list with status filter and pagination |
| 2.3.0 | 2026-08-18 | Remove an item from a pending order (migration 0004) |
| 2.4.0 | 2026-10-06 | `orders.cust_id` renamed to `customer_id`, status CHECK (migration 0005) |
| 2.4.1 | 2026-10-20 | Dependency updates |

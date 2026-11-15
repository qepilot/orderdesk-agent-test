---
id: DOC-money
type: standard
date: 2026-03-25
title: Money handling standard
tags: money, rounding, pricing
---

# Money handling standard

- Amounts are integer cents everywhere: database, code, API.
- Percentages are applied in integer arithmetic and rounded half up to the cent:
  `(amount * (100 - percent) + 50) // 100`.
- `int()` and `//` on an unrounded value truncate and are not allowed for money.
- Discounts never combine to more than 100%, and a total is never negative.
- The same total must be computed by one function. Order total, invoice total and charge amount for an order
  are the same number.

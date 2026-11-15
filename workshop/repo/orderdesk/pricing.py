"""Price calculations. All money is integer cents (see docs/ARCHITECTURE.md)."""

from __future__ import annotations


def line_total(quantity: int, unit_price_cents: int) -> int:
    return quantity * unit_price_cents


def apply_discount(subtotal_cents: int, percent_off: int) -> int:
    """Returns the subtotal after a percentage discount, in cents."""
    if percent_off <= 0:
        return subtotal_cents
    return int(subtotal_cents * (100 - percent_off) / 100)

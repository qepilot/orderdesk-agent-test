"""Wire formats: timestamps are ISO-8601 UTC; money is integer `*_cents` fields."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_iso(value: datetime) -> str:
    """Format a datetime as ISO-8601 UTC with a trailing Z (naive means UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

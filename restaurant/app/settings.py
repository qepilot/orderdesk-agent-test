"""Application settings read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

VALID_ENVS = ("development", "test", "production")
DEFAULT_SECRET_KEY = "change-me"  # noqa: S105 - documented placeholder, refused in production


class SettingsError(ValueError):
    """Raised when a setting is missing or invalid; the message names the variable."""


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    db_path: str = "restaurant/data/restaurant.db"
    secret_key: str = DEFAULT_SECRET_KEY
    tax_percent: int = 8
    delivery_fee_cents: int = 300


def _int(environ: Mapping[str, str], name: str, default: int, minimum: int, maximum: int | None):
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise SettingsError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum or (maximum is not None and value > maximum):
        bound = f">= {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise SettingsError(f"{name} must be {bound}, got {value}")
    return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from environment variables, validating every value."""
    environ = os.environ if environ is None else environ

    env = environ.get("RESTAURANT_ENV", "development").strip()
    if env not in VALID_ENVS:
        raise SettingsError(
            f"RESTAURANT_ENV must be one of {', '.join(VALID_ENVS)}, got {env!r}"
        )

    db_path = environ.get("RESTAURANT_DB_PATH", Settings.db_path).strip()
    if not db_path:
        raise SettingsError("RESTAURANT_DB_PATH must not be empty")

    secret_key = environ.get("RESTAURANT_SECRET_KEY", DEFAULT_SECRET_KEY)
    if env == "production" and (not secret_key.strip() or secret_key == DEFAULT_SECRET_KEY):
        raise SettingsError(
            "RESTAURANT_SECRET_KEY must be set to a non-default value in production"
        )

    return Settings(
        env=env,
        db_path=db_path,
        secret_key=secret_key,
        tax_percent=_int(environ, "RESTAURANT_TAX_PERCENT", Settings.tax_percent, 0, 100),
        delivery_fee_cents=_int(
            environ, "RESTAURANT_DELIVERY_FEE_CENTS", Settings.delivery_fee_cents, 0, None
        ),
    )

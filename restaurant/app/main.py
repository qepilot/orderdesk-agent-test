"""FastAPI application entry point: `uvicorn restaurant.app.main:app`."""

from __future__ import annotations

from fastapi import FastAPI

from restaurant.app.settings import Settings, SettingsError, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    application = FastAPI(title="Restaurant ordering")
    application.state.settings = settings

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


try:
    app = create_app()
except SettingsError as exc:
    raise SystemExit(f"Invalid configuration: {exc}") from None

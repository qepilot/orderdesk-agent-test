"""FastAPI application entry point: `uvicorn restaurant.app.main:app`."""

from __future__ import annotations

from fastapi import FastAPI

from restaurant.app.api import api_router
from restaurant.app.api.errors import install_error_handlers
from restaurant.app.api.request_id import RequestIdMiddleware
from restaurant.app.settings import Settings, SettingsError, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    docs_enabled = settings.env != "production"
    application = FastAPI(
        title="Restaurant ordering",
        docs_url="/api/docs" if docs_enabled else None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        redoc_url=None,
    )
    # CORS is deliberately off: no CORSMiddleware is installed.
    install_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(api_router)
    application.state.settings = settings

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


try:
    app = create_app()
except SettingsError as exc:
    raise SystemExit(f"Invalid configuration: {exc}") from None

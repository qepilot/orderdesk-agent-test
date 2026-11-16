"""Uniform error body and exception handlers.

Every error response looks like::

    {"error": {"code": "...", "message": "...", "details": [...]?, "request_id": "..."}}

Stable machine-readable codes: ``validation_error`` (422), ``not_found`` (404),
``conflict`` (409), ``http_error`` fallbacks (``bad_request``, ``unauthorized``,
``forbidden``, ``method_not_allowed``), ``internal_error`` (500).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from restaurant.app.api.request_id import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger("restaurant.api")

INTERNAL_MESSAGE = "An unexpected error occurred."

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
}


class AppError(Exception):
    """Base class for errors services raise on purpose."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class AppValidationError(AppError):
    status_code = 422
    code = "validation_error"


def error_body(
    code: str, message: str, request_id: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    error["request_id"] = request_id
    return {"error": error}


def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    out = dict(headers or {})
    out[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        error_body(code, message, request_id, details), status_code=status_code, headers=out
    )


def internal_error_response(request_id: str) -> JSONResponse:
    return error_response(500, "internal_error", INTERNAL_MESSAGE, request_id)


def _field_name(loc: tuple[Any, ...]) -> str:
    parts = list(loc)
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    return ".".join(str(p) for p in parts)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            exc.status_code, exc.code, exc.message, get_request_id(request), exc.details
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted input back: it may hold personal data.
        details = [
            {"field": _field_name(tuple(e["loc"])), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(
            422, "validation_error", "Request validation failed.", get_request_id(request), details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        if exc.status_code >= 500:
            return internal_error_response(get_request_id(request))
        message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ")
        return error_response(
            exc.status_code,
            code,
            message,
            get_request_id(request),
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error", exc_info=exc)
        return internal_error_response(get_request_id(request))

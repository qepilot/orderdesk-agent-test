"""X-Request-ID middleware (pure ASGI so it also covers unexpected errors)."""

from __future__ import annotations

import logging
import re
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# Accepted incoming ids: 8-64 chars of letters, digits, dot, underscore, dash.
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

logger = logging.getLogger("restaurant.api")


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        if incoming and VALID_REQUEST_ID.match(incoming):
            request_id = incoming
        else:
            request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception("Unhandled error (request_id=%s)", request_id)
            if started:
                raise
            from restaurant.app.api.errors import internal_error_response

            response = internal_error_response(request_id)
            await response(scope, receive, send_with_id)

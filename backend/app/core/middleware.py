"""ASGI middleware: request IDs, security headers, access logs and a last-resort error handler.

This is written as plain ASGI middleware (not ``BaseHTTPMiddleware``) so that it
works with streaming responses such as video range requests and keeps
context variables intact.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import INTERNAL_ERROR_MESSAGE, error_response
from app.core.logging import request_id_var

logger = logging.getLogger("app.request")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    # Media and JSON from the API may be used by the web app on the same site only.
    "Cross-Origin-Resource-Policy": "same-site",
}
#: Sent only in production (HTTPS): browsers then refuse plain-HTTP connections to the API.
HSTS = "max-age=31536000; includeSubDomains"

# Paths that are polled frequently; their access logs are written at DEBUG level.
QUIET_PATHS = {"/api/v1/health"}


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1").strip()
            if _REQUEST_ID_RE.match(candidate):
                return candidate
    return None


class RequestContextMiddleware:
    """Assigns a request ID, adds security headers and logs every request."""

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        state = {"status": 500, "response_started": False}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["response_started"] = True
                state["status"] = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", HSTS)
                headers.setdefault("Cache-Control", "no-store")
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            logger.exception(
                "Unhandled error while processing request",
                extra={"method": scope.get("method"), "path": scope.get("path")},
            )
            if state["response_started"]:
                raise  # Too late to send a clean error response.
            response = error_response(500, "internal_error", INTERNAL_ERROR_MESSAGE)
            await response(scope, receive, send_with_headers)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            path = scope.get("path", "")
            log = logger.debug if path in QUIET_PATHS else logger.info
            log(
                "Request completed",
                extra={
                    "method": scope.get("method"),
                    "path": path,
                    "status": state["status"],
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)

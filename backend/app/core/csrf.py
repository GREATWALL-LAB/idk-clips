"""Cross-site request forgery protection for cookie-authenticated API calls.

Defense in depth on top of ``SameSite=Lax`` cookies. Every state-changing
request (POST/PUT/PATCH/DELETE) under ``/api/`` must:

1. carry the header ``X-Requested-With: OpenClip``. Browsers only let other
   sites send custom headers after a CORS preflight, which fails for origins
   that are not on the allow list; and
2. if the browser sends an ``Origin`` header, that origin must be on the allow
   list, or be this API's own origin (the web interface served by the API itself).
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import error_response

CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "OpenClip"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CSRFMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = {origin.lower() for origin in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope.get("method") in UNSAFE_METHODS
            and str(scope.get("path", "")).startswith("/api/")
        ):
            headers = {
                name.decode("latin-1").lower(): value.decode("latin-1")
                for name, value in scope["headers"]
            }
            origin = headers.get("origin")
            same_origin = (
                bool(origin)
                and origin.lower().split("://", 1)[-1] == headers.get("host", "").lower()
            )
            if (
                origin
                and not same_origin
                and origin.lower() not in self.allowed_origins
                and origin != "null"
            ):
                response = error_response(
                    403, "csrf_failed", "This request came from a website that is not allowed."
                )
                await response(scope, receive, send)
                return
            if origin == "null" or headers.get(CSRF_HEADER.lower()) != CSRF_HEADER_VALUE:
                response = error_response(
                    403,
                    "csrf_failed",
                    f"Missing or invalid {CSRF_HEADER} header. Requests must come from the IDK Clips app.",
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

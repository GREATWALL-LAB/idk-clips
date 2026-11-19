"""Keep a local-only service local.

Used by local mode and by the worker's bridge. Two checks on every request:

1. The TCP peer must be this computer (a loopback address).
2. The ``Host`` header must name this computer. A malicious website can make a
   browser resolve its own domain to 127.0.0.1 ("DNS rebinding"); such requests
   arrive from loopback but carry the attacker's host name, and are refused here.
"""

from __future__ import annotations

import ipaddress

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import error_response

LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def is_loopback_address(host: str | None) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_loopback


def host_name(header_value: str) -> str:
    """'localhost:8000' -> 'localhost', '[::1]:8000' -> '::1'."""
    value = header_value.strip().lower()
    if value.startswith("["):
        return value[1:].split("]", 1)[0]
    return value.rsplit(":", 1)[0] if ":" in value else value


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, *, enforce_peer: bool = True) -> None:
        self.app = app
        self.enforce_peer = enforce_peer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        if self.enforce_peer and not is_loopback_address(client[0] if client else None):
            response = error_response(
                403, "local_only", "This service only accepts requests from this computer."
            )
            await response(scope, receive, send)
            return
        host = ""
        for name, value in scope.get("headers", []):
            if name == b"host":
                host = host_name(value.decode("latin-1"))
                break
        if host not in LOOPBACK_NAMES:
            response = error_response(
                403, "local_only", "Open this service through http://localhost or http://127.0.0.1."
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

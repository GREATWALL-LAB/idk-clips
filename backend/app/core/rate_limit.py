"""In-memory rate limiting.

A token bucket per client (and per "bucket name") limits request bursts. The
limiter lives in process memory, which is correct for the default single-process
deployment. If you run several API processes behind a load balancer, each
process enforces its own limit; see docs/SECURITY.md.

Client identity is the socket peer address. When running behind a reverse
proxy, start uvicorn with ``--proxy-headers --forwarded-allow-ips=<proxy ip>``
so the real client address is used instead of the proxy's.
"""

from __future__ import annotations

import ipaddress
import math
import re
import threading
import time
from collections.abc import Callable

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import RateLimitError, error_response


class TokenBucketLimiter:
    """Thread-safe token buckets keyed by an arbitrary string."""

    def __init__(
        self,
        capacity: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 50_000,
    ) -> None:
        if capacity < 1 or window_seconds <= 0:
            raise ValueError("capacity must be >= 1 and window_seconds > 0")
        self.capacity = float(capacity)
        self.refill_per_second = capacity / window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """Take ``cost`` tokens. Returns ``(allowed, retry_after_seconds)``."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)
            if tokens >= cost:
                self._buckets[key] = (tokens - cost, now)
                result = (True, 0.0)
            else:
                self._buckets[key] = (tokens, now)
                result = (False, (cost - tokens) / self.refill_per_second)
            if len(self._buckets) > self._max_keys:
                self._prune(now)
        return result

    def _prune(self, now: float) -> None:
        # Drop buckets that have fully refilled; they carry no state.
        full_after = self.capacity / self.refill_per_second
        stale = [key for key, (_, last) in self._buckets.items() if now - last >= full_after]
        for key in stale:
            del self._buckets[key]

    def available(self, key: str) -> float:
        """Tokens currently left for ``key`` (without taking any)."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            return min(self.capacity, tokens + (now - last) * self.refill_per_second)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_key(scope: Scope) -> str:
    client = scope.get("client")
    return client[0] if client else "unknown"


#: Answers that suggest probing or guessing. 401 from "who am I?" is normal for visitors.
FAILURE_STATUSES = frozenset({401, 403, 404})
NORMAL_FAILURES = frozenset({"/api/v1/auth/me"})


class RateLimitMiddleware:
    """Applies a general per-client request budget to every HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
        limiter: TokenBucketLimiter,
        enabled: bool = True,
        exempt_paths: frozenset[str] = frozenset(),
        failure_limiter: TokenBucketLimiter | None = None,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.enabled = enabled
        self.exempt_paths = exempt_paths
        self.failure_limiter = failure_limiter

    async def _refuse(self, scope: Scope, receive: Receive, send: Send, retry_after: float) -> None:
        response = error_response(
            429,
            RateLimitError.code,
            RateLimitError.default_message,
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            not self.enabled
            or scope["type"] != "http"
            or scope.get("method") == "OPTIONS"
            or scope.get("path") in self.exempt_paths
        ):
            await self.app(scope, receive, send)
            return

        client = client_key(scope)
        failures = self.failure_limiter
        path = str(scope.get("path", ""))
        if failures is not None and failures.available(f"fail:{client}") < 1:
            await self._refuse(scope, receive, send, 1 / failures.refill_per_second)
            return
        allowed, retry_after = self.limiter.acquire(f"global:{client}")
        if not allowed:
            await self._refuse(scope, receive, send, retry_after)
            return
        if failures is None or not path.startswith("/api/") or path in NORMAL_FAILURES:
            await self.app(scope, receive, send)
            return

        async def counting_send(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] in FAILURE_STATUSES:
                failures.acquire(f"fail:{client}")
            await send(message)

        await self.app(scope, receive, counting_send)


class ClientIPMiddleware:
    """Takes the client address from a header set by a trusted proxy (opt-in)."""

    def __init__(self, app: ASGIApp, header: str) -> None:
        self.app = app
        self.header = header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            for name, value in scope.get("headers", []):
                if name == self.header:
                    candidate = value.decode("latin-1").split(",")[0].strip()
                    try:
                        ipaddress.ip_address(candidate)
                    except ValueError:
                        break
                    scope = {**scope, "client": (candidate, 0)}
                    break
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Refuses request bodies above a size limit before they are read into memory.

    Video uploads have their own, much larger limit (``max_upload_mb``) that is
    enforced while the file is streamed to disk, so they are excluded here.
    """

    def __init__(
        self,
        app: ASGIApp,
        default_bytes: int,
        worker_bytes: int,
        stream_paths: tuple[re.Pattern[str], ...] = (),
    ) -> None:
        self.app = app
        self.default_bytes = default_bytes
        self.worker_bytes = worker_bytes
        self.stream_paths = stream_paths

    def _limit(self, path: str) -> int | None:
        if any(pattern.match(path) for pattern in self.stream_paths):
            return None
        return self.worker_bytes if path.startswith("/api/v1/agent/") else self.default_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        limit = self._limit(str(scope.get("path", "")))
        if limit is None:
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > limit:
                await _too_large(scope, receive, send, limit)
                return
        state = {"received": 0, "too_large": False, "replaced": False}

        async def counting_receive() -> Message:
            if state["too_large"]:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > limit:
                    # Stop reading; whatever the app answers is replaced by a 413 below.
                    state["too_large"] = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message: Message) -> None:
            if not state["too_large"]:
                await send(message)
            elif not state["replaced"]:
                state["replaced"] = True
                await _too_large(scope, receive, send, limit)

        await self.app(scope, counting_receive, guarded_send)


async def _too_large(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
    response = error_response(
        413,
        "request_too_large",
        f"This request is too large (the limit is {limit // (1024 * 1024)} MB).",
    )
    await response(scope, receive, send)


ROUTE_LIMIT_LABELS = {
    "login": "sign-in",
    "register": "sign-up",
    "upload": "upload or import",
    "jobs": "processing",
    "pair": "worker pairing",
    "verify": "verification",
    "resend": "code request",
}


def build_route_limiters(settings) -> dict[str, TokenBucketLimiter]:  # type: ignore[no-untyped-def]
    """Stricter, per-purpose budgets for expensive or sensitive endpoints."""
    return {
        "login": TokenBucketLimiter(settings.login_rate_limit_per_minute, 60),
        "register": TokenBucketLimiter(settings.register_rate_limit_per_hour, 3600),
        "upload": TokenBucketLimiter(settings.upload_rate_limit_per_hour, 3600),
        "jobs": TokenBucketLimiter(settings.job_rate_limit_per_hour, 3600),
        # Pairing codes are short, so guessing must be slow: 10 tries per 10 minutes.
        "pair": TokenBucketLimiter(10, 600),
        # Wrong codes are also counted per account; this limits guessing across accounts.
        "verify": TokenBucketLimiter(20, 600),
        "resend": TokenBucketLimiter(10, 3600),
    }


def route_limit(name: str, key: str = "ip") -> Callable[[Request], None]:
    """FastAPI dependency. ``key="user"`` limits per signed-in user instead of per IP.

    Per-user limits must be declared after the ``CurrentUser`` dependency so the
    user is known; otherwise the client IP is used.
    """

    def dependency(request: Request) -> None:
        settings = request.app.state.settings
        if not settings.rate_limit_enabled:
            return
        limiter: TokenBucketLimiter = request.app.state.route_limiters[name]
        identity = getattr(request.state, "user_id", None) if key == "user" else None
        bucket = f"{name}:{identity or client_key(request.scope)}"
        allowed, retry_after = limiter.acquire(bucket)
        if not allowed:
            wait = max(1, math.ceil(retry_after))
            label = ROUTE_LIMIT_LABELS.get(name, name)
            raise RateLimitError(
                f"Too many {label} attempts. Try again in {wait} seconds.",
                headers={"Retry-After": str(wait)},
            )

    return dependency

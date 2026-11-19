"""One-time email codes, delivered and checked by Supabase Auth.

IDK Clips keeps its own accounts and passwords. Supabase Auth is used only to prove that a
person controls an email address:

1. ``send(email)`` asks Supabase to email a one-time code (``POST /auth/v1/otp``). The
   email template in Supabase must contain ``{{ .Token }}`` so the message shows the code.
2. ``verify(email, code)`` asks Supabase whether the code is right for that address
   (``POST /auth/v1/verify``). Only this server talks to Supabase; the browser never sees
   a Supabase session, and the session Supabase returns is revoked straight away.

Only the project URL and the public (anon / publishable) key are needed: no service-role
key is used or stored. Supabase also enforces its own limits (one code per address per
60 seconds by default, and an expiry that should match ``email_otp_ttl_minutes``).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Protocol

import httpx

from app.core.errors import RateLimitError, ServiceUnavailableError

logger = logging.getLogger("app.email_codes")

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


#: "verify": prove a new address (Supabase "Magic Link" / "Confirm signup" email).
#: "reset": a password reset code (Supabase "Reset Password" email).
Purpose = str


class EmailCodes(Protocol):
    def send(self, email: str, purpose: Purpose = "verify") -> None: ...

    def verify(self, email: str, code: str, purpose: Purpose = "verify") -> bool: ...


class SupabaseEmailCodes:
    def __init__(
        self, url: str, anon_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base = url.rstrip("/") + "/auth/v1"
        self.headers = {
            "apikey": anon_key,
            "Content-Type": "application/json",
            "User-Agent": "IDKClips/0.1 (email verification)",
        }
        # Legacy anon keys are JWTs and also go in Authorization. The newer publishable
        # keys (sb_publishable_...) are not JWTs and must only be sent as `apikey`.
        if anon_key.count(".") == 2:
            self.headers["Authorization"] = f"Bearer {anon_key}"
        self.transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=TIMEOUT, transport=self.transport, follow_redirects=False)

    def _post(self, path: str, body: dict, headers: dict | None = None) -> httpx.Response:
        try:
            with self._client() as client:
                return client.post(self.base + path, json=body, headers=headers or self.headers)
        except httpx.HTTPError as exc:
            logger.warning("Supabase Auth is unreachable", extra={"error": type(exc).__name__})
            raise ServiceUnavailableError(
                "The email service is not reachable right now. Try again in a minute.",
                code="email_service_unavailable",
            ) from exc

    @staticmethod
    def _rate_limited(response: httpx.Response) -> RateLimitError:
        wait = response.headers.get("retry-after", "60")
        return RateLimitError(
            "Too many codes were requested for this address. Wait a minute and try again.",
            code="code_rate_limited",
            headers={"Retry-After": wait if wait.isdigit() else "60"},
        )

    def send(self, email: str, purpose: Purpose = "verify") -> None:
        if purpose == "reset":
            # The Supabase user exists since the address was verified.
            response = self._post("/recover", {"email": email})
        else:
            response = self._post("/otp", {"email": email, "create_user": True})
        if response.status_code == 429:
            raise self._rate_limited(response)
        if response.status_code >= 400:
            logger.error(
                "Supabase refused to send a code",
                extra={"status": response.status_code, "body": response.text[:300]},
            )
            raise ServiceUnavailableError(
                "We could not send the verification email. Try again in a minute.",
                code="email_send_failed",
            )

    def verify(self, email: str, code: str, purpose: Purpose = "verify") -> bool:
        kind = "recovery" if purpose == "reset" else "email"
        response = self._post("/verify", {"type": kind, "email": email, "token": code})
        if response.status_code == 429:
            raise self._rate_limited(response)
        if response.status_code in {400, 401, 403, 404, 422}:
            return False  # wrong or expired code
        if response.status_code >= 400:
            raise ServiceUnavailableError(
                "The email service is not reachable right now. Try again in a minute.",
                code="email_service_unavailable",
            )
        try:
            data = response.json()
        except ValueError:
            return False
        confirmed = str((data.get("user") or {}).get("email") or "").strip().lower()
        if confirmed != email:
            return False
        self._revoke(data.get("access_token"))
        return True

    def _revoke(self, access_token: str | None) -> None:
        """Supabase returns a session on success; IDK Clips does not use it."""
        if not access_token:
            return
        headers = {**self.headers, "Authorization": f"Bearer {access_token}"}
        with contextlib.suppress(ServiceUnavailableError):  # best effort; it expires anyway
            self._post("/logout?scope=global", {}, headers=headers)


def build_email_codes(settings) -> EmailCodes | None:  # type: ignore[no-untyped-def]
    if not settings.email_verification_ready:
        return None
    return SupabaseEmailCodes(
        settings.supabase_url,
        settings.supabase_anon_key.get_secret_value(),
    )

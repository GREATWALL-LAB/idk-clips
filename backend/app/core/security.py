"""Password hashing, session tokens and sign-in throttling."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# argon2id with the library's defaults (RFC 9106 recommended parameters).
_hasher = PasswordHasher()
# Verifying against a dummy hash when the account does not exist keeps response
# times similar, so attackers cannot learn which emails are registered.
_DUMMY_HASH = _hasher.hash("openclip-dummy-password-used-for-timing-only")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        matched = _hasher.verify(stored_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return bool(matched and stored_hash)


def password_needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def password_problem(password: str, email: str | None = None) -> str | None:
    """Return a user-facing reason the password is unacceptable, or None."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Use at most {PASSWORD_MAX_LENGTH} characters."
    if password.strip() != password or not password.strip():
        return "The password cannot start or end with spaces."
    if email and password.lower() == email.lower():
        return "The password cannot be your email address."
    if len(set(password)) < 4:
        return "The password is too repetitive."
    return None


def new_session_token() -> str:
    """256 bits of randomness, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginThrottle:
    """Locks an account for a while after repeated failed sign-ins (per email address)."""

    def __init__(
        self, max_failures: int = 5, window_seconds: float = 900, clock=time.monotonic
    ) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and now - attempts[0] > self.window:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str) -> float:
        """Seconds until ``key`` may try again (0 when not locked)."""
        now = self._clock()
        with self._lock:
            attempts = self._recent(key, now)
            if len(attempts) < self.max_failures:
                return 0.0
            return max(0.0, self.window - (now - attempts[0]))

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            self._recent(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

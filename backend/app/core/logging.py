"""Structured logging with request IDs and secret redaction.

Two output formats share the same structure:
- ``console``: human-readable ``time level logger: message key=value ...``
- ``json``: one JSON object per line, for log collectors.

Every record passes through :class:`SecretRedactor`, which masks registered
secret values (for example API keys from settings) and common token patterns.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes that every LogRecord has; anything else was passed via ``extra=``.
_RESERVED_ATTRS = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {
    "message",
    "asctime",
    "taskName",
}

_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}")
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password)\b(\s*[=:]\s*)([^\s,;&\"']+)"
)


class SecretRedactor:
    """Masks secret values and token-like strings in log output."""

    def __init__(self) -> None:
        self._values: set[str] = set()

    def register(self, value: str | None) -> None:
        if value and len(value) >= 4:
            self._values.add(value)

    def redact(self, text: str) -> str:
        for secret in self._values:
            if secret in text:
                text = text.replace(secret, "***")
        text = _BEARER_RE.sub("Bearer ***", text)
        text = _SK_RE.sub("sk-***", text)
        return _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


redactor = SecretRedactor()


def _clean(value: Any) -> Any:
    if isinstance(value, bool | int | float) or value is None:
        return value
    return redactor.redact(str(value))


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: _clean(value)
        for key, value in record.__dict__.items()
        if key not in _RESERVED_ATTRS and not key.startswith("_")
    }


def _timestamp(record: logging.LogRecord) -> str:
    moment = datetime.fromtimestamp(record.created, UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": _timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": redactor.redact(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["exception"] = redactor.redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Readable single-line format that keeps the structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        fields = _extra_fields(record)
        request_id = request_id_var.get()
        if request_id:
            fields["request_id"] = request_id
        suffix = " ".join(f"{key}={value}" for key, value in fields.items())
        line = (
            f"{_timestamp(record)} {record.levelname:<7} {record.name}: "
            f"{redactor.redact(record.getMessage())}"
        )
        if suffix:
            line = f"{line} | {suffix}"
        if record.exc_info:
            line = f"{line}\n{redactor.redact(self.formatException(record.exc_info))}"
        return line


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Install a single stdout handler on the root logger."""
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        # Never crash on characters the console code page cannot encode.
        reconfigure(errors="backslashreplace")

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # Route uvicorn's own logs through our handler; we write our own access log.
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True

    for noisy in (
        "httpx",
        "httpx2",
        "httpcore",
        "multipart",
        "watchfiles",
        "huggingface_hub",
        "faster_whisper",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

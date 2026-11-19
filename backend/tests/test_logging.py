from __future__ import annotations

import json
import logging

from app.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    SecretRedactor,
    redactor,
    request_id_var,
)


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_structured_fields_and_request_id() -> None:
    token = request_id_var.set("req-123")
    try:
        line = JsonFormatter().format(_record("Request completed", status=200, path="/x"))
    finally:
        request_id_var.reset(token)
    payload = json.loads(line)
    assert payload["message"] == "Request completed"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-123"
    assert payload["status"] == 200
    assert payload["path"] == "/x"
    assert payload["time"].endswith("Z")


def test_console_formatter_includes_fields() -> None:
    line = ConsoleFormatter().format(_record("hello", status=201))
    assert "hello" in line
    assert "status=201" in line


def test_redactor_masks_registered_values_and_token_patterns() -> None:
    local = SecretRedactor()
    local.register("my-super-secret-value")
    text = local.redact(
        "key my-super-secret-value; Authorization: Bearer abcdefghijklmnop; "
        "sk-ABCDEFGHIJKLMNOPQRSTUV; api_key=hunter2hunter2"
    )
    assert "my-super-secret-value" not in text
    assert "abcdefghijklmnop" not in text
    assert "ABCDEFGHIJKLMNOPQRSTUV" not in text
    assert "hunter2hunter2" not in text


def test_formatters_redact_secrets_in_messages_and_fields() -> None:
    redactor.register("registered-secret-123")
    line = JsonFormatter().format(
        _record("calling provider with registered-secret-123", header="Bearer zzzzzzzzzzzz")
    )
    assert "registered-secret-123" not in line
    assert "zzzzzzzzzzzz" not in line

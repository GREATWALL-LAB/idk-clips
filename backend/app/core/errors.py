"""Centralized error types and handlers.

Every error response has the same envelope::

    {"error": {"code": "not_found", "message": "...", "details": [...], "request_id": "..."}}

Messages are written for end users. Stack traces, file paths and internal
details are logged on the server and never returned to clients.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for errors that are safe to show to users."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    default_message = "The request could not be processed."


class AuthenticationError(AppError):
    status_code = 401
    code = "not_authenticated"
    default_message = "Please sign in to continue."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to do this."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with the current state of the resource."


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    default_message = "The uploaded file is too large."


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_media_type"
    default_message = "This file type is not supported."


class UnprocessableError(AppError):
    status_code = 422
    code = "unprocessable"
    default_message = "The request was understood but cannot be processed."


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests. Please wait a moment and try again."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    default_message = "A required service is unavailable."


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    416: "range_not_satisfiable",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}

_FRIENDLY_MESSAGES = {
    404: "The requested resource was not found.",
    405: "This HTTP method is not allowed for this endpoint.",
}

INTERNAL_ERROR_MESSAGE = "An unexpected error occurred. It has been logged on the server."


def error_body(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    request_id = request_id_var.get()
    if request_id:
        error["request_id"] = request_id
    return {"error": error}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content=error_body(code, message, details), headers=headers
    )


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # pragma: no cover - registered for AppError only
        raise exc
    log = logger.error if exc.status_code >= 500 else logger.info
    log("Request failed", extra={"error_code": exc.code, "status": exc.status_code})
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    details = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", ()))
        # The rejected input is deliberately not echoed back (it may be large or sensitive).
        details.append(
            {
                "field": location,
                "message": err.get("msg", "Invalid value."),
                "type": err.get("type"),
            }
        )
    return error_response(422, "validation_error", "Some request fields are invalid.", details)


def _status_phrase(status_code: int) -> str | None:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return None


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    detail = exc.detail if isinstance(exc.detail, str) else None
    default_phrase = _status_phrase(exc.status_code)
    if not detail or detail == default_phrase:
        message = _FRIENDLY_MESSAGES.get(exc.status_code, default_phrase or "Request failed.")
    else:
        message = detail
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)

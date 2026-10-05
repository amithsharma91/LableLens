"""API error model (Stage 11).

Every expected failure returns the spec envelope
``{"error": {"code", "message", "details"}, "meta": {...}}`` with
the request ID attached. Domain exceptions map here in one place;
unexpected exceptions become generic 500s with no internals leaked
(no stack traces, SQL text, provider payloads, or credentials).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.common import ErrorDetail, ErrorResponse, MetaResponse

__all__ = [
    "ApiError",
    "RequestIdMiddleware",
    "register_handlers",
    "error_body",
]

logger = logging.getLogger("labellens.api")


class ApiError(Exception):
    """Expected API failure with a controlled code and HTTP status."""

    def __init__(
        self, status: int, code: str, message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value or "unknown"


def error_body(
    request: Request, status: int, code: str, message: str,
    details: dict | None = None,
) -> dict:
    """Spec-shaped error payload (safe to serialize)."""
    return ErrorResponse(
        error=ErrorDetail(
            code=code, message=message, details=details or {}),
        meta=MetaResponse(request_id=_request_id(request)),
    ).model_dump()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach/propagate a request correlation ID (never secrets)."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "").strip()
        request_id = incoming[:64] if incoming else str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _log_outcome(
    request: Request, status: int, code: str, subject: str = "-"
) -> None:
    logger.info(
        "%s %s -> %d %s subject=%s request_id=%s",
        request.method,
        request.url.path,
        status,
        code,
        subject,
        _request_id(request),
    )


def register_handlers(app: FastAPI) -> None:
    """Wire envelope handlers (validation, HTTP, API, fallback)."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: Exception):
        _log_outcome(request, 422, "VALIDATION_ERROR")
        return JSONResponse(
            status_code=422,
            content=error_body(
                request, 422, "VALIDATION_ERROR",
                "request validation failed"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN",
                 404: "NOT_FOUND", 429: "RATE_LIMITED",
                 503: "SERVICE_UNAVAILABLE"}
        code = codes.get(exc.status_code, "INTERNAL_ERROR")
        status = exc.status_code if exc.status_code < 500 else 500
        _log_outcome(request, status, code)
        return JSONResponse(
            status_code=status,
            content=error_body(request, status, code, str(exc.detail)),
        )

    @app.exception_handler(ApiError)
    async def api_handler(request: Request, exc: ApiError):
        _log_outcome(request, exc.status, exc.code)
        headers = None
        retry_after = getattr(request.state, "rate_limit_retry_after", None)
        if exc.status == 429 and retry_after:
            headers = {"Retry-After": str(int(retry_after))}
        return JSONResponse(
            status_code=exc.status,
            content=error_body(
                request, exc.status, exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception):
        logger.error(
            "%s %s -> 500 INTERNAL_ERROR request_id=%s error_category=%s",
            request.method, request.url.path, _request_id(request),
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=error_body(
                request, 500, "INTERNAL_ERROR", "unexpected error"),
        )


__all__ = [
    "ApiError",
    "RequestIdMiddleware",
    "register_handlers",
    "error_body",
    "ERROR_RESPONSES",
]

ERROR_RESPONSES = {
    400: {"description": "Bad request", "model": ErrorResponse},
    401: {"description": "Unauthenticated", "model": ErrorResponse},
    403: {"description": "Forbidden", "model": ErrorResponse},
    404: {"description": "Not found", "model": ErrorResponse},
    409: {"description": "Conflict", "model": ErrorResponse},
    422: {"description": "Validation error", "model": ErrorResponse},
    429: {"description": "Rate limited", "model": ErrorResponse},
    500: {"description": "Internal error", "model": ErrorResponse},
    503: {"description": "Dependency unavailable", "model": ErrorResponse},
}

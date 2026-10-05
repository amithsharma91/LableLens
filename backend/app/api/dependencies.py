"""Shared FastAPI dependencies.

The only dependency routes declare is the service bundle that
:class:`~app.main.ServiceScopeMiddleware` binds to `request.state`.
It is resolved here -- never constructed here -- so routes contain no
wiring and no business logic.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from starlette.requests import Request

from app.api.errors import ApiError

__all__ = ["services", "observation_service", "review_service"]


def services(request: Request) -> SimpleNamespace:
    """Return the request-scoped service bundle.

    Raises a controlled 500 when the application was assembled without
    a repository boundary (no `repos`/`engine`), which keeps the failure
    explicit instead of surfacing an AttributeError.
    """
    bundle: Optional[SimpleNamespace] = getattr(
        request.state, "services", None)
    if bundle is None:
        raise ApiError(
            500, "INTERNAL_ERROR", "service layer not configured")
    return bundle


def observation_service(request: Request):
    """The request-scoped observation service."""
    return services(request).observations


def review_service(request: Request):
    """The request-scoped review service."""
    return services(request).reviews

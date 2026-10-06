"""Shared service-layer exceptions (API mapping boundary).

Repositories raise storage-oriented errors (KeyError, PermissionError,
implementation-specific conflicts); services translate them once,
here, into stable domain errors the API maps to HTTP statuses.
Messages are safe for client display (no internals, no secrets).
"""

from __future__ import annotations

__all__ = [
    "ConflictError",
    "NotFoundError",
    "StaleError",
    "ForbiddenError",
    "MissingEntityError",
    "ServiceError",
]


class ServiceError(Exception):
    """Base class for expected service failures (never 500s)."""


class ConflictError(ServiceError, ValueError):
    """Concurrent modification or duplicate active state (HTTP 409)."""


class NotFoundError(ServiceError, KeyError):
    """Referenced record does not exist (HTTP 404)."""


def require_owner_match(row_owner, owner, *, resource="record") -> None:
    """Refuse foreign owned rows as not-found (anti-enumeration).

    `owner` is the authenticated caller (None = internal/legacy
    caller, no check). Rows without an owner predate ownership and
    keep legacy readability. Anything else that mismatches answers
    exactly like a missing row so callers cannot probe for it.
    """
    if owner is not None and row_owner is not None and row_owner != owner:
        raise NotFoundError("%s not found" % resource)


class StaleError(ServiceError, ValueError):
    """Evidence changed since the operation's basis (HTTP 409)."""


class ForbiddenError(ServiceError, PermissionError):
    """Caller lacks permission (HTTP 403)."""


class MissingEntityError(ServiceError, ValueError):
    """A decision names a canonical entity that is not registered.

    Claims carry a foreign key to `chemical_entities`; the service
    checks existence first so the failure surfaces as a controlled
    error instead of an opaque integrity violation (HTTP 422).
    """

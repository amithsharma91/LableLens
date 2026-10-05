"""Authentication boundary (Stage 11 API).

A bearer token establishes a typed request principal
(subject + role). Identity always comes from the verified token,
never from client-supplied fields. The verifier is an interface:
tests and development use an explicit static map, while Supabase
JWT verification remains the documented production path (not
implemented here -- no Supabase Auth dependency exists yet).

Roles: "authenticated" (reads + observation creation) and
"reviewer" (review claim/decision). Subjects are restricted to a
safe charset so they can be embedded in audit actor strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Tuple

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ApiError

__all__ = [
    "Principal",
    "TokenVerifier",
    "StaticTokenVerifier",
    "ROLE_AUTHENTICATED",
    "ROLE_REVIEWER",
    "get_principal",
    "require_reviewer",
]

ROLE_AUTHENTICATED = "authenticated"
ROLE_REVIEWER = "reviewer"

_SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Authenticated request identity (never client-asserted)."""

    subject: str
    role: str

    @property
    def reviewer_id(self) -> str:
        """Audit actor string derived from authentication."""
        return "human:%s" % self.subject


class TokenVerifier(Protocol):
    """Maps a bearer token to a principal (or rejects it)."""

    def verify(self, token: str) -> Principal:
        """Return the principal or raise NotAuthenticated."""


class NotAuthenticated(Exception):
    """Token missing, malformed, unknown, or unverifiable."""


class StaticTokenVerifier:
    """Explicit token map (development/tests only, never production).

    Production must use Supabase JWT verification (documented future);
    this map exists so the auth boundary is fully testable offline.
    """

    def __init__(self, tokens: Dict[str, Tuple[str, str]]) -> None:
        self._tokens = dict(tokens)

    def verify(self, token: str) -> Principal:
        try:
            subject, role = self._tokens[token]
        except KeyError:
            raise NotAuthenticated("unknown token")
        if not _SUBJECT_RE.match(subject):
            raise NotAuthenticated("invalid subject")
        if role not in (ROLE_AUTHENTICATED, ROLE_REVIEWER):
            raise NotAuthenticated("invalid role")
        return Principal(subject=subject, role=role)


def _verifier_from_app(request: Request):
    """Resolve the configured verifier (duck-typed, never permissive)."""
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        return None
    if callable(getattr(verifier, "verify", None)):
        return verifier
    return None


async def get_principal(request: Request) -> Principal:
    """Bearer -> Principal. Missing/malformed/unknown token: 401."""
    credentials: Optional[HTTPAuthorizationCredentials] = None
    try:
        credentials = await _bearer_scheme(request)
    except Exception:
        credentials = None
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "UNAUTHORIZED", "authentication required")
    token = (credentials.credentials or "").strip()
    if not token or len(token) > 512:
        raise ApiError(401, "UNAUTHORIZED", "authentication required")
    verifier = _verifier_from_app(request)
    if verifier is None:
        raise ApiError(401, "UNAUTHORIZED", "authentication required")
    try:
        return verifier.verify(token)
    except NotAuthenticated:
        raise ApiError(401, "UNAUTHORIZED", "authentication required")


async def require_reviewer(
    principal: Principal = Depends(get_principal),
) -> Principal:
    """Reviewer role required; anything else: 403."""
    if principal.role != ROLE_REVIEWER:
        raise ApiError(403, "FORBIDDEN", "reviewer role required")
    return principal


async def require_authenticated(
    principal: Principal = Depends(get_principal),
) -> Principal:
    """Any authenticated principal (explicit dependency for clarity)."""
    return principal

"""Authentication boundary (Stage 11 API, hardened in Stage 12).

A bearer token establishes a typed request principal
(subject + role). Identity always comes from the verified token,
never from client-supplied fields.

The verifier is an interface. Two implementations ship:

* :class:`StaticTokenVerifier` -- an explicit token map for local
  development and offline tests. It is refused outright when
  ``ENVIRONMENT=production``; there is no silent fallback.
* :class:`app.api.supabase_jwt.SupabaseJWTVerifier` -- production
  verification of Supabase access tokens against the project JWKS
  (signature, issuer, audience, expiry, not-before, subject).

Roles: "authenticated" (reads + observation creation) and
"reviewer" (review claim/decision). Subjects are restricted to a
safe charset so they can be embedded in audit actor strings.

Authentication failures are deliberately indistinguishable from the
outside: unknown, expired, mis-signed, malformed, wrong-issuer, and
wrong-audience tokens all produce the same public 401. The specific
reason is kept as an internal diagnostic and logged without token
material.
"""

from __future__ import annotations

import logging
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
    "require_authenticated",
    "require_reviewer",
    "build_token_verifier",
]

logger = logging.getLogger("labellens.auth")

ROLE_AUTHENTICATED = "authenticated"
ROLE_REVIEWER = "reviewer"

# Token length bound. A Supabase access token is well under 2 KB;
# anything far larger is refused before parsing.
MAX_TOKEN_CHARS = 4096

_SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Authenticated request identity (never client-asserted).

    Carries only trusted material: the verified subject, the derived
    role, and non-sensitive token metadata (key id, issuer, expiry)
    useful for diagnostics. No email, phone, or raw token/payload is
    retained.
    """

    subject: str
    role: str
    verifier: str = "unspecified"
    token_id: Optional[str] = None
    issuer: Optional[str] = None
    expires_at: Optional[int] = None

    @property
    def reviewer_id(self) -> str:
        """Audit actor string derived from authentication."""
        return "human:%s" % self.subject


class TokenVerifier(Protocol):
    """Maps a bearer token to a principal (or rejects it).

    ``verify`` is async because the production verifier performs
    network I/O (JWKS retrieval) before a token can be trusted.
    """

    async def verify(self, token: str) -> Principal:
        """Return the principal or raise NotAuthenticated/AuthFailure."""


class NotAuthenticated(Exception):
    """Token missing, malformed, unknown, or unverifiable."""


class StaticTokenVerifier:
    """Explicit token map (development/tests only, never production).

    ``build_token_verifier`` refuses to construct this in a production
    environment; a development server that receives real Supabase
    tokens is instead wired to the Supabase verifier.
    """

    def __init__(self, tokens: Dict[str, Tuple[str, str]]) -> None:
        self._tokens = dict(tokens)

    async def verify(self, token: str) -> Principal:
        try:
            subject, role = self._tokens[token]
        except KeyError:
            raise NotAuthenticated("unknown token")
        if not _SUBJECT_RE.match(subject):
            raise NotAuthenticated("invalid subject")
        if role not in (ROLE_AUTHENTICATED, ROLE_REVIEWER):
            raise NotAuthenticated("invalid role")
        return Principal(subject=subject, role=role, verifier="static")


def parse_dev_tokens(raw: str) -> Dict[str, Tuple[str, str]]:
    """Parse ``token:subject:role`` entries (development only)."""
    mapping: Dict[str, Tuple[str, str]] = {}
    for entry in raw.split(","):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) == 3 and all(parts):
            token, subject, role = parts
            mapping[token] = (subject, role)
    return mapping


def build_token_verifier(
    config,
    *,
    jwks_client=None,
    clock=None,
):
    """Resolve the configured verifier; fail closed in production.

    Production requires a fully configured Supabase verifier: no
    configured issuer/JWKS endpoint, or any configured static dev
    token, raises instead of degrading to a weaker boundary.
    """
    from app.api.jwks import JWKSCache
    from app.api.supabase_jwt import SupabaseJWTVerifier

    dev_tokens = (config.dev_api_tokens or "").strip()
    if config.is_production:
        if dev_tokens:
            raise RuntimeError(
                "DEV_API_TOKENS must not be configured when "
                "ENVIRONMENT=production")
        if not config.supabase_configured:
            raise RuntimeError(
                "Supabase JWT verification is not configured "
                "(SUPABASE_URL or SUPABASE_JWT_ISSUER required)")
        if not config.jwt_algorithms:
            raise RuntimeError(
                "no JWT verification algorithm configured")

    if config.supabase_configured:
        cache = JWKSCache(
            config.supabase_jwt_jwks_url,
            ttl_seconds=config.supabase_jwt_jwks_ttl_seconds,
            min_refresh_seconds=config.supabase_jwt_jwks_min_refresh_seconds,
            max_keys=config.supabase_jwt_jwks_max_keys,
            timeout_seconds=config.supabase_jwt_fetch_timeout_seconds,
            allowed_algorithms=config.jwt_algorithms,
            client=jwks_client,
        )
        if dev_tokens:
            logger.warning(
                "static development tokens configured but ignored: "
                "Supabase JWT verification is active")
        return SupabaseJWTVerifier(
            jwks=cache,
            issuer=config.supabase_jwt_issuer,
            audiences=config.jwt_audiences,
            algorithms=config.jwt_algorithms,
            leeway_seconds=config.supabase_jwt_leeway_seconds,
            reviewer_subjects=config.reviewer_subjects,
            clock=clock,
        )

    if dev_tokens:
        return StaticTokenVerifier(parse_dev_tokens(dev_tokens))
    return None


def _verifier_from_app(request: Request):
    """Resolve the configured verifier (duck-typed, never permissive)."""
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        return None
    if callable(getattr(verifier, "verify", None)):
        return verifier
    return None


def _reject_auth(request: Request, reason: str) -> ApiError:
    """One public failure shape, internal reason kept out of the body."""
    logger.info(
        "authentication rejected reason=%s request_id=%s path=%s",
        reason,
        getattr(request.state, "request_id", "unknown"),
        request.url.path,
    )
    return ApiError(401, "UNAUTHORIZED", "authentication required")


async def get_principal(request: Request) -> Principal:
    """Bearer -> Principal. Missing/malformed/unknown token: 401."""
    from app.api.supabase_jwt import AuthFailure

    credentials: Optional[HTTPAuthorizationCredentials] = None
    try:
        credentials = await _bearer_scheme(request)
    except Exception:
        credentials = None
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _reject_auth(request, "no_bearer_credentials")
    token = (credentials.credentials or "").strip()
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise _reject_auth(request, "token_absent_or_oversized")
    verifier = _verifier_from_app(request)
    if verifier is None:
        raise _reject_auth(request, "no_verifier_configured")
    try:
        return await verifier.verify(token)
    except NotAuthenticated:
        raise _reject_auth(request, "unknown_token")
    except AuthFailure as exc:
        raise _reject_auth(request, exc.reason)
    except Exception as exc:
        # Unexpected verifier failure: still an authentication
        # failure, logged by category only.
        logger.error(
            "verifier failure request_id=%s category=%s",
            getattr(request.state, "request_id", "unknown"),
            type(exc).__name__,
        )
        raise _reject_auth(request, "verifier_error")


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

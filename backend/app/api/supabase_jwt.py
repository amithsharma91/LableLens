"""Supabase access-token verification (production identity).

Follows the current Supabase signing model
(supabase.com/docs/guides/auth/jwts and /guides/auth/signing-keys):

* public keys come from the project's JWKS document;
* the token's ``kid`` selects the key;
* ``iss``/``aud``/``exp``/``nbf``/``sub`` are verified, and the
  signature is always verified -- there is no decode-only path.

Every rejection collapses to one public authentication failure; the
specific reason exists only as an internal diagnostic string that is
never returned to the client and never carries token material.

Symmetric (HS256) verification is intentionally unsupported: Supabase
publishes no keys for symmetric projects and documents shared-secret
verification as not recommended.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Optional, Tuple

import jwt
from jwt import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
    PyJWTError,
)

from app.api.jwks import JWKSUnavailable, JWKSCache

__all__ = ["SupabaseJWTVerifier", "AuthFailure"]

# Supabase `role` claim values that are PostgreSQL roles, not user
# identities. `service_role` and friends must never authenticate as a
# person: that credential belongs to the backend only.
PRIVILEGED_ROLES = frozenset({
    "service_role", "service_role_backend", "supabase_admin",
    "supabase_auth_admin", "supabase_storage_admin", "postgres",
    "anon", "authenticated_api",
})
ALLOWED_ROLES = frozenset({"authenticated"})

_SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class AuthFailure(Exception):
    """Internal authentication failure with a non-sensitive reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SupabaseJWTVerifier:
    """Verify Supabase-issued access tokens against the project JWKS."""

    verifier_id = "supabase_jwks"

    def __init__(
        self,
        *,
        jwks: JWKSCache,
        issuer: str,
        audiences: Tuple[str, ...] = ("authenticated",),
        algorithms: Tuple[str, ...] = ("ES256", "RS256"),
        leeway_seconds: int = 60,
        reviewer_subjects: frozenset = frozenset(),
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if not issuer:
            raise AuthFailure("issuer is not configured")
        if not algorithms:
            raise AuthFailure("no verification algorithm configured")
        self._jwks = jwks
        self._issuer = issuer
        self._audiences = tuple(audiences)
        self._algorithms = tuple(algorithms)
        self._leeway = max(0, int(leeway_seconds))
        self._reviewer_subjects = frozenset(reviewer_subjects)
        self._clock = clock

    @property
    def audience_required(self) -> bool:
        return bool(self._audiences)

    async def verify(self, token: str) -> "object":
        """Return a Principal or raise :class:`AuthFailure`."""
        from app.api.auth import Principal  # local import: cycle-free

        header = self._read_header(token)
        kid = header.get("kid")
        alg = header.get("alg")
        try:
            key = await self._jwks.get_key(
                kid if isinstance(kid, str) else None,
                alg if isinstance(alg, str) else "",
            )
        except JWKSUnavailable as exc:
            raise AuthFailure(str(exc))
        options = {
            "require": ["exp", "iss", "sub"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "verify_iss": True,
            "verify_aud": self.audience_required,
            "verify_sub": True,
        }
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(self._algorithms),
                audience=list(self._audiences) if self._audiences else None,
                issuer=self._issuer,
                leeway=self._leeway,
                options=options,
            )
        except MissingRequiredClaimError as exc:
            raise AuthFailure("missing claim: %s" % exc.claim)
        except ExpiredSignatureError:
            raise AuthFailure("token expired")
        except ImmatureSignatureError:
            raise AuthFailure("token not yet valid")
        except InvalidAudienceError:
            raise AuthFailure("wrong audience")
        except InvalidIssuerError:
            raise AuthFailure("wrong issuer")
        except InvalidSignatureError:
            raise AuthFailure("invalid signature")
        except InvalidTokenError as exc:
            raise AuthFailure("invalid token: %s" % type(exc).__name__)
        except PyJWTError as exc:  # defensive: never leak the message
            raise AuthFailure("verification failed: %s" % type(exc).__name__)

        subject = claims.get("sub")
        if not isinstance(subject, str) or not _SUBJECT_RE.match(subject):
            raise AuthFailure("invalid subject")
        role_claim = claims.get("role")
        if role_claim is None:
            role_claim = "authenticated"
        if not isinstance(role_claim, str):
            raise AuthFailure("invalid role claim")
        if role_claim in PRIVILEGED_ROLES:
            # A service/anon credential is not a person. Refuse rather
            # than silently downgrade it to a user identity.
            raise AuthFailure("privileged role claim")
        if role_claim not in ALLOWED_ROLES:
            raise AuthFailure("role claim not permitted")
        role = (
            "reviewer" if subject in self._reviewer_subjects
            else "authenticated"
        )
        expires_at = claims.get("exp")
        return Principal(
            subject=subject,
            role=role,
            token_id=kid if isinstance(kid, str) else None,
            issuer=self._issuer,
            expires_at=int(expires_at) if isinstance(expires_at, int) else None,
        )

    @staticmethod
    def _read_header(token: str) -> Dict[str, object]:
        try:
            return jwt.get_unverified_header(token)
        except PyJWTError as exc:
            raise AuthFailure("malformed token: %s" % type(exc).__name__)

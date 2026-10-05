"""JSON Web Key Set handling for Supabase JWT verification.

Implements what Supabase documents for third-party verifiers
(supabase.com/docs/guides/auth/jwts, /guides/auth/signing-keys):

* the trusted public keys live at
  ``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``;
* a key is selected by the token header's ``kid``;
* the Supabase edge caches that document for 10 minutes, so this
  cache stays strictly shorter and refreshes when it sees an unknown
  ``kid`` (key rotation), subject to a minimum interval that bounds
  the work an attacker can trigger with random key ids.

The cache holds public material only. Private keys and shared
secrets never reach this process, and symmetric (HS256) verification
is deliberately unsupported: Supabase serves no keys for symmetric
projects and documents symmetric verification as not recommended, so
such deployments fail closed here rather than accepting a token
signed with a secret.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Callable, Dict, Optional, Tuple

import httpx
import jwt

__all__ = ["JWKSUnavailable", "JWKSCache"]

# Bounds for an untrusted-but-official document.
MAX_JWKS_BYTES = 65_536
MAX_KEYS = 16
MIN_ALLOWED_ALGS = ("ES256", "RS256", "ES384", "ES512", "RS384", "RS512")
ALLOWED_KEY_TYPES = ("EC", "RSA", "OKP")


class JWKSUnavailable(Exception):
    """The key set could not be retrieved or trusted."""


def _now() -> float:
    return time.monotonic()


class JWKSCache:
    """Bounded, refresh-on-miss cache of JWKS public keys."""

    def __init__(
        self,
        url: str,
        *,
        ttl_seconds: int = 300,
        min_refresh_seconds: int = 30,
        max_keys: int = MAX_KEYS,
        timeout_seconds: float = 5.0,
        allowed_algorithms: Optional[Tuple[str, ...]] = None,
        client: Optional[httpx.AsyncClient] = None,
        clock: Callable[[], float] = _now,
    ) -> None:
        if not url.lower().startswith("https://"):
            # No plaintext transport for key material: a MITM could
            # otherwise mint its own trusted keys.
            raise JWKSUnavailable("JWKS URL must use https")
        self._url = url
        self._ttl = max(1, int(ttl_seconds))
        self._min_refresh = max(0, int(min_refresh_seconds))
        self._max_keys = max(1, min(int(max_keys), MAX_KEYS))
        self._timeout = float(timeout_seconds)
        self._algorithms = tuple(allowed_algorithms or MIN_ALLOWED_ALGS)
        self._clock = clock
        self._client = client
        self._owns_client = client is None
        self._keys: Dict[str, dict] = {}
        self._fetched_at: Optional[float] = None
        self._last_attempt: Optional[float] = None
        self._lock = asyncio.Lock()

    # -- public API ------------------------------------------------------

    async def get_key(self, kid: Optional[str], alg: str) -> dict:
        """Return one JWK for ``kid``/``alg``, refreshing when stale.

        Raises :class:`JWKSUnavailable` when the key cannot be
        trusted. An unknown key id triggers at most one refresh per
        minimum-refresh interval, so random ids cannot be used to
        hammer the endpoint.
        """
        if not kid:
            raise JWKSUnavailable("token header has no kid")
        if alg not in self._algorithms:
            raise JWKSUnavailable("algorithm not allowed")
        if not self._is_stale():
            entry = self._peek(kid)
            if entry is not None:
                return self._cryptography_key(entry, alg)
        async with self._lock:
            if not self._is_stale():
                entry = self._peek(kid)
                if entry is not None:
                    return self._cryptography_key(entry, alg)
            now = self._clock()
            # The cooldown also covers a *failed* fetch: a key set that
            # cannot be retrieved must not turn into an unlimited
            # refetch loop driven by unknown key ids.
            cooled = (
                self._last_attempt is None
                or (now - self._last_attempt) >= self._min_refresh
            )
            if not cooled:
                raise JWKSUnavailable("unknown key id")
            await self._refresh()
            entry = self._peek(kid)
            if entry is None:
                raise JWKSUnavailable("unknown key id")
            return self._cryptography_key(entry, alg)

    @staticmethod
    def _cryptography_key(entry: dict, alg: str):
        """Convert a validated JWK into a usable public key object.

        PyJWK performs the curve/algorithm binding and refuses
        mismatches, so a key published for one algorithm cannot verify
        a token signed with another.
        """
        try:
            return jwt.PyJWK(entry, algorithm=alg).key
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise JWKSUnavailable(
                "key %s unusable: %s" % (type(exc).__name__, ""))

    async def aclose(self) -> None:
        """Release an owned HTTP client."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- internals -------------------------------------------------------

    def _peek(self, kid: str) -> Optional[dict]:
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        """True when no fetch has happened yet or the TTL elapsed."""
        if self._fetched_at is None:
            return True
        return (self._clock() - self._fetched_at) >= self._ttl

    def _client_or_new(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
            )
        return self._client

    async def _fetch(self) -> dict:
        client = self._client_or_new()
        try:
            response = await client.get(
                self._url, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise JWKSUnavailable("key set unreachable: %s" % type(exc).__name__)
        if response.status_code != 200:
            raise JWKSUnavailable(
                "key set returned HTTP %d" % response.status_code)
        body = response.content
        if len(body) > MAX_JWKS_BYTES:
            raise JWKSUnavailable("key set exceeds size bound")
        try:
            payload = json.loads(body)
        except ValueError:
            raise JWKSUnavailable("key set is not valid JSON")
        if not isinstance(payload, dict):
            raise JWKSUnavailable("key set must be an object")
        keys = payload.get("keys")
        if not isinstance(keys, list) or not keys:
            # Expected for symmetric-secret projects: no asymmetric
            # keys are published. Fail closed.
            raise JWKSUnavailable("key set contains no keys")
        if len(keys) > self._max_keys:
            raise JWKSUnavailable("key set exceeds key bound")
        return payload

    def _validate(self, payload: dict) -> Dict[str, dict]:
        accepted: Dict[str, dict] = {}
        for entry in payload["keys"]:
            if not isinstance(entry, dict):
                continue
            kid = entry.get("kid")
            alg = entry.get("alg")
            kty = entry.get("kty")
            if not isinstance(kid, str) or not kid or len(kid) > 200:
                continue
            if kty not in ALLOWED_KEY_TYPES:
                continue
            use = entry.get("use")
            if use is not None and use != "sig":
                continue
            key_ops = entry.get("key_ops")
            if isinstance(key_ops, list) and "verify" not in key_ops:
                continue
            if isinstance(alg, str) and alg:
                # Advertised algorithm must be configured as allowed.
                if alg.upper() not in self._algorithms:
                    continue
                accepted[kid] = entry
                continue
            # No advertised algorithm: accept only for key types whose
            # algorithm family is allowed by configuration.
            if kty == "EC" and "ES256" in self._algorithms:
                accepted[kid] = entry
            elif kty == "RSA" and any(
                item.startswith("RS") for item in self._algorithms
            ):
                accepted[kid] = entry
        if not accepted:
            raise JWKSUnavailable("no usable key in key set")
        return accepted

    async def _refresh(self) -> None:
        self._last_attempt = self._clock()
        payload = await self._fetch()
        validated = self._validate(payload)
        self._keys = dict(list(validated.items())[: self._max_keys])
        self._fetched_at = self._clock()

    @property
    def key_ids(self) -> Tuple[str, ...]:
        """Cached key ids (diagnostics only)."""
        return tuple(sorted(self._keys))

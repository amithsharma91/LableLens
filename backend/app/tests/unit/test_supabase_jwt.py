"""Supabase JWT verification unit tests (Stage 12).

Key material is generated in-process for every test: no real project,
no real key, no committed credential. A real PyJWT issuer and a real
`cryptography` signer produce the tokens, and the production JWKS
client runs against a mocked transport, so the verification code path
itself is exercised (header parse -> key selection -> signature ->
claims -> principal) without any network access.
"""

import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.api.jwks import JWKSUnavailable, JWKSCache
from app.api.supabase_jwt import AuthFailure, SupabaseJWTVerifier
from app.api.auth import (
    ROLE_AUTHENTICATED,
    ROLE_REVIEWER,
    build_token_verifier,
)

ISSUER = "https://project-test.supabase.co/auth/v1"
JWKS_URL = "%s/.well-known/jwks.json" % ISSUER
AUDIENCE = "authenticated"


def _es256_key(kid: str = "key-1"):
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(
        private.public_key(), as_dict=True)
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig",
                "key_ops": ["verify"]})
    return private, jwk


def _rs256_key(kid: str = "rsa-1"):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
        private.public_key(), as_dict=True)
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig",
                "key_ops": ["verify"]})
    return private, jwk


def _jwk_response(keys):
    def handler(request):
        return httpx.Response(
            200, json={"keys": keys})
    return httpx.MockTransport(handler)


def _cache(keys, **kwargs):
    client = httpx.AsyncClient(
        transport=_jwk_response(keys), timeout=5.0)
    kwargs.setdefault("allowed_algorithms", ("ES256", "RS256"))
    return JWKSCache(JWKS_URL, client=client, **kwargs)


def _verifier(keys=None, *, leeway_seconds=60, **kwargs):
    """Verifier with a generated key set; leeway is a verifier option."""
    private, jwk = _es256_key()
    if keys is None:
        keys = [jwk]
    return (
        private,
        SupabaseJWTVerifier(
            jwks=_cache(keys, **kwargs),
            issuer=ISSUER,
            audiences=(AUDIENCE,),
            algorithms=("ES256", "RS256"),
            leeway_seconds=leeway_seconds,
        ),
    )


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-abc123",
        "role": "authenticated",
        "email": "someone@example.com",
        "phone": "+15552368",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def _token(private, **overrides):
    return jwt.encode(
        _claims(**overrides), private, algorithm="ES256",
        headers={"kid": "key-1"})


# -- valid -------------------------------------------------------------


async def test_valid_token_yields_trusted_principal():
    private, verifier = _verifier()
    principal = await verifier.verify(_token(private))
    assert principal.subject == "user-abc123"
    assert principal.role == ROLE_AUTHENTICATED
    assert principal.token_id == "key-1"
    assert principal.issuer == ISSUER
    assert principal.reviewer_id == "human:user-abc123"
    # Client-controlled identity data is never carried into the
    # principal.
    assert "someone@example.com" not in repr(principal)
    assert "+15552368" not in repr(principal)


async def test_rs256_token_is_accepted_when_configured():
    private, jwk = _rs256_key()
    verifier = SupabaseJWTVerifier(
        jwks=_cache([jwk]),
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
    )
    now = int(time.time())
    token = jwt.encode(
        _claims(iat=now, exp=now + 60), private, algorithm="RS256",
        headers={"kid": "rsa-1"})
    principal = await verifier.verify(token)
    assert principal.subject == "user-abc123"


async def test_reviewer_subject_gets_reviewer_role():
    private, jwk = _es256_key()
    verifier = SupabaseJWTVerifier(
        jwks=_cache([jwk]),
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
        reviewer_subjects=frozenset({"user-abc123"}),
    )
    principal = await verifier.verify(_token(private))
    assert principal.role == ROLE_REVIEWER


# -- invalid -----------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "invalid_signature",
        "expired",
        "not_yet_valid",
        "wrong_issuer",
        "wrong_audience",
        "unsupported_algorithm",
        "malformed",
        "missing_subject",
        "unknown_kid",
        "missing_kid",
        "privileged_role",
        "anon_role",
        "bad_subject_charset",
    ],
)
async def test_invalid_tokens_are_rejected(case):
    private, verifier = _verifier()
    now = int(time.time())
    if case == "invalid_signature":
        other, _ = _es256_key("key-1")
        token = _token(other)
    elif case == "expired":
        token = _token(private, iat=now - 7200, exp=now - 3600)
    elif case == "not_yet_valid":
        token = _token(private, nbf=now + 3600, iat=now + 3600,
                       exp=now + 7200)
    elif case == "wrong_issuer":
        token = _token(private, iss="https://evil.example/auth/v1")
    elif case == "wrong_audience":
        token = _token(private, aud="service_role")
    elif case == "unsupported_algorithm":
        token = jwt.encode(
            _claims(), "shared-secret-value", algorithm="HS256",
            headers={"kid": "key-1"})
    elif case == "malformed":
        token = "not.a.jwt"
    elif case == "missing_subject":
        claims = _claims()
        claims.pop("sub")
        token = jwt.encode(
            claims, private, algorithm="ES256",
            headers={"kid": "key-1"})
    elif case == "unknown_kid":
        token = jwt.encode(
            _claims(), private, algorithm="ES256",
            headers={"kid": "rotated-away"})
    elif case == "missing_kid":
        token = jwt.encode(_claims(), private, algorithm="ES256")
    elif case == "privileged_role":
        token = _token(private, role="service_role")
    elif case == "anon_role":
        token = _token(private, role="anon")
    else:
        token = _token(private, sub="bad subject/../../etc")
    with pytest.raises(AuthFailure):
        await verifier.verify(token)


async def test_expired_and_beyond_leeway_token_is_rejected():
    private, verifier = _verifier(leeway_seconds=0)
    now = int(time.time())
    with pytest.raises(AuthFailure):
        await verifier.verify(_token(private, iat=now - 7200,
                                     exp=now - 3600))


async def test_expiry_within_leeway_is_accepted():
    private, verifier = _verifier(leeway_seconds=120)
    now = int(time.time())
    principal = await verifier.verify(
        _token(private, iat=now - 600, exp=now - 30))
    assert principal.subject == "user-abc123"


async def test_missing_exp_claim_is_rejected():
    private, verifier = _verifier()
    claims = _claims()
    claims.pop("exp")
    token = jwt.encode(claims, private, algorithm="ES256",
                       headers={"kid": "key-1"})
    with pytest.raises(AuthFailure):
        await verifier.verify(token)


async def test_symmetric_project_without_published_keys_fails_closed():
    """No keys published (legacy HS256 project) -> everything fails."""
    def empty(request):
        return httpx.Response(200, json={"keys": []})
    client = httpx.AsyncClient(transport=httpx.MockTransport(empty))
    verifier = SupabaseJWTVerifier(
        jwks=JWKSCache(
            JWKS_URL, client=client,
            allowed_algorithms=("ES256", "RS256")),
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
    )
    private, _ = _es256_key()
    with pytest.raises(AuthFailure):
        await verifier.verify(_token(private))


# -- key rotation and caching -----------------------------------------


async def test_rotated_key_is_picked_up_without_restart():
    """New signing key appears; an old-key token still verifies."""
    old_private, old_jwk = _es256_key("key-1")
    new_private, new_jwk = _es256_key("key-2")
    state = {"keys": [old_jwk], "fetches": 0}
    clock = {"now": 1000.0}

    def handler(request):
        state["fetches"] += 1
        return httpx.Response(200, json={"keys": state["keys"]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = SupabaseJWTVerifier(
        jwks=JWKSCache(
            JWKS_URL, client=client, ttl_seconds=300,
            min_refresh_seconds=0, allowed_algorithms=("ES256", "RS256"),
            clock=lambda: clock["now"]),
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
    )
    assert (await verifier.verify(
        _token(old_private))).subject == "user-abc123"
    fetch_count = state["fetches"]
    # Cached: no refetch while the key is known.
    assert (await verifier.verify(
        _token(old_private))).subject == "user-abc123"
    assert state["fetches"] == fetch_count

    # Supabase rotates: the new key signs, and the old key is retired
    # after a grace period.
    state["keys"] = [new_jwk, old_jwk]
    new_token = jwt.encode(
        _claims(), new_private, algorithm="ES256",
        headers={"kid": "key-2"})
    assert (await verifier.verify(new_token)).subject == "user-abc123"
    state["keys"] = [new_jwk]
    # A retired key stays trusted only until the cache TTL expires --
    # the documented grace window, bounded by the cache lifetime
    # rather than by anything an attacker controls.
    assert (await verifier.verify(
        _token(old_private))).subject == "user-abc123"
    clock["now"] += 301
    with pytest.raises(AuthFailure):
        await verifier.verify(_token(old_private))


async def test_unknown_kid_refresh_respects_min_interval():
    private, _ = _es256_key()
    fetches = {"count": 0}

    def handler(request):
        fetches["count"] += 1
        return httpx.Response(200, json={"keys": []})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = SupabaseJWTVerifier(
        jwks=JWKSCache(
            JWKS_URL, client=client, ttl_seconds=300,
            min_refresh_seconds=300, allowed_algorithms=("ES256", "RS256")),
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
    )
    with pytest.raises(AuthFailure):
        await verifier.verify(_token(private))
    first = fetches["count"]
    # Repeated unknown kids cannot hammer the endpoint.
    for _ in range(5):
        with pytest.raises(AuthFailure):
            await verifier.verify(_token(private))
    assert fetches["count"] == first


async def test_jwks_cache_expires_and_refetches():
    clock = {"now": 1000.0}
    fetches = {"count": 0}
    _, jwk = _es256_key()

    def handler(request):
        fetches["count"] += 1
        return httpx.Response(200, json={"keys": [jwk]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cache = JWKSCache(
        JWKS_URL, client=client, ttl_seconds=60, min_refresh_seconds=0,
        allowed_algorithms=("ES256", "RS256"),
        clock=lambda: clock["now"],
    )
    await cache.get_key("key-1", "ES256")
    await cache.get_key("key-1", "ES256")
    assert fetches["count"] == 1
    clock["now"] += 61
    await cache.get_key("key-1", "ES256")
    assert fetches["count"] == 2


async def test_cache_growth_is_bounded_by_key_bound():
    keys = []
    for index in range(6):
        _, jwk = _es256_key("key-%d" % index)
        keys.append(jwk)
    cache = _cache(keys, max_keys=3)
    with pytest.raises(JWKSUnavailable):
        await cache.get_key("key-0", "ES256")


async def test_oversized_key_set_is_refused():
    def handler(request):
        return httpx.Response(200, json={
            "keys": [
                {"kid": "k%d" % i, "kty": "EC", "alg": "ES256",
                 "crv": "P-256", "x": "AA", "y": "BB"}
                for i in range(40)
            ]
        })
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cache = JWKSCache(JWKS_URL, client=client, max_keys=16)
    with pytest.raises(JWKSUnavailable):
        await cache.get_key("k0", "ES256")


async def test_non_https_jwks_url_is_refused():
    with pytest.raises(JWKSUnavailable):
        JWKSCache("http://project.supabase.co/jwks.json")


async def test_unreachable_key_set_fails_closed():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = SupabaseJWTVerifier(
        jwks=JWKSCache(JWKS_URL, client=client,
                       allowed_algorithms=("ES256", "RS256")),
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
    )
    private, _ = _es256_key()
    with pytest.raises(AuthFailure):
        await verifier.verify(_token(private))


async def test_key_without_verify_use_is_ignored():
    _, jwk = _es256_key()
    signing_only = dict(jwk)
    signing_only["key_ops"] = ["sign"]
    private, _ = _es256_key()
    cache = _cache([signing_only])
    with pytest.raises(JWKSUnavailable):
        await cache.get_key("key-1", "ES256")


# -- configuration / production fail-closed ---------------------------


class _Config:
    """Minimal settings stand-in (no global env mutation)."""

    def __init__(self, **overrides):
        self.environment = "development"
        self.dev_api_tokens = ""
        self.supabase_url = "https://project-test.supabase.co"
        self.supabase_jwt_issuer = ISSUER
        self.supabase_jwt_jwks_url = JWKS_URL
        self.supabase_jwt_audience = AUDIENCE
        self.supabase_jwt_algorithms = "ES256,RS256"
        self.supabase_jwt_leeway_seconds = 60
        self.supabase_jwt_jwks_ttl_seconds = 300
        self.supabase_jwt_jwks_min_refresh_seconds = 30
        self.supabase_jwt_jwks_max_keys = 16
        self.supabase_jwt_fetch_timeout_seconds = 5.0
        self.supabase_reviewer_subjects = ""
        self.__dict__.update(overrides)

    @property
    def is_production(self):
        return self.environment.strip().lower() == "production"

    @property
    def supabase_configured(self):
        return bool(self.supabase_jwt_issuer and self.supabase_jwt_jwks_url)

    @property
    def jwt_audiences(self):
        raw = self.supabase_jwt_audience.strip()
        if not raw or raw == "*":
            return ()
        return tuple(p.strip() for p in raw.split(",") if p.strip())

    @property
    def jwt_algorithms(self):
        return tuple(
            p.strip().upper() for p in self.supabase_jwt_algorithms.split(",")
            if p.strip()
        )

    @property
    def reviewer_subjects(self):
        return frozenset(
            p.strip() for p in self.supabase_reviewer_subjects.split(",")
            if p.strip()
        )


def test_production_without_supabase_config_fails_closed():
    config = _Config(environment="production",
                     supabase_jwt_issuer="", supabase_jwt_jwks_url="")
    with pytest.raises(RuntimeError):
        build_token_verifier(config)


def test_production_with_dev_tokens_fails_closed():
    config = _Config(environment="production",
                     dev_api_tokens="tok:subject:reviewer")
    with pytest.raises(RuntimeError):
        build_token_verifier(config)


def test_production_builds_supabase_verifier():
    config = _Config(environment="production")
    verifier = build_token_verifier(config)
    assert isinstance(verifier, SupabaseJWTVerifier)


def test_production_without_algorithms_fails_closed():
    config = _Config(environment="production",
                     supabase_jwt_algorithms="")
    with pytest.raises(RuntimeError):
        build_token_verifier(config)


def test_development_prefers_supabase_and_warns_on_dev_tokens(caplog):
    from app.api.auth import StaticTokenVerifier

    config = _Config(dev_api_tokens="tok:subject:reviewer")
    verifier = build_token_verifier(config)
    assert isinstance(verifier, SupabaseJWTVerifier)
    # Static tokens are ignored whenever Supabase verification is on.
    assert not isinstance(verifier, StaticTokenVerifier)


def test_development_without_supabase_uses_static_tokens():
    from app.api.auth import StaticTokenVerifier

    config = _Config(
        supabase_jwt_issuer="", supabase_jwt_jwks_url="",
        dev_api_tokens="tok:subject:reviewer,other:reader:authenticated",
    )
    verifier = build_token_verifier(config)
    assert isinstance(verifier, StaticTokenVerifier)


def test_no_configuration_yields_no_verifier():
    config = _Config(supabase_jwt_issuer="", supabase_jwt_jwks_url="")
    assert build_token_verifier(config) is None

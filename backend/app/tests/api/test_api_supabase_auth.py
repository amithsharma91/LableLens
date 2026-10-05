"""HTTP coverage for production Supabase JWT authentication.

The application is built by the production factory with a Supabase
verifier whose JWKS client is backed by a mocked transport, so the
whole HTTP boundary -- bearer parsing, verification, principal
construction, uniform failure -- is exercised without a network or a
real project. Keys are generated per test; no credential is committed.
"""

import logging
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.api.auth import build_token_verifier
from app.api.jwks import JWKSCache
from app.api.supabase_jwt import SupabaseJWTVerifier
from app.main import create_app
from app.tests.api.helpers import register_snapshot_entities
from app.repositories.memory import MemoryUnitOfWork
from app.services.verification.adapters.snapshot import SnapshotAdapter

from app.tests.api.helpers import SNAPSHOT_PATH

ISSUER = "https://project-test.supabase.co/auth/v1"
JWKS_URL = "%s/.well-known/jwks.json" % ISSUER
AUDIENCE = "authenticated"
REVIEWER_SUBJECT = "reviewer-user"


def _keypair(kid="key-1"):
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(private.public_key(),
                                            as_dict=True)
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig",
                "key_ops": ["verify"]})
    return private, jwk


class _Jwks:
    """Mocked JWKS endpoint (in-process, no network)."""

    def __init__(self, keys, **cache_kwargs):
        self.keys = list(keys)
        self.fetches = 0
        cache_kwargs.setdefault("allowed_algorithms", ("ES256", "RS256"))
        self.cache = JWKSCache(JWKS_URL, client=self._client(),
                               **cache_kwargs)

    def _client(self):
        def handler(request):
            self.fetches += 1
            return httpx.Response(200, json={"keys": list(self.keys)})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-abc123",
        "role": "authenticated",
        "email": "someone@example.com",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def _make_client(jwks, **verifier_kwargs):
    verifier = SupabaseJWTVerifier(
        jwks=jwks.cache,
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
        reviewer_subjects=frozenset({REVIEWER_SUBJECT}),
        **verifier_kwargs,
    )
    uow = register_snapshot_entities(MemoryUnitOfWork())
    application = create_app(
        repos=uow,
        verifier=verifier,
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
    )
    return TestClient(application), uow


def _bearer(token):
    return {"Authorization": "Bearer %s" % token}


# -- valid -------------------------------------------------------------


def test_valid_token_reaches_a_protected_route():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    response = client.post("/api/v1/observations",
                           headers=_bearer(token),
                           json={"raw_text": "Ingredients: citric acid"})
    assert response.status_code == 201, response.text


def test_reviewer_subject_reaches_the_reviewer_route():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(sub=REVIEWER_SUBJECT), private,
                       algorithm="ES256", headers={"kid": "key-1"})
    # Claiming a review is reviewer-only; a non-existent id yields 404,
    # which proves the role gate passed rather than 403.
    response = client.post("/api/v1/reviews/r-missing/claim",
                           headers=_bearer(token))
    assert response.status_code == 404, response.text


def test_non_reviewer_is_forbidden_from_review_routes():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    response = client.post("/api/v1/reviews/r-missing/claim",
                           headers=_bearer(token))
    assert response.status_code == 403


# -- uniform failure ---------------------------------------------------


def _failure_cases(private, jwk, other_private):
    now = int(time.time())
    return {
        "unknown_token": "not-a-jwt",
        "malformed": "aaa.bbb.ccc",
        "invalid_signature": jwt.encode(
            _claims(), other_private, algorithm="ES256",
            headers={"kid": "key-1"}),
        "expired": jwt.encode(
            _claims(iat=now - 7200, exp=now - 3600), private,
            algorithm="ES256", headers={"kid": "key-1"}),
        "wrong_issuer": jwt.encode(
            _claims(iss="https://evil.example/auth/v1"), private,
            algorithm="ES256", headers={"kid": "key-1"}),
        "wrong_audience": jwt.encode(
            _claims(aud="service_role"), private, algorithm="ES256",
            headers={"kid": "key-1"}),
        "unknown_kid": jwt.encode(
            _claims(), private, algorithm="ES256",
            headers={"kid": "nope"}),
    }


def test_every_invalid_token_returns_an_identical_401():
    private, jwk = _keypair()
    other_private, _ = _keypair("key-1")
    client, _ = _make_client(_Jwks([jwk]))
    bodies = []
    for name, token in _failure_cases(private, jwk, other_private).items():
        response = client.post("/api/v1/observations",
                               headers=_bearer(token),
                               json={"raw_text": "Ingredients: water"})
        assert response.status_code == 401, name
        body = response.json()
        assert body["error"]["code"] == "UNAUTHORIZED"
        # Same public message for every failure category: no oracle.
        assert body["error"]["message"] == "authentication required"
        assert body["error"]["details"] == {}
        bodies.append((name, body["error"]))
    assert len({repr(item) for _, item in bodies}) == 1


def test_missing_authorization_header_is_401():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    response = client.post("/api/v1/observations",
                           json={"raw_text": "Ingredients: water"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_service_role_token_cannot_act_as_a_user():
    """The backend credential is not a person: 401, not a role."""
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(role="service_role"), private,
                       algorithm="ES256", headers={"kid": "key-1"})
    response = client.get("/api/v1/observations/%s" % (
        "11111111-1111-4111-8111-111111111111"), headers=_bearer(token))
    assert response.status_code == 401


def test_anon_token_is_rejected():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(role="anon"), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    response = client.get("/api/v1/reviews/pending", headers=_bearer(token))
    assert response.status_code == 401


# -- rotation ----------------------------------------------------------


def test_rotated_key_is_accepted_after_refresh():
    old_private, old_jwk = _keypair("key-1")
    new_private, new_jwk = _keypair("key-2")
    jwks = _Jwks([old_jwk], ttl_seconds=300, min_refresh_seconds=0)
    client, _ = _make_client(jwks)
    old_token = jwt.encode(_claims(), old_private, algorithm="ES256",
                           headers={"kid": "key-1"})
    assert client.post("/api/v1/observations", headers=_bearer(old_token),
                       json={"raw_text": "Ingredients: citric acid"}
                       ).status_code == 201

    # Supabase rotates to a new key.
    jwks.keys = [new_jwk, old_jwk]
    new_token = jwt.encode(_claims(), new_private, algorithm="ES256",
                           headers={"kid": "key-2"})
    assert client.post("/api/v1/observations", headers=_bearer(new_token),
                       json={"raw_text": "Ingredients: citric acid"}
                       ).status_code == 201
    assert jwks.fetches >= 2


# -- identity cannot be overridden -------------------------------------


def test_identity_headers_cannot_override_the_principal():
    private, jwk = _keypair()
    client, uow = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(sub="user-abc123"), private,
                       algorithm="ES256", headers={"kid": "key-1"})
    response = client.post(
        "/api/v1/observations",
        headers={**_bearer(token), "X-User-ID": "someone-else",
                 "X-Reviewer-ID": "someone-else"},
        json={"raw_text": "Ingredients: citric acid"},
    )
    assert response.status_code == 201, response.text
    assert "someone-else" not in repr(uow._store.tables)


def test_spoofed_identity_fields_in_the_body_are_rejected():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    response = client.post(
        "/api/v1/observations",
        headers=_bearer(token),
        json={"raw_text": "Ingredients: citric acid",
              "reviewer": "someone-else", "actor": "someone-else",
              "subject": "someone-else"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reviewer_body_field_is_rejected_by_validation():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(sub=REVIEWER_SUBJECT), private,
                       algorithm="ES256", headers={"kid": "key-1"})
    response = client.post(
        "/api/v1/reviews/r-missing/decision",
        headers=_bearer(token),
        json={"decision": "reject", "reason": "no", "reviewer": "mallory"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# -- no leakage --------------------------------------------------------


def test_token_never_appears_in_a_response_body():
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    response = client.post("/api/v1/observations", headers=_bearer(token),
                           json={"raw_text": "Ingredients: citric acid"})
    assert response.status_code == 201
    body = response.text
    assert token not in body
    assert "someone@example.com" not in body
    assert response.headers.get("authorization") is None


def test_token_and_claims_are_not_logged(caplog):
    private, jwk = _keypair()
    client, _ = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    with caplog.at_level(logging.DEBUG):
        bad = client.post("/api/v1/observations",
                          headers=_bearer(token + "tampered"),
                          json={"raw_text": "Ingredients: citric acid"})
    assert bad.status_code == 401
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in logged
    assert "someone@example.com" not in logged
    # An internal reason is logged; it names a failure category only.
    assert "authentication rejected reason=" in logged
    assert "tampered" not in logged


def test_token_is_not_persisted():
    private, jwk = _keypair()
    client, uow = _make_client(_Jwks([jwk]))
    token = jwt.encode(_claims(), private, algorithm="ES256",
                       headers={"kid": "key-1"})
    client.post("/api/v1/observations", headers=_bearer(token),
                json={"raw_text": "Ingredients: citric acid"})
    assert token not in repr(uow._store.tables)


# -- production configuration -----------------------------------------


def test_production_app_refuses_to_build_without_supabase(monkeypatch):
    """ENVIRONMENT=production with no verifier configuration fails."""
    from app import config as config_module
    from app import main as main_module

    production = config_module.Settings(
        environment="production",
        supabase_url="",
        supabase_jwt_issuer="",
        supabase_jwt_jwks_url="",
        dev_api_tokens="",
    )
    monkeypatch.setattr(main_module, "settings", production)
    with pytest.raises(RuntimeError):
        main_module.create_app(repos=MemoryUnitOfWork())


def test_production_app_refuses_static_tokens(monkeypatch):
    from app import config as config_module
    from app import main as main_module

    production = config_module.Settings(
        environment="production",
        supabase_url="https://project-test.supabase.co",
        supabase_jwt_issuer=ISSUER,
        supabase_jwt_jwks_url=JWKS_URL,
        dev_api_tokens="static-token:subject:reviewer",
    )
    monkeypatch.setattr(main_module, "settings", production)
    with pytest.raises(RuntimeError):
        main_module.create_app(repos=MemoryUnitOfWork())


def test_production_app_builds_with_supabase_configuration(monkeypatch):
    from app import config as config_module
    from app import main as main_module

    production = config_module.Settings(
        environment="production",
        supabase_url="https://project-test.supabase.co",
        supabase_jwt_issuer=ISSUER,
        supabase_jwt_jwks_url=JWKS_URL,
        supabase_jwt_audience=AUDIENCE,
        dev_api_tokens="",
    )
    monkeypatch.setattr(main_module, "settings", production)
    application = main_module.create_app(repos=MemoryUnitOfWork())
    verifier = application.state.token_verifier
    assert isinstance(verifier, SupabaseJWTVerifier)
    assert build_token_verifier(production) is not verifier


def test_settings_derive_issuer_and_jwks_from_supabase_url(monkeypatch):
    from app import config as config_module

    monkeypatch.setenv("SUPABASE_URL", "https://derived.supabase.co/")
    monkeypatch.delenv("SUPABASE_JWT_ISSUER", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_JWKS_URL", raising=False)
    derived = config_module.Settings()
    assert derived.supabase_jwt_issuer == \
        "https://derived.supabase.co/auth/v1"
    assert derived.supabase_jwt_jwks_url == (
        "https://derived.supabase.co/auth/v1/.well-known/jwks.json")

"""End-to-end production path against live Postgres (Stage 12).

This module is the integration evidence for the stage: one run performs
the canonical import through the service-role path, starts the
application the way production does (Postgres engine, Supabase JWT
verification with a mocked JWKS endpoint, registry projected from
`chemical_entities`), then drives a real user through HTTP:

    JWT -> principal -> POST observations -> POST analyze
        -> registry resolution -> evidence -> verification rules V1-V7
        -> persisted decision / claims / matches
        -> reviewer decision -> 429 once the configured budget is spent

No test double stands in for the database, the verifier, or the
registry projection. The only mock is the JWKS HTTP transport (a real
Supabase project is neither available nor desirable in tests), and keys
are generated per test, so no credential is committed.
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import asyncpg
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.api.jwks import JWKSCache
from app.api.supabase_jwt import SupabaseJWTVerifier
from app.main import create_app
from app.repositories.postgres import PostgresUnitOfWork
from app.services.rate_limit import InMemoryRateLimiter
from app.services.registration import register_canonical_entities
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.gate import VERIFICATION_RULES_VERSION
from app.tests.api.helpers import envelope

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not TEST_URL, reason="no live test database configured")

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "snapshots" / "canonical_v1.json"
)
CITRIC_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"

ISSUER = "https://project-test.supabase.co/auth/v1"
JWKS_URL = "%s/.well-known/jwks.json" % ISSUER
AUDIENCE = "authenticated"
READER_SUBJECT = "user-reader-1"
REVIEWER_SUBJECT = "user-reviewer-1"

MIGRATED_TABLES = (
    "review_events",
    "reviews",
    "verification_events",
    "verification_decisions",
    "claim_sources",
    "claims",
    "entity_matches",
    "ingredient_candidates",
    "ingredient_normalizations",
    "ingredient_observations",
    "ingredient_aliases",
    "chemical_entities",
    "sources",
    "domains",
    "roles",
)

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _migrations():
    root = Path(__file__).resolve().parents[4]
    return [
        (root / "backend" / "migrations" / name).read_text()
        for name in (
            "001_initial_schema.sql",
            "002_seed_data.sql",
            "003_verification_review.sql",
        )
    ]


def _asyncpg_kwargs():
    from sqlalchemy.engine import make_url

    url = make_url(TEST_URL)
    query = dict(url.query)
    return {
        "host": query.get("host", "localhost"),
        "port": int(query.get("port", 5432)),
        "user": url.username,
        "database": url.database,
    }


def _await(coro):
    return _LOOP.run_until_complete(coro)


def _reset_database():
    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        for role in ("anon", "authenticated"):
            try:
                await conn.execute("CREATE ROLE %s NOLOGIN" % role)
            except Exception:
                pass
        await conn.execute(
            "DROP TABLE IF EXISTS %s CASCADE" % ", ".join(MIGRATED_TABLES))
        for sql in _migrations():
            try:
                await conn.execute(sql)
            except asyncpg.exceptions.DuplicateTableError:
                pass
            except asyncpg.exceptions.DuplicateObjectError:
                pass
        await conn.close()

    _await(go())


def _engine():
    return create_async_engine(TEST_URL, poolclass=NullPool)


def _fetch_all(sql: str) -> list:
    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            return [dict(row) for row in await conn.fetch(sql)]
        finally:
            await conn.close()

    return _await(go())


def _keypair(kid="key-1"):
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(
        private.public_key(), as_dict=True)
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig",
                "key_ops": ["verify"]})
    return private, jwk


class _Jwks:
    """Mocked JWKS endpoint (keys generated in this process)."""

    def __init__(self, keys, **cache_kwargs):
        self.keys = list(keys)
        self.fetches = 0
        cache_kwargs.setdefault("allowed_algorithms", ("ES256", "RS256"))
        self.cache = JWKSCache(JWKS_URL, client=self._client(), **cache_kwargs)

    def _client(self):
        def handler(request):
            self.fetches += 1
            return httpx.Response(200, json={"keys": list(self.keys)})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class _Policy:
    """Explicit budgets so the 429 boundary is deterministic."""

    def __init__(self, create="3/60", analyze="3/60", decision="1/60"):
        self._table = {
            "observations.create": create,
            "observations.analyze": analyze,
            "reviews.decision": decision,
        }

    def for_action(self, action: str) -> str:
        return self._table.get(action, "0/0")


def _claims(subject, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": subject,
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def _token(private, subject, **overrides):
    return jwt.encode(_claims(subject, **overrides), private,
                      algorithm="ES256", headers={"kid": "key-1"})


def _bearer(token):
    return {"Authorization": "Bearer %s" % token}


@pytest.fixture()
def flow():
    """Registered database + production-shaped application + tokens."""
    _reset_database()
    private, jwk = _keypair()
    engine = _engine()

    # 1. The one authoritative registration path: a service-role import
    #    of the approved snapshot. Nothing below seeds entities by hand.
    report = _await(_register(engine))
    assert report.registered == 4

    jwks = _Jwks([jwk])
    verifier = SupabaseJWTVerifier(
        jwks=jwks.cache,
        issuer=ISSUER,
        audiences=(AUDIENCE,),
        algorithms=("ES256", "RS256"),
        reviewer_subjects=frozenset({REVIEWER_SUBJECT}),
    )
    application = create_app(
        engine=engine,
        verifier=verifier,
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
        rate_limiter=InMemoryRateLimiter(max_keys=100),
    )
    application.state.rate_limit_policy = _Policy()
    with TestClient(application) as client:
        yield {
            "client": client,
            "jwks": jwks,
            "reader": _bearer(_token(private, READER_SUBJECT)),
            "reviewer": _bearer(_token(private, REVIEWER_SUBJECT)),
            "token": _token(private, READER_SUBJECT),
        }
    _await(engine.dispose())


async def _register(engine):
    return await register_canonical_entities(
        PostgresUnitOfWork(engine), SnapshotAdapter(str(SNAPSHOT_PATH)),
        expected_snapshot_version="canonical_v1")


# -- the whole path ----------------------------------------------------


@needs_db
def test_production_flow_from_jwt_to_persisted_verdict(flow):
    client = flow["client"]
    reader = flow["reader"]

    created = envelope(client.post(
        "/api/v1/observations",
        headers=reader,
        json={"raw_text": "Citric Acid (E330)",
              "observation_id": str(uuid.uuid4())}), status=201)
    observation_id = created[0]["observation_id"]

    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id, headers=reader))
    assert analyzed["status"] == "verified"
    assert analyzed["decision_id"]
    # The candidate ref is registry-local, minted from the registered
    # canonical entity -- not the entity UUID.
    candidate_ref = analyzed["resolution"]["entity"]["candidate_ref"]
    assert candidate_ref.startswith("CANON-")
    assert CITRIC_ID not in candidate_ref

    detail = envelope(client.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=reader))
    # V1-V7: all seven frozen rules ran and reported.
    assert len(detail["gate_results"]) == 7
    assert [result["rule_id"] for result in detail["gate_results"]] == [
        "V1_admissible_candidate",
        "V2_authoritative_source",
        "V3_identity_agreement",
        "V4_identifier_validation",
        "V5_entity_type_validation",
        "V6_source_appropriateness",
        "V7_context_checks",
    ]
    assert all(result["result"] == "PASS" for result in detail["gate_results"])
    assert detail["status"] == "verified"
    assert detail["snapshot_version"] == "canonical_v1"
    # Evidence is attached to every claim that was decided.
    fields = {item["claim"]["field"]: item for item in detail["claims"]}
    assert fields["identity"]["claim"]["status"] == "verified"
    assert fields["identity"]["evidence"]
    assert fields["formula"]["claim"]["status"] == "verified"
    assert fields["formula"]["evidence"]

    # Everything above was committed, not held in memory.
    decisions = _fetch_all(
        "SELECT id, status, identity_confidence, rules_version, "
        "snapshot_version FROM verification_decisions")
    assert len(decisions) == 1
    assert decisions[0]["status"] == "verified"
    assert decisions[0]["rules_version"] == VERIFICATION_RULES_VERSION
    matches = _fetch_all(
        "SELECT chemical_entity_id, match_status, identity_confidence, "
        "selected_by, reason_code FROM entity_matches")
    assert len(matches) == 1
    assert matches[0]["match_status"] == "exact_match"
    assert matches[0]["identity_confidence"] == "HIGH"
    assert matches[0]["selected_by"] == "deterministic"
    assert matches[0]["reason_code"]
    # Stage-5 invariant, still enforced: a resolver match never becomes
    # a canonical entity identity. The entity id is only attached where
    # evidence supplies it (claims, below).
    assert matches[0]["chemical_entity_id"] is None
    # The claim references the entity the import registered.
    claims = _fetch_all(
        "SELECT chemical_entity_id, field_name, verification_status "
        "FROM claims WHERE chemical_entity_id IS NOT NULL")
    assert claims
    assert {str(row["chemical_entity_id"]) for row in claims} == {CITRIC_ID}


@needs_db
def test_registry_loaded_from_database_serves_resolution(flow):
    """The resolver's candidates come only from registered entities."""
    client = flow["client"]
    registered = envelope(client.post(
        "/api/v1/observations", headers=flow["reader"],
        json={"raw_text": "glycerol",
              "observation_id": str(uuid.uuid4())}), status=201)
    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze"
        % registered[0]["observation_id"], headers=flow["reader"]))
    # Glycerol is one of the four imported records, so the projection
    # built from `chemical_entities` resolves it.
    assert analyzed["resolution"]["entity"]["candidate_ref"].startswith(
        "CANON-")

    unregistered = envelope(client.post(
        "/api/v1/observations", headers=flow["reader"],
        json={"raw_text": "sodium cyclamate",
              "observation_id": str(uuid.uuid4())}), status=201)
    unresolved = envelope(client.post(
        "/api/v1/observations/%s/analyze"
        % unregistered[0]["observation_id"], headers=flow["reader"]))
    # Not in the approved snapshot and not in the registry: nothing is
    # resolved and no registry ref is invented for it.
    assert unresolved["status"] != "verified"
    assert unresolved["resolution"]["entity"] is None
    assert unresolved["resolution"]["match_status"] == "unresolved"
    assert "CANON-" not in json.dumps(unresolved)
    assert "sodium cyclamate" not in json.dumps(
        _fetch_all("SELECT preferred_name FROM chemical_entities"))


@needs_db
def test_reviewer_decision_flows_and_then_rate_limits(flow):
    client = flow["client"]
    created = envelope(client.post(
        "/api/v1/observations", headers=flow["reader"],
        json={"raw_text": "citric acid",
              "observation_id": str(uuid.uuid4())}), status=201)
    observation_id = created[0]["observation_id"]
    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=flow["reader"]))
    assert analyzed["status"] == "provisional"
    review_id = analyzed["review_id"]
    assert review_id is not None

    claimed = envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                                   headers=flow["reviewer"]))
    assert claimed["status"] == "in_review"
    # The reviewer identity is the verified JWT subject, not a payload.
    assert claimed["reviewer"] == "human:%s" % REVIEWER_SUBJECT

    decided = envelope(client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        headers=flow["reviewer"],
        json={"decision": "reject_identity",
              "reason": "needs a second independent source"}))
    assert decided["status"] == "rejected"

    # Budget is one decision per window: the next attempt is refused,
    # with the standard envelope and a Retry-After header.
    refused = client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        headers=flow["reviewer"],
        json={"decision": "reject_identity", "reason": "again"})
    assert refused.status_code == 429
    body = refused.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["details"]["action"] == "reviews.decision"
    assert refused.headers["Retry-After"] == "60"

    # Events were appended by the successful decision only.
    events = envelope(client.get("/api/v1/reviews/%s" % review_id,
                                 headers=flow["reader"]))["events"]
    types = [event["event_type"] for event in events]
    assert types.count("ReviewDecisionRecorded") == 1


@needs_db
def test_repeated_create_is_rate_limited_with_retry_after(flow):
    client = flow["client"]
    for _ in range(3):
        assert client.post("/api/v1/observations", headers=flow["reader"],
                           json={"raw_text": "citric acid",
                                 "observation_id": str(uuid.uuid4())}
                           ).status_code == 201
    limited = client.post("/api/v1/observations", headers=flow["reader"],
                          json={"raw_text": "citric acid",
                                "observation_id": str(uuid.uuid4())})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    # No observation row was written for the refused request.
    observations = _fetch_all("SELECT count(*) AS total "
                              "FROM ingredient_observations")
    assert observations[0]["total"] == 3


@needs_db
def test_reads_are_never_rate_limited(flow):
    client = flow["client"]
    for _ in range(20):
        assert client.get("/api/v1/reviews/pending",
                          headers=flow["reader"]).status_code == 200
        assert client.get("/api/v1/health").status_code == 200


@needs_db
def test_unverified_and_privileged_tokens_never_reach_a_route(flow):
    client = flow["client"]
    private, _ = _keypair()
    service_token = _token(private, "backend", role="service_role")
    expired = _token(private, READER_SUBJECT,
                     iat=int(time.time()) - 7200,
                     exp=int(time.time()) - 3600)
    for token in (service_token, expired, "not-a-jwt"):
        response = client.post("/api/v1/observations", headers=_bearer(token),
                               json={"raw_text": "citric acid"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert _fetch_all(
        "SELECT count(*) AS total FROM ingredient_observations"
    )[0]["total"] == 0


@needs_db
def test_snapshot_artifact_is_not_modified_by_the_flow(flow):
    before = json.loads(SNAPSHOT_PATH.read_text())
    client = flow["client"]
    created = envelope(client.post(
        "/api/v1/observations", headers=flow["reader"],
        json={"raw_text": "Citric Acid (E330)",
              "observation_id": str(uuid.uuid4())}), status=201)
    client.post("/api/v1/observations/%s/analyze" % created[0]["observation_id"],
                headers=flow["reader"])
    assert json.loads(SNAPSHOT_PATH.read_text()) == before

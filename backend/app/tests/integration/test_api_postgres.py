"""Live-Postgres API coverage (require TEST_DATABASE_URL).

Replays the authenticated boundary -- create, analyze, verify, review,
claim, decide -- against real Postgres with migrations 001-003 applied,
through the production per-request-connection/transaction wiring
(`create_app(engine=...)`). Each HTTP request opens its own connection,
so this also proves reads observe previously committed writes and
that conditional claims really serialize across connections.

The test truncates only the pipeline tables it writes (never the
`001`/`002` seed reference data) so repeated runs start from the same
state. Skipped -- never faked -- when no test database is configured.
"""

import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.main import create_app
from app.services.entity_resolver import InMemoryRegistry, RegistryEntry
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.tests.api.helpers import (
    READER,
    REVIEWER1,
    REVIEWER2,
    SNAPSHOT_PATH,
    PermissivePolicy,
    auth,
    envelope,
    verifier,
)

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not TEST_URL, reason="no live test database configured")

# Pipeline tables written by this flow. Seeded reference data
# (sources, chemical_entities, aliases) is left untouched.
PIPELINE_TABLES = (
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
)

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _snapshot_entity_ids():
    """Canonical entity ids named by the immutable snapshot records.

    `claims.chemical_entity_id` references `chemical_entities`, and a
    decision's entity id comes from the evidence adapter -- not from the
    resolver registry. Registering these rows is the entity-registration
    prerequisite (a service-role import, out of scope for this stage);
    it is done explicitly here so the foreign-key invariant is
    exercised rather than bypassed.
    """
    import json

    payload = json.loads(SNAPSHOT_PATH.read_text())
    return [
        (record["entity_id"], record["preferred_name"])
        for record in payload["records"]
    ]


def _migrations():
    root = Path(__file__).resolve().parents[4]
    return [
        (root / "backend" / "migrations" / name).read_text()
        for name in (
            "001_initial_schema.sql",
            "002_seed_data.sql",
            "003_verification_review.sql",
            "004_ocr_boundary.sql",
            "005_ocr_ownership.sql",
        )
    ]


def _asyncpg_url():
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


def _reset_schema():
    """Rebuild the pipeline tables from the current migration files.

    The test database is disposable: pipeline tables are dropped (the
    `001`/`002` reference data and `sources` seed rows survive) and
    re-created by re-applying 001-003, so the live schema always equals
    the committed migrations rather than a stale earlier application.
    """
    async def go():
        conn = await asyncpg.connect(**_asyncpg_url())
        for role in ("anon", "authenticated"):
            try:
                await conn.execute("CREATE ROLE %s NOLOGIN" % role)
            except Exception:
                pass
        await conn.execute(
            "DROP TABLE IF EXISTS %s CASCADE"
            % ", ".join(PIPELINE_TABLES))
        for sql in _migrations():
            try:
                await conn.execute(sql)
            except asyncpg.exceptions.DuplicateTableError:
                pass
            except asyncpg.exceptions.DuplicateObjectError:
                pass
        await conn.execute(
            "TRUNCATE %s CASCADE" % ", ".join(PIPELINE_TABLES))
        for entity_id, label in _snapshot_entity_ids():
            await conn.execute(
                "INSERT INTO chemical_entities (id, preferred_name, "
                "entity_type, representation_type, status, "
                "structure_status) "
                "VALUES ($1, $2, 'chemical_entity', 'single_molecule', "
                "'active', 'unavailable') "
                "ON CONFLICT (id) DO NOTHING",
                entity_id, label,
            )
        await conn.close()

    _await(go())


@pytest.fixture()
def client():
    """TestClient over the production per-request Postgres wiring."""
    if not TEST_URL:
        pytest.skip("no live test database configured")
    _reset_schema()
    # NullPool: connections are created and closed inside each request's
    # event loop, so nothing is ever reused across loops.
    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    registry = InMemoryRegistry(
        [
            RegistryEntry(
                ref="7a111111-1111-1111-1111-111111111111",
                preferred_name="citric acid",
                display_name="Citric Acid (live fixture)",
                identifiers=["E330"],
                entity_class="single_molecule",
                source="synthetic_test_fixture",
            ),
            RegistryEntry(
                ref="7a222222-2222-2222-2222-222222222222",
                preferred_name="sodium benzoate",
                display_name="Sodium Benzoate (live fixture)",
                identifiers=["E211"],
                entity_class="salt",
                source="synthetic_test_fixture",
            ),
        ],
        registry_id="live_api_registry",
        version="t11",
    )
    application = create_app(
        engine=engine,
        verifier=verifier(),
        registry=registry,
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
    )
    # Budgets are exercised in test_api_rate_limit / test_production_flow;
    # here they would only interfere with the flow under test.
    application.state.rate_limit_policy = PermissivePolicy()
    with TestClient(application) as built:
        yield built
    _await(engine.dispose())


@needs_db
def test_unauthenticated_request_rejected(client):
    response = client.get("/api/v1/reviews/pending")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@needs_db
def test_observation_and_analysis_persist(client):
    created = envelope(client.post(
        "/api/v1/observations",
        json={"raw_text": "Citric Acid (E330)",
              "observation_id": str(uuid.uuid4())},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    assert created[0]["raw_text"] == "Citric Acid (E330)"
    assert created[0]["normalized_text"] == "citric acid E 330"

    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    assert analyzed["status"] == "verified"
    assert analyzed["identity_confidence"] == "HIGH"
    assert analyzed["decision_id"]
    assert analyzed["review_id"] is None
    assert analyzed["resolution"]["entity"]["candidate_ref"] == (
        "7a111111-1111-1111-1111-111111111111")

    detail = envelope(client.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=auth(READER)))
    assert detail["status"] == "verified"
    assert detail["rules_version"] == "1.0.0"
    assert detail["snapshot_version"] == "canonical_v1"
    assert len(detail["gate_results"]) == 7
    fields = {c["claim"]["field"]: c["claim"]["status"]
              for c in detail["claims"]}
    assert fields["identity"] == "verified"
    assert fields["formula"] == "verified"
    assert all(
        c["evidence"] for c in detail["claims"] if c["claim"]["field"] in (
            "identity", "formula"))


@needs_db
def test_review_lifecycle_across_connections(client):
    created = envelope(client.post(
        "/api/v1/observations",
        json={"raw_text": "citric acid",
              "observation_id": str(uuid.uuid4())},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    assert analyzed["status"] == "provisional"
    review_id = analyzed["review_id"]
    assert review_id is not None

    pending = envelope(client.get("/api/v1/reviews/pending",
                                  headers=auth(READER)))
    assert any(r["review_id"] == review_id for r in pending)

    # Every call below is a separate connection and committed write.
    claimed = envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                                   headers=auth(REVIEWER1)))
    assert claimed["status"] == "in_review"
    assert claimed["reviewer"] == "human:reviewer1"

    rejected = envelope(client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        json={"decision": "reject_identity",
              "reason": "needs a second independent source"},
        headers=auth(REVIEWER1)))
    assert rejected["status"] == "rejected"

    events = envelope(client.get("/api/v1/reviews/%s" % review_id,
                                 headers=auth(READER)))["events"]
    types = [e["event_type"] for e in events]
    assert types[0] == "ReviewCreated"
    assert "ReviewClaimed" in types
    assert "ReviewDecisionRecorded" in types
    assert not envelope(client.get("/api/v1/reviews/pending",
                                   headers=auth(READER)))


@needs_db
def test_concurrent_claim_conflicts_in_database(client):
    created = envelope(client.post(
        "/api/v1/observations",
        json={"raw_text": "sodium benzoate",
              "observation_id": str(uuid.uuid4())},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    assert analyzed["status"] == "provisional"
    review_id = analyzed["review_id"]

    first = client.post("/api/v1/reviews/%s/claim" % review_id,
                        headers=auth(REVIEWER1))
    second = client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER2))
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]
    assert second.json()["error"]["code"] == "CONFLICT"


@needs_db
def test_reader_cannot_review(client):
    created = envelope(client.post(
        "/api/v1/observations",
        json={"raw_text": "citric acid",
              "observation_id": str(uuid.uuid4())},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    review_id = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))["review_id"]
    response = client.post("/api/v1/reviews/%s/claim" % review_id,
                           headers=auth(READER))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@needs_db
def test_unanalyzed_observation_is_not_found(client):
    response = client.get(
        "/api/v1/observations/%s/verification" % uuid.uuid4(),
        headers=auth(READER))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

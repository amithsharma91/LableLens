"""Real-label regression against live Postgres (Stage 13).

Requires TEST_DATABASE_URL. The database is disposable: this module
drops every migrated table and re-applies migrations 001-003, runs
the service-role import so the canonical registry is genuinely
registered, then runs the same four real labels through
`run_label` and proves persisted state -- observations,
normalizations, candidates, matches, decisions, claims, claim
sources, and audit events -- rather than merely returned objects.

Skipped -- never faked -- when no test database is configured.
"""

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.regression.label_input import LabelInput
from app.regression.metrics import summarize
from app.regression.runner import run_label
from app.repositories.postgres import (
    PostgresClaimRepository,
    PostgresEntityRepository,
    PostgresEvidenceRepository,
    PostgresMatchRepository,
    PostgresReviewRepository,
    PostgresUnitOfWork,
    PostgresVerificationRepository,
)
from app.services.observation_service import ObservationService
from app.services.registration import (
    build_registry,
    register_canonical_entities,
)
from app.services.review_service import ReviewService
from app.services.verification.adapters.snapshot import SnapshotAdapter

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not TEST_URL, reason="no live test database configured")

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "regression" / "fixtures" / "real_labels"
)
SNAPSHOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "snapshots" / "canonical_v1.json"
)
LABEL_IDS = ("RL-13-01", "RL-13-02", "RL-13-03", "RL-13-04",
             "RL-14-01", "RL-15-01")

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

CITRIC_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"
BENZOATE_ID = "6223de87-1d0c-49f9-a926-e2b57e0fc8ae"

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _migrations():
    root = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
    )
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


def _fixture(label_id: str) -> dict:
    return json.loads((FIXTURES / ("%s.json" % label_id)).read_text())


def _label(fixture: dict) -> LabelInput:
    return LabelInput.from_dict({
        "label_id": fixture["label_id"],
        "raw_text": fixture["raw_text"],
        "input_method": fixture["input_method"],
        "source_reference": fixture["source_reference"],
    })


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


@pytest.fixture()
def live():
    """Registered database, live registry, and a run helper."""
    _reset_database()
    engine = _engine()

    async def prepare():
        await register_canonical_entities(
            PostgresUnitOfWork(engine),
            SnapshotAdapter(str(SNAPSHOT)),
            expected_snapshot_version="canonical_v1")
        async with PostgresUnitOfWork(engine).atomic() as scope:
            entities = await scope.entities.list_entities(
                role="service")
            aliases = await scope.entities.list_aliases(role="service")
        return build_registry(
            entities, aliases, version=str(len(entities)))

    registry = _await(prepare())
    adapter = SnapshotAdapter(str(SNAPSHOT))

    async def run_one(fixture: dict) -> dict:
        connection = await engine.connect()
        transaction = await connection.begin()
        try:
            repos = SimpleNamespace(
                matches=PostgresMatchRepository(connection),
                claims=PostgresClaimRepository(connection),
                evidence=PostgresEvidenceRepository(connection),
                verification=PostgresVerificationRepository(
                    connection),
                reviews=PostgresReviewRepository(connection),
                entities=PostgresEntityRepository(connection),
            )
            reviews = ReviewService(repos, adapters=[adapter])
            service = ObservationService(
                repos, registry=registry, adapters=[adapter],
                review_service=reviews)
            run = await run_label(
                service, _label(fixture), fixture)
            await transaction.commit()
            return run.to_dict()
        except Exception:
            await transaction.rollback()
            raise
        finally:
            await connection.close()

    yield run_one
    _await(engine.dispose())


# -- the regression, persisted --------------------------------------------------


@needs_db
def test_live_regression_matches_reviewed_expectations(live):
    runs = [_await(live(_fixture(label_id))) for label_id in LABEL_IDS]
    for run in runs:
        assert run["mismatches"] == [], run["label_id"]
    metrics = summarize(runs)
    assert metrics["ingredients_observed"] == 62
    assert metrics["exact_matches"] == 7
    assert metrics["provisional"] == 4
    assert metrics["unverified"] == 1
    assert metrics["verified"] == 2
    assert metrics["unknown"] == 55
    assert metrics["entity_match_false_positives"] == 0
    assert metrics["mismatches"] == 0


@needs_db
def test_live_persisted_rows_cover_the_chain(live):
    _await(live(_fixture("RL-13-04")))
    observations = _fetch_all(
        "SELECT id, raw_text, sequence_number FROM "
        "ingredient_observations ORDER BY sequence_number")
    assert len(observations) == 14
    assert observations[1]["raw_text"] == "citric acid"
    normalizations = _fetch_all(
        "SELECT id, observation_id, normalized_text FROM "
        "ingredient_normalizations")
    assert len(normalizations) == 14
    assert {row["normalized_text"] for row in normalizations} >= {
        "citric acid", "sodium benzoate", "glycerin"}
    matches = _fetch_all(
        "SELECT id, normalization_id, match_status FROM entity_matches")
    assert len(matches) == 14
    assert sum(
        row["match_status"] == "exact_match" for row in matches) == 2
    candidates = _fetch_all(
        "SELECT id, normalization_id FROM ingredient_candidates")
    # Exact matches and the glycerin candidate persist candidates.
    assert len(candidates) == 3
    decisions = _fetch_all(
        "SELECT id, entity_match_id, status, rules_version, "
        "snapshot_version FROM verification_decisions")
    assert len(decisions) == 14
    assert {row["status"] for row in decisions} == {
        "provisional", "unknown"}
    assert {row["rules_version"] for row in decisions} == {"1.0.0"}
    claims = _fetch_all(
        "SELECT id, chemical_entity_id, field_name, "
        "verification_status FROM claims")
    assert claims
    by_entity = {
        str(row["chemical_entity_id"]): row["verification_status"]
        for row in claims if row["chemical_entity_id"] is not None
    }
    assert by_entity[CITRIC_ID] == "provisional"
    assert by_entity[BENZOATE_ID] == "provisional"
    links = _fetch_all(
        "SELECT claim_id, source_id FROM claim_sources")
    assert all(row["source_id"] for row in links)
    # Every claim that names a canonical entity traces to a source;
    # unknown claims have no supporting source and link to none.
    linked = {str(row["claim_id"]) for row in links}
    for row in claims:
        if row["chemical_entity_id"] is not None:
            assert str(row["id"]) in linked
        else:
            assert row["verification_status"] == "unknown"
    # Audit rows remain intact: events are written only when a
    # claim actually changes state, never per analysis. A repeated
    # analysis with the same outcome appends nothing.
    events_before = _fetch_all(
        "SELECT count(*) AS total FROM verification_events")[0]["total"]
    _await(live(_fixture("RL-13-04")))
    events_after = _fetch_all(
        "SELECT count(*) AS total FROM verification_events")[0]["total"]
    assert events_after == events_before


@needs_db
def test_live_correction_keeps_raw_and_uses_display(live):
    run = _await(live(_fixture("RL-13-02")))
    assert run["mismatches"] == []
    correction = run["correction"]
    assert correction["raw_preserved"] == "Saccharin Sodium"
    rows = _fetch_all(
        "SELECT raw_text, display_text, original_text, "
        "user_corrected, correction_reason, source_type FROM "
        "ingredient_observations WHERE id = '%s'"
        % correction["observation_id"])
    assert len(rows) == 1
    assert rows[0]["raw_text"] == "Saccharin Sodium"
    assert rows[0]["display_text"] == "Sodium Saccharin"
    assert rows[0]["original_text"] == "Saccharin Sodium"
    assert rows[0]["user_corrected"] is True
    assert rows[0]["source_type"] == "user_corrected"
    assert rows[0]["correction_reason"]
    norms = _fetch_all(
        "SELECT normalized_text FROM ingredient_normalizations "
        "WHERE observation_id = '%s'" % correction["observation_id"])
    assert len(norms) == 2
    assert {row["normalized_text"] for row in norms} == {
        "saccharin sodium", "sodium saccharin"}


@needs_db
def test_live_identifier_resolution_without_verification(live):
    run = _await(live(_fixture("RL-14-01")))
    assert run["mismatches"] == []
    acidity = next(
        result for result in run["ingredient_results"]
        if result["normalized_text"] == "acidity regulator INS 330")
    assert acidity["match_status"] == "exact_match"
    assert acidity["entity_ref"] == "CANON-2671a263ff76"
    assert acidity["verification_status"] == "unverified"
    rows = _fetch_all(
        "SELECT status, rules_version FROM verification_decisions "
        "WHERE id = '%s'" % acidity["decision_id"])
    assert len(rows) == 1
    assert rows[0]["status"] == "unverified"
    assert rows[0]["rules_version"] == "1.0.0"


@needs_db
def test_live_verified_path_persists_decision_claim_evidence(live):
    run = _await(live(_fixture("RL-15-01")))
    assert run["mismatches"] == []
    for normalized, entity_id in (
        ("glycerol E 422",
         "763389d0-3732-47dd-ad27-2c62a50e95b8"),
        ("sodium benzoate E 211",
         "6223de87-1d0c-49f9-a926-e2b57e0fc8ae"),
    ):
        result = next(
            item for item in run["ingredient_results"]
            if item["normalized_text"] == normalized)
        assert result["verification_status"] == "verified"
        decisions = _fetch_all(
            "SELECT id, status, identity_confidence, rules_version, "
            "snapshot_version FROM verification_decisions "
            "WHERE id = '%s'" % result["decision_id"])
        assert len(decisions) == 1
        assert decisions[0]["status"] == "verified"
        assert decisions[0]["identity_confidence"] == "HIGH"
        assert decisions[0]["rules_version"] == "1.0.0"
        claims = _fetch_all(
            "SELECT id, chemical_entity_id, field_name, "
            "verification_status, confidence FROM claims "
            "WHERE chemical_entity_id = '%s'" % entity_id)
        assert claims
        assert {row["verification_status"] for row in claims} == {
            "verified"}
        assert {str(row["chemical_entity_id"]) for row in claims} == {
            entity_id}
        identity = next(
            row for row in claims if row["field_name"] == "identity")
        assert identity["confidence"] == "HIGH"
        links = _fetch_all(
            "SELECT claim_id, source_id FROM claim_sources "
            "WHERE claim_id = '%s'" % identity["id"])
        assert len(links) == 1
        assert links[0]["source_id"]
        sources = _fetch_all(
            "SELECT id, name FROM sources WHERE id = '%s'"
            % links[0]["source_id"])
        assert len(sources) == 1
        assert sources[0]["name"]
    # The three unrelated nodes stayed unknown with no entity.
    unknowns = _fetch_all(
        "SELECT chemical_entity_id, verification_status FROM claims "
        "WHERE chemical_entity_id IS NULL")
    assert unknowns
    assert {row["verification_status"] for row in unknowns} == {
        "unknown"}


@needs_db
def test_live_registry_still_holds_only_registered_entities(live):
    _await(live(_fixture("RL-13-03")))
    entities = _fetch_all(
        "SELECT id, preferred_name FROM chemical_entities")
    assert len(entities) == 4
    assert {row["preferred_name"] for row in entities} == {
        "citric acid", "sodium benzoate", "glycerol", "ethanol"}


@needs_db
def test_live_rerun_is_stable(live):
    fixture = _fixture("RL-13-04")
    first = _await(live(fixture))
    before = {
        table: _fetch_all("SELECT count(*) AS total FROM %s" % table)[
            0]["total"]
        for table in ("ingredient_observations",
                      "ingredient_normalizations",
                      "entity_matches", "verification_decisions",
                      "claims", "claim_sources", "chemical_entities")
    }
    second = _await(live(fixture))
    assert second["mismatches"] == []
    assert second["ingredient_results"] == first["ingredient_results"]
    after = {
        table: _fetch_all("SELECT count(*) AS total FROM %s" % table)[
            0]["total"]
        for table in before
    }
    assert after == before

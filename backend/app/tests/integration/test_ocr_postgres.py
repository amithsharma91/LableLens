"""Live-Postgres OCR boundary coverage (Stage 16).

Requires TEST_DATABASE_URL. The database is disposable: this module
drops every migrated table and re-applies migrations 001-004, runs
the service-role import, then proves OCR runs, corrections, and the
full observe/analyze path persist -- and that reruns and second
corrections behave. Skipped -- never faked -- without a database.
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.repositories.postgres import (
    PostgresClaimRepository,
    PostgresEntityRepository,
    PostgresEvidenceRepository,
    PostgresMatchRepository,
    PostgresOCRRepository,
    PostgresReviewRepository,
    PostgresVerificationRepository,
    PostgresUnitOfWork,
)
from app.services.observation_service import ObservationService
from app.services.ocr_provider import (
    FakeOCRProvider,
    OCRResult,
    ProviderFailure,
)
from app.services.ocr_service import OCRService
from app.services.registration import (
    build_registry,
    register_canonical_entities,
)
from app.services.review_service import ReviewService
from app.services.verification.adapters.snapshot import SnapshotAdapter

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not TEST_URL, reason="no live test database configured")

SNAPSHOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "snapshots" / "canonical_v1.json"
)

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
    "ocr_corrections",
    "ocr_runs",
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
            "004_ocr_boundary.sql",
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


def _json(value):
    """JSONB arrives as text unless a codec is installed."""
    import json

    return json.loads(value) if isinstance(value, str) else value


@pytest.fixture()
def live():
    """Registered database plus an OCR service runner."""
    _reset_database()
    engine = _engine()
    providers = {
        "fake-test": FakeOCRProvider(
            {
                "doc-live": OCRResult(
                    document_id="doc-live",
                    provider="fake-test",
                    raw_text=("Sodium Benzoate (E211), "
                              "Glycerol (E422)"),
                    ocr_confidence=0.81,
                ),
            },
            name="fake-test",
        ),
    }

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

    async def use(fn_name, *args, **kwargs):
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
                ocr=PostgresOCRRepository(connection),
            )
            reviews = ReviewService(repos, adapters=[adapter])
            observations = ObservationService(
                repos, registry=registry, adapters=[adapter],
                review_service=reviews)
            service = OCRService(
                repos, registry=registry, adapters=[adapter],
                providers=dict(providers),
                review_service=reviews)
            outcome = await getattr(service, fn_name)(
                *args, **kwargs)
            await transaction.commit()
            return outcome, observations
        except Exception:
            await transaction.rollback()
            raise
        finally:
            await connection.close()

    yield use

    async def cleanup():
        # This module leaves no rows behind: test_postgres.py
        # applies migrations without truncating and assumes an
        # empty claims table, so teardown removes everything this
        # module wrote.
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            await conn.execute(
                "TRUNCATE %s CASCADE" % ", ".join(MIGRATED_TABLES))
        finally:
            await conn.close()

    _await(cleanup())
    _await(engine.dispose())


# -- persistence -----------------------------------------------------------------


@needs_db
def test_live_ocr_run_and_correction_persist(live):
    outcome, _ = _await(live(
        "register_result",
        OCRResult(
            document_id="doc-a", provider="fake-test",
            raw_text="Sodium Benzoatc (E211)",
            ocr_confidence=0.6,
            page_metadata={"page": 1},
            source_reference={"scan": "scan-a"},
        ),
        run_id="aaaaaaaa-aaaa-4111-8111-aaaaaaaaaaaa",
        role="service",
    ))
    assert outcome["raw_text"] == "Sodium Benzoatc (E211)"
    runs = _fetch_all("SELECT * FROM ocr_runs")
    assert len(runs) == 1
    assert runs[0]["raw_text"] == "Sodium Benzoatc (E211)"
    assert float(runs[0]["ocr_confidence"]) == 0.6
    assert _json(runs[0]["page_metadata"]) == {"page": 1}
    correction, _ = _await(live(
        "correct_run", outcome["id"],
        corrected_text="Sodium Benzoate (E211)",
        reason="ocr substitution", actor="human:reviewer-1",
        role="service",
    ))
    assert correction["corrected_text"] == "Sodium Benzoate (E211)"
    rows = _fetch_all("SELECT * FROM ocr_corrections")
    assert len(rows) == 1
    assert rows[0]["actor"] == "human:reviewer-1"
    # Raw text was never mutated by the correction.
    assert _fetch_all(
        "SELECT raw_text FROM ocr_runs")[0]["raw_text"] == (
        "Sodium Benzoatc (E211)")


@needs_db
def test_live_second_correction_refused(live):
    outcome, _ = _await(live(
        "register_result",
        OCRResult(
            document_id="doc-b", provider="fake-test",
            raw_text="water"),
        role="service",
    ))
    _await(live(
        "correct_run", outcome["id"], corrected_text="Water!",
        reason="first", actor="human:r", role="service"))
    with pytest.raises(Exception):
        _await(live(
            "correct_run", outcome["id"], corrected_text="Water?",
            reason="second", actor="human:r", role="service"))
    assert len(_fetch_all("SELECT * FROM ocr_corrections")) == 1


@needs_db
def test_live_provider_failure_persists_nothing(live):
    with pytest.raises(ProviderFailure):
        _await(live(
            "extract_with", "fake-test", "doc-missing",
            role="service"))
    assert _fetch_all(
        "SELECT count(*) AS total FROM ocr_runs")[0]["total"] == 0


# -- full path ----------------------------------------------------------------------


@needs_db
def test_live_ocr_to_verified_persists_everything(live):
    outcome, _ = _await(live(
        "extract_with", "fake-test", "doc-live", role="service"))
    analyzed, _ = _await(live("analyze_run", outcome["id"],
                              role="service"))
    assert analyzed["corrected"] is False
    assert len(analyzed["items"]) == 2
    assert {item["decision"]["status"]
            for item in analyzed["items"]} == {"verified"}
    assert _fetch_all(
        "SELECT count(*) AS total FROM ingredient_observations"
    )[0]["total"] == 2
    observations = _fetch_all(
        "SELECT ocr_run_id, ocr_confidence FROM "
        "ingredient_observations")
    assert {str(row["ocr_run_id"]) for row in observations} == {
        outcome["id"]}
    assert {float(row["ocr_confidence"]) for row in observations} == {
        0.81}
    decisions = _fetch_all(
        "SELECT status FROM verification_decisions")
    assert len(decisions) == 2
    assert {row["status"] for row in decisions} == {"verified"}
    claims = _fetch_all(
        "SELECT chemical_entity_id FROM claims "
        "WHERE chemical_entity_id IS NOT NULL")
    assert {str(row["chemical_entity_id"]) for row in claims} == {
        "763389d0-3732-47dd-ad27-2c62a50e95b8", BENZOATE_ID}
    links = _fetch_all(
        "SELECT claim_id, source_id FROM claim_sources")
    assert links and all(row["source_id"] for row in links)


@needs_db
def test_live_corrected_run_reaches_verified(live):
    outcome, _ = _await(live(
        "register_result",
        OCRResult(
            document_id="doc-c", provider="fake-test",
            raw_text="Sodium Benzoatc (E211)"),
        role="service",
    ))
    before, _ = _await(live("analyze_run", outcome["id"],
                            role="service"))
    assert before["items"][0]["decision"]["status"] == "unverified"
    _await(live(
        "correct_run", outcome["id"],
        corrected_text="Sodium Benzoate (E211)",
        reason="ocr substitution", actor="human:r", role="service"))
    after, _ = _await(live("analyze_run", outcome["id"],
                           role="service"))
    assert after["corrected"] is True
    assert after["items"][0]["decision"]["status"] == "verified"
    # Both generations persist: raw-derived and corrected-derived.
    raws = sorted(
        row["raw_text"] for row in _fetch_all(
            "SELECT raw_text FROM ingredient_observations"))
    assert raws == ["Sodium Benzoatc (E211)", "Sodium Benzoate (E211)"]


@needs_db
def test_live_rerun_is_stable(live):
    outcome, _ = _await(live(
        "extract_with", "fake-test", "doc-live", role="service"))
    first, _ = _await(live("analyze_run", outcome["id"],
                           role="service"))
    before = {
        table: _fetch_all("SELECT count(*) AS total FROM %s" % table)[
            0]["total"]
        for table in ("ocr_runs", "ocr_corrections",
                      "ingredient_observations",
                      "ingredient_normalizations", "entity_matches",
                      "verification_decisions", "claims")
    }
    second, _ = _await(live("analyze_run", outcome["id"],
                            role="service"))
    assert [item["observation_id"]
            for item in second["items"]] == [
        item["observation_id"] for item in first["items"]]
    after = {
        table: _fetch_all("SELECT count(*) AS total FROM %s" % table)[
            0]["total"]
        for table in before
    }
    assert after == before

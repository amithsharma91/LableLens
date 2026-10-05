"""Live Postgres integration tests (require TEST_DATABASE_URL).

Validates for real, against the applied 001-003 migrations: schema
application, RLS role behavior, append-only triggers, FK/CHECK
enforcement, idempotent upserts, conditional claims, atomic scopes,
and full-chain round-trips through the Postgres repositories.

Skipped (never faked) when no test database is configured.
"""

import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from app.repositories.postgres import ReviewClaimConflict
from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import create_async_engine


TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not TEST_URL, reason="no live test database configured")


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


def _asyncpg_url():
    # TEST_DATABASE_URL is a SQLAlchemy URL; derive asyncpg kwargs.
    from sqlalchemy.engine import make_url

    url = make_url(TEST_URL)
    query = dict(url.query)
    return {
        "host": query.get("host", "localhost"),
        "port": int(query.get("port", 5432)),
        "user": url.username,
        "database": url.database,
    }


@pytest.fixture(scope="module")
def migrated():
    if not TEST_URL:
        pytest.skip("no live test database configured")

    async def apply():
        conn = await asyncpg.connect(**_asyncpg_url())
        try:
            await conn.execute("CREATE ROLE anon NOLOGIN")
        except Exception:
            pass
        try:
            await conn.execute("CREATE ROLE authenticated NOLOGIN")
        except Exception:
            pass
        for sql in _migrations():
            try:
                await conn.execute(sql)
            except asyncpg.exceptions.DuplicateTableError:
                pass
            except asyncpg.exceptions.DuplicateObjectError:
                pass
        await conn.close()

    _await(apply())
    return True


@pytest.fixture()
def uow(migrated):
    from types import SimpleNamespace

    from app.repositories.postgres import (
        PostgresClaimRepository,
        PostgresEvidenceRepository,
        PostgresMatchRepository,
        PostgresReviewRepository,
        PostgresVerificationRepository,
    )

    async def build():
        from sqlalchemy import text as _text

        engine = create_async_engine(TEST_URL)
        conn = await engine.connect()
        await conn.execute(_text("BEGIN"))
        bound = SimpleNamespace(
            engine=engine,
            matches=PostgresMatchRepository(conn),
            claims=PostgresClaimRepository(conn),
            evidence=PostgresEvidenceRepository(conn),
            verification=PostgresVerificationRepository(conn),
            reviews=PostgresReviewRepository(conn),
        )
        return engine, conn, bound

    loop = _LOOP
    engine, conn, bound = loop.run_until_complete(build())
    yield bound
    loop.run_until_complete(conn.execute(_text("ROLLBACK")))
    loop.run_until_complete(conn.close())
    loop.run_until_complete(engine.dispose())


@needs_db
def test_seed_repair_present(uow):
    async def go():
        rows = await uow.evidence._conn.execute(
            _text("SELECT count(*) FROM sources"))
        assert rows.scalar() == 9

    _await(go())


@needs_db
def test_full_chain_round_trip(uow):
    async def go():
        scan = str(uuid.uuid4())
        obs = str(uuid.uuid4())
        await uow.matches.save_observation({
            "id": obs, "scan_id": scan, "sequence_number": 0,
            "raw_text": "Sodiurn Benzoate", "display_text": None,
            "source_type": "ocr", "ocr_run_id": None,
            "ocr_confidence": None, "user_corrected": False,
            "original_text": None, "correction_reason": None,
        })
        norm = str(uuid.uuid4())
        await uow.matches.save_normalization({
            "id": norm, "observation_id": obs,
            "normalized_text": "sodlum benzoate",
            "normalization_method": "rule", "normalizer_version": "1.0.0",
            "confidence": None, "status": "complete",
        })
        match = str(uuid.uuid4())
        await uow.matches.save_match({
            "id": match, "normalization_id": norm,
            "chemical_entity_id": None, "match_status": "unresolved",
            "identity_confidence": "UNKNOWN", "selected_by": "deterministic",
            "selected_at": None, "reason_code": None,
            "review_status": None, "review_notes": None,
        })
        chain = await uow.matches.get_chain(norm)
        assert chain["observation"]["raw_text"] == "Sodiurn Benzoate"
        assert chain["match"]["id"] == match

    _await(go())


@needs_db
def test_check_and_fk_enforcement(uow):
    async def go():
        from sqlalchemy.exc import IntegrityError

        conn = uow.claims._conn
        await _survives(
            conn,
            lambda: uow.claims.save_claim({
                "id": str(uuid.uuid4()), "chemical_entity_id": None,
                "product_id": None, "product_label_id": None,
                "entity_role_id": None, "claim_type": "formula",
                "field_name": "formula", "claim_value_text": "C1",
                "claim_value_numeric": None, "claim_value_json": None,
                "unit": None, "provenance_type": "source_reported",
                "verification_status": "bogus", "confidence": "HIGH",
                "valid_from": None, "valid_until": None,
                "source_version": None, "freshness_class": None,
                "last_checked_at": None,
            }),
            IntegrityError,
            match="claims_verification",
        )
        await _survives(
            conn,
            lambda: uow.matches.save_normalization({
                "id": str(uuid.uuid4()),
                "observation_id": str(uuid.uuid4()),
                "normalized_text": "x", "normalization_method": "rule",
                "normalizer_version": "1.0.0", "confidence": None,
                "status": "complete",
            }),
            IntegrityError,
            match="ingredient_normal",
        )

    _await(go())


@needs_db
def test_trigger_blocks_event_mutation(uow):
    async def go():
        await uow.reviews.submit_review({
            "id": "REV-T1", "candidate_key": "k", "raw_text": "r",
            "normalized_text": "n", "identifier": None, "resolution": {},
            "verification_status": "queued", "evidence_context": {},
            "evidence_hash": "h", "priority": 0, "status": "queued",
            "reviewer": None,
        })
        from sqlalchemy import text as _text

        conn = uow.reviews._conn
        await _survives(
            conn,
            lambda: conn.execute(_text(
                "UPDATE review_events SET reason='x' "
                "WHERE review_id='REV-T1'")),
            Exception,
            match="append-only",
        )
        await _survives(
            conn,
            lambda: conn.execute(_text(
                "DELETE FROM review_events WHERE review_id='REV-T1'")),
            Exception,
            match="append-only",
        )
        events = await uow.reviews.list_events("REV-T1")
        assert len(events) == 1

    _await(go())


@needs_db
def test_rls_roles_behave(uow):
    async def go():
        engine = uow.engine
        conn = await engine.connect()
        try:
            await conn.execute(_text("SET ROLE authenticated"))
            rows = (await conn.execute(
                _text("SELECT count(*) FROM claims"))).scalar()
            assert rows == 0
            await _survives(
                conn,
                lambda: conn.execute(_text(
                    "INSERT INTO reviews(id, candidate_key, raw_text,"
                    " normalized_text, resolution, verification_status,"
                    " evidence_context, evidence_hash, priority, status)"
                    " VALUES ('x','k','r','n','{}','queued','{}','h',0,"
                    "'queued')")),
                Exception,
                match="permission denied",
            )
            await conn.execute(_text("RESET ROLE"))
            await conn.execute(_text("SET ROLE anon"))
            await _survives(
                conn,
                lambda: conn.execute(_text("SELECT count(*) FROM claims")),
                Exception,
                match="permission denied",
            )
        finally:
            await conn.close()

    _await(go())


@needs_db
def test_idempotent_resubmission(uow):
    async def go():
        payload = {
            "id": "REV-T2", "candidate_key": "k", "raw_text": "r",
            "normalized_text": "n", "identifier": None, "resolution": {},
            "verification_status": "queued", "evidence_context": {},
            "evidence_hash": "h", "priority": 0, "status": "queued",
            "reviewer": None,
        }
        assert await uow.reviews.submit_review(dict(payload)) == "REV-T2"
        assert await uow.reviews.submit_review(dict(payload)) == "REV-T2"
        assert len(await uow.reviews.list_events("REV-T2")) == 1

    _await(go())


@needs_db
def test_concurrent_claim_conflict(uow):
    async def go():
        await uow.reviews.submit_review({
            "id": "REV-T3", "candidate_key": "k", "raw_text": "r",
            "normalized_text": "n", "identifier": None, "resolution": {},
            "verification_status": "queued", "evidence_context": {},
            "evidence_hash": "h", "priority": 0, "status": "queued",
            "reviewer": None,
        })
        event = {
            "id": "REV-T3:001", "review_id": "REV-T3",
            "event_type": "ReviewClaimed", "actor": "human:a",
            "reason": "mine", "previous_state": "queued",
            "new_state": "in_review", "evidence_context_hash": "h",
            "rules_version": "1.0.0", "snapshot_version": "v",
        }
        await uow.reviews.transition_review(
            "REV-T3", event, "in_review", expect_status="queued")
        with pytest.raises(ReviewClaimConflict):
            await uow.reviews.transition_review(
                "REV-T3", dict(event, id="REV-T3:099"),
                "in_review", expect_status="queued")

    _await(go())


_LOOP = __import__("asyncio").new_event_loop()
__import__("asyncio").set_event_loop(_LOOP)


def _await(coro):
    return _LOOP.run_until_complete(coro)


async def _survives(conn, fn, exc, match=None):
    """Run fn expecting exc, rolling back to a savepoint after."""
    try:
        async with conn.begin_nested():
            await fn()
    except exc as err:
        if match is not None and match not in str(err):
            raise AssertionError("wrong constraint: %s" % err)
        return
    raise AssertionError("expected %s" % exc)

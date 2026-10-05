"""Live-Postgres canonical registration coverage (Stage 12).

Requires TEST_DATABASE_URL. The database is disposable: this module
drops the pipeline tables plus `chemical_entities` /
`ingredient_aliases` and re-applies migrations 001-003, so the schema
under test is exactly the committed migrations and the registry starts
empty -- the state a fresh production database is in.

What is proven here, against real Postgres rather than a double: the
import writes the approved snapshot, is idempotent across runs, records
provenance, is atomic, and the resolver registry projection built from
those rows can resolve the canonical entities.

Each test runs its coroutine on one dedicated event loop (the module
pattern already used by the Postgres API tests), so no connection is
ever shared across loops.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.repositories.postgres import PostgresUnitOfWork
from app.services.registration import (
    RegistrationError,
    RegistrationRejected,
    build_registry,
    register_canonical_entities,
)
from app.services.verification.adapters.snapshot import (
    SnapshotAdapter,
    SnapshotError,
)
from app.services.verification.gate import VERIFICATION_RULES_VERSION

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not TEST_URL, reason="no live test database configured")

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "snapshots" / "canonical_v1.json"
)
CITRIC_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"
BENZOATE_ID = "6223de87-1d0c-49f9-a926-e2b57e0fc8ae"
ETHANOL_ID = "c5a7fba9-c693-4b5e-ad26-9f61bfe6b161"

# Every table the migrations create. All are dropped and rebuilt so the
# schema under test is exactly migrations 001-003 on an empty database
# -- `chemical_entities` included, because this module's whole point is
# to start from an unregistered registry.
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
    """Rebuild the schema; entities are truncated, not hand-seeded."""
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
    # NullPool: every connection lives inside one event loop and is
    # closed again, so nothing leaks across loops.
    return create_async_engine(TEST_URL, poolclass=NullPool)


def _count(table: str) -> int:
    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            return await conn.fetchval("SELECT count(*) FROM %s" % table)
        finally:
            await conn.close()

    return _await(go())


def _row(entity_id: str) -> dict:
    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            record = await conn.fetchrow(
                "SELECT * FROM chemical_entities WHERE id = $1",
                entity_id)
            return dict(record) if record else {}
        finally:
            await conn.close()

    return _await(go())


def _json(value):
    """JSONB arrives as text unless a codec is installed."""
    return json.loads(value) if isinstance(value, str) else value


def _aliases() -> list:
    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            return [
                dict(record) for record in await conn.fetch(
                    "SELECT * FROM ingredient_aliases ORDER BY alias")
            ]
        finally:
            await conn.close()

    return _await(go())


def _adapter(path=None) -> SnapshotAdapter:
    return SnapshotAdapter(str(path or SNAPSHOT_PATH))


def _payload() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text())


def _write_snapshot(tmp_path, payload):
    path = tmp_path / "canonical_import_test.json"
    path.write_text(json.dumps(payload))
    return path


async def _import(snapshot_path=None, **kwargs):
    engine = _engine()
    try:
        return await register_canonical_entities(
            PostgresUnitOfWork(engine), _adapter(snapshot_path), **kwargs)
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_database():
    if not TEST_URL:
        pytest.skip("no live test database configured")
    _reset_database()


# -- the happy path ----------------------------------------------------


@needs_db
def test_import_writes_every_approved_record():
    report = _await(_import())
    assert report.considered == 4
    assert report.registered == 4
    assert report.already_present == 0
    assert report.rejected == 0
    assert _count("chemical_entities") == 4
    assert _count("ingredient_aliases") >= 1


@needs_db
def test_imported_row_keeps_approved_fields_and_provenance():
    _await(_import())
    row = _row(CITRIC_ID)
    assert row["preferred_name"] == "citric acid"
    assert row["entity_type"] == "chemical_entity"
    assert row["representation_type"] == "single_molecule"
    assert row["status"] == "verified"
    assert row["formula"] == "C6H8O7"
    assert row["inchikey"] == "KRKNYBCHXYNGOX-UHFFFAOYSA-N"
    assert row["pubchem_cid"] == 311
    assert float(row["molecular_weight"]) == 192.12
    assert row["molecular_weight_unit"] == "g/mol"
    # Provenance answers "why is this entity allowed to exist?".
    metadata = _json(row["metadata"])
    assert metadata["snapshot_version"] == "canonical_v1"
    assert metadata["rules_version"] == VERIFICATION_RULES_VERSION
    assert metadata["verification_status"] == "verified"
    assert metadata["provenance"]["source_id"] == "PUBCHEM"
    assert metadata["provenance"]["record_locator"]
    assert metadata["imported_by"] == "canonical-registration-import"
    assert row["first_verified_at"] is not None


@needs_db
def test_salt_type_is_preserved_without_an_invented_class():
    _await(_import())
    benzoate = _row(BENZOATE_ID)
    assert benzoate["preferred_name"] == "sodium benzoate"
    assert benzoate["representation_type"] == "salt"
    # No structure classification is derived for a salt.
    assert benzoate["chemical_class"] is None


@needs_db
def test_aliases_reference_their_entity_and_carry_no_source():
    _await(_import())
    entities = {
        row["id"]: row["preferred_name"]
        for row in _rows_of("chemical_entities")
    }
    aliases = _aliases()
    assert aliases
    for alias in aliases:
        assert alias["verified"] is True
        assert alias["source_id"] is None
        parent = entities[alias["chemical_entity_id"]]
        assert alias["alias"].lower() != parent.lower()


def _rows_of(table: str) -> list:
    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            return [
                dict(record) for record in await conn.fetch(
                    "SELECT id, preferred_name FROM %s" % table)
            ]
        finally:
            await conn.close()

    return _await(go())


# -- idempotency -------------------------------------------------------


@needs_db
def test_second_import_creates_no_duplicates():
    first = _await(_import())
    assert first.registered == 4
    second = _await(_import())
    assert second.registered == 0
    assert second.already_present == 4
    assert _count("chemical_entities") == 4


@needs_db
def test_identity_and_content_are_stable_across_imports():
    _await(_import())
    first = _row(ETHANOL_ID)
    alias_count = _count("ingredient_aliases")
    _await(_import())
    second = _row(ETHANOL_ID)
    assert str(first["id"]) == str(second["id"]) == ETHANOL_ID
    assert first["formula"] == second["formula"]
    assert first["molecular_weight"] == second["molecular_weight"]
    assert _count("ingredient_aliases") == alias_count


# -- refusal and atomicity --------------------------------------------


@needs_db
def test_unapproved_verification_state_writes_nothing(tmp_path):
    payload = _payload()
    payload["records"][1]["verification_status"] = "provisional"
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(RegistrationRejected) as excinfo:
        _await(_import(path))
    assert excinfo.value.report.registered == 0
    assert excinfo.value.report.rejected == 1
    # All-or-nothing against a real database: no rows survive.
    assert _count("chemical_entities") == 0
    assert _count("ingredient_aliases") == 0


@needs_db
def test_missing_provenance_is_refused(tmp_path):
    payload = _payload()
    payload["records"][0]["provenance"]["record_locator"] = ""
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(RegistrationRejected):
        _await(_import(path))
    assert _count("chemical_entities") == 0


@needs_db
def test_unsupported_entity_type_is_refused(tmp_path):
    payload = _payload()
    payload["records"][0]["entity_type"] = "product"
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(RegistrationRejected):
        _await(_import(path))
    assert _count("chemical_entities") == 0


@needs_db
def test_duplicate_entity_id_is_refused(tmp_path):
    payload = _payload()
    payload["records"][1]["entity_id"] = payload["records"][0]["entity_id"]
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(RegistrationRejected):
        _await(_import(path))
    assert _count("chemical_entities") == 0


@needs_db
def test_malformed_record_is_refused_by_the_parser(tmp_path):
    payload = _payload()
    payload["records"][0]["preferred_name"] = 42
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(SnapshotError):
        _await(_import(path))
    assert _count("chemical_entities") == 0


@needs_db
def test_wrong_rules_version_is_refused(tmp_path):
    payload = _payload()
    payload["verification_rule_version"] = "0.9.0"
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(RegistrationError):
        _await(_import(path))
    assert _count("chemical_entities") == 0


@needs_db
def test_wrong_expected_snapshot_version_is_refused():
    with pytest.raises(RegistrationError):
        _await(_import(expected_snapshot_version="canonical_v2"))
    assert _count("chemical_entities") == 0


@needs_db
def test_expected_snapshot_version_is_accepted():
    report = _await(_import(expected_snapshot_version="canonical_v1"))
    assert report.registered == 4


@needs_db
def test_failed_write_rolls_the_whole_import_back():
    """A mid-import write failure is a real database rollback.

    The injected failure must escape the transaction (it is not caught
    inside the scope), otherwise the earlier writes would be committed.
    """
    engine = _engine()

    async def go():
        unit_of_work = PostgresUnitOfWork(engine)
        async with unit_of_work.atomic() as scope:
            scope.entities = _FailingEntities(scope.entities)
            await register_canonical_entities(_ScopeShim(scope), _adapter())

    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            _await(go())
    finally:
        _await(engine.dispose())
    # Neither the two entities written before the failure nor the
    # aliases that would have followed the third survived.
    assert _count("chemical_entities") == 0
    assert _count("ingredient_aliases") == 0


class _ScopeShim:
    """Unit-of-work shim over an already-open real transaction.

    `atomic` yields the current scope instead of opening a nested
    transaction, so the enclosing rollback is the only one in play.
    """

    def __init__(self, scope):
        self.entities = scope.entities

    @asynccontextmanager
    async def atomic(self):
        yield self


class _FailingEntities:
    """Entity repository that fails on the third entity write."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    async def get_entity(self, entity_id, *, role="service"):
        return await self._inner.get_entity(entity_id, role=role)

    async def save_entity(self, row, *, role="service"):
        self.calls += 1
        if self.calls == 3:
            raise RuntimeError("injected failure")
        return await self._inner.save_entity(row, role=role)

    async def save_alias(self, row, *, role="service"):
        return await self._inner.save_alias(row, role=role)


# -- registry integration ----------------------------------------------


@needs_db
def test_registry_projection_resolves_registered_entities():
    _await(_import())

    async def load():
        engine = _engine()
        try:
            unit_of_work = PostgresUnitOfWork(engine)
            async with unit_of_work.atomic() as scope:
                entities = await scope.entities.list_entities(
                    role="service")
                aliases = await scope.entities.list_aliases(role="service")
            return entities, aliases
        finally:
            await engine.dispose()

    entities, aliases = _await(load())
    registry = build_registry(entities, aliases, version=str(len(entities)))
    assert registry.registry_id == "canonical_registry"
    hits = registry.lookup_exact_name("citric acid")
    assert len(hits) == 1
    assert hits[0].entity_class == "single_molecule"
    assert hits[0].source == "PUBCHEM"
    assert registry.lookup_identifier("e330")
    # Nothing that was not registered is resolvable.
    assert registry.lookup_exact_name("unobtainium") == []


@needs_db
def test_claims_can_reference_imported_entities():
    """The foreign key that blocked unregistered decisions now holds."""
    _await(_import())

    async def go():
        conn = await asyncpg.connect(**_asyncpg_kwargs())
        try:
            await conn.execute(
                "INSERT INTO claims (id, chemical_entity_id, "
                "claim_type, field_name, claim_value_text, "
                "provenance_type, verification_status, confidence) "
                "VALUES ('11111111-1111-4111-8111-111111111111', "
                "$1, 'identity', 'identity', 'citric acid', "
                "'curated', 'verified', 'HIGH')",
                CITRIC_ID)
            return await conn.fetchval("SELECT count(*) FROM claims")
        finally:
            await conn.close()

    assert _await(go()) == 1


@needs_db
def test_import_touches_no_product_scan_or_role_data():
    _await(_import())
    # Seeded reference data from migration 002 survives untouched.
    assert _count("sources") > 0
    assert _count("domains") > 0
    # Nothing else in the database was written by the import.
    for table in ("roles", "reviews", "claims", "claim_sources",
                  "verification_decisions", "verification_events",
                  "ingredient_observations", "ingredient_candidates",
                  "entity_matches"):
        assert _count(table) == 0, table

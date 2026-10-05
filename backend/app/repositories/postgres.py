"""Postgres/Supabase repository implementations (SQLAlchemy Core).

Mirrors migration 003 table-for-table; a static test asserts every
table/column here exists in the migration SQL. All writes are
parameter-bound (no SQL string construction from data), use
ON CONFLICT DO NOTHING for idempotent retries, and run on the
caller-supplied connection so :func:`atomic` scopes transactions.
Application-level role checks mirror the memory implementations
(RLS enforces the same boundary in the database).

No live database is required to import or unit-test this module;
live integration tests connect only when TEST_DATABASE_URL is set.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    NUMERIC,
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    Date,
    Integer,
    MetaData,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from app.repositories.protocols import (
    AUTHENTICATED_ROLE,
    SERVICE_ROLE,
)

__all__ = [
    "metadata",
    "TABLES",
    "ReviewClaimConflict",
    "PostgresMatchRepository",
    "PostgresClaimRepository",
    "PostgresEvidenceRepository",
    "PostgresVerificationRepository",
    "PostgresReviewRepository",
    "PostgresUnitOfWork",
]


class ReviewClaimConflict(ValueError):
    """A conditional claim/transition lost its race (deterministic)."""


metadata = MetaData()
TABLES = {}


def _id() -> Column:
    return Column("id", PG_UUID(as_uuid=False), primary_key=True)


def _ts(name: str) -> Column:
    return Column(name, TIMESTAMP(timezone=True))


def _register(table: Table) -> Table:
    TABLES[table.name] = table
    return table


_register(Table(
    "ingredient_observations", metadata,
    _id(),
    Column("scan_id", PG_UUID(as_uuid=False), nullable=False),
    Column("sequence_number", Integer, nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("display_text", Text),
    Column("source_type", Text, nullable=False),
    Column("ocr_run_id", PG_UUID(as_uuid=False)),
    Column("ocr_confidence", NUMERIC),
    Column("user_corrected", Boolean, nullable=False, default=False),
    Column("original_text", Text),
    Column("correction_reason", Text),
    _ts("created_at"), _ts("updated_at"),
))

_register(Table(
    "ingredient_normalizations", metadata,
    _id(),
    Column("observation_id", PG_UUID(as_uuid=False), nullable=False),
    Column("normalized_text", Text, nullable=False),
    Column("normalization_method", Text, nullable=False),
    Column("normalizer_version", Text),
    Column("confidence", NUMERIC),
    Column("status", Text, nullable=False),
    _ts("created_at"), _ts("updated_at"),
))

_register(Table(
    "ingredient_candidates", metadata,
    _id(),
    Column("normalization_id", PG_UUID(as_uuid=False), nullable=False),
    Column("chemical_entity_id", PG_UUID(as_uuid=False)),
    Column("candidate_name", Text, nullable=False),
    Column("match_status", Text, nullable=False),
    Column("candidate_score", NUMERIC),
    Column("match_reasons", JSONB),
    Column("source_id", PG_UUID(as_uuid=False)),
    _ts("created_at"),
))

_register(Table(
    "entity_matches", metadata,
    _id(),
    Column("normalization_id", PG_UUID(as_uuid=False), nullable=False),
    Column("chemical_entity_id", PG_UUID(as_uuid=False)),
    Column("match_status", Text, nullable=False),
    Column("identity_confidence", Text, nullable=False),
    Column("selected_by", Text),
    Column("selected_at", TIMESTAMP(timezone=True)),
    Column("reason_code", Text),
    Column("review_status", Text),
    Column("review_notes", Text),
    _ts("created_at"), _ts("updated_at"),
))

_register(Table(
    "claims", metadata,
    _id(),
    Column("chemical_entity_id", PG_UUID(as_uuid=False)),
    Column("product_id", PG_UUID(as_uuid=False)),
    Column("product_label_id", PG_UUID(as_uuid=False)),
    Column("entity_role_id", PG_UUID(as_uuid=False)),
    Column("claim_type", Text, nullable=False),
    Column("field_name", Text),
    Column("claim_value_text", Text),
    Column("claim_value_numeric", NUMERIC),
    Column("claim_value_json", JSONB),
    Column("unit", Text),
    Column("provenance_type", Text, nullable=False),
    Column("verification_status", Text, nullable=False),
    Column("confidence", Text, nullable=False),
    Column("valid_from", TIMESTAMP(timezone=True)),
    Column("valid_until", TIMESTAMP(timezone=True)),
    Column("source_version", Text),
    Column("freshness_class", Text),
    Column("last_checked_at", TIMESTAMP(timezone=True)),
    _ts("created_at"), _ts("updated_at"),
))

_register(Table(
    "claim_sources", metadata,
    Column("claim_id", PG_UUID(as_uuid=False), primary_key=True),
    Column("source_id", PG_UUID(as_uuid=False), primary_key=True),
    Column("support_type", Text, nullable=False),
    Column("support_strength", Text, nullable=False),
    Column("source_locator", Text),
    Column("source_value", Text),
    Column("review_status", Text),
    Column("review_notes", Text),
    Column("provider", Text),
    Column("source_version", Text),
    Column("retrieved_at", TIMESTAMP(timezone=True)),
    Column("response_hash", Text),
    _ts("created_at"),
))

_register(Table(
    "verification_events", metadata,
    _id(),
    Column("claim_id", PG_UUID(as_uuid=False), nullable=False),
    Column("previous_status", Text),
    Column("new_status", Text, nullable=False),
    Column("previous_confidence", Text),
    Column("new_confidence", Text),
    Column("review_method", Text, nullable=False),
    Column("reviewer_type", Text, nullable=False),
    Column("reason", Text),
    Column("source_id", PG_UUID(as_uuid=False)),
    _ts("created_at"),
))

_register(Table(
    "verification_decisions", metadata,
    _id(),
    Column("entity_match_id", PG_UUID(as_uuid=False)),
    Column("candidate_key", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("identity_confidence", Text, nullable=False),
    Column("rules_version", Text, nullable=False),
    Column("snapshot_version", Text, nullable=False),
    Column("evidence_context_hash", Text, nullable=False),
    Column("reason", Text),
    Column("warnings", JSONB),
    Column("gate_results", JSONB),
    Column("claim_ids", JSONB),
    _ts("created_at"),
))

_register(Table(
    "reviews", metadata,
    Column("id", Text, primary_key=True),
    Column("candidate_key", Text, nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("normalized_text", Text, nullable=False),
    Column("identifier", Text),
    Column("resolution", JSONB, nullable=False),
    Column("verification_status", Text, nullable=False),
    Column("evidence_context", JSONB, nullable=False),
    Column("evidence_hash", Text, nullable=False),
    Column("priority", Integer, nullable=False),
    Column("status", Text, nullable=False),
    Column("reviewer", Text),
    _ts("created_at"), _ts("updated_at"),
))

_register(Table(
    "review_events", metadata,
    Column("id", Text, primary_key=True),
    Column("review_id", Text, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("previous_state", Text),
    Column("new_state", Text, nullable=False),
    Column("evidence_context_hash", Text, nullable=False),
    Column("rules_version", Text, nullable=False),
    Column("snapshot_version", Text, nullable=False),
    _ts("created_at"),
))


_SOURCES_TABLE = Table(
    "sources", metadata,
    Column("id", PG_UUID(as_uuid=False), primary_key=True),
    Column("name", Text),
    Column("publisher", Text),
    Column("source_type", Text),
    Column("url", Text),
    Column("identifier", Text),
    Column("jurisdiction", Text),
    Column("language_code", Text),
    Column("authority_level", Text),
    Column("license", Text),
    Column("redistribution_allowed", Boolean),
    Column("caching_allowed", Boolean),
    Column("publication_date", Date),
    Column("retrieved_at", TIMESTAMP(timezone=True)),
    Column("last_checked_at", TIMESTAMP(timezone=True)),
    Column("freshness_class", Text),
    Column("status", Text),
    Column("notes", Text),
    Column("created_at", TIMESTAMP(timezone=True)),
    Column("updated_at", TIMESTAMP(timezone=True)),
    extend_existing=True,
)

_ENTITIES_TABLE = Table(
    "chemical_entities", metadata,
    Column("id", PG_UUID(as_uuid=False), primary_key=True),
    Column("preferred_name", Text),
    Column("entity_type", Text),
    Column("representation_type", Text),
    Column("status", Text),
    Column("formula", Text),
    Column("molecular_weight", NUMERIC),
    Column("cas_number", Text),
    Column("pubchem_cid", BigInteger),
    Column("chebi_id", Text),
    Column("inchi", Text),
    Column("inchikey", Text),
    Column("smiles", Text),
    Column("chemical_class", Text),
    Column("structure_status", Text),
    extend_existing=True,
)


def _require_write(role: str) -> None:
    if role != SERVICE_ROLE:
        raise PermissionError("writes require the service role")


def _require_read(role: str) -> None:
    if role not in (SERVICE_ROLE, AUTHENTICATED_ROLE):
        raise PermissionError("reads require an authenticated role")


def _row(result_row) -> dict:
    return dict(result_row._mapping)


class _Bound:
    """Shared connection binding for repository implementations."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._conn = connection


class PostgresMatchRepository(_Bound):
    """Observation chain store (Postgres)."""

    async def save_observation(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        stmt = insert(TABLES["ingredient_observations"]).values(**row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return str(row["id"])

    async def save_normalization(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        stmt = insert(TABLES["ingredient_normalizations"]).values(**row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return str(row["id"])

    async def save_candidates(self, rows: list, *, role: str = SERVICE_ROLE) -> list:
        _require_write(role)
        ids = []
        for row in rows:
            stmt = insert(TABLES["ingredient_candidates"]).values(**row)
            stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
            await self._conn.execute(stmt)
            ids.append(str(row["id"]))
        return ids

    async def save_match(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        stmt = insert(TABLES["entity_matches"]).values(**row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return str(row["id"])

    async def get_normalization_for_observation(
        self,
        observation_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        norms = TABLES["ingredient_normalizations"]
        result = await self._conn.execute(
            select(norms).where(norms.c.observation_id == observation_id)
        )
        row = result.first()
        if row is None:
            raise KeyError(observation_id)
        return _row(row)

    async def get_chain(
        self,
        normalization_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        norms = TABLES["ingredient_normalizations"]
        result = await self._conn.execute(
            select(norms).where(norms.c.id == normalization_id)
        )
        norm = result.first()
        if norm is None:
            raise KeyError(normalization_id)
        norm_row = _row(norm)
        obs = TABLES["ingredient_observations"]
        result = await self._conn.execute(
            select(obs).where(obs.c.id == norm_row["observation_id"])
        )
        cands = TABLES["ingredient_candidates"]
        result_c = await self._conn.execute(
            select(cands).where(cands.c.normalization_id == normalization_id)
        )
        matches = TABLES["entity_matches"]
        result_m = await self._conn.execute(
            select(matches).where(matches.c.normalization_id == normalization_id)
        )
        first_match = result_m.first()
        return {
            "observation": _row(result.first()),
            "normalization": norm_row,
            "candidates": [_row(r) for r in result_c.all()],
            "match": _row(first_match) if first_match else None,
        }


class PostgresClaimRepository(_Bound):
    """Claim rows with atomic status+event updates (Postgres)."""

    async def save_claim(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        stmt = insert(TABLES["claims"]).values(**row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return str(row["id"])

    async def get_claim(self, claim_id: str, *, role: str = AUTHENTICATED_ROLE) -> dict:
        _require_read(role)
        claims = TABLES["claims"]
        result = await self._conn.execute(
            select(claims).where(claims.c.id == claim_id)
        )
        row = result.first()
        if row is None:
            raise KeyError(claim_id)
        return _row(row)

    async def list_by_entity(
        self,
        entity_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        claims = TABLES["claims"]
        result = await self._conn.execute(
            select(claims).where(claims.c.chemical_entity_id == entity_id)
        )
        return [_row(r) for r in result.all()]

    async def update_claim_status(
        self,
        claim_id: str,
        new_status: str,
        new_confidence: str,
        *,
        event: dict,
        role: str = SERVICE_ROLE,
    ) -> dict:
        """Status update plus event append in one transaction scope."""
        _require_write(role)
        claims = TABLES["claims"]
        result = await self._conn.execute(
            update(claims)
            .where(claims.c.id == claim_id)
            .values(verification_status=new_status, confidence=new_confidence)
            .returning(claims)
        )
        row = result.first()
        if row is None:
            raise KeyError(claim_id)
        events = TABLES["verification_events"]
        stmt = insert(events).values(**event)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return _row(row)


class PostgresEvidenceRepository(_Bound):
    """Source rows and claim-source links (Postgres)."""

    async def ensure_source(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        known = {c.name for c in _SOURCES_TABLE.columns}
        clean = {k: v for k, v in row.items() if k in known}
        result = await self._conn.execute(
            select(_SOURCES_TABLE.c.id).where(
                _SOURCES_TABLE.c.name == clean["name"])
        )
        found = result.first()
        if found is not None:
            return str(found[0])
        stmt = insert(_SOURCES_TABLE).values(**clean)
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await self._conn.execute(stmt)
        result = await self._conn.execute(
            select(_SOURCES_TABLE.c.id).where(
                _SOURCES_TABLE.c.name == clean["name"])
        )
        return str(result.first()[0])

    async def link_source(self, row: dict, *, role: str = SERVICE_ROLE) -> None:
        _require_write(role)
        links = TABLES["claim_sources"]
        stmt = insert(links).values(**row)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["claim_id", "source_id"]
        )
        await self._conn.execute(stmt)

    async def list_for_claim(
        self,
        claim_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        links = TABLES["claim_sources"]
        result = await self._conn.execute(
            select(links).where(links.c.claim_id == claim_id)
        )
        return [_row(r) for r in result.all()]

    async def get_source(
        self,
        source_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        result = await self._conn.execute(
            select(_SOURCES_TABLE).where(
                _SOURCES_TABLE.c.id == source_id)
        )
        row = result.first()
        if row is None:
            raise KeyError(source_id)
        return _row(row)


class PostgresEntityRepository(_Bound):
    """Canonical entity existence checks (Postgres, read-only)."""

    async def get_entity(
        self,
        entity_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        result = await self._conn.execute(
            select(_ENTITIES_TABLE).where(
                _ENTITIES_TABLE.c.id == entity_id)
        )
        row = result.first()
        if row is None:
            raise KeyError(entity_id)
        return _row(row)


class PostgresVerificationRepository(_Bound):
    """Decisions plus claim-level event log (Postgres)."""

    async def save_decision(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        decisions = TABLES["verification_decisions"]
        stmt = insert(decisions).values(**row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return str(row["id"])

    async def get_decision(
        self,
        verification_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        decisions = TABLES["verification_decisions"]
        result = await self._conn.execute(
            select(decisions).where(decisions.c.id == verification_id)
        )
        row = result.first()
        if row is None:
            raise KeyError(verification_id)
        return _row(row)

    async def list_decisions(
        self,
        *,
        status: Optional[str] = None,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        decisions = TABLES["verification_decisions"]
        query = select(decisions)
        if status is not None:
            query = query.where(decisions.c.status == status)
        result = await self._conn.execute(query)
        return [_row(r) for r in result.all()]

    async def append_event(self, row: dict, *, role: str = SERVICE_ROLE) -> bool:
        _require_write(role)
        events = TABLES["verification_events"]
        stmt = insert(events).values(**row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        result = await self._conn.execute(stmt)
        return result.rowcount == 1

    async def list_claim_events(
        self,
        claim_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        events = TABLES["verification_events"]
        result = await self._conn.execute(
            select(events).where(events.c.claim_id == claim_id)
        )
        return [_row(r) for r in result.all()]


class PostgresReviewRepository(_Bound):
    """Reviews with conditional transitions (Postgres)."""

    async def submit_review(self, item: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        reviews = TABLES["reviews"]
        stmt = insert(reviews).values(**item)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        created = {
            "id": "%s:000" % item["id"],
            "review_id": item["id"],
            "event_type": "ReviewCreated",
            "actor": "system:review-router",
            "reason": "routed for human review",
            "previous_state": "",
            "new_state": item["status"],
            "evidence_context_hash": item["evidence_hash"],
            "rules_version": "",
            "snapshot_version": "",
        }
        events = TABLES["review_events"]
        stmt = insert(events).values(**created)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return str(item["id"])

    async def transition_review(
        self,
        review_id: str,
        event: dict,
        new_status: str,
        *,
        expect_status: Optional[str] = None,
        role: str = SERVICE_ROLE,
    ) -> dict:
        """Conditional UPDATE..WHERE plus event insert, one scope."""
        _require_write(role)
        reviews = TABLES["reviews"]
        query = (
            update(reviews)
            .where(reviews.c.id == review_id)
            .values(status=new_status, reviewer=event.get("actor"))
        )
        if expect_status is not None:
            query = query.where(reviews.c.status == expect_status)
        query = query.returning(reviews)
        result = await self._conn.execute(query)
        row = result.first()
        if row is None:
            check = await self._conn.execute(
                select(reviews.c.id).where(reviews.c.id == review_id)
            )
            if check.first() is None:
                raise KeyError(review_id)
            raise ReviewClaimConflict(
                "review %s changed underfoot" % review_id
            )
        events = TABLES["review_events"]
        stmt = insert(events).values(**event)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        await self._conn.execute(stmt)
        return _row(row)

    async def append_event(self, event: dict, *, role: str = SERVICE_ROLE) -> bool:
        _require_write(role)
        events = TABLES["review_events"]
        stmt = insert(events).values(**event)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        result = await self._conn.execute(stmt)
        return result.rowcount == 1

    async def get_review(
        self,
        review_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        reviews = TABLES["reviews"]
        result = await self._conn.execute(
            select(reviews).where(reviews.c.id == review_id)
        )
        row = result.first()
        if row is None:
            raise KeyError(review_id)
        return _row(row)

    async def list_pending(self, *, role: str = AUTHENTICATED_ROLE) -> list:
        _require_read(role)
        reviews = TABLES["reviews"]
        result = await self._conn.execute(
            select(reviews)
            .where(reviews.c.status.in_(["queued", "in_review"]))
            .order_by(reviews.c.priority, reviews.c.id)
        )
        return [_row(r) for r in result.all()]

    async def list_events(
        self,
        review_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        events = TABLES["review_events"]
        result = await self._conn.execute(
            select(events).where(events.c.review_id == review_id)
        )
        return [_row(r) for r in result.all()]


class PostgresUnitOfWork:
    """Engine-bound repositories sharing transactional scopes."""

    def __init__(self, engine) -> None:
        self._engine: AsyncEngine = engine

    def atomic(self):
        """Transaction scope yielding a bound unit of work."""
        return _PostgresScope(self._engine)


class _PostgresScope:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connect_cm = None
        self._tx_cm = None
        self._connection: Optional[AsyncConnection] = None

    async def __aenter__(self) -> "_PostgresScope":
        self._connect_cm = self._engine.connect()
        self._connection = await self._connect_cm.__aenter__()
        self._tx_cm = self._connection.begin()
        await self._tx_cm.__aenter__()
        self.matches = PostgresMatchRepository(self._connection)
        self.claims = PostgresClaimRepository(self._connection)
        self.evidence = PostgresEvidenceRepository(self._connection)
        self.verification = PostgresVerificationRepository(self._connection)
        self.reviews = PostgresReviewRepository(self._connection)
        self.entities = PostgresEntityRepository(self._connection)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                await self._tx_cm.__aexit__(exc_type, exc, tb)
            else:
                await self._tx_cm.__aexit__(exc_type, exc, tb)
        finally:
            await self._connect_cm.__aexit__(exc_type, exc, tb)
        return False

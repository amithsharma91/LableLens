"""In-memory repository implementations (contract reference).

Used by contract tests, offline development, and as fakes for future
service tests. Writes require the service role; reads require an
authenticated-or-service role. Event tables expose append and read
only -- no update or delete path exists by construction. Multi-write
operations run inside :meth:`MemoryUnitOfWork.transaction`, which
rolls back to a snapshot on error.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Dict, Optional

from app.repositories.protocols import (
    AUTHENTICATED_ROLE,
    SERVICE_ROLE,
)

__all__ = [
    "ReviewClaimConflict",
    "DuplicateRow",
    "MemoryMatchRepository",
    "MemoryClaimRepository",
    "MemoryEvidenceRepository",
    "MemoryVerificationRepository",
    "MemoryReviewRepository",
    "MemoryUnitOfWork",
]


class ReviewClaimConflict(ValueError):
    """A conditional claim/transition lost its race (deterministic)."""


class DuplicateRow(ValueError):
    """A logical duplicate slipped past idempotent guards (a bug)."""


def _require_write(role: str) -> None:
    if role != SERVICE_ROLE:
        raise PermissionError("writes require the service role")


def _require_read(role: str) -> None:
    if role not in (SERVICE_ROLE, AUTHENTICATED_ROLE):
        raise PermissionError("reads require an authenticated role")


class _Store:
    """Dict tables with deep-copy isolation and PK dedupe."""

    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, dict]] = {}

    def table(self, name: str) -> Dict[str, dict]:
        return self.tables.setdefault(name, {})

    def insert(self, table: str, row: dict, *, key: str = "id") -> str:
        rows = self.table(table)
        row_id = str(row[key])
        if row_id in rows:
            return row_id
        rows[row_id] = copy.deepcopy(row)
        return row_id

    def snapshot(self) -> dict:
        """Deep copy for transaction rollback."""
        return copy.deepcopy(self.tables)

    def restore(self, snapshot: dict) -> None:
        self.tables = snapshot


class MemoryMatchRepository:
    """Observation chain store (memory)."""

    def __init__(self, store: Optional[_Store] = None) -> None:
        self._store = store or _Store()

    async def save_observation(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        return self._store.insert("ingredient_observations", row)

    async def save_normalization(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        parent = row["observation_id"]
        if parent not in self._store.table("ingredient_observations"):
            raise ValueError("observation %s missing" % parent)
        return self._store.insert("ingredient_normalizations", row)

    async def save_candidates(self, rows: list, *, role: str = SERVICE_ROLE) -> list:
        _require_write(role)
        return [self._store.insert("ingredient_candidates", r) for r in rows]

    async def save_match(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        parent = row["normalization_id"]
        if parent not in self._store.table("ingredient_normalizations"):
            raise ValueError("normalization %s missing" % parent)
        return self._store.insert("entity_matches", row)

    async def get_chain(
        self,
        normalization_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        norms = self._store.table("ingredient_normalizations")
        if normalization_id not in norms:
            raise KeyError(normalization_id)
        norm = copy.deepcopy(norms[normalization_id])
        obs = copy.deepcopy(
            self._store.table("ingredient_observations")[norm["observation_id"]]
        )
        cands = [
            copy.deepcopy(r)
            for r in self._store.table("ingredient_candidates").values()
            if r["normalization_id"] == normalization_id
        ]
        matches = [
            copy.deepcopy(r)
            for r in self._store.table("entity_matches").values()
            if r["normalization_id"] == normalization_id
        ]
        return {
            "observation": obs,
            "normalization": norm,
            "candidates": cands,
            "match": matches[0] if matches else None,
        }


class MemoryClaimRepository:
    """Claim rows with atomic status+event updates (memory)."""

    def __init__(self, store: Optional[_Store] = None) -> None:
        self._store = store or _Store()

    async def save_claim(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        return self._store.insert("claims", row)

    async def get_claim(self, claim_id: str, *, role: str = AUTHENTICATED_ROLE) -> dict:
        _require_read(role)
        try:
            return copy.deepcopy(self._store.table("claims")[claim_id])
        except KeyError:
            raise KeyError(claim_id)

    async def list_by_entity(
        self,
        entity_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        return [
            copy.deepcopy(r)
            for r in self._store.table("claims").values()
            if (r.get("chemical_entity_id") or "") == entity_id
        ]

    async def update_claim_status(
        self,
        claim_id: str,
        new_status: str,
        new_confidence: str,
        *,
        event: dict,
        role: str = SERVICE_ROLE,
    ) -> dict:
        """Status update plus event append as one atomic step."""
        _require_write(role)
        claims = self._store.table("claims")
        if claim_id not in claims:
            raise KeyError(claim_id)
        claims[claim_id] = {
            **claims[claim_id],
            "verification_status": new_status,
            "confidence": new_confidence,
        }
        self._store.insert("verification_events", event)
        return copy.deepcopy(claims[claim_id])


class MemoryEvidenceRepository:
    """Source registry rows and claim-source links (memory)."""

    def __init__(self, store: Optional[_Store] = None) -> None:
        self._store = store or _Store()

    async def ensure_source(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        for existing in self._store.table("sources").values():
            if existing.get("name") == row.get("name"):
                return str(existing["id"])
        return self._store.insert("sources", row)

    async def link_source(self, row: dict, *, role: str = SERVICE_ROLE) -> None:
        _require_write(role)
        key = "%s|%s" % (row["claim_id"], row["source_id"])
        table = self._store.table("claim_sources")
        if key not in table:
            table[key] = copy.deepcopy(row)

    async def list_for_claim(
        self,
        claim_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        return [
            copy.deepcopy(r)
            for r in self._store.table("claim_sources").values()
            if r["claim_id"] == claim_id
        ]


class MemoryVerificationRepository:
    """Decisions plus claim-level event log (memory)."""

    def __init__(self, store: Optional[_Store] = None) -> None:
        self._store = store or _Store()

    async def save_decision(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
        return self._store.insert("verification_decisions", row)

    async def get_decision(
        self,
        verification_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        try:
            return copy.deepcopy(
                self._store.table("verification_decisions")[verification_id]
            )
        except KeyError:
            raise KeyError(verification_id)

    async def list_decisions(
        self,
        *,
        status: Optional[str] = None,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        rows = self._store.table("verification_decisions").values()
        return [
            copy.deepcopy(r) for r in rows
            if status is None or r.get("status") == status
        ]

    async def append_event(self, row: dict, *, role: str = SERVICE_ROLE) -> bool:
        _require_write(role)
        table = self._store.table("verification_events")
        if row["id"] in table:
            return False
        table[row["id"]] = copy.deepcopy(row)
        return True

    async def list_claim_events(
        self,
        claim_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        return [
            copy.deepcopy(r)
            for r in self._store.table("verification_events").values()
            if r["claim_id"] == claim_id
        ]


class MemoryReviewRepository:
    """Reviews with conditional transitions (memory)."""

    def __init__(self, store: Optional[_Store] = None) -> None:
        self._store = store or _Store()

    async def submit_review(self, item: dict, *, role: str = SERVICE_ROLE) -> str:
        _require_write(role)
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
        self._store.insert("reviews", item)
        self._store.insert("review_events", created)
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
        """Move status iff current matches expectation, plus event."""
        _require_write(role)
        reviews = self._store.table("reviews")
        if review_id not in reviews:
            raise KeyError(review_id)
        current = reviews[review_id]["status"]
        if expect_status is not None and current != expect_status:
            raise ReviewClaimConflict(
                "review %s is %s, expected %s"
                % (review_id, current, expect_status)
            )
        reviews[review_id] = {
            **reviews[review_id],
            "status": new_status,
            "reviewer": event.get("actor", reviews[review_id].get("reviewer")),
        }
        self._store.insert("review_events", event)
        return copy.deepcopy(reviews[review_id])

    async def append_event(self, event: dict, *, role: str = SERVICE_ROLE) -> bool:
        _require_write(role)
        table = self._store.table("review_events")
        if event["id"] in table:
            return False
        table[event["id"]] = copy.deepcopy(event)
        return True

    async def get_review(
        self,
        review_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        _require_read(role)
        try:
            return copy.deepcopy(self._store.table("reviews")[review_id])
        except KeyError:
            raise KeyError(review_id)

    async def list_pending(self, *, role: str = AUTHENTICATED_ROLE) -> list:
        _require_read(role)
        open_statuses = ("queued", "in_review")
        rows = [
            r for r in self._store.table("reviews").values()
            if r.get("status") in open_statuses
        ]
        rows.sort(key=lambda r: (r.get("priority", 99), r.get("id", "")))
        return [copy.deepcopy(r) for r in rows]

    async def list_events(
        self,
        review_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        _require_read(role)
        return [
            copy.deepcopy(r)
            for r in self._store.table("review_events").values()
            if r["review_id"] == review_id
        ]


class MemoryUnitOfWork:
    """Shared store plus snapshot-rollback transactions (memory)."""

    def __init__(self) -> None:
        store = _Store()
        self.matches = MemoryMatchRepository(store)
        self.claims = MemoryClaimRepository(store)
        self.evidence = MemoryEvidenceRepository(store)
        self.verification = MemoryVerificationRepository(store)
        self.reviews = MemoryReviewRepository(store)
        self._store = store

    @contextmanager
    def transaction(self):
        """Roll back all tables when the block raises."""
        snapshot = self._store.snapshot()
        try:
            yield self
        except Exception:
            self._store.restore(snapshot)
            raise

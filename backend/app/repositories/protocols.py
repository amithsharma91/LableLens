"""Repository contracts for Stage-10 persistence (Protocols).

Service logic depends on these interfaces, never on Supabase or
Postgres directly. Every write defaults to the service role;
repositories reject other roles themselves (application-level
defense in depth; the database adds RLS on top).

Roles: "service" (backend only, full access), "authenticated"
(reads on audit data), "anon" (nothing). No per-user row scoping
yet: user_id does not exist on these tables (auth stage).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

SERVICE_ROLE = "service"
AUTHENTICATED_ROLE = "authenticated"
ANON_ROLE = "anon"

READ_ROLES = (SERVICE_ROLE, AUTHENTICATED_ROLE)


@runtime_checkable
class MatchRepository(Protocol):
    """Observation -> normalization -> candidates -> match chain."""

    async def save_observation(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        """Insert an ingredient_observations row. Returns id."""

    async def save_normalization(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        """Insert an ingredient_normalizations row. Returns id."""

    async def save_candidates(self, rows: list, *, role: str = SERVICE_ROLE) -> list:
        """Insert ingredient_candidates rows. Returns ids."""

    async def save_match(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        """Insert an entity_matches row. Returns id."""

    async def get_chain(
        self,
        normalization_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        """Return observation + normalization + candidates + match."""

    async def get_normalization_for_observation(
        self,
        observation_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        """Return the normalization row for one observation."""


@runtime_checkable
class ClaimRepository(Protocol):
    """Claim rows with independent verification states."""

    async def save_claim(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        """Insert a claims row (idempotent on deterministic id)."""

    async def get_claim(self, claim_id: str, *, role: str = AUTHENTICATED_ROLE) -> dict:
        """Return one claim row by id."""

    async def list_by_entity(
        self,
        entity_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        """Return all claim rows for one entity."""

    async def update_claim_status(
        self,
        claim_id: str,
        new_status: str,
        new_confidence: str,
        *,
        event: dict,
        role: str = SERVICE_ROLE,
    ) -> dict:
        """Update claim status AND append its verification event atomically."""


@runtime_checkable
class EvidenceRepository(Protocol):
    """Source registry rows and claim-source evidence links."""

    async def ensure_source(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        """Return the sources id for a name, inserting when absent."""

    async def link_source(self, row: dict, *, role: str = SERVICE_ROLE) -> None:
        """Insert a claim_sources row (idempotent on its PK)."""

    async def list_for_claim(
        self,
        claim_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        """Return evidence links for one claim."""

    async def get_source(
        self,
        source_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        """Return one source registry row by id."""


@runtime_checkable
class VerificationRepository(Protocol):
    """Verification decisions plus the claim-level event log."""

    async def save_decision(self, row: dict, *, role: str = SERVICE_ROLE) -> str:
        """Insert a verification_decisions row (idempotent on id)."""

    async def get_decision(
        self,
        verification_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        """Return one decision by id."""

    async def list_decisions(
        self,
        *,
        status: Optional[str] = None,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        """List decisions, optionally filtered by status."""

    async def append_event(self, row: dict, *, role: str = SERVICE_ROLE) -> bool:
        """Append a verification_events row. False when deduplicated."""

    async def list_claim_events(
        self,
        claim_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        """Return a claim's verification events in recorded order."""


@runtime_checkable
class ReviewRepository(Protocol):
    """Reviews with conditional transitions and append-only events."""

    async def submit_review(self, item: dict, *, role: str = SERVICE_ROLE) -> str:
        """Insert a review row plus its ReviewCreated event atomically."""

    async def transition_review(
        self,
        review_id: str,
        event: dict,
        new_status: str,
        *,
        expect_status: Optional[str] = None,
        role: str = SERVICE_ROLE,
    ) -> dict:
        """Conditionally move status and append the event atomically."""

    async def append_event(self, event: dict, *, role: str = SERVICE_ROLE) -> bool:
        """Append a review_events row. False when deduplicated."""

    async def get_review(
        self,
        review_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        """Return one review row by id."""

    async def list_pending(self, *, role: str = AUTHENTICATED_ROLE) -> list:
        """Return open reviews in priority order."""

    async def list_events(
        self,
        review_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> list:
        """Return a review's events in recorded order."""


@runtime_checkable
class EntityRepository(Protocol):
    """Canonical entity existence/lookup (read-only).

    `chemical_entities` is the authority on which canonical entities
    exist. Claims link to it by foreign key, so the service checks
    existence before persisting a decision that names an entity.
    Registration of new entities is a service-role operation with no
    API route in this stage.
    """

    async def get_entity(
        self,
        entity_id: str,
        *,
        role: str = AUTHENTICATED_ROLE,
    ) -> dict:
        """Return one chemical_entities row by id."""

    async def save_entity(
        self, row: dict, *, role: str = SERVICE_ROLE
    ) -> str:
        """Insert one canonical entity (service role; import path).

        Idempotent by primary key: re-importing an already registered
        entity must not create a second row.
        """

    async def save_alias(
        self, row: dict, *, role: str = SERVICE_ROLE
    ) -> str:
        """Insert one ingredient_aliases row (service role; import)."""

    async def list_entities(
        self, *, role: str = AUTHENTICATED_ROLE
    ) -> list:
        """All canonical entities ordered by id (registry projection)."""

    async def list_aliases(
        self, *, role: str = AUTHENTICATED_ROLE
    ) -> list:
        """All alias rows ordered by id (registry projection)."""

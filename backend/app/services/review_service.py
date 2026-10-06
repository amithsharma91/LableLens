"""Review service: Stage-9 workflow over persisted rows.

Composes the in-memory `ReviewQueue` (validation) with repository
rows (truth): every transition is validated by the queue against
hydrated state, then persisted conditionally. Confirmations re-enter
the frozen gate via `reverify_candidate` with fresh adapter
evidence; the API never decides chemistry.
"""

from __future__ import annotations

from typing import Optional

from app.services import errors as _errors
from app.services.entity_resolver import Candidate, Resolution
from app.repositories.serialize import review_event_to_row, review_to_row
from app.services.storage import store_verification_decision
from app.services.verification.evidence import CombinedAdapter
from app.services.verification.orchestrator import reverify_candidate
from app.services.verification.review import (
    ReviewEvent,
    ReviewQueue,
    ReviewSelection,
    candidate_key_for,
)

__all__ = ["ReviewService", "resolution_from_dict"]


def resolution_from_dict(data: dict) -> Resolution:
    """Rebuild a Resolution from its persisted `to_dict` view."""
    entity = data.get("entity") or {}
    alternatives = data.get("alternatives") or []

    def _candidate(item: dict) -> Candidate:
        return Candidate(
            candidate_ref=item.get("candidate_ref", ""),
            display_name=item.get("display_name", ""),
            candidate_type=item.get("candidate_type", "unknown"),
            source=item.get("source", ""),
            match_method=item.get("match_method", ""),
            match_score=item.get("match_score", 0.0) or 0.0,
            reason=item.get("reason", ""),
        )

    candidates = [_candidate(c) for c in alternatives]
    selected = _candidate(entity) if entity.get("candidate_ref") else None
    if selected is not None:
        candidates = [selected] + [
            c for c in candidates
            if c.candidate_ref != selected.candidate_ref
        ]
    return Resolution(
        raw_text=data.get("raw_text", ""),
        normalized_text=data.get("normalized_text", ""),
        parser_node_id=data.get("parser_node_id", ""),
        normalization_id=data.get("normalization_id", ""),
        parent_id=data.get("parent_id"),
        depth=int(data.get("depth", 0) or 0),
        position=int(data.get("position", 0) or 0),
        percentage=data.get("percentage"),
        identifier=data.get("identifier"),
        status=data.get("match_status", "unresolved"),
        candidates=candidates,
        selected_candidate=selected,
        identity_confidence=data.get("identity_confidence", "UNKNOWN"),
        methods=list(data.get("methods") or []),
        warnings=list(data.get("warnings") or []),
        provenance=dict(data.get("provenance") or {}),
        children=[],
    )


class ReviewService:
    """Human-review workflow (queue validation + persistence)."""

    def __init__(self, repos, adapters=None, manual=None) -> None:
        self._repos = repos
        self._adapters = list(adapters or [])
        self._manual = manual
        # Process-scoped queue: review IDs sequence deterministically
        # across submissions (never restart per call).
        self._queue = ReviewQueue()

    # -- submission ------------------------------------------------------

    async def submit(
        self, decision, resolution, records, *,
        owner: Optional[str] = None, role: str = "service",
    ) -> Optional[str]:
        """Route a live decision for review; persist when routed."""
        for _attempt in range(1000):
            item = self._queue.submit(
                decision, resolution.to_dict(), list(records),
                has_alternatives=bool(resolution.alternatives),
            )
            if item is None:
                return None
            try:
                existing = await self._repos.reviews.get_review(
                    item.review_id, role=role)
            except KeyError:
                existing = None
            if existing is None or existing.get(
                    "candidate_key") == item.candidate_key:
                await self._persist_item(
                    item, self._queue, owner=owner, role=role)
                return item.review_id
            # Persisted row from a previous process owns this ID and
            # differs: advance the counter and mint the next one.
            continue
        raise _errors.ServiceError("review id space exhausted")

    async def _persist_item(
        self, item, queue, *, owner: Optional[str] = None,
        role: str = "service",
    ) -> None:
        row = review_to_row(item)
        row["owner_subject"] = owner
        await self._repos.reviews.submit_review(row, role=role)
        for event in queue.events_for(item.review_id)[1:]:
            await self._repos.reviews.append_event(
                review_event_to_row(event), role=role)

    # -- reads ---------------------------------------------------------------

    async def list_pending(
        self, *, page: int = 1, page_size: int = 20,
        owner: Optional[str] = None, reviewer: bool = False,
        role: str = "authenticated",
    ) -> dict:
        """Open reviews in deterministic priority order, paginated.

        Reviewers see the whole queue (the allowlisted-operator
        workflow); everyone else sees only their own rows plus
        legacy rows without an owner.
        """
        rows = await self._repos.reviews.list_pending(role=role)
        if not reviewer:
            rows = [
                row for row in rows
                if row.get("owner_subject") is None
                or row.get("owner_subject") == owner
            ]
        total = len(rows)
        start = (page - 1) * page_size
        return {
            "items": rows[start:start + page_size],
            "total": total,
        }

    async def get(
        self, review_id: str, *, owner: Optional[str] = None,
        reviewer: bool = False, role: str = "authenticated",
    ) -> dict:
        """One review with its event history."""
        try:
            row = await self._repos.reviews.get_review(review_id, role=role)
            if not reviewer:
                _errors.require_owner_match(
                    row.get("owner_subject"), owner,
                    resource="review")
            events = await self._repos.reviews.list_events(
                review_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("review not found")
        return {"review": row, "events": events}

    # -- claim ---------------------------------------------------------------

    async def claim(
        self, review_id: str, principal, *, role: str = "service"
    ) -> dict:
        """Claim a queued review as the authenticated reviewer."""
        queue = await self._hydrated(review_id, role=role)
        reviewer = "human:%s" % principal.subject
        try:
            queue.claim(review_id, reviewer)
        except ValueError as exc:
            raise _errors.ConflictError(str(exc))
        event = queue.events_for(review_id)[-1]
        await self._transition(review_id, event, "in_review",
                               expect_status="queued", role=role)
        return await self.get(review_id, role="authenticated")

    # -- decision --------------------------------------------------------------

    async def decide(
        self, review_id: str, payload: dict, principal, *,
        role: str = "service",
    ) -> dict:
        """Validate, persist, and (on confirm) reverify a decision."""
        queue = await self._hydrated(review_id, role=role)
        reviewer = "human:%s" % principal.subject
        try:
            selection = queue.decide(
                review_id,
                decision=payload["decision"],
                reviewer=reviewer,
                reason=payload.get("reason", ""),
                selected_candidate_ref=payload.get(
                    "selected_candidate_ref"),
                corrected_identifier=payload.get("corrected_identifier"),
                corrected_type=payload.get("corrected_type"),
                context=payload.get("context"),
                approved_fields=tuple(
                    payload.get("approved_fields", ("identity",))),
            )
        except ValueError as exc:
            message = str(exc)
            if "requires an explicit selection" in message or (
                    "not among" in message):
                raise _errors.ConflictError(message)
            raise _errors.ServiceError(message)
        event = queue.events_for(review_id)[-1]
        await self._transition(
            review_id, event, queue.get(review_id).status,
            expect_status="in_review", role=role)
        if selection is None:
            return await self.get(review_id, role="authenticated")
        return await self._confirm(
            review_id, queue, selection, role=role)

    async def _confirm(
        self, review_id: str, queue: ReviewQueue, selection: ReviewSelection,
        *, role: str,
    ) -> dict:
        item = queue.get(review_id)
        resolution = resolution_from_dict(item.resolution)
        combined = CombinedAdapter(list(self._adapters))
        try:
            decision = reverify_candidate(resolution, combined, selection)
        except ValueError as exc:
            raise _errors.ConflictError(str(exc))
        stored = await store_verification_decision(
            self._repos,
            decision,
            None,
            candidate_key_for(
                resolution.normalized_text or "",
                resolution.identifier,
            ),
            role=role,
        )
        if self._manual is not None:
            self._manual.register_selection(selection)
        await self._repos.reviews.append_event(
            review_event_to_row(self._reverify_event(
                queue, review_id, "reverification started")),
            role=role,
        )
        await self._repos.reviews.append_event(
            review_event_to_row(self._reverify_event(
                queue, review_id,
                "reverification completed; new status %s"
                % decision.status)),
            role=role,
        )
        return {
            "review_id": review_id,
            "status": queue.get(review_id).status,
            "decision": decision.to_dict(),
            "stored": stored,
        }

    def _reverify_event(self, queue, review_id, reason):
        import time as _time

        item = queue.get(review_id)
        seq = len(queue.events_for(review_id)) + 1
        return ReviewEvent(
            event_id="%s:%03d" % (review_id, seq),
            review_id=review_id,
            event_type="ReverificationTriggered",
            timestamp=_time.time(),
            actor="system:reverification",
            reason=reason,
            previous_state=item.status,
            new_state=item.status,
            evidence_context_hash=item.evidence_hash,
            rules_version="1.0.0",
            snapshot_version="",
        )

    # -- internals ---------------------------------------------------------------

    async def _hydrated(self, review_id: str, *, role: str) -> ReviewQueue:
        try:
            row = await self._repos.reviews.get_review(review_id, role=role)
            events = await self._repos.reviews.list_events(
                review_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("review not found")
        return ReviewQueue.hydrate([row], events)

    async def _transition(
        self, review_id: str, event, new_status: str, *,
        expect_status: Optional[str] = None, role: str,
    ) -> None:
        from app.repositories.serialize import (
            review_event_to_row as _to_row,
        )

        try:
            await self._repos.reviews.transition_review(
                review_id, _to_row(event), new_status,
                expect_status=expect_status, role=role)
        except KeyError:
            raise _errors.NotFoundError("review not found")
        except Exception as exc:
            if type(exc).__name__ == "ReviewClaimConflict":
                raise _errors.ConflictError(str(exc))
            raise

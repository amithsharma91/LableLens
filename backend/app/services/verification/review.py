"""Human-review domain model (Stage 9, internal service layer).

Principle: human review is evidence + accountable judgment, never a
shortcut to truth. A reviewer decision cannot set a verification
status directly -- it produces a ``ReviewSelection`` that re-enters
the frozen V1-V7 gate via ``reverify_candidate``. Name corrections
are rejected here: a renamed candidate must go back through
normalization/resolution, not through verification.

Review lifecycle (review status, separate from verification status):

    queued -> in_review -> approved | rejected
                       -> needs_more_evidence | closed_unknown

Events are append-only; history is never rewritten. IDs and priority
are deterministic (counters, fixed ordering) -- no ML ranking, no
risk scores, no randomness.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field as dc_field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.services.verification.models import (
    FieldEvidence,
    SourceMetadata,
    SourceRecord,
    VerificationDecision,
)

__all__ = [
    "REVIEW_QUEUED",
    "REVIEW_IN_REVIEW",
    "REVIEW_APPROVED",
    "REVIEW_REJECTED",
    "REVIEW_NEEDS_MORE",
    "REVIEW_CLOSED_UNKNOWN",
    "DECIDE_CONFIRM",
    "DECIDE_REJECT",
    "DECIDE_MORE_EVIDENCE",
    "DECIDE_MARK_UNKNOWN",
    "EVENT_CREATED",
    "EVENT_CLAIMED",
    "EVENT_DECIDED",
    "EVENT_REVERIFY_TRIGGERED",
    "EVENT_RESULT_RECORDED",
    "ReviewItem",
    "ReviewEvent",
    "ReviewDecision",
    "ReviewSelection",
    "ReviewQueue",
    "current_context_hash",
    "evidence_context_hash",
    "APPROVABLE_FIELDS",
]

REVIEW_QUEUED = "queued"
REVIEW_IN_REVIEW = "in_review"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_NEEDS_MORE = "needs_more_evidence"
REVIEW_CLOSED_UNKNOWN = "closed_unknown"

DECIDE_CONFIRM = "confirm_identity"
DECIDE_REJECT = "reject_identity"
DECIDE_MORE_EVIDENCE = "request_more_evidence"
DECIDE_MARK_UNKNOWN = "mark_unknown"

EVENT_CREATED = "ReviewCreated"
EVENT_CLAIMED = "ReviewClaimed"
EVENT_DECIDED = "ReviewDecisionRecorded"
EVENT_REVERIFY_TRIGGERED = "ReverificationTriggered"
EVENT_RESULT_RECORDED = "VerificationResultRecorded"

# Claim-level boundary: a confirm decision may approve identity (and
# nothing else by default). Formula/structure/weight/role approvals
# do not exist in this stage.
APPROVABLE_FIELDS = ("identity",)

# Priority order: conflicts first, then provisional, unknown,
# unverified. FIFO within a level by creation sequence.
_PRIORITY = {
    "conflicted": 0,
    "provisional": 1,
    "unknown": 2,
    "unverified": 3,
}

# Always routed; unknown/unverified only when the reviewer has
# something to choose (resolution alternatives present).
_ALWAYS_ROUTE = ("conflicted", "provisional")


def _canon(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _freeze(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def evidence_context_hash(
    candidate_key: str,
    evidence: Sequence[FieldEvidence],
    source_refs: Sequence[SourceMetadata],
    *,
    snapshot_version: str,
    rules_version: str,
) -> str:
    """Stable hash of the reviewed evidence context.

    Volatile timestamps are excluded on purpose: identical evidence
    re-fetched later must hash identically, while any material change
    (values, sources, versions) changes the hash and forces re-review.
    """
    payload = {
        "candidate_key": candidate_key,
        "evidence": sorted(
            [
                [e.field, str(e.value), e.source.source_id,
                 e.source.record_locator]
                for e in evidence
            ]
        ),
        "sources": sorted(
            [[s.source_id, s.record_locator] for s in source_refs]
        ),
        "snapshot_version": snapshot_version,
        "rules_version": rules_version,
    }
    return hashlib.sha256(_freeze(payload).encode("utf-8")).hexdigest()


def current_context_hash(
    candidate_key: str,
    records: Sequence[SourceRecord],
    *,
    snapshot_version: str,
    rules_version: str,
) -> str:
    """Fingerprint of the evidence a reviewer actually saw.

    Built from record identities + source refs only (never volatile
    timestamps), so identical evidence re-fetched later hashes
    identically, while any material change forces re-review. Both
    ``ReviewQueue.submit`` and re-verification must use this helper
    on their respective record sets.
    """
    identity = [
        FieldEvidence(
            field="identity",
            value=r.entity.preferred_name,
            unit=None,
            source=r.source,
        )
        for r in sorted(records, key=lambda x: x.entity.entity_id)
    ]
    refs = sorted(
        {(r.source.source_id, r.source.record_locator) for r in records}
    )
    sources = [
        SourceMetadata(source_id=sid, record_locator=loc)
        for sid, loc in refs
    ]
    return evidence_context_hash(
        candidate_key,
        identity,
        sources,
        snapshot_version=snapshot_version,
        rules_version=rules_version,
    )


def candidate_key_for(normalized_text: str, identifier: Optional[str]) -> str:
    """Stable identity of a review subject (text + code)."""
    return "%s|%s" % (_canon(normalized_text), _canon(identifier or ""))


def _check_reviewer(reviewer: str) -> str:
    name = (reviewer or "").strip()
    if not name:
        raise ValueError("reviewer identity is required")
    lowered = name.lower()
    if lowered == "ai" or lowered.startswith(("ai:", "llm:")):
        raise ValueError("AI systems cannot act as human reviewers")
    return name


def _check_reason(reason: str) -> str:
    text = (reason or "").strip()
    if not text:
        raise ValueError("a decision reason is required")
    return text


@dataclass(frozen=True)
class ReviewEvent:
    """One append-only audit event in a review's history."""

    event_id: str = ""
    review_id: str = ""
    event_type: str = ""
    timestamp: float = 0.0
    actor: str = ""
    reason: str = ""
    previous_state: str = ""
    new_state: str = ""
    evidence_context_hash: str = ""
    rules_version: str = ""
    snapshot_version: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "event_id": self.event_id,
            "review_id": self.review_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "reason": self.reason,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "evidence_context_hash": self.evidence_context_hash,
            "rules_version": self.rules_version,
            "snapshot_version": self.snapshot_version,
        }


@dataclass
class ReviewItem:
    """One queued review with its frozen evidence context."""

    review_id: str = ""
    candidate_key: str = ""
    raw_text: str = ""
    normalized_text: str = ""
    identifier: Optional[str] = None
    resolution: dict = dc_field(default_factory=dict)
    verification_status: str = ""
    verification_summary: dict = dc_field(default_factory=dict)
    evidence_context: dict = dc_field(default_factory=dict)
    evidence_hash: str = ""
    priority: int = 99
    status: str = REVIEW_QUEUED
    created_at: float = 0.0
    updated_at: float = 0.0
    reviewer: Optional[str] = None

    def to_dict(self) -> dict:
        """JSON-serialisable view (evidence context included)."""
        return {
            "review_id": self.review_id,
            "candidate_key": self.candidate_key,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "identifier": self.identifier,
            "resolution": dict(self.resolution),
            "verification_status": self.verification_status,
            "verification_summary": dict(self.verification_summary),
            "evidence_context": dict(self.evidence_context),
            "evidence_hash": self.evidence_hash,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reviewer": self.reviewer,
        }


@dataclass(frozen=True)
class ReviewDecision:
    """A reviewer's explicit, reasoned decision (input, not outcome)."""

    review_id: str = ""
    decision: str = ""
    reviewer: str = ""
    timestamp: float = 0.0
    reason: str = ""
    selected_candidate_ref: Optional[str] = None
    corrected_identifier: Optional[str] = None
    corrected_type: Optional[str] = None
    context: Optional[str] = None
    approved_fields: Tuple[str, ...] = ("identity",)
    evidence_context_hash: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "review_id": self.review_id,
            "decision": self.decision,
            "reviewer": self.reviewer,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "selected_candidate_ref": self.selected_candidate_ref,
            "corrected_identifier": self.corrected_identifier,
            "corrected_type": self.corrected_type,
            "context": self.context,
            "approved_fields": list(self.approved_fields),
            "evidence_context_hash": self.evidence_context_hash,
        }


@dataclass(frozen=True)
class ReviewSelection:
    """Gate-ready output of an approved review (reverify input)."""

    review_id: str = ""
    reviewer: str = ""
    reason: str = ""
    decided_at: float = 0.0
    candidate_key: str = ""
    selected_candidate_ref: str = ""
    corrected_identifier: Optional[str] = None
    corrected_type: Optional[str] = None
    context: Optional[str] = None
    approved_fields: Tuple[str, ...] = ("identity",)
    evidence_context_hash: str = ""
    snapshot_version: str = ""
    rules_version: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "review_id": self.review_id,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "candidate_key": self.candidate_key,
            "selected_candidate_ref": self.selected_candidate_ref,
            "corrected_identifier": self.corrected_identifier,
            "corrected_type": self.corrected_type,
            "context": self.context,
            "approved_fields": list(self.approved_fields),
            "evidence_context_hash": self.evidence_context_hash,
            "snapshot_version": self.snapshot_version,
            "rules_version": self.rules_version,
        }


class ReviewQueue:
    """In-memory review queue with append-only audit events.

    No persistence, no network, no authentication in this stage;
    reviewer identity is an explicit caller-supplied string.
    """

    def __init__(
        self, *, clock: Callable[[], float] = time.time
    ) -> None:
        self._clock = clock
        self._seq = 0
        self._items: Dict[str, ReviewItem] = {}
        self._events: List[ReviewEvent] = []

    # -- submission ----------------------------------------------------

    def submit(
        self,
        decision: VerificationDecision,
        resolution: dict,
        records: Sequence[SourceRecord],
        *,
        has_alternatives: bool = False,
    ) -> Optional[ReviewItem]:
        """Route a verification outcome for review, or None.

        Routes conflicted/provisional always; unknown/unverified only
        when alternatives give the reviewer something to choose;
        verified never. ``records`` are the evidence behind the
        decision; the item fingerprints them so later re-verification
        can detect changed evidence.
        """
        status = decision.status
        if status in _ALWAYS_ROUTE or (
            status in ("unknown", "unverified") and has_alternatives
        ):
            return self._enqueue(decision, resolution, records, status)
        return None

    def _enqueue(
        self,
        decision: VerificationDecision,
        resolution: dict,
        records: Sequence[SourceRecord],
        status: str,
    ) -> ReviewItem:
        self._seq += 1
        now = self._clock()
        normalized = str(resolution.get("normalized_text", ""))
        identifier = resolution.get("identifier")
        key = candidate_key_for(normalized, identifier)
        evidence = list(decision.evidence)
        source_refs = list(decision.source_refs)
        context = {
            "candidate_key": key,
            "evidence": [e.to_dict() for e in evidence],
            "source_refs": [s.to_dict() for s in source_refs],
            "snapshot_version": decision.snapshot_version,
            "rules_version": decision.rules_version,
        }
        item = ReviewItem(
            review_id="REV-%04d" % self._seq,
            candidate_key=key,
            raw_text=str(resolution.get("raw_text", "")),
            normalized_text=normalized,
            identifier=identifier,
            resolution=dict(resolution),
            verification_status=status,
            verification_summary={
                "status": decision.status,
                "identity_confidence": decision.identity_confidence,
                "reason": decision.reason,
            },
            evidence_context=context,
            evidence_hash=current_context_hash(
                key,
                list(records),
                snapshot_version=decision.snapshot_version,
                rules_version=decision.rules_version,
            ),
            priority=_PRIORITY.get(status, 99),
            status=REVIEW_QUEUED,
            created_at=now,
            updated_at=now,
        )
        self._items[item.review_id] = item
        self._record(
            item, EVENT_CREATED, "system:review-router",
            "routed for human review", "", REVIEW_QUEUED, now,
        )
        return item

    # -- lifecycle -------------------------------------------------------

    def claim(self, review_id: str, reviewer: str) -> ReviewItem:
        """Move queued -> in_review under a named reviewer."""
        item = self._require(review_id)
        if item.status != REVIEW_QUEUED:
            raise ValueError("only queued items can be claimed")
        reviewer = _check_reviewer(reviewer)
        return self._transition(
            item, REVIEW_IN_REVIEW, reviewer, "review claimed"
        )

    def decide(
        self,
        review_id: str,
        *,
        decision: str,
        reviewer: str,
        reason: str,
        selected_candidate_ref: Optional[str] = None,
        corrected_identifier: Optional[str] = None,
        corrected_type: Optional[str] = None,
        context: Optional[str] = None,
        approved_fields: Tuple[str, ...] = ("identity",),
    ) -> Optional[ReviewSelection]:
        """Record a reasoned decision; returns a selection only for
        approved identity confirmations (reverify input)."""
        item = self._require(review_id)
        if item.status != REVIEW_IN_REVIEW:
            raise ValueError("only in-review items can be decided")
        reviewer = _check_reviewer(reviewer)
        reason = _check_reason(reason)
        if decision not in (
            DECIDE_CONFIRM,
            DECIDE_REJECT,
            DECIDE_MORE_EVIDENCE,
            DECIDE_MARK_UNKNOWN,
        ):
            raise ValueError("unknown decision type %s" % decision)
        if decision == DECIDE_CONFIRM:
            # Claim-level boundary: identity approval never carries
            # formula/structure/weight/role approvals with it.
            if tuple(approved_fields) != ("identity",):
                raise ValueError("confirmation approves identity only")
            if not selected_candidate_ref:
                raise ValueError("confirmation requires an explicit selection")
            return self._approve(
                item, reviewer, reason, selected_candidate_ref,
                corrected_identifier, corrected_type, context,
                approved_fields,
            )
        terminal = {
            DECIDE_REJECT: REVIEW_REJECTED,
            DECIDE_MORE_EVIDENCE: REVIEW_NEEDS_MORE,
            DECIDE_MARK_UNKNOWN: REVIEW_CLOSED_UNKNOWN,
        }[decision]
        self._transition(item, terminal, reviewer, reason)
        return None

    def _approve(
        self,
        item: ReviewItem,
        reviewer: str,
        reason: str,
        selected_candidate_ref: str,
        corrected_identifier: Optional[str],
        corrected_type: Optional[str],
        context: Optional[str],
        approved_fields: Tuple[str, ...],
    ) -> ReviewSelection:
        refs = {c.get("candidate_ref") for c in self._candidates(item)}
        if selected_candidate_ref not in refs:
            raise ValueError("selection is not among resolution candidates")
        self._transition(item, REVIEW_APPROVED, reviewer, reason)
        now = self._clock()
        return ReviewSelection(
            review_id=item.review_id,
            reviewer=reviewer,
            reason=reason,
            decided_at=now,
            candidate_key=item.candidate_key,
            selected_candidate_ref=selected_candidate_ref,
            corrected_identifier=corrected_identifier,
            corrected_type=corrected_type,
            context=context,
            approved_fields=tuple(approved_fields),
            evidence_context_hash=item.evidence_hash,
            snapshot_version=item.evidence_context.get(
                "snapshot_version", ""),
            rules_version=item.evidence_context.get("rules_version", ""),
        )

    @staticmethod
    def _candidates(item: ReviewItem) -> list:
        resolution = item.resolution
        candidates = []
        selected = resolution.get("entity")
        if isinstance(selected, dict) and selected.get("candidate_ref"):
            candidates.append(selected)
        alternatives = resolution.get("alternatives", [])
        if isinstance(alternatives, list):
            candidates.extend(
                c for c in alternatives if isinstance(c, dict)
            )
        return candidates

    # -- re-verification history -------------------------------------------

    def record_reverification(
        self,
        review_id: str,
        new_decision: VerificationDecision,
        *,
        actor: str = "system:reverification",
        reason: str = "reverification completed",
    ) -> ReviewEvent:
        """Append result events; previous results are retained."""
        item = self._require(review_id)
        now = self._clock()
        self._record(
            item, EVENT_REVERIFY_TRIGGERED, actor,
            "reverification started", item.status, item.status, now,
        )
        return self._record(
            item, EVENT_RESULT_RECORDED, actor,
            "%s; new status %s" % (reason, new_decision.status),
            item.status, item.status, now,
        )

    # -- queries -------------------------------------------------------------

    def pending(self) -> List[ReviewItem]:
        """Queued/in-review items in deterministic priority order."""
        open_items = [
            i for i in self._items.values()
            if i.status in (REVIEW_QUEUED, REVIEW_IN_REVIEW)
        ]
        open_items.sort(key=lambda i: (i.priority, i.review_id))
        return open_items

    def get(self, review_id: str) -> ReviewItem:
        """Return a queued item by ID."""
        return self._require(review_id)

    def events_for(self, review_id: str) -> List[ReviewEvent]:
        """Append-only history for one review, in recorded order."""
        self._require(review_id)
        return [e for e in self._events if e.review_id == review_id]

    def all_events(self) -> List[ReviewEvent]:
        """Full audit log in recorded order (never rewritten)."""
        return list(self._events)

    # -- internals -------------------------------------------------------------

    def _require(self, review_id: str) -> ReviewItem:
        try:
            return self._items[review_id]
        except KeyError:
            raise ValueError("unknown review %s" % review_id)

    def _transition(
        self, item: ReviewItem, new_state: str, actor: str, reason: str
    ) -> ReviewItem:
        previous = item.status
        item.status = new_state
        item.updated_at = self._clock()
        if new_state == REVIEW_IN_REVIEW:
            item.reviewer = actor
        self._record(
            item, EVENT_CLAIMED if new_state == REVIEW_IN_REVIEW
            else EVENT_DECIDED, actor, reason, previous, new_state,
            item.updated_at,
        )
        return item

    def _record(
        self,
        item: ReviewItem,
        event_type: str,
        actor: str,
        reason: str,
        previous_state: str,
        new_state: str,
        timestamp: float,
    ) -> ReviewEvent:
        seq = sum(
            1 for e in self._events if e.review_id == item.review_id
        ) + 1
        event = ReviewEvent(
            event_id="%s:%03d" % (item.review_id, seq),
            review_id=item.review_id,
            event_type=event_type,
            timestamp=timestamp,
            actor=actor,
            reason=reason,
            previous_state=previous_state,
            new_state=new_state,
            evidence_context_hash=item.evidence_hash,
            rules_version=item.evidence_context.get("rules_version", ""),
            snapshot_version=item.evidence_context.get(
                "snapshot_version", ""),
        )
        self._events.append(event)
        return event

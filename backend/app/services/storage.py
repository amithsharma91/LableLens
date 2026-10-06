"""Shared verification-decision persistence (used by services).

Stores one orchestrator decision as: a `verification_decisions` row,
one `claims` row per decision claim (idempotent deterministic IDs,
status/confidence reconciled with events on change), and
`claim_sources` links with ensured source rows. Returns the stored
decision id plus claim ids for response building.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from app.repositories.serialize import (
    claim_to_row,
    claim_source_row,
    decision_to_row,
    verification_event_row,
    verification_id_for,
)
from app.services import errors as _errors
from app.services.verification.models import (
    IdentityClaim,
    VerificationDecision,
)

__all__ = ["store_verification_decision"]


def _source_row(name: str) -> dict:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "source:" + name)),
        "name": name,
        "publisher": None,
        "source_type": "unknown",
        "url": None,
        "identifier": None,
        "jurisdiction": None,
        "language_code": None,
        "authority_level": "unknown",
        "license": None,
        "redistribution_allowed": None,
        "caching_allowed": None,
        "publication_date": None,
        "retrieved_at": None,
        "last_checked_at": None,
        "freshness_class": None,
        "status": "approved",
        "notes": "auto-registered from decision evidence",
    }


def _claim_evidence(
    decision: VerificationDecision, claim: IdentityClaim
) -> list:
    """Evidence items backing one claim from the decision bundle."""
    wanted = "identity" if claim.field == "identity" else claim.field
    return [
        item for item in decision.evidence if item.field == wanted
    ]


async def store_verification_decision(
    repos,
    decision: VerificationDecision,
    match_id: Optional[str],
    candidate_key: str,
    *,
    owner_subject: Optional[str] = None,
    role: str = "service",
) -> dict:
    """Persist a decision with its claims and evidence links.

    The decision row inherits the analyzed observation's owner.
    Claims, sources, and links stay owner-free by design: claim
    identity is deterministic shared chemistry content, never
    per-user state.
    """
    row = decision_to_row(
        decision, candidate_key=candidate_key, entity_match_id=match_id,
        owner_subject=owner_subject,
    )
    row["id"] = verification_id_for(
        candidate_key,
        decision.status,
        decision.rules_version,
        decision.snapshot_version,
        row["evidence_context_hash"],
        match_id or "",
    )
    claim_ids: List[str] = []
    for claim in decision.claims:
        entity_id = decision.entity_id or claim.entity_id or None
        await _require_registered_entity(repos, entity_id, role=role)
        claim_row = claim_to_row(claim, entity_id=entity_id)
        stored = await _reconcile_claim(repos, claim_row, role=role)
        claim_ids.append(stored["id"])
        for evidence in _claim_evidence(decision, claim):
            source_id = await repos.evidence.ensure_source(
                _source_row(evidence.source.source_id), role=role
            )
            await repos.evidence.link_source(
                claim_source_row(
                    stored["id"], source_id, evidence, response_hash=None
                ),
                role=role,
            )
    row["claim_ids"] = claim_ids
    decision_id = await repos.verification.save_decision(row, role=role)
    return {"id": decision_id, "claim_ids": claim_ids}


async def _require_registered_entity(
    repos, entity_id: Optional[str], *, role: str
) -> None:
    """Fail fast when a claim would reference an unknown entity.

    `chemical_entities` is the authority on canonical entity
    existence. The check runs before any write so the caller gets a
    controlled 422 rather than a foreign-key violation, and no
    partially-linked claim rows are left behind.
    """
    if not entity_id:
        return
    reader = getattr(repos, "entities", None)
    if reader is None:
        return
    try:
        await reader.get_entity(str(entity_id), role=role)
    except KeyError:
        raise _errors.MissingEntityError(
            "canonical entity %s is not registered" % entity_id
        )


async def _reconcile_claim(repos, claim_row: dict, *, role: str) -> dict:
    try:
        stored = await repos.claims.get_claim(claim_row["id"], role=role)
    except KeyError:
        stored = None
    if stored is None:
        await repos.claims.save_claim(dict(claim_row), role=role)
        return dict(claim_row)
    if (
        stored.get("verification_status") != claim_row["verification_status"]
        or stored.get("confidence") != claim_row["confidence"]
    ):
        event = verification_event_row(
            claim_id=stored["id"],
            previous_status=stored.get("verification_status"),
            new_status=claim_row["verification_status"],
            previous_confidence=stored.get("confidence"),
            new_confidence=claim_row["confidence"],
            review_method="gate_decision",
            reviewer_type="system",
            reason="re-verification changed claim state",
        )
        updated = await repos.claims.update_claim_status(
            stored["id"],
            claim_row["verification_status"],
            claim_row["confidence"],
            event=event,
            role=role,
        )
        return updated
    return stored

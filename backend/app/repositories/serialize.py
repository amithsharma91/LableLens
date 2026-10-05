"""Domain-to-row serialization for Stage-10 persistence.

All identifiers are deterministic (uuid5 over stable inputs) so
accidental retries insert nothing twice. ``validate_no_secrets``
rejects credential-like keys/values before any write; SQL-injection
payloads and other hostile strings pass through untouched as data
(they are never executed, only stored).
"""

from __future__ import annotations

import datetime
import re
import uuid
from typing import List, Optional

from app.services.entity_resolver import Resolution
from app.services.verification.models import (
    IdentityClaim,
    VerificationDecision,
)

__all__ = [
    "verification_id_for",
    "claim_id_for",
    "validate_no_secrets",
    "decision_to_row",
    "decision_from_row",
    "claim_to_row",
    "claim_from_row",
    "claim_source_row",
    "review_to_row",
    "review_event_to_row",
    "verification_event_row",
    "observation_row",
    "normalization_row",
    "candidate_rows",
    "match_row",
]

_SECRET_KEY_RE = re.compile(
    r"(?i)(secret|password|passwd|api[_-]?key|token|"
    r"private[_-]?key|service[_-]?role|credential)"
)
_SECRET_VALUE_RE = re.compile(r"(?i)^(sk-|Bearer\s+).+")


def validate_no_secrets(mapping: dict, *, path: str = "root") -> None:
    """Reject credential-like keys/values in data bound for storage."""
    if isinstance(mapping, dict):
        items = mapping.items()
    else:
        return
    for key, value in items:
        where = "%s.%s" % (path, key)
        if isinstance(key, str) and _SECRET_KEY_RE.match(key):
            raise ValueError("secret-like key refused: %s" % where)
        if isinstance(value, str) and _SECRET_VALUE_RE.match(value):
            raise ValueError("secret-like value refused: %s" % where)
        if isinstance(value, dict):
            validate_no_secrets(value, path=where)
        elif isinstance(value, list):
            for i, entry in enumerate(value):
                if isinstance(entry, dict):
                    validate_no_secrets(entry, path="%s[%d]" % (where, i))


def _get(obj: object, key: str, default=None):
    """Attribute-or-key read: domain objects and plain rows both work."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def verification_id_for(
    candidate_key: str,
    status: str,
    rules_version: str,
    snapshot_version: str,
    evidence_hash: str,
) -> str:
    """Deterministic decision ID: same inputs always collide."""
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join([
                "verification", candidate_key, status,
                rules_version, snapshot_version, evidence_hash,
            ]),
        )
    )


def claim_id_for(entity_id: str, field: str, value: object) -> str:
    """Deterministic claim ID: same fact always collides."""
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(["claim", entity_id, field, str(value)]),
        )
    )


_CLAIM_TYPES = {
    "identity": "chemical_identity",
    "preferred_name": "chemical_identity",
    "formula": "formula",
    "molecular_weight": "molecular_weight",
    "smiles": "smiles",
    "inchi": "smiles",
    "inchikey": "smiles",
}


def decision_to_row(
    decision: VerificationDecision,
    *,
    candidate_key: str,
    entity_match_id: Optional[str] = None,
) -> dict:
    """Serialize a VerificationDecision to a verification_decisions row."""
    gate_results = [
        {"rule_id": _get(g, "rule_id"), "result": _get(g, "result"),
         "detail": _get(g, "detail")}
        for g in _get(decision, "gate_results") or []
    ]
    return {
        "id": verification_id_for(
            candidate_key,
            decision.status,
            decision.rules_version,
            decision.snapshot_version,
            _evidence_fingerprint(decision),
        ),
        "entity_match_id": entity_match_id,
        "candidate_key": candidate_key,
        "status": decision.status,
        "identity_confidence": decision.identity_confidence,
        "rules_version": decision.rules_version,
        "snapshot_version": decision.snapshot_version,
        "evidence_context_hash": _evidence_fingerprint(decision),
        "reason": decision.reason,
        "warnings": list(decision.warnings),
        "gate_results": gate_results,
    }


def _evidence_fingerprint(decision: object) -> str:
    import hashlib
    import json

    parts = sorted(
        "%s=%s@%s" % (_get(e, "field"), _get(e, "value"),
                      _get(_get(e, "source"), "source_id"))
        for e in _get(decision, "evidence") or []
    )
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")
    ).hexdigest()


def decision_from_row(row: dict) -> dict:
    """Rebuild the stored core of a decision (evidence via links)."""
    import copy

    return {
        "id": str(row["id"]),
        "entity_match_id": (
            str(row["entity_match_id"]) if row.get("entity_match_id") else None
        ),
        "candidate_key": row["candidate_key"],
        "status": row["status"],
        "identity_confidence": row["identity_confidence"],
        "rules_version": row["rules_version"],
        "snapshot_version": row["snapshot_version"],
        "evidence_context_hash": row["evidence_context_hash"],
        "reason": row.get("reason"),
        "warnings": list(row.get("warnings") or []),
        "gate_results": copy.deepcopy(row.get("gate_results") or []),
    }


def claim_to_row(
    claim: IdentityClaim,
    *,
    entity_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    provenance_type: str = "source_reported",
) -> dict:
    """Serialize an IdentityClaim to a claims row."""
    value = _get(claim, "value")
    field = _get(claim, "field")
    entity = entity_id or _get(claim, "entity_id") or None
    row = {
        "id": claim_id_for(entity or "", field, value),
        "chemical_entity_id": entity,
        "product_id": None,
        "product_label_id": None,
        "entity_role_id": None,
        "claim_type": claim_type or _CLAIM_TYPES.get(field, field),
        "field_name": field,
        "claim_value_text": value if isinstance(value, str) else None,
        "claim_value_numeric": (
            value if isinstance(value, (int, float)) else None
        ),
        "claim_value_json": None,
        "unit": None,
        "provenance_type": provenance_type,
        "verification_status": _get(claim, "status"),
        "confidence": _get(claim, "confidence"),
        "valid_from": None,
        "valid_until": None,
        "source_version": None,
        "freshness_class": "stable",
        "last_checked_at": None,
    }
    return row


def claim_from_row(row: dict) -> dict:
    """Rebuild the stored core of a claim (evidence via links)."""
    value = row.get("claim_value_text")
    if value is None:
        value = row.get("claim_value_numeric")
    return {
        "id": str(row["id"]),
        "entity_id": (
            str(row["chemical_entity_id"])
            if row.get("chemical_entity_id")
            else ""
        ),
        "field": row.get("field_name") or "",
        "value": value,
        "status": row.get("verification_status"),
        "confidence": row.get("confidence"),
        "claim_type": row.get("claim_type"),
    }


def claim_source_row(
    claim_id: str,
    source_id: str,
    evidence: object,
    *,
    response_hash: Optional[str] = None,
) -> dict:
    """Serialize one evidence item to a claim_sources row."""
    source = getattr(evidence, "source", None)
    retrieved = (
        getattr(source, "retrieved_at", "") if source is not None else ""
    ) or getattr(evidence, "retrieved_at", "") or ""
    if len(retrieved) == 10:
        retrieved += "T00:00:00Z"
    value = getattr(evidence, "value", None)
    if value is None:
        value = getattr(evidence, "source_value", "")
    return {
        "claim_id": claim_id,
        "source_id": source_id,
        "support_type": getattr(evidence, "support_type", "direct"),
        "support_strength": getattr(evidence, "support_strength", "moderate"),
        "source_locator": getattr(evidence, "locator", ""),
        "source_value": str(value),
        "review_status": getattr(evidence, "review_status", "unreviewed"),
        "review_notes": None,
        "provider": getattr(evidence, "provider", ""),
        "source_version": getattr(evidence, "source_version", "") or None,
        "retrieved_at": retrieved or None,
        "response_hash": response_hash,
    }


def review_to_row(item: object) -> dict:
    """Serialize a ReviewItem to a reviews row."""
    return {
        "id": _get(item, "review_id"),
        "candidate_key": _get(item, "candidate_key"),
        "raw_text": _get(item, "raw_text"),
        "normalized_text": _get(item, "normalized_text"),
        "identifier": _get(item, "identifier"),
        "resolution": dict(_get(item, "resolution") or {}),
        "verification_status": _get(item, "verification_status"),
        "evidence_context": dict(_get(item, "evidence_context") or {}),
        "evidence_hash": _get(item, "evidence_hash"),
        "priority": _get(item, "priority"),
        "status": _get(item, "status"),
        "reviewer": _get(item, "reviewer"),
    }


def review_event_to_row(event: object) -> dict:
    """Serialize a ReviewEvent to a review_events row."""
    return {
        "id": _get(event, "event_id"),
        "review_id": _get(event, "review_id"),
        "event_type": _get(event, "event_type"),
        "actor": _get(event, "actor"),
        "reason": _get(event, "reason"),
        "previous_state": _get(event, "previous_state") or None,
        "new_state": _get(event, "new_state"),
        "evidence_context_hash": _get(event, "evidence_context_hash"),
        "rules_version": _get(event, "rules_version"),
        "snapshot_version": _get(event, "snapshot_version"),
    }


def verification_event_row(
    *,
    claim_id: str,
    previous_status: Optional[str],
    new_status: str,
    previous_confidence: Optional[str] = None,
    new_confidence: Optional[str] = None,
    review_method: str = "gate_decision",
    reviewer_type: str = "system",
    reason: Optional[str] = None,
    source_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> dict:
    """Build a verification_events row (deterministic id optional)."""
    import uuid as _uuid

    return {
        "id": event_id
        or str(
            _uuid.uuid5(
                _uuid.NAMESPACE_URL,
                "|".join([
                    "verification_event", claim_id,
                    previous_status or "", new_status,
                ]),
            )
        ),
        "claim_id": claim_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "previous_confidence": previous_confidence,
        "new_confidence": new_confidence,
        "review_method": review_method,
        "reviewer_type": reviewer_type,
        "reason": reason,
        "source_id": source_id,
    }


def observation_row(
    *, observation_id: str, scan_id: str, sequence_number: int,
    raw_text: str, display_text: Optional[str] = None,
    source_type: str = "ocr", user_corrected: bool = False,
    original_text: Optional[str] = None,
) -> dict:
    """Serialize one parser node to an ingredient_observations row."""
    return {
        "id": observation_id,
        "scan_id": scan_id,
        "sequence_number": sequence_number,
        "raw_text": raw_text,
        "display_text": display_text,
        "source_type": source_type,
        "ocr_run_id": None,
        "ocr_confidence": None,
        "user_corrected": user_corrected,
        "original_text": original_text,
        "correction_reason": None,
    }


def normalization_row(
    *, normalization_id: str, observation_id: str, normalized_text: str,
    method: str = "rule", version: str = "1.0.0",
    status: str = "complete",
) -> dict:
    """Serialize one normalized node to ingredient_normalizations."""
    return {
        "id": normalization_id,
        "observation_id": observation_id,
        "normalized_text": normalized_text,
        "normalization_method": method,
        "normalizer_version": version,
        "confidence": None,
        "status": status,
    }


def candidate_rows(
    resolution: Resolution, *, normalization_id: str,
) -> List[dict]:
    """Serialize Stage-5 candidates (registry refs stay in reasons)."""
    rows = []
    selected = resolution.selected_candidate
    for candidate in list(resolution.candidates):
        rows.append(
            {
                "id": str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "|".join([
                        "candidate", normalization_id,
                        candidate.candidate_ref,
                    ]),
                )),
                "normalization_id": normalization_id,
                "chemical_entity_id": None,
                "candidate_name": candidate.display_name,
                "match_status": candidate.match_method,
                "candidate_score": candidate.match_score,
                "match_reasons": {
                    "candidate_ref": candidate.candidate_ref,
                    "candidate_type": candidate.candidate_type,
                    "display_name": candidate.display_name,
                    "reason": candidate.reason,
                    "selected": (
                        selected is not None
                        and selected.candidate_ref
                        == candidate.candidate_ref
                    ),
                },
                "source_id": None,
            }
        )
    return rows


def match_row(
    resolution: Resolution, *, match_id: Optional[str] = None,
    normalization_id: str, selected_by: str = "deterministic",
) -> dict:
    """Serialize a Stage-5 resolution to an entity_matches row."""
    return {
        "id": match_id
        or str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "|".join(["match", normalization_id,
                          resolution.status]),
            )
        ),
        "normalization_id": normalization_id,
        "chemical_entity_id": None,
        "match_status": resolution.status,
        "identity_confidence": resolution.identity_confidence,
        "selected_by": selected_by,
        "selected_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "reason_code": "; ".join(resolution.methods or []),
        "review_status": None,
        "review_notes": None,
    }

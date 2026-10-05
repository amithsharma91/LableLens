"""Typed internal models for Stage-7 verification.

Strictly separated record kinds (never merged):

- Stage-5 ``Resolution``  — the hypothesis (imported, never rewritten).
- ``CanonicalEntity``     — a versioned identity record from a source.
- ``IdentityClaim``       — one verifiable fact about an entity.
- ``FieldEvidence``       — an observed value tied to its source.
- ``VerificationDecision``— the orchestrator's explained outcome.

No ``dict[str, Any]`` primary models. All containers are frozen
(immutable) dataclasses with JSON-serialisable ``to_dict`` views.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional, Tuple, Union

__all__ = [
    "PASS",
    "FAIL",
    "UNKNOWN",
    "STATUS_CANDIDATE",
    "STATUS_PROVISIONAL",
    "STATUS_VERIFIED",
    "STATUS_CONFLICTED",
    "STATUS_UNVERIFIED",
    "STATUS_UNKNOWN",
    "STATUS_OBSOLETE",
    "CONF_HIGH",
    "CONF_MEDIUM",
    "CONF_LOW",
    "CONF_UNKNOWN",
    "CONF_CONFLICTED",
    "RULE_V1",
    "RULE_V2",
    "RULE_V3",
    "RULE_V4",
    "RULE_V5",
    "RULE_V6",
    "RULE_V7",
    "Identifier",
    "SourceMetadata",
    "FieldEvidence",
    "CanonicalEntity",
    "SourceRecord",
    "GateResult",
    "IdentityClaim",
    "VerificationDecision",
]

# Gate rule outcomes. UNKNOWN never counts as PASS.
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

# Verification statuses (Stage-7 owned; see ADR-019).
STATUS_CANDIDATE = "candidate"
STATUS_PROVISIONAL = "provisional"
STATUS_VERIFIED = "verified"
STATUS_CONFLICTED = "conflicted"
STATUS_UNVERIFIED = "unverified"
STATUS_UNKNOWN = "unknown"
STATUS_OBSOLETE = "obsolete"

# Qualitative confidence only. Never calibrated percentages.
CONF_HIGH = "HIGH"
CONF_MEDIUM = "MEDIUM"
CONF_LOW = "LOW"
CONF_UNKNOWN = "UNKNOWN"
CONF_CONFLICTED = "CONFLICTED"

RULE_V1 = "V1_admissible_candidate"
RULE_V2 = "V2_authoritative_source"
RULE_V3 = "V3_identity_agreement"
RULE_V4 = "V4_identifier_validation"
RULE_V5 = "V5_entity_type_validation"
RULE_V6 = "V6_source_appropriateness"
RULE_V7 = "V7_context_checks"


@dataclass(frozen=True)
class Identifier:
    """One typed identifier with its own provenance note."""

    id_type: str = ""  # e.g. pubchem_cid | inchikey | e_number
    value: str = ""
    provenance_note: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "id_type": self.id_type,
            "value": self.value,
            "provenance_note": self.provenance_note,
        }


@dataclass(frozen=True)
class SourceMetadata:
    """Where an observed value came from (retrieval-level facts)."""

    source_id: str = ""  # stable registry ID, e.g. PUBCHEM
    record_locator: str = ""  # CID, URL, or record path
    source_version: str = ""  # source version/date as reported
    retrieved_at: str = ""  # ISO date of retrieval
    license_note: str = ""
    source_class: str = ""  # A | B | C | D | E per SOURCE_REGISTRY

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "source_id": self.source_id,
            "record_locator": self.record_locator,
            "source_version": self.source_version,
            "retrieved_at": self.retrieved_at,
            "license_note": self.license_note,
            "source_class": self.source_class,
        }


@dataclass(frozen=True)
class FieldEvidence:
    """One observed field value tied to the source that states it."""

    field: str = ""
    value: Union[str, float, int] = ""
    unit: Optional[str] = None
    source: SourceMetadata = dc_field(default_factory=SourceMetadata)

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "field": self.field,
            "value": self.value,
            "unit": self.unit,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class CanonicalEntity:
    """A versioned identity record. Identity ONLY -- fields below are
    evidenced observations, each independently graded at claim time."""

    entity_id: str = ""
    preferred_name: str = ""
    entity_type: str = ""  # mirrors chemistry-spec entity classes
    representation_type: str = ""
    identifiers: Tuple[Identifier, ...] = ()
    names: Tuple[str, ...] = ()
    fields: Tuple[FieldEvidence, ...] = ()
    contexts: Tuple[str, ...] = ()  # required contexts; empty = none
    verification_status: str = STATUS_VERIFIED
    snapshot_version: str = ""
    verified_at: str = ""
    last_checked: str = ""
    source: SourceMetadata = dc_field(default_factory=SourceMetadata)

    def field_value(self, name: str) -> Optional[FieldEvidence]:
        """Return stored evidence for ``name``, or None if absent."""
        for item in self.fields:
            if item.field == name:
                return item
        return None

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "entity_id": self.entity_id,
            "preferred_name": self.preferred_name,
            "entity_type": self.entity_type,
            "representation_type": self.representation_type,
            "identifiers": [i.to_dict() for i in self.identifiers],
            "names": list(self.names),
            "fields": [f.to_dict() for f in self.fields],
            "contexts": list(self.contexts),
            "verification_status": self.verification_status,
            "snapshot_version": self.snapshot_version,
            "verified_at": self.verified_at,
            "last_checked": self.last_checked,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class SourceRecord:
    """One adapter observation: an entity plus retrieval metadata."""

    entity: CanonicalEntity = dc_field(default_factory=CanonicalEntity)
    source: SourceMetadata = dc_field(default_factory=SourceMetadata)

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "entity": self.entity.to_dict(),
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single gate rule (PASS | FAIL | UNKNOWN)."""

    rule_id: str = ""
    result: str = UNKNOWN
    detail: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "rule_id": self.rule_id,
            "result": self.result,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class IdentityClaim:
    """One verifiable fact, graded independently of its entity."""

    entity_id: str = ""
    field: str = ""  # identity | <stored field name>
    value: Union[str, float, int] = ""
    status: str = STATUS_UNVERIFIED
    confidence: str = CONF_UNKNOWN
    evidence: Tuple[SourceMetadata, ...] = ()

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "entity_id": self.entity_id,
            "field": self.field,
            "value": self.value,
            "status": self.status,
            "confidence": self.confidence,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class VerificationDecision:
    """The orchestrator's explained outcome for one candidate."""

    status: str = STATUS_UNKNOWN
    identity_confidence: str = CONF_UNKNOWN
    gate_results: Tuple[GateResult, ...] = ()
    claims: Tuple[IdentityClaim, ...] = ()
    evidence: Tuple[FieldEvidence, ...] = ()
    source_refs: Tuple[SourceMetadata, ...] = ()
    reason: str = ""
    warnings: Tuple[str, ...] = ()
    rules_version: str = ""
    snapshot_version: str = ""
    entity_id: Optional[str] = None

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "status": self.status,
            "identity_confidence": self.identity_confidence,
            "gate_results": [g.to_dict() for g in self.gate_results],
            "claims": [c.to_dict() for c in self.claims],
            "evidence": [e.to_dict() for e in self.evidence],
            "source_refs": [s.to_dict() for s in self.source_refs],
            "reason": self.reason,
            "warnings": list(self.warnings),
            "rules_version": self.rules_version,
            "snapshot_version": self.snapshot_version,
            "entity_id": self.entity_id,
        }

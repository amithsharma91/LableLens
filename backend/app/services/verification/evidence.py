"""Typed evidence layer for Stage-8 official providers.

Separation enforced here (per EVIDENCE_AND_CONFIDENCE_SPEC.md):

    ChemicalEntity  --has-->  Claim(field, value)
    Claim           --supported_by-->  EvidenceItem(provider field quote)
    EvidenceItem    --from-->  provider response (never the reverse)

Provider payloads become ``EvidenceItem`` rows (field-level, sourced);
``build_source_records`` turns agreed evidence into ``SourceRecord``
inputs for the frozen V1-V7 gate. ``detect_conflicts`` finds genuine
field disagreements between records so the orchestrator can map them
to ``conflicted`` without touching the gate.

``CombinedAdapter`` merges child ``VerificationSource`` lookups
(snapshot + official providers) into one deterministic record list.
It adds no verification semantics of its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
    Identifier,
    SourceMetadata,
    SourceRecord,
)

__all__ = [
    "SUPPORT_DIRECT",
    "SUPPORT_CONTEXTUAL",
    "SUPPORT_SECONDARY",
    "SUPPORT_DISCOVERY",
    "SUPPORT_CONTRADICTORY",
    "REVIEW_UNREVIEWED",
    "REVIEW_VALIDATED",
    "CONFLICT_FIELDS",
    "EvidenceItem",
    "EvidenceSet",
    "EvidenceConflict",
    "CombinedAdapter",
    "detect_conflicts",
    "build_source_records",
]

# Support vocabulary mirrors the evidence specification.
SUPPORT_DIRECT = "direct"
SUPPORT_CONTEXTUAL = "contextual"
SUPPORT_SECONDARY = "secondary"
SUPPORT_DISCOVERY = "discovery"
SUPPORT_CONTRADICTORY = "contradictory"

REVIEW_UNREVIEWED = "unreviewed"
REVIEW_VALIDATED = "validated"

# Fields whose cross-record disagreement is a genuine conflict
# (canonical identity hashes and scalars). Raw SMILES/InChI strings
# are deliberately EXCLUDED: equivalent structures serialize
# differently across providers, and only cheminformatics (out of
# scope) could compare them. Name absence is never disagreement.
CONFLICT_FIELDS = frozenset(
    {
        "formula",
        "inchikey",
        "molecular_weight",
    }
)


@dataclass(frozen=True)
class EvidenceItem:
    """One provider-stated field value with full provenance."""

    source: str = ""  # human source name, e.g. PubChem
    source_id: str = ""  # stable registry ID, e.g. PUBCHEM
    provider: str = ""  # adapter id, e.g. pubchem
    retrieved_at: str = ""  # ISO date of retrieval
    publication_date: Optional[str] = None
    source_version: Optional[str] = None
    field: str = ""
    source_value: Union[str, float, int] = ""
    unit: Optional[str] = None
    support_type: str = SUPPORT_DIRECT
    support_strength: str = "moderate"
    review_status: str = REVIEW_UNREVIEWED
    locator: str = ""  # endpoint/record path for reproduction

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "provider": self.provider,
            "retrieved_at": self.retrieved_at,
            "publication_date": self.publication_date,
            "source_version": self.source_version,
            "field": self.field,
            "source_value": self.source_value,
            "unit": self.unit,
            "support_type": self.support_type,
            "support_strength": self.support_strength,
            "review_status": self.review_status,
            "locator": self.locator,
        }


@dataclass(frozen=True)
class EvidenceSet:
    """All evidence from one provider lookup (one candidate)."""

    provider: str = ""
    lookup_key: str = ""
    retrieved_at: str = ""
    response_hash: str = ""
    locator: str = ""
    items: Tuple[EvidenceItem, ...] = ()
    notices: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "provider": self.provider,
            "lookup_key": self.lookup_key,
            "retrieved_at": self.retrieved_at,
            "response_hash": self.response_hash,
            "locator": self.locator,
            "items": [i.to_dict() for i in self.items],
            "notices": list(self.notices),
        }

    def fields(self, name: str) -> List[EvidenceItem]:
        """Evidence items for one field, in stored order."""
        return [i for i in self.items if i.field == name]


@dataclass(frozen=True)
class EvidenceConflict:
    """A genuine field disagreement between overlapping records."""

    field: str = ""
    values: Tuple[Tuple[str, str, str], ...] = ()
    # (entity_id, value, source_id) per disagreeing side.
    note: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "field": self.field,
            "values": [list(v) for v in self.values],
            "note": self.note,
        }


def _canon(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _canon_code(code: str) -> str:
    return re.sub(r"[\s\-.]+", "", (code or "").strip().upper())


def _records_overlap(a: SourceRecord, b: SourceRecord) -> bool:
    """True when two records plausibly describe the same entity."""
    if a.entity.entity_id and a.entity.entity_id == b.entity.entity_id:
        return True
    if _canon(a.entity.preferred_name) == _canon(
        b.entity.preferred_name
    ) and _canon(a.entity.preferred_name):
        return True
    a_codes = {_canon_code(i.value) for i in a.entity.identifiers}
    b_codes = {_canon_code(i.value) for i in b.entity.identifiers}
    return bool(a_codes & b_codes)


def detect_conflicts(
    records: Sequence[SourceRecord],
) -> List[EvidenceConflict]:
    """Find genuine field disagreements between overlapping records.

    Absence of a field is not disagreement. Name differences are not
    disagreement (non-agreement is handled by gate V3). Identifier
    values claimed by two different entities conflict.
    """
    conflicts: List[EvidenceConflict] = []
    seen = set()
    items = list(records)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            pair = (a.entity.entity_id, b.entity.entity_id)
            if pair in seen or not _records_overlap(a, b):
                continue
            seen.add(pair)
            a_fields = {f.field: str(f.value) for f in a.entity.fields}
            b_fields = {f.field: str(f.value) for f in b.entity.fields}
            for field_name in CONFLICT_FIELDS:
                if (
                    field_name in a_fields
                    and field_name in b_fields
                    and a_fields[field_name] != b_fields[field_name]
                ):
                    conflicts.append(
                        EvidenceConflict(
                            field=field_name,
                            values=(
                                (
                                    a.entity.entity_id,
                                    a_fields[field_name],
                                    a.source.source_id,
                                ),
                                (
                                    b.entity.entity_id,
                                    b_fields[field_name],
                                    b.source.source_id,
                                ),
                            ),
                            note="overlapping records disagree",
                        )
                    )
            a_codes: Dict[str, str] = {}
            for ident in a.entity.identifiers:
                a_codes.setdefault(_canon_code(ident.value), a.entity.entity_id)
            a_names = {_canon(a.entity.preferred_name)}
            a_names.update(_canon(n) for n in a.entity.names)
            a_names.discard("")
            b_names = {_canon(b.entity.preferred_name)}
            b_names.update(_canon(n) for n in b.entity.names)
            b_names.discard("")
            for ident in b.entity.identifiers:
                code = _canon_code(ident.value)
                if (
                    code in a_codes
                    and b.entity.entity_id != a_codes[code]
                    and not (a_names & b_names)
                ):
                    conflicts.append(
                        EvidenceConflict(
                            field="identifier:" + ident.id_type,
                            values=(
                                (a_codes[code], code, a.source.source_id),
                                (
                                    b.entity.entity_id,
                                    code,
                                    b.source.source_id,
                                ),
                            ),
                            note="identifier claimed by two entities",
                        )
                    )
    conflicts.sort(key=lambda c: (c.field, c.values))
    return conflicts


def build_source_records(
    sets: Sequence[EvidenceSet],
) -> List[SourceRecord]:
    """Turn provider evidence sets into gate-ready source records.

    One record per (provider, entity) group, identified by the
    provider's own entity key. No cross-provider entity linking is
    invented: records from different providers keep distinct IDs,
    so agreement must come from field/identifier overlap, never from
    an assumed shared identity.
    """
    records: List[SourceRecord] = []
    for eset in sets:
        by_entity: Dict[str, List[EvidenceItem]] = {}
        for item in eset.items:
            by_entity.setdefault(item.locator, []).append(item)
        for locator in sorted(by_entity):
            records.append(
                _record_from_items(eset.provider, locator, by_entity[locator])
            )
    records.sort(key=lambda r: r.entity.entity_id)
    return records


def _record_from_items(
    provider: str, locator: str, items: List[EvidenceItem]
) -> SourceRecord:
    names = [i.source_value for i in items if i.field == "preferred_name"]
    preferred = str(names[0]) if names else ""
    identifiers = []
    for item in items:
        if item.field.startswith("identifier:"):
            identifiers.append(
                Identifier(
                    id_type=item.field.split(":", 1)[1],
                    value=str(item.source_value),
                    provenance_note="provider evidence " + provider,
                )
            )
    fields = []
    for item in items:
        if item.field in (
            "preferred_name",
        ) or item.field.startswith("identifier:"):
            continue
        fields.append(
            FieldEvidence(
                field=item.field,
                value=item.source_value,
                unit=item.unit,
                source=SourceMetadata(
                    source_id=item.source_id,
                    record_locator=item.locator,
                    source_version=item.source_version or "",
                    retrieved_at=item.retrieved_at,
                    license_note="provider evidence",
                    source_class="A",
                ),
            )
        )
    entity_id = "%s:%s" % (
        provider.upper(),
        re.sub(r"[^A-Za-z0-9]+", "-", locator).strip("-") or "record",
    )
    first = items[0]
    meta = SourceMetadata(
        source_id=first.source_id,
        record_locator=locator,
        source_version=first.source_version or "",
        retrieved_at=first.retrieved_at,
        license_note="provider evidence via " + provider,
        source_class="A",
    )
    entity = CanonicalEntity(
        entity_id=entity_id,
        preferred_name=preferred,
        entity_type="chemical_entity",
        representation_type="single_molecule",
        identifiers=tuple(identifiers),
        names=tuple(
            str(i.source_value)
            for i in items
            if i.field == "synonym"
        ),
        fields=tuple(fields),
        contexts=(),
        verification_status="candidate",
        snapshot_version="",
        verified_at="",
        last_checked=first.retrieved_at,
        source=meta,
    )
    return SourceRecord(entity=entity, source=meta)


class CombinedAdapter(VerificationSource):
    """Deterministic fan-out over child verification sources.

    Merges record lists in child order, deduplicating identical
    entity IDs. Adds no verification semantics: every record still
    passes through the frozen gate. Child notices are merged.
    """

    adapter_id = "combined"
    adapter_version = "1.0.0"

    def __init__(self, children: List[VerificationSource]) -> None:
        super().__init__()
        self._children = list(children)
        versions = sorted(
            {
                c.snapshot_version
                for c in self._children
                if getattr(c, "snapshot_version", "")
            }
        )
        self.snapshot_version = "+".join(versions)

    def lookup_identity(
        self, resolution: Resolution
    ) -> List[SourceRecord]:
        """Merged child records, deterministic entity-ID order."""
        seen = set()
        merged: List[SourceRecord] = []
        for child in self._children:
            for record in child.lookup_identity(resolution) or []:
                if record.entity.entity_id not in seen:
                    seen.add(record.entity.entity_id)
                    merged.append(record)
        merged.sort(key=lambda r: r.entity.entity_id)
        return merged

    def drain_notices(self) -> List[str]:
        """Collect and clear notices from all children."""
        notices: List[str] = []
        for child in self._children:
            drain = getattr(child, "drain_notices", None)
            if callable(drain):
                notices.extend(drain())
        return notices

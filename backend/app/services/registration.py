"""Canonical entity registration (Stage 12, service-role import).

This is the single controlled path that creates rows in
``chemical_entities``. It exists because the resolver must not invent
entities: a canonical record reaches the registry only through

    approved snapshot record -> registration validation
      -> chemical_entities (+ ingredient_aliases)
      -> resolver registry projection

Rules this module keeps (Stage-12 boundary):

* only already-approved canonical records are registrable -- a
  snapshot record must be ``verified`` with complete provenance; the
  import never promotes provisional/conflicted/unknown/unverified
  data and never expands the snapshot itself;
* no chemistry is computed. Formula, mass, structure, and identifier
  values are copied verbatim from the approved snapshot or left NULL.
  A missing field stays missing;
* entity type and representation type are preserved, so a salt or a
  mixture is never stored as a molecule;
* the whole import is all-or-nothing: validation completes before any
  write, and a rejected record aborts the run with an explicit report
  instead of a partial import;
* the operation is idempotent -- entity and alias ids are stable, so a
  second run reports the same records as already present;
* every row keeps the provenance that answers "why is this entity
  allowed into the canonical registry?" (snapshot version, rules
  version, source, locator, verification status and date).

It is an administrative import: no API route calls it, and the
repository methods it uses require the service role.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from app.repositories.protocols import SERVICE_ROLE
from app.repositories.serialize import timestamp_value
from app.services import errors as _errors
from app.services.verification.adapters.snapshot import (
    ALLOWED_REPRESENTATIONS,
    SnapshotAdapter,
)
from app.services.verification.gate import VERIFICATION_RULES_VERSION
from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
)

__all__ = [
    "ImportRejection",
    "ImportReport",
    "RegistrationError",
    "RegistrationRejected",
    "canonical_entity_uuid",
    "entity_row_for",
    "alias_rows_for",
    "build_registry",
    "registration_scope",
    "register_canonical_entities",
    "load_registry_from_repository",
    "empty_registry",
]

# Only entities that are themselves canonical chemicals are
# registrable. Nothing else may create a canonical entity here.
ALLOWED_ENTITY_TYPES = frozenset({"chemical_entity"})

# Only an explicitly approved record may enter the registry.
REGISTRABLE_STATUSES = frozenset({"verified"})

# Fields copied verbatim when the approved snapshot provides them.
# Nothing is derived, defaulted, or inferred.
_FIELD_COLUMNS = {
    "formula": "formula",
    "inchi": "inchi",
    "inchikey": "inchikey",
    "smiles": "smiles",
}
_IDENTIFIER_COLUMNS = {
    "cas": "cas_number",
    "cas_number": "cas_number",
    "chebi": "chebi_id",
    "chebi_id": "chebi_id",
    "inchikey": "inchikey",
    "pubchem_cid": "pubchem_cid",
}
_REGISTRY_REGISTRY_ID = "canonical_registry"


class RegistrationError(_errors.ServiceError):
    """The import cannot proceed (nothing is written)."""


class RegistrationRejected(RegistrationError):
    """One or more records failed validation; whole import refused."""

    def __init__(self, report: "ImportReport") -> None:
        super().__init__(
            "canonical registration refused: %d of %d records rejected"
            % (report.rejected, report.considered)
        )
        self.report = report


@dataclass(frozen=True)
class ImportRejection:
    """One refused record with a machine-readable reason."""

    entity_id: str
    reason: str

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "reason": self.reason}


@dataclass(frozen=True)
class ImportReport:
    """Deterministic import outcome (no timestamps, no secrets)."""

    snapshot_version: str
    rules_version: str
    considered: int
    registered: int
    already_present: int
    rejections: Tuple[ImportRejection, ...] = ()

    @property
    def rejected(self) -> int:
        return len(self.rejections)

    def as_dict(self) -> dict:
        return {
            "snapshot_version": self.snapshot_version,
            "rules_version": self.rules_version,
            "records_considered": self.considered,
            "records_registered": self.registered,
            "records_already_present": self.already_present,
            "records_rejected": self.rejected,
            "rejections": [item.as_dict() for item in self.rejections],
        }


def canonical_entity_uuid(record_id: str) -> str:
    """Stable entity id for an approved snapshot record.

    A record that already carries a UUID keeps it verbatim. Any other
    stable identifier is mapped deterministically, so repeated imports
    resolve to the same row instead of creating a new identity.
    """
    try:
        return str(uuid.UUID(record_id))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(
            uuid.NAMESPACE_URL, "canonical-entity:" + str(record_id)))


def _identifier_map(entity: CanonicalEntity) -> Dict[str, str]:
    return {
        item.id_type.strip().lower(): item.value
        for item in entity.identifiers
        if item.value
    }


def _field_map(entity: CanonicalEntity) -> Dict[str, FieldEvidence]:
    return {item.field.strip().lower(): item for item in entity.fields}


def _text_value(value: object) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _provenance(entity: CanonicalEntity) -> dict:
    """Provenance kept verbatim so the approval stays auditable."""
    return {
        "source_id": entity.source.source_id,
        "source_class": entity.source.source_class,
        "record_locator": entity.source.record_locator,
        "source_version": entity.source.source_version,
        "retrieved_at": entity.source.retrieved_at,
        "license_note": entity.source.license_note,
    }


def _validate_entity(entity: CanonicalEntity) -> Optional[str]:
    """Return a rejection reason, or None when the record is valid."""
    if not entity.entity_id.strip():
        return "missing stable entity id"
    if entity.entity_type.strip().lower() not in ALLOWED_ENTITY_TYPES:
        return "unsupported entity type %s" % entity.entity_type
    representation = entity.representation_type.strip().lower()
    if representation not in ALLOWED_REPRESENTATIONS:
        return "unsupported representation type %s" % (
            entity.representation_type,)
    if entity.verification_status.strip().lower() not in (
        REGISTRABLE_STATUSES
    ):
        return "record is not approved (%s)" % entity.verification_status
    if not _text_value(entity.preferred_name):
        return "missing preferred name"
    if not entity.identifiers:
        return "no identity identifiers"
    source = entity.source
    if not (source.source_id or "").strip():
        return "missing provenance source"
    if not (source.record_locator or "").strip():
        return "missing provenance locator"
    if not (source.retrieved_at or "").strip():
        return "missing provenance retrieval date"
    if not (entity.verified_at or "").strip():
        return "missing verification date"
    for item in entity.identifiers:
        column = _IDENTIFIER_COLUMNS.get(item.id_type.strip().lower())
        if column == "pubchem_cid" and not item.value.strip().isdigit():
            return "malformed pubchem_cid value"
    return None


def entity_row_for(
    entity: CanonicalEntity,
    *,
    snapshot_version: str,
    rules_version: str,
) -> dict:
    """Project one approved record onto `chemical_entities`.

    Only values present in the approved snapshot are written. Absent
    fields stay NULL: nothing is calculated, defaulted, or guessed.
    """
    fields = _field_map(entity)
    identifiers = _identifier_map(entity)
    row: Dict[str, object] = {
        "id": canonical_entity_uuid(entity.entity_id),
        "preferred_name": entity.preferred_name.strip(),
        "entity_type": entity.entity_type.strip(),
        "representation_type": entity.representation_type.strip(),
        "status": entity.verification_status.strip(),
        "formula": None,
        "molecular_weight": None,
        "molecular_weight_unit": None,
        "cas_number": None,
        "pubchem_cid": None,
        "chebi_id": None,
        "inchi": None,
        "inchikey": None,
        "smiles": None,
        "chemical_class": None,
        "structure_status": None,
        "first_verified_at": timestamp_value(entity.verified_at),
        "last_verified_at": timestamp_value(entity.last_checked),
        "metadata": {
            "snapshot_version": snapshot_version,
            "rules_version": rules_version,
            "verification_status": entity.verification_status.strip(),
            "verified_at": entity.verified_at.strip(),
            "provenance": _provenance(entity),
            "identifiers": [
                {
                    "id_type": item.id_type,
                    "value": item.value,
                    "provenance_note": item.provenance_note,
                }
                for item in entity.identifiers
            ],
            "imported_by": "canonical-registration-import",
        },
    }
    for field_name, column in _FIELD_COLUMNS.items():
        row[column] = _text_value(fields[field_name].value) \
            if field_name in fields else None
    mass = fields.get("molecular_weight")
    if mass is not None and isinstance(mass.value, (int, float)):
        # Verbatim transcription as an exact decimal: the snapshot
        # value is preserved, never recomputed or re-rounded.
        row["molecular_weight"] = Decimal(str(mass.value))
        row["molecular_weight_unit"] = _text_value(mass.unit)
    for id_type, column in _IDENTIFIER_COLUMNS.items():
        value = identifiers.get(id_type)
        if value is None:
            continue
        if column == "pubchem_cid":
            row[column] = int(value.strip())
        else:
            row[column] = _text_value(value)
    return row


def alias_rows_for(
    entity: CanonicalEntity, *, verified: bool
) -> List[dict]:
    """Alias rows for every declared name except the preferred one."""
    preferred = entity.preferred_name.strip().lower()
    rows: List[dict] = []
    seen = set()
    for name in entity.names:
        text = (name or "").strip()
        key = text.lower()
        if not text or key == preferred or key in seen:
            continue
        seen.add(key)
        rows.append({
            "id": str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                "canonical-alias:%s:%s" % (
                    canonical_entity_uuid(entity.entity_id), key))),
            "chemical_entity_id": canonical_entity_uuid(entity.entity_id),
            "alias": text,
            "alias_type": "name",
            "language_code": None,
            "region_code": None,
            "source_id": None,
            "verified": bool(verified),
        })
    return rows


def build_registry(
    entity_rows: Sequence[dict],
    alias_rows: Sequence[dict],
    *,
    version: str = "0",
):
    """Project registered canonical entities into a resolver registry.

    The projection is a read model of `chemical_entities` +
    `ingredient_aliases`: it is rebuilt from those rows, never edited
    separately, so there is exactly one authoritative registration
    path. Live provider responses are never added here -- only
    registered canonical entities are resolvable.

    `RegistryEntry.ref` stays registry-local by design (the resolver
    yields candidates; verification assigns canonical identity from
    evidence), so the ref is a stable derived label rather than the
    entity UUID.
    """
    from app.services.entity_resolver import (
        InMemoryRegistry,
        RegistryEntry,
    )

    aliases_by_entity: Dict[str, List[str]] = {}
    for row in alias_rows:
        aliases_by_entity.setdefault(
            str(row.get("chemical_entity_id")), []
        ).append(str(row.get("alias", "")))
    entries: List[RegistryEntry] = []
    for row in entity_rows:
        entity_id = str(row.get("id"))
        identifiers = [
            str(item.get("value"))
            for item in (row.get("metadata") or {}).get("identifiers", [])
            if isinstance(item, dict) and item.get("value")
        ]
        entries.append(
            RegistryEntry(
                ref=_registry_ref(entity_id),
                preferred_name=str(row.get("preferred_name", "")),
                display_name=str(row.get("preferred_name", "")),
                aliases=sorted(set(aliases_by_entity.get(entity_id, []))),
                identifiers=identifiers,
                entity_class=str(row.get("representation_type") or "unknown"),
                contexts=[],
                source=str(
                    ((row.get("metadata") or {}).get("provenance") or {})
                    .get("source_id", "")
                ),
            )
        )
    return InMemoryRegistry(
        entries, registry_id=_REGISTRY_REGISTRY_ID, version=version)


def _registry_ref(entity_id: str) -> str:
    return "CANON-%s" % entity_id.replace("-", "")[:12]


def empty_registry():
    """Registry with no entries (nothing is resolvable)."""
    from app.services.entity_resolver import InMemoryRegistry

    return InMemoryRegistry(
        [], registry_id=_REGISTRY_REGISTRY_ID, version="0")


async def load_registry_from_repository(
    entity_repo,
    *,
    role: str = SERVICE_ROLE,
    version: str = "0",
):
    """Build the resolver registry from registered canonical entities.

    This is the one integration point between the canonical registry
    and the resolver: the resolver reads a projection of
    `chemical_entities` + `ingredient_aliases`. Live provider
    responses are never injected here, so a lookup can only ever
    return an entity that was registered through the import path.
    """
    entities = await entity_repo.list_entities(role=role)
    aliases = await entity_repo.list_aliases(role=role)
    return build_registry(entities, aliases, version=version)


@asynccontextmanager
async def registration_scope(unit_of_work):
    """Transactional scope across both unit-of-work flavours."""
    atomic = getattr(unit_of_work, "atomic", None)
    if callable(atomic):
        async with atomic() as bound:
            yield bound
        return
    with unit_of_work.transaction() as bound:
        yield bound


async def register_canonical_entities(
    unit_of_work,
    adapter: SnapshotAdapter,
    *,
    expected_snapshot_version: Optional[str] = None,
    rules_version: str = VERIFICATION_RULES_VERSION,
    role: str = SERVICE_ROLE,
) -> ImportReport:
    """Import the approved canonical records into `chemical_entities`.

    All-or-nothing. Validation of the whole artifact completes first;
    any rejected record raises :class:`RegistrationRejected` carrying
    the report, and nothing is written. A rejected *write* (for
    example a constraint violation) propagates inside the
    transaction, so the run leaves no partial state either.
    """
    snapshot_version = adapter.snapshot_version
    if not snapshot_version.strip():
        raise RegistrationError("snapshot version is missing")
    if expected_snapshot_version and (
        snapshot_version != expected_snapshot_version
    ):
        raise RegistrationError(
            "snapshot version %s is not the expected %s"
            % (snapshot_version, expected_snapshot_version))
    artifact_rules = adapter.rules_version
    if artifact_rules.strip() != rules_version.strip():
        raise RegistrationError(
            "snapshot rule version %s does not match verification "
            "rules %s" % (artifact_rules, rules_version))

    entities = adapter.canonical_entities()
    rejections: List[ImportRejection] = []
    for entity in entities:
        reason = _validate_entity(entity)
        if reason is not None:
            rejections.append(
                ImportRejection(entity_id=entity.entity_id, reason=reason))
    duplicate_ids = _duplicate_ids(entities)
    rejections.extend(duplicate_ids)
    if rejections:
        raise RegistrationRejected(
            ImportReport(
                snapshot_version=snapshot_version,
                rules_version=rules_version,
                considered=len(entities),
                registered=0,
                already_present=0,
                rejections=tuple(rejections),
            )
        )

    registered = 0
    present = 0
    async with registration_scope(unit_of_work) as repos:
        entities_repo = repos.entities
        for entity in entities:
            entity_id = canonical_entity_uuid(entity.entity_id)
            if await _exists(entities_repo, entity_id, role=role):
                present += 1
                continue
            row = entity_row_for(
                entity,
                snapshot_version=snapshot_version,
                rules_version=rules_version,
            )
            await entities_repo.save_entity(row, role=role)
            for alias in alias_rows_for(
                entity, verified=True
            ):
                await entities_repo.save_alias(alias, role=role)
            registered += 1
    return ImportReport(
        snapshot_version=snapshot_version,
        rules_version=rules_version,
        considered=len(entities),
        registered=registered,
        already_present=present,
    )


def _duplicate_ids(entities: Sequence[CanonicalEntity]) -> List[ImportRejection]:
    seen: Dict[str, int] = {}
    for entity in entities:
        key = canonical_entity_uuid(entity.entity_id)
        seen[key] = seen.get(key, 0) + 1
    return [
        ImportRejection(
            entity_id=entity.entity_id,
            reason="duplicate entity id in artifact",
        )
        for entity in entities
        if seen[canonical_entity_uuid(entity.entity_id)] > 1
    ]


async def _exists(entities_repo, entity_id: str, *, role: str) -> bool:
    try:
        await entities_repo.get_entity(entity_id, role=role)
    except KeyError:
        return False
    return True

"""Local canonical snapshot adapter (the Stage-7 authority).

Loads a versioned snapshot artifact (``snapshots/canonical_vN.json``),
validates structure and bounds, and answers identity lookups purely
from local data: deterministic, offline, no network access.

The snapshot file is immutable at runtime -- this adapter never
writes. A future ingestion process creates ``canonical_v(N+1)``;
this stage does not implement ingestion.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Union

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.gate import (
    MOLECULAR_ONLY_FIELDS,
    NON_MOLECULAR_TYPES,
    derive_name_key,
)
from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
    Identifier,
    SourceMetadata,
    SourceRecord,
)

__all__ = ["SnapshotAdapter", "SnapshotError"]

SNAPSHOT_ADAPTER_VERSION = "1.0.0"

# Load-time bounds (untrusted-file hygiene; snapshot is data, not code).
MAX_SNAPSHOT_BYTES = 1_048_576
MAX_RECORDS = 1000
MAX_STRING_LEN = 2000
MAX_IDENTIFIERS = 50
MAX_NAMES = 50
MAX_FIELDS = 100

_ALLOWED_REPRESENTATIONS = frozenset(
    {
        "single_molecule",
        "salt",
        "salt_or_form",
        "polymer",
        "mixture",
        "natural_complex",
        "formulation",
        "material",
        "trade_name",
        "unknown",
    }
)
_ALLOWED_STATUSES = frozenset({"verified", "provisional"})


class SnapshotError(ValueError):
    """Raised when a snapshot artifact fails structural validation."""


def _canon(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _canon_code(code: str) -> str:
    return re.sub(r"[\s\-.]+", "", (code or "").strip().upper())


def _check_str(value: object, *, what: str) -> str:
    if not isinstance(value, str):
        raise SnapshotError("%s must be a string" % what)
    if len(value) > MAX_STRING_LEN:
        raise SnapshotError("%s exceeds string bound" % what)
    return value


class SnapshotAdapter(VerificationSource):
    """Deterministic lookup over a validated snapshot artifact."""

    adapter_id = "local_canonical_snapshot"
    adapter_version = SNAPSHOT_ADAPTER_VERSION

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)
        raw = self._read_file()
        data = self._parse_json(raw)
        self.snapshot_version = self._load_version(data)
        self.rules_version = self._load_rules_version(data)
        self._entities = self._load_records(data)
        self._by_name: Dict[str, List[CanonicalEntity]] = {}
        self._by_code: Dict[str, List[CanonicalEntity]] = {}
        for entity in self._entities:
            keys = {_canon(entity.preferred_name)}
            keys.update(_canon(n) for n in entity.names)
            for key in keys:
                if key:
                    self._by_name.setdefault(key, []).append(entity)
            for ident in entity.identifiers:
                code = _canon_code(ident.value)
                if code:
                    self._by_code.setdefault(code, []).append(entity)
        self.available = True

    @property
    def record_count(self) -> int:
        """Number of loaded canonical records."""
        return len(self._entities)

    def _read_file(self) -> bytes:
        try:
            size = self._path.stat().st_size
        except OSError as exc:
            raise SnapshotError("snapshot unreadable: %s" % exc)
        if size > MAX_SNAPSHOT_BYTES:
            raise SnapshotError("snapshot exceeds size bound")
        try:
            return self._path.read_bytes()
        except OSError as exc:
            raise SnapshotError("snapshot unreadable: %s" % exc)

    def _parse_json(self, raw: bytes) -> dict:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("snapshot is not valid JSON: %s" % exc)
        if not isinstance(data, dict):
            raise SnapshotError("snapshot top level must be an object")
        return data

    def _load_version(self, data: dict) -> str:
        version = data.get("snapshot_version")
        return _check_str(version, what="snapshot_version")

    def _load_rules_version(self, data: dict) -> str:
        version = data.get("verification_rule_version")
        return _check_str(version, what="verification_rule_version")

    def _load_records(self, data: dict) -> List[CanonicalEntity]:
        records = data.get("records")
        if not isinstance(records, list):
            raise SnapshotError("snapshot records must be a list")
        if len(records) > MAX_RECORDS:
            raise SnapshotError("snapshot exceeds record bound")
        return [self._load_entity(item, i) for i, item in enumerate(records)]

    def _load_entity(self, item: object, index: int) -> CanonicalEntity:
        what = "record %d" % index
        if not isinstance(item, dict):
            raise SnapshotError("%s must be an object" % what)
        for key in (
            "entity_id",
            "preferred_name",
            "entity_type",
            "representation_type",
            "verification_status",
        ):
            if key not in item:
                raise SnapshotError("%s missing %s" % (what, key))
        entity_id = _check_str(item["entity_id"], what="entity_id")
        preferred = _check_str(item["preferred_name"], what="name")
        entity_type = _check_str(item["entity_type"], what="type")
        representation = _check_str(
            item["representation_type"], what="representation"
        )
        if representation not in _ALLOWED_REPRESENTATIONS:
            raise SnapshotError("%s bad representation" % what)
        status = _check_str(item["verification_status"], what="status")
        if status not in _ALLOWED_STATUSES:
            raise SnapshotError("%s bad status %s" % (what, status))
        identifiers = self._load_identifiers(item.get("identifiers"), what)
        names = self._load_names(item.get("names"), what)
        fields = self._load_fields(
            item.get("fields"), what, representation
        )
        contexts = self._load_names(item.get("contexts"), what)
        source = self._load_source(item.get("provenance"), what)
        return CanonicalEntity(
            entity_id=entity_id,
            preferred_name=preferred,
            entity_type=entity_type,
            representation_type=representation,
            identifiers=tuple(identifiers),
            names=tuple(names),
            fields=tuple(fields),
            contexts=tuple(contexts),
            verification_status=status,
            snapshot_version=self.snapshot_version,
            verified_at=str(item.get("verified_at", ""))[:MAX_STRING_LEN],
            last_checked=str(item.get("last_checked", ""))[
                :MAX_STRING_LEN
            ],
            source=source,
        )

    def _load_identifiers(
        self, value: object, what: str
    ) -> List[Identifier]:
        if value is None:
            return []
        if not isinstance(value, list) or len(value) > MAX_IDENTIFIERS:
            raise SnapshotError("%s bad identifiers" % what)
        out = []
        for entry in value:
            if not isinstance(entry, dict):
                raise SnapshotError("%s bad identifier" % what)
            out.append(
                Identifier(
                    id_type=_check_str(
                        entry.get("id_type"), what="id_type"
                    ),
                    value=_check_str(entry.get("value"), what="id"),
                    provenance_note=str(
                        entry.get("provenance_note", "")
                    )[:MAX_STRING_LEN],
                )
            )
        return out

    def _load_names(
        self, value: object, what: str
    ) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list) or len(value) > MAX_NAMES:
            raise SnapshotError("%s bad names" % what)
        return [_check_str(v, what="name") for v in value]

    def _load_fields(
        self, value: object, what: str, representation: str
    ) -> List[FieldEvidence]:
        if value is None:
            return []
        if not isinstance(value, dict) or len(value) > MAX_FIELDS:
            raise SnapshotError("%s bad fields" % what)
        non_mol = representation in NON_MOLECULAR_TYPES
        out = []
        for name, spec in value.items():
            if non_mol and name in MOLECULAR_ONLY_FIELDS:
                raise SnapshotError(
                    "%s forbids molecular field %s" % (what, name)
                )
            if not isinstance(spec, dict) or "value" not in spec:
                raise SnapshotError("%s bad field %s" % (what, name))
            raw_value = spec["value"]
            if not isinstance(raw_value, (str, float, int)):
                raise SnapshotError("%s bad value %s" % (what, name))
            if isinstance(raw_value, str) and len(raw_value) > (
                MAX_STRING_LEN
            ):
                raise SnapshotError("%s value too long" % what)
            unit = spec.get("unit")
            if unit is not None and not isinstance(unit, str):
                raise SnapshotError("%s bad unit" % what)
            out.append(
                FieldEvidence(
                    field=_check_str(name, what="field")[:MAX_STRING_LEN],
                    value=raw_value,
                    unit=unit,
                    source=self._field_source(what),
                )
            )
        return out

    def _field_source(self, what: str) -> SourceMetadata:
        return SourceMetadata(
            source_id="SNAPSHOT:%s" % self.snapshot_version,
            record_locator=what,
            source_version=self.snapshot_version,
            retrieved_at="",
            license_note="field transcribed from snapshot record",
            source_class="A",
        )

    def _load_source(
        self, value: object, what: str
    ) -> SourceMetadata:
        if not isinstance(value, dict):
            raise SnapshotError("%s bad provenance" % what)
        return SourceMetadata(
            source_id=_check_str(value.get("source_id"), what="src"),
            record_locator=_check_str(
                value.get("record_locator", ""), what="locator"
            ),
            source_version=_check_str(
                value.get("source_version", ""), what="srcver"
            ),
            retrieved_at=_check_str(
                value.get("retrieved_at", ""), what="retrieved"
            ),
            license_note=_check_str(
                value.get("license_note", ""), what="license"
            ),
            source_class=_check_str(
                value.get("source_class", ""), what="class"
            ),
        )

    def _record_for(self, entity: CanonicalEntity) -> SourceRecord:
        return SourceRecord(entity=entity, source=entity.source)

    def lookup_identity(
        self, resolution: Resolution
    ) -> List[SourceRecord]:
        """Exact name/identifier retrieval. Unknown input -> []."""
        if resolution is None:
            return []
        key = derive_name_key(
            resolution.normalized_text or "", resolution.identifier
        )
        seen = set()
        hits: List[CanonicalEntity] = []
        for entity in self._by_name.get(key, []):
            if entity.entity_id not in seen:
                seen.add(entity.entity_id)
                hits.append(entity)
        if resolution.identifier:
            want = _canon_code(resolution.identifier)
            for entity in self._by_code.get(want, []):
                if entity.entity_id not in seen:
                    seen.add(entity.entity_id)
                    hits.append(entity)
        hits.sort(key=lambda e: e.entity_id)
        return [self._record_for(e) for e in hits]

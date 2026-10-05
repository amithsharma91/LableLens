"""Tests for the typed evidence model, conflict detection,
record building, and the combined adapter (no network)."""

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.evidence import (
    CombinedAdapter,
    EvidenceItem,
    EvidenceSet,
    build_source_records,
    detect_conflicts,
)
from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
    Identifier,
    SourceMetadata,
    SourceRecord,
)


def _meta(source_id="PUBCHEM", cls="A", locator="CID:1"):
    return SourceMetadata(
        source_id=source_id,
        record_locator=locator,
        source_version="v",
        retrieved_at="2026-10-05",
        license_note="test",
        source_class=cls,
    )


def _record(eid, name, fields=(), ids=(), cls="A", sid="PUBCHEM"):
    meta = _meta(source_id=sid, cls=cls, locator=eid)
    return SourceRecord(
        entity=CanonicalEntity(
            entity_id=eid,
            preferred_name=name,
            entity_type="chemical_entity",
            representation_type="single_molecule",
            identifiers=tuple(
                Identifier(id_type=t, value=v, provenance_note="t")
                for t, v in ids
            ),
            names=(),
            fields=tuple(fields),
            contexts=(),
            verification_status="verified",
            snapshot_version="s",
            verified_at="2026-10-05",
            last_checked="2026-10-05",
            source=meta,
        ),
        source=meta,
    )


def _field(name, value):
    return FieldEvidence(field=name, value=value, unit=None,
                         source=_meta())


def test_field_level_evidence_preserved():
    rec = _record("E1", "test", fields=[_field("formula", "C1")])
    assert rec.entity.field_value("formula").value == "C1"
    assert rec.entity.field_value("missing") is None


def test_formula_disagreement_is_conflict():
    a = _record("E1", "test", fields=[_field("formula", "C1")])
    b = _record("E2", "test", fields=[_field("formula", "C2")])
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].field == "formula"


def test_agreement_is_not_conflict():
    a = _record("E1", "test", fields=[_field("formula", "C1")])
    b = _record("E2", "test", fields=[_field("formula", "C1")])
    assert detect_conflicts([a, b]) == []


def test_absence_is_not_conflict():
    a = _record("E1", "test", fields=[_field("formula", "C1")])
    b = _record("E2", "test")
    assert detect_conflicts([a, b]) == []


def test_name_difference_is_not_conflict():
    a = _record("E1", "alpha", fields=[_field("formula", "C1")])
    b = _record("E2", "beta", fields=[_field("formula", "C1")])
    assert detect_conflicts([a, b]) == []


def test_identifier_claimed_twice_conflicts():
    a = _record("E1", "alpha", ids=[("e_number", "E330")])
    b = _record("E2", "beta", ids=[("e_number", "E330")])
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].field == "identifier:e_number"


def test_smiles_serialization_difference_not_conflict():
    a = _record("E1", "test", fields=[_field("smiles", "CCO")])
    b = _record("E2", "test", fields=[_field("smiles", "OCC")])
    assert detect_conflicts([a, b]) == []


def test_build_source_records_namespaces_providers():
    eset = EvidenceSet(
        provider="pubchem",
        lookup_key="pubchem:name:test",
        retrieved_at="2026-10-05",
        response_hash="h",
        locator="CID:99",
        items=(
            EvidenceItem(
                source="PubChem", source_id="PUBCHEM", provider="pubchem",
                retrieved_at="2026-10-05", field="preferred_name",
                source_value="Test", locator="CID:99",
            ),
            EvidenceItem(
                source="PubChem", source_id="PUBCHEM", provider="pubchem",
                retrieved_at="2026-10-05", field="formula",
                source_value="C1", locator="CID:99",
            ),
        ),
        notices=(),
    )
    records = build_source_records([eset])
    assert len(records) == 1
    assert records[0].entity.entity_id == "PUBCHEM:CID-99"
    assert records[0].entity.preferred_name == "Test"


def test_combined_adapter_merges_deterministically():
    import pathlib

    snap = (
        pathlib.Path(__file__).resolve().parents[4]
        / "snapshots" / "canonical_v1.json"
    )
    adapter = CombinedAdapter([SnapshotAdapter(snap), SnapshotAdapter(snap)])
    res = Resolution(raw_text="citric acid", normalized_text="citric acid",
                     status="exact_match")
    first = [r.entity.entity_id for r in adapter.lookup_identity(res)]
    second = [r.entity.entity_id for r in adapter.lookup_identity(res)]
    assert first == second
    assert len(first) == 1  # deduplicated across children
    assert adapter.snapshot_version == "canonical_v1"
    assert adapter.drain_notices() == []

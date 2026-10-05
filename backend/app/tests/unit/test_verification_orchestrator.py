"""Tests for the verification orchestrator (decision mapping).

End-to-end decisions use the real ``snapshots/canonical_v1.json``
(genuine PubChem provenance). Synthetic adapters/records (``SYNTH``)
cover conflict, mismatch, context, and degradation paths.
"""

import json
from pathlib import Path

from app.services.entity_resolver import (
    Candidate,
    InMemoryRegistry,
    RegistryEntry,
    Resolution,
    resolve_node,
)
from app.services.ingredient_normalizer import normalize_label_text
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.adapters.manual import ManualAdapter
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.models import (
    CanonicalEntity,
    Identifier,
    SourceMetadata,
    SourceRecord,
)
from app.services.verification.orchestrator import verify_candidate

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "snapshots" / "canonical_v1.json"
)

CITRIC_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"
SYNTH = "SYNTHETIC_FIXTURE_SOURCE"


def _stage5_registry():
    return InMemoryRegistry(
        [
            RegistryEntry(
                ref="T7-001",
                preferred_name="citric acid",
                display_name="Citric Acid (stage-7 fixture)",
                identifiers=["E330"],
                entity_class="single_molecule",
                source="synthetic_test_fixture",
            ),
            RegistryEntry(
                ref="T7-002",
                preferred_name="sodium benzoate",
                display_name="Sodium Benzoate (stage-7 fixture)",
                identifiers=["E211"],
                entity_class="salt",
                source="synthetic_test_fixture",
            ),
        ],
        registry_id="stage7_test_registry",
        version="t7",
    )


def _resolve(text):
    norm = normalize_label_text(text)
    assert len(norm.nodes) == 1, text
    return resolve_node(norm.nodes[0], _stage5_registry())


def _synth_meta(eid, cls="A"):
    return SourceMetadata(
        source_id=SYNTH,
        record_locator="synth:" + eid,
        source_version="synth-1",
        retrieved_at="2026-10-05",
        license_note="synthetic fixture, not evidence",
        source_class=cls,
    )


def _synth_record(eid, name, rep="single_molecule", ids=(), contexts=()):
    meta = _synth_meta(eid)
    return SourceRecord(
        entity=CanonicalEntity(
            entity_id=eid,
            preferred_name=name,
            entity_type="chemical_entity",
            representation_type=rep,
            identifiers=tuple(
                Identifier(id_type=t, value=v, provenance_note="synthetic")
                for t, v in ids
            ),
            names=(),
            fields=(),
            contexts=tuple(contexts),
            verification_status="verified",
            snapshot_version="synth",
            verified_at="2026-10-05",
            last_checked="2026-10-05",
            source=meta,
        ),
        source=meta,
    )


class _StaticAdapter(VerificationSource):
    """Deterministic synthetic adapter for degradation paths."""

    adapter_id = "synthetic_static"
    adapter_version = "t7"
    snapshot_version = "synth"
    rules_version = "1.0.0"

    def __init__(self, records):
        self._records = list(records)

    def lookup_identity(self, resolution):
        return list(self._records)


def _direct_resolution(text, identifier=None, candidate_type="single_molecule"):
    return Resolution(
        raw_text=text,
        normalized_text=text.lower(),
        identifier=identifier,
        status="exact_match",
        candidates=[
            Candidate(
                candidate_ref="T7-X",
                display_name=text,
                candidate_type=candidate_type,
                source="synthetic_test_fixture",
                match_method="exact_normalized_name",
                match_score=0.95,
                reason="synthetic",
            )
        ],
    )


# --- Full verification against the real snapshot -------------------------

def test_verified_identity_with_dual_agreement():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("Citric Acid (E330)"), adapter)
    assert decision.status == "verified"
    assert decision.identity_confidence == "HIGH"
    assert decision.entity_id == CITRIC_ID
    assert decision.snapshot_version == "canonical_v1"
    assert decision.rules_version == "1.0.0"
    assert any(s.source_id == "PUBCHEM" for s in decision.source_refs)
    assert all(g.result == "PASS" for g in decision.gate_results)


def test_verified_field_values_match_snapshot_verbatim():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("Citric Acid (E330)"), adapter)
    assert decision.status == "verified"
    by_field = {c.field: c.value for c in decision.claims}
    assert by_field["formula"] == "C6H8O7"
    assert by_field["inchikey"] == "KRKNYBCHXYNGOX-UHFFFAOYSA-N"
    assert by_field["molecular_weight"] == 192.12
    assert by_field["smiles"] == "C(C(=O)O)C(CC(=O)O)(C(=O)O)O"


def test_bare_name_single_source_is_provisional():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("citric acid"), adapter)
    assert decision.status == "provisional"
    assert decision.entity_id is None
    assert not [c for c in decision.claims if c.field != "identity"]


def test_ocr_near_candidate_never_verifies():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("Sodlum Benzoate"), adapter)
    assert decision.status in ("unknown", "unverified", "provisional")
    assert decision.status != "verified"
    assert decision.entity_id is None


def test_unknown_input_unknown_decision():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("XYZ proprietary blend"), adapter)
    assert decision.status == "unknown"
    assert decision.entity_id is None
    assert decision.evidence == ()


# --- Degradation paths (synthetic adapters) --------------------------------

def test_identifier_mismatch_is_conflicted():
    adapter = _StaticAdapter(
        [
            _synth_record("ENT-A", "test acid"),
            _synth_record(
                "ENT-B", "other acid", ids=[("e_number", "E999")]
            ),
        ]
    )
    res = _direct_resolution("test acid E999", identifier="E 999")
    decision = verify_candidate(res, adapter)
    assert decision.status == "conflicted"
    assert decision.identity_confidence == "CONFLICTED"


def test_entity_type_mismatch_is_unverified():
    adapter = _StaticAdapter(
        [_synth_record("ENT-M", "test blend", rep="mixture")]
    )
    res = _direct_resolution("test blend", candidate_type="single_molecule")
    decision = verify_candidate(res, adapter)
    assert decision.status == "unverified"
    assert decision.entity_id is None


def test_context_contradiction_is_provisional():
    adapter = _StaticAdapter(
        [_synth_record("ENT-C", "test blend", rep="mixture",
                       contexts=["food"])]
    )
    res = _direct_resolution(
        "test blend", candidate_type="mixture", identifier=None
    )
    decision = verify_candidate(res, adapter, context="cosmetics")
    assert decision.status == "provisional"


def test_human_disambiguation_admits_ambiguous():
    adapter = _StaticAdapter(
        [
            _synth_record("ENT-1", "test shared alias"),
            _synth_record("ENT-2", "test shared alias"),
        ]
    )
    res = Resolution(
        raw_text="test shared alias",
        normalized_text="test shared alias",
        status="ambiguous",
        candidates=[],
    )
    without = verify_candidate(res, adapter)
    assert without.status in ("provisional", "unverified", "unknown")
    with_human = verify_candidate(
        res, adapter, human_disambiguation=True
    )
    v1 = [g for g in with_human.gate_results if g.rule_id.startswith("V1")]
    assert v1 and v1[0].result == "PASS"


def test_rules_version_mismatch_downgrades():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    adapter.rules_version = "0.0.0"
    decision = verify_candidate(_resolve("Citric Acid (E330)"), adapter)
    assert decision.status == "provisional"
    assert any("mismatch" in w for w in decision.warnings)


def test_manual_adapter_never_verifies():
    decision = verify_candidate(_resolve("Citric Acid (E330)"),
                                ManualAdapter())
    assert decision.status == "unknown"
    assert decision.entity_id is None


def test_obsolete_never_emitted():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    for text in ("Citric Acid (E330)", "citric acid", "Sodlum Benzoate",
                 "XYZ proprietary blend", "glycerol", "E422"):
        decision = verify_candidate(_resolve(text), adapter)
        assert decision.status != "obsolete", text


# --- Safety / determinism / serialization -----------------------------------

def test_safety_unknown_carries_no_chemistry():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("XYZ proprietary blend"), adapter)
    payload = json.dumps(decision.to_dict()).lower()
    for token in ("smiles", "inchi", "formula", "molecular_weight",
                  "cas", "role", "rdkit"):
        assert token not in payload


def test_determinism():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    res = _resolve("Citric Acid (E330)")
    assert (verify_candidate(res, adapter).to_dict()
            == verify_candidate(res, adapter).to_dict())


def test_decision_json_serializable():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    decision = verify_candidate(_resolve("Citric Acid (E330)"), adapter)
    json.dumps(decision.to_dict())

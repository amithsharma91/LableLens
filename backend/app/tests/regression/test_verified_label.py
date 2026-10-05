"""First real-label VERIFIED path (Stage 15, RL-15-01).

Simple Linctus Sugar Free, UK SmPC §6.1: `Glycerol (E422)` and
`Sodium Benzoate (E211)` carry a registry-agreeing name together
with a belonging identifier on the same record, so the frozen
V1–V7 gate verifies both with no waiver, no shortcut, and no human
override involved. The three remaining nodes stay unresolved.

Every assertion below runs through the unchanged pipeline
(`run_label` over `ObservationService`); nothing here special-cases
the fixture.
"""

import asyncio
import json
from pathlib import Path

from app.regression.label_input import LabelInput
from app.regression.metrics import summarize
from app.regression.runner import run_label
from app.repositories.memory import MemoryUnitOfWork
from app.services.observation_service import ObservationService
from app.services.registration import (
    alias_rows_for,
    build_registry,
    entity_row_for,
)
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.gate import VERIFICATION_RULES_VERSION

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "regression" / "fixtures" / "real_labels"
)
SNAPSHOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "snapshots" / "canonical_v1.json"
)

GLYCEROL_ID = "763389d0-3732-47dd-ad27-2c62a50e95b8"
BENZOATE_ID = "6223de87-1d0c-49f9-a926-e2b57e0fc8ae"
GLYCEROL_REF = "CANON-763389d03732"
BENZOATE_REF = "CANON-6223de871d0c"

FROZEN_RULES = [
    "V1_admissible_candidate",
    "V2_authoritative_source",
    "V3_identity_agreement",
    "V4_identifier_validation",
    "V5_entity_type_validation",
    "V6_source_appropriateness",
    "V7_context_checks",
]


def _fixture() -> dict:
    return json.loads((FIXTURES / "RL-15-01.json").read_text())


def _label(fixture: dict) -> LabelInput:
    return LabelInput.from_dict({
        "label_id": fixture["label_id"],
        "raw_text": fixture["raw_text"],
        "input_method": fixture["input_method"],
        "source_reference": fixture["source_reference"],
    })


def _service():
    adapter = SnapshotAdapter(str(SNAPSHOT))
    entities = adapter.canonical_entities()
    rows = [
        entity_row_for(
            entity, snapshot_version="canonical_v1",
            rules_version=VERIFICATION_RULES_VERSION)
        for entity in entities
    ]
    registry = build_registry(
        rows,
        [alias for entity in entities
         for alias in alias_rows_for(entity, verified=True)],
        version=str(len(rows)),
    )
    unit_of_work = MemoryUnitOfWork()
    for row in rows:
        unit_of_work.entities.register({
            "id": row["id"],
            "preferred_name": row["preferred_name"],
            "entity_type": "chemical_entity",
            "representation_type": row["representation_type"],
            "status": "active",
            "structure_status": "unavailable",
        })
    service = ObservationService(
        unit_of_work, registry=registry, adapters=[adapter])
    return service, unit_of_work, registry


def _run():
    fixture = _fixture()
    service, unit_of_work, _ = _service()
    run = asyncio.run(run_label(service, _label(fixture), fixture))
    return run.to_dict(), service, unit_of_work


def _by_norm(run, normalized: str) -> dict:
    return next(
        result for result in run["ingredient_results"]
        if result["normalized_text"] == normalized)


# -- parsing, normalization, resolution ---------------------------------------


def test_verified_fixture_matches_expectations_with_no_mismatch():
    run, _, _ = _run()
    assert run["mismatches"] == []
    assert len(run["ingredient_results"]) == 5


def test_normalized_forms_keep_name_and_code():
    run, _, _ = _run()
    assert _by_norm(run, "glycerol E 422")["raw_text"] == "Glycerol (E422)"
    assert _by_norm(
        run, "sodium benzoate E 211")["raw_text"] == "Sodium Benzoate (E211)"


def test_exact_identifier_resolution_to_registry_entities():
    run, _, _ = _run()
    glycerol = _by_norm(run, "glycerol E 422")
    assert glycerol["match_status"] == "exact_match"
    assert glycerol["entity_ref"] == GLYCEROL_REF
    benzoate = _by_norm(run, "sodium benzoate E 211")
    assert benzoate["match_status"] == "exact_match"
    assert benzoate["entity_ref"] == BENZOATE_REF


def test_registry_lookup_names_the_same_entities():
    _, _, registry = _service()
    glycerol = registry.lookup_identifier("E422")
    assert [entry.ref for entry in glycerol] == [GLYCEROL_REF]
    assert registry.lookup_exact_name("glycerol")[0].ref == GLYCEROL_REF
    benzoate = registry.lookup_identifier("E211")
    assert [entry.ref for entry in benzoate] == [BENZOATE_REF]


# -- V1–V7, one rule at a time --------------------------------------------------


def test_all_seven_gates_pass_for_both_ingredients():
    run, service, _ = _run()
    for normalized in ("glycerol E 422", "sodium benzoate E 211"):
        result = _by_norm(run, normalized)
        detail = asyncio.run(service.get_verification(
            result["observation_id"], role="service"))
        rules = {
            item["rule_id"]: item["result"]
            for item in detail["decision"]["gate_results"]
        }
        assert [item["rule_id"] for item in detail["decision"][
            "gate_results"]] == FROZEN_RULES
        for rule_id in FROZEN_RULES:
            assert rules[rule_id] == "PASS", (normalized, rule_id)
        assert detail["decision"]["rules_version"] == (
            VERIFICATION_RULES_VERSION)
        assert detail["decision"]["snapshot_version"] == "canonical_v1"


def test_verified_decision_with_high_confidence():
    run, _, _ = _run()
    for normalized in ("glycerol E 422", "sodium benzoate E 211"):
        result = _by_norm(run, normalized)
        assert result["verification_status"] == "verified"
        assert result["verification_confidence"] == "HIGH"


def test_salt_representation_preserved_on_verified_benzoate():
    run, service, _ = _run()
    result = _by_norm(run, "sodium benzoate E 211")
    detail = asyncio.run(service.get_verification(
        result["observation_id"], role="service"))
    v5 = next(
        item for item in detail["decision"]["gate_results"]
        if item["rule_id"] == "V5_entity_type_validation")
    assert "salt" in v5["detail"]


# -- persistence -----------------------------------------------------------------


def test_verified_decision_claim_evidence_persisted():
    run, service, unit_of_work = _run()
    tables = unit_of_work._store.tables
    assert tables["verification_decisions"]
    assert tables["claims"]
    assert tables["claim_sources"]
    for normalized, entity_id in (
        ("glycerol E 422", GLYCEROL_ID),
        ("sodium benzoate E 211", BENZOATE_ID),
    ):
        result = _by_norm(run, normalized)
        detail = asyncio.run(service.get_verification(
            result["observation_id"], role="service"))
        assert detail["decision"]["status"] == "verified"
        identity = next(
            item for item in detail["claims"]
            if item["claim"]["field_name"] == "identity")
        assert identity["claim"]["chemical_entity_id"] == entity_id
        assert identity["claim"]["verification_status"] == "verified"
        assert identity["claim"]["confidence"] == "HIGH"
        assert identity["evidence"], normalized
        assert all(
            row["source_id"] for row in identity["evidence"]
        ), normalized


# -- provenance -------------------------------------------------------------------


def test_end_to_end_provenance_reconstruction():
    run, _, _ = _run()
    fixture = _fixture()
    glycerol = _by_norm(run, "glycerol E 422")
    link = next(
        item for item in run["provenance"]
        if item["observation_id"] == glycerol["observation_id"])
    assert link["label_id"] == "RL-15-01"
    assert link["entity_ref"] == GLYCEROL_REF
    assert link["match_id"]
    assert link["decision_id"]
    assert fixture["source_reference"]["url"] == (
        "https://www.medicines.org.uk/emc/product/4928/smpc/print")
    assert "PL 12965/0050" in fixture["source_reference"][
        "marketing_authorisation"]


# -- negatives ----------------------------------------------------------------------


def test_unrelated_ingredients_remain_unknown():
    run, _, _ = _run()
    for normalized in (
        "aniseed flavour (contains propylene glycol) phl-090803",
        "liquid maltitol E 965",
        "purified water",
    ):
        result = _by_norm(run, normalized)
        assert result["entity_ref"] is None
        assert result["match_status"] == "unresolved"
        assert result["verification_status"] == "unknown"


def test_false_positive_protection():
    run, _, _ = _run()
    for result in run["ingredient_results"]:
        if result["normalized_text"] in (
            "aniseed flavour (contains propylene glycol) phl-090803",
            "liquid maltitol E 965",
            "purified water",
        ):
            assert result["entity_ref"] is None


# -- idempotency ---------------------------------------------------------------------


def test_verified_rerun_is_stable():
    fixture = _fixture()
    service, unit_of_work, _ = _service()
    label = _label(fixture)
    first = asyncio.run(run_label(service, label, fixture)).to_dict()
    counts_first = {
        name: len(rows)
        for name, rows in unit_of_work._store.tables.items()
    }
    second = asyncio.run(run_label(service, label, fixture)).to_dict()
    assert second["mismatches"] == []
    assert second["ingredient_results"] == first["ingredient_results"]
    counts_second = {
        name: len(rows)
        for name, rows in unit_of_work._store.tables.items()
    }
    assert counts_second == counts_first


# -- metrics --------------------------------------------------------------------------


def test_verified_fixture_metrics():
    run, _, _ = _run()
    metrics = summarize([run])
    assert metrics["ingredients_observed"] == 5
    assert metrics["exact_matches"] == 2
    assert metrics["verified"] == 2
    assert metrics["unknown"] == 3
    assert metrics["entity_match_false_positives"] == 0
    assert metrics["mismatches"] == 0

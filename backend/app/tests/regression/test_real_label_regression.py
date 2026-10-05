"""Real-label deterministic vertical slice (Stage 13, offline).

Four real product labels run the full trust pipeline through the
unchanged service layer: raw text -> extraction -> persisted
observations -> correction boundary -> normalization -> registry
resolution -> official evidence -> V1-V7 -> persisted claims,
decisions, and provenance.

Every expectation below was reviewed against the approved sources,
not snapshotted from output: exact registered names resolve, the
glycerin/glycerol synonym gap stays unresolved (the approved names
do not list it), generic terms (alcohol, flavor, parfum) and color
additives never become entities, and bare names verify only to
provisional because a single source cannot corroborate itself.
"""

import asyncio
import csv
import json
from pathlib import Path

import pytest

from app.regression.label_input import (
    LabelInput,
    observation_id_for,
    scan_id_for,
)
from app.regression.metrics import summarize
from app.regression.runner import run_label
from app.repositories.memory import MemoryUnitOfWork
from app.services import errors as service_errors
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
REPO_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
)

CITRIC_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"
BENZOATE_ID = "6223de87-1d0c-49f9-a926-e2b57e0fc8ae"
CITRIC_REF = "CANON-2671a263ff76"
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


def _fixture(label_id: str) -> dict:
    return json.loads((FIXTURES / ("%s.json" % label_id)).read_text())


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
    return service, unit_of_work


def _run(fixture: dict):
    service, unit_of_work = _service()
    run = asyncio.run(run_label(service, _label(fixture), fixture))
    return run.to_dict(), service, unit_of_work


# -- the slice, per label ------------------------------------------------


@pytest.mark.parametrize(
    "label_id",
    ["RL-13-01", "RL-13-02", "RL-13-03", "RL-13-04", "RL-14-01"])
def test_real_label_pipeline_matches_reviewed_expectations(label_id):
    fixture = _fixture(label_id)
    run, _, _ = _run(fixture)
    assert run["mismatches"] == []
    assert len(run["ingredient_results"]) == len(
        fixture["expected_ingredients"])
    counts = fixture["expected_counts"]
    assert len(run["ingredient_results"]) == counts["ingredients"]


def test_coca_cola_ocr_text_survives_verbatim_and_resolves_nothing():
    run, _, _ = _run(_fixture("RL-13-01"))
    assert len(run["ingredient_results"]) == 6
    raws = [item["raw_text"] for item in run["observations"]]
    assert raws[0] == "pledse recycle cans"
    assert "phosphoric acid" in raws[1]
    for result in run["ingredient_results"]:
        assert result["entity_ref"] is None
        assert result["match_status"] == "unresolved"
        assert result["verification_status"] == "unknown"


def test_registered_food_chemistry_resolves_and_stays_provisional():
    run, _, _ = _run(_fixture("RL-13-04"))
    by_norm = {
        result["normalized_text"]: result
        for result in run["ingredient_results"]
    }
    citric = by_norm["citric acid"]
    assert citric["entity_ref"] == CITRIC_REF
    assert citric["match_status"] == "exact_match"
    # Bare name, single source: provisional, never forced verified.
    assert citric["verification_status"] == "provisional"
    benzoate = by_norm["sodium benzoate"]
    assert benzoate["entity_ref"] == BENZOATE_REF
    assert benzoate["verification_status"] == "provisional"


def test_glycerin_synonym_gap_is_not_promoted():
    # Glycerin is genuinely glycerol's common name, but the approved
    # registry names do not list it: the runner records a candidate
    # and the verdict stays unknown. Promoting it would be fixture
    # truth overriding the canonical registry.
    for label_id in ("RL-13-03", "RL-13-04"):
        run, _, _ = _run(_fixture(label_id))
        glycerin = next(
            result for result in run["ingredient_results"]
            if result["normalized_text"] == "glycerin")
        assert glycerin["match_status"] == "candidate"
        assert glycerin["entity_ref"] is None
        assert glycerin["verification_status"] == "unknown"


def test_generic_terms_and_additives_never_become_entities():
    run, _, _ = _run(_fixture("RL-13-02"))
    by_norm = {
        result["normalized_text"]: result
        for result in run["ingredient_results"]
    }
    for term in ("alcohol", "flavor", "green 3", "water", "sorbitol",
                 "benzoic acid", "sodium saccharin", "poloxamer 407"):
        assert by_norm[term]["entity_ref"] is None, term
        assert by_norm[term]["match_status"] == "unresolved", term
    run, _, _ = _run(_fixture("RL-13-03"))
    by_norm = {
        result["normalized_text"]: result
        for result in run["ingredient_results"]
    }
    # Near-miss guard: shares a word with sodium benzoate, different
    # substance, must not resolve.
    assert by_norm["benzyl benzoate"]["entity_ref"] is None
    assert by_norm["parfum"]["entity_ref"] is None


# -- correction boundary ---------------------------------------------------


def test_documented_correction_preserves_raw_and_re_normalizes():
    fixture = _fixture("RL-13-02")
    run, service, _ = _run(fixture)
    correction = run["correction"]
    assert correction is not None
    # Raw observed text is immutable and stored verbatim.
    assert correction["raw_preserved"] == "Saccharin Sodium"
    stored = asyncio.run(service.get(
        correction["observation_id"], role="service"))
    assert stored["raw_text"] == "Saccharin Sodium"
    assert stored["display_text"] == "Sodium Saccharin"
    assert stored["user_corrected"] is True
    assert stored["normalized_text"] == "sodium saccharin"
    # The correction changes text only: no identity is established.
    assert correction["match_status"] == "unresolved"
    assert correction["verification_status"] == "unknown"


def test_correction_refusals():
    service, _ = _service()
    created = asyncio.run(service.create(
        "Saccharin Sodium", scan_id="scan-corr", role="service"))
    observation_id = created["items"][0]["observation_id"]
    with pytest.raises(service_errors.ServiceError):
        asyncio.run(service.correct(
            observation_id, corrected_text="  ",
            reason="blank", role="service"))
    with pytest.raises(service_errors.ServiceError):
        asyncio.run(service.correct(
            observation_id, corrected_text="Sodium Saccharin",
            reason="  ", role="service"))
    with pytest.raises(service_errors.NotFoundError):
        asyncio.run(service.correct(
            "00000000-0000-4000-8000-000000000000",
            corrected_text="Sodium Saccharin", reason="nope",
            role="service"))
    asyncio.run(service.correct(
        observation_id, corrected_text="Sodium Saccharin",
        reason="panel reading", role="service"))
    # No correction chain: the second revision is refused.
    with pytest.raises(service_errors.ServiceError):
        asyncio.run(service.correct(
            observation_id, corrected_text="Sodium Saccharin!",
            reason="again", role="service"))


def test_analysis_uses_corrected_text():
    service, _ = _service()
    created = asyncio.run(service.create(
        "Saccharin Sodium", scan_id="scan-corr", role="service"))
    observation_id = created["items"][0]["observation_id"]
    asyncio.run(service.correct(
        observation_id, corrected_text="Sodium Saccharin",
        reason="panel reading", role="service"))
    analyzed = asyncio.run(
        service.analyze(observation_id, role="service"))
    assert analyzed["resolution"]["normalized_text"] == "sodium saccharin"


# -- persistence and provenance ----------------------------------------------


def test_provisional_match_persists_claims_evidence_decision():
    run, service, unit_of_work = _run(_fixture("RL-13-04"))
    citric = next(
        result for result in run["ingredient_results"]
        if result["normalized_text"] == "citric acid")
    detail = asyncio.run(service.get_verification(
        citric["observation_id"], role="service"))
    assert detail["decision"]["status"] == "provisional"
    assert detail["decision"]["rules_version"] == (
        VERIFICATION_RULES_VERSION)
    assert [item["rule_id"] for item in detail["decision"][
        "gate_results"]] == FROZEN_RULES
    identity = next(
        item for item in detail["claims"]
        if item["claim"]["field_name"] == "identity")
    assert identity["claim"]["chemical_entity_id"] == CITRIC_ID
    assert identity["evidence"], "provisional claim without evidence"
    tables = unit_of_work._store.tables
    assert tables["ingredient_observations"]
    assert tables["ingredient_normalizations"]
    assert tables["ingredient_candidates"]
    assert tables["entity_matches"]
    assert tables["verification_decisions"]
    assert tables["claims"]
    assert tables["claim_sources"]


def test_unknown_claim_carries_no_entity_or_chemistry():
    run, service, _ = _run(_fixture("RL-13-02"))
    flavor = next(
        result for result in run["ingredient_results"]
        if result["normalized_text"] == "flavor")
    detail = asyncio.run(service.get_verification(
        flavor["observation_id"], role="service"))
    assert detail["decision"]["status"] == "unknown"
    payload = json.dumps(detail, default=str).lower()
    for invented in ("formula", "cas", "smiles", "inchi",
                     "molecular_weight"):
        assert invented not in payload
    for item in detail["claims"]:
        assert item["claim"]["chemical_entity_id"] is None


def test_full_provenance_chain_links_real_ids():
    run, _, _ = _run(_fixture("RL-13-04"))
    assert run["provenance"]
    for link in run["provenance"]:
        assert link["observation_id"]
        assert link["match_id"]
        assert link["decision_id"]
    citric = next(
        link for link in run["provenance"]
        if link["entity_ref"] == CITRIC_REF)
    assert citric["label_id"] == "RL-13-04"


def test_label_input_boundary():
    fixture = _fixture("RL-13-01")
    label = _label(fixture)
    assert label.scan_id == scan_id_for("RL-13-01")
    assert label.observation_id(3) == observation_id_for("RL-13-01", 3)
    assert label.observation_id(3) != label.observation_id(4)
    with pytest.raises(ValueError):
        LabelInput.from_dict({
            "label_id": "X", "raw_text": "water",
            "input_method": "telepathy",
            "source_reference": {
                "source_id": "S", "retrieved_at": "2026-10-05"}})
    with pytest.raises(ValueError):
        LabelInput.from_dict({
            "label_id": "X", "raw_text": "water",
            "input_method": "manual",
            "source_reference": {"source_id": "S"}})
    # Untrusted keys never enter the pipeline.
    with pytest.raises(ValueError):
        LabelInput.from_dict({
            "label_id": "X", "raw_text": "water",
            "input_method": "manual",
            "source_reference": {
                "source_id": "S", "retrieved_at": "2026-10-05"},
            "subject": "admin", "role": "reviewer"})


# -- metrics -----------------------------------------------------------------


def test_stage13_metrics_are_exact():
    runs = []
    for label_id in ("RL-13-01", "RL-13-02", "RL-13-03", "RL-13-04",
                     "RL-14-01"):
        run, _, _ = _run(_fixture(label_id))
        runs.append(run)
    metrics = summarize(runs)
    assert metrics["labels_processed"] == 5
    assert metrics["ingredients_observed"] == 57
    assert metrics["ingredients_normalized"] == 57
    assert metrics["exact_matches"] == 5
    assert metrics["alias_matches"] == 0
    assert metrics["candidate_matches"] == 2
    assert metrics["ambiguous"] == 0
    assert metrics["unresolved"] == 50
    assert metrics["verified"] == 0
    assert metrics["provisional"] == 4
    assert metrics["unverified"] == 1
    assert metrics["conflicted"] == 0
    assert metrics["unknown"] == 52
    assert metrics["entity_match_false_positives"] == 0
    assert metrics["unknown_count"] == 52
    assert metrics["mismatches"] == 0
    # 4 of 7 resolved ingredients reached a terminal decision; the
    # identifier-resolved Frooti ingredient is honestly unverified.
    assert metrics["verification_coverage"] == round(4 / 7, 4)


# -- idempotency -----------------------------------------------------------------


def test_repeated_regression_creates_no_duplicates():
    fixture = _fixture("RL-13-04")
    service, unit_of_work = _service()
    label = _label(fixture)
    first = asyncio.run(run_label(service, label, fixture)).to_dict()
    counts_first = {
        name: len(rows)
        for name, rows in unit_of_work._store.tables.items()
    }
    second = asyncio.run(run_label(service, label, fixture)).to_dict()
    counts_second = {
        name: len(rows)
        for name, rows in unit_of_work._store.tables.items()
    }
    assert second["mismatches"] == []
    assert counts_second == counts_first
    assert first["ingredient_results"] == second["ingredient_results"]


# -- governance: no false gold ---------------------------------------------------------


def test_regression_datasets_still_hold_no_verified_truth():
    with open(REPO_ROOT / "LABEL_REGRESSION_DATASET.csv") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 30
    assert {row["review_status"] for row in rows} == {"needs_real_label"}
    assert all(
        not row["expected_ingredient_text"].strip() for row in rows)
    with open(REPO_ROOT / "INGREDIENT_GOLDEN_DATA.csv") as handle:
        golden = list(csv.DictReader(handle))
    assert len(golden) == 100
    assert {row["review_status"] for row in golden} == {
        "needs_verification"}


def test_fixtures_are_marked_draft_not_verified():
    for label_id in ("RL-13-01", "RL-13-02", "RL-13-03", "RL-13-04",
                     "RL-14-01"):
        fixture = _fixture(label_id)
        assert fixture["review_status"] == "draft"
        assert fixture["source_reference"]["retrieved_at"]
        assert fixture["source_reference"]["url"]
        review = fixture["independent_review"]
        assert review["reviewed_at"] == "2026-10-05"
        assert review["chemistry_inferred"] is False


def test_identifier_resolves_without_verification():
    # The Frooti function-name carries a registered identifier, so
    # resolution is exact -- but the name agrees with no record, and
    # the frozen V3/V4 dual-agreement rules honestly refuse to
    # verify. Identifier resolution must never imply verification.
    run, service, _ = _run(_fixture("RL-14-01"))
    acidity = next(
        result for result in run["ingredient_results"]
        if result["normalized_text"] == "acidity regulator INS 330")
    assert acidity["match_status"] == "exact_match"
    assert acidity["entity_ref"] == CITRIC_REF
    assert acidity["verification_status"] == "unverified"
    detail = asyncio.run(service.get_verification(
        acidity["observation_id"], role="service"))
    assert detail["decision"]["status"] == "unverified"
    rules = {
        item["rule_id"]: item["result"]
        for item in detail["decision"]["gate_results"]
    }
    assert rules["V1_admissible_candidate"] == "PASS"
    assert rules["V2_authoritative_source"] == "PASS"
    assert rules["V3_identity_agreement"] == "FAIL"
    assert rules["V4_identifier_validation"] == "FAIL"


def test_nested_ins_codes_stay_in_the_parse_tree():
    run, service, _ = _run(_fixture("RL-14-01"))
    preservatives = next(
        result for result in run["ingredient_results"]
        if result["normalized_text"]
        == "permitted class ii preservatives")
    assert preservatives["match_status"] == "unresolved"
    assert preservatives["entity_ref"] is None
    detail = asyncio.run(service.get(
        preservatives["observation_id"], role="service"))
    tree_names = [
        node["name"] for node in detail["tree"][0]["children"]
    ] if detail["tree"][0].get("children") else []
    assert tree_names == ["INS 211", "INS 224", "INS 202"]


def test_retailer_typo_is_preserved_literally():
    run, _, _ = _run(_fixture("RL-14-01"))
    last = run["ingredient_results"][-1]
    assert last["raw_text"].endswith("(Mango).")
    assert last["match_status"] == "unresolved"
    assert last["verification_status"] == "unknown"

"""OCR regression over real-label fixtures (Stage 16).

Synthetic OCR corruption is derived from the existing real-label
fixtures; fixture truth is never altered. Each case proves the two
halves of the OCR safety contract: corrupted text resolves to
nothing (or warns) without inventing chemistry, and the documented
human correction restores exactly the pre-corruption deterministic
behavior.

Labels: RL-14-01 (food/beverage), RL-13-03 (cosmetic),
RL-13-02 (personal care), RL-15-01 (pharmaceutical).
"""

import asyncio
import json
from pathlib import Path

from app.repositories.memory import MemoryUnitOfWork
from app.services.ocr_provider import OCRResult
from app.services.ocr_service import OCRService
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
    return OCRService(
        unit_of_work, registry=registry, adapters=[adapter])


def _run(coro):
    return asyncio.run(coro)


def _fixture(label_id: str) -> dict:
    return json.loads((FIXTURES / ("%s.json" % label_id)).read_text())


def _corrupt_and_restore(label_id, corrupt, corrected):
    service = _service()
    fixture = _fixture(label_id)
    run = _run(service.register_result(
        OCRResult(
            document_id=label_id, provider="fake-test",
            raw_text=corrupt),
        role="service"))
    before = _run(service.analyze_run(run["id"], role="service"))
    _run(service.correct_run(
        run["id"], corrected_text=corrected,
        reason="ocr corruption repaired against the fixture text",
        actor="human:regression", role="service"))
    after = _run(service.analyze_run(run["id"], role="service"))
    return service, fixture, before, after


def _clean_outcome(label_id, raw_text):
    service = _service()
    run = _run(service.register_result(
        OCRResult(
            document_id="%s-clean" % label_id, provider="fake-test",
            raw_text=raw_text),
        role="service"))
    return _run(service.analyze_run(run["id"], role="service"))


# -- food: Frooti identifier corruption ----------------------------------------------


def test_food_corrupted_code_blocks_verification():
    fixture = _fixture("RL-14-01")
    corrupt = fixture["raw_text"].replace("INS 330", "INS 33O")
    service, _, before, after = _corrupt_and_restore(
        "RL-14-01", corrupt, fixture["raw_text"])
    acidity_before = next(
        item for item in before["items"]
        if "acidity" in item["raw_text"].lower())
    assert acidity_before["decision"]["status"] == "unknown"
    assert acidity_before["resolution"]["entity"] is None
    acidity_after = next(
        item for item in after["items"]
        if "acidity" in item["raw_text"].lower())
    # Restored behavior equals the fixture expectation: exact
    # identifier resolution, honestly unverified (function-name).
    assert acidity_after["resolution"]["match_status"] == "exact_match"
    assert acidity_after["decision"]["status"] == "unverified"
    assert after["corrected"] is True


# -- cosmetic: Nivea name corruption ------------------------------------------------


def test_cosmetic_corrupted_name_resolves_nothing():
    segment = "Citric Acid, Magnesium Stearate"
    corrupt = "Citric Ac1d, Magnesium Stearate"
    _, _, before, after = _corrupt_and_restore(
        "RL-13-03", corrupt, segment)
    assert before["items"][0]["decision"]["status"] == "unknown"
    assert before["items"][0]["resolution"]["entity"] is None
    citric = after["items"][0]
    assert citric["resolution"]["match_status"] == "exact_match"
    assert citric["decision"]["status"] == "provisional"


# -- personal care: Listerine substitution + breaks --------------------------------


def test_personal_care_substitution_and_breaks():
    fixture = _fixture("RL-13-02")
    corrupt = ("Water, Alcohol (21.6%), Sorbitol, Poloxamer 407,\n"
               "Benzoic Acid, Sodium Saccharin, Sodium Benzoatc,\n"
               "Flavor, Green 3")
    clean = ("Water, Alcohol (21.6%), Sorbitol, Poloxamer 407,\n"
             "Benzoic Acid, Sodium Saccharin, Sodium Benzoate,\n"
             "Flavor, Green 3")
    _, _, before, after = _corrupt_and_restore(
        "RL-13-02", corrupt, clean)
    assert len(before["items"]) == 9
    assert len(after["items"]) == 9
    corrupted = next(
        item for item in before["items"]
        if "Benzoatc" in item["raw_text"])
    # Corrupted name and no identifier: nothing to resolve.
    assert corrupted["decision"]["status"] == "unknown"
    assert corrupted["resolution"]["entity"] is None
    restored = next(
        item for item in after["items"]
        if item["raw_text"] == "Sodium Benzoate")
    assert restored["decision"]["status"] == "provisional"
    # Multiline layout changes nothing: the same nine segments in
    # the same order as the clean single-line run.
    clean = _clean_outcome("RL-13-02", fixture["raw_text"])
    assert [item["raw_text"] for item in after["items"]] == [
        item["raw_text"] for item in clean["items"]
    ]


# -- pharmaceutical: Simple Linctus verified path --------------------------------------


def test_pharma_corruption_breaks_verified_then_restores():
    fixture = _fixture("RL-15-01")
    corrupt = fixture["raw_text"].replace(
        "Sodium Benzoate (E211)", "Sodium Benzoatc (E211)")
    service, _, before, after = _corrupt_and_restore(
        "RL-15-01", corrupt, fixture["raw_text"])
    assert before["items"][3]["decision"]["status"] == "unverified"
    glycerol = next(
        item for item in after["items"]
        if item["raw_text"] == "Glycerol (E422)")
    benzoate = next(
        item for item in after["items"]
        if item["raw_text"] == "Sodium Benzoate (E211)")
    assert glycerol["decision"]["status"] == "verified"
    assert benzoate["decision"]["status"] == "verified"
    # The three unrelated nodes stayed unknown throughout.
    assert sum(
        item["decision"]["status"] == "unknown"
        for item in after["items"]
    ) == 3


def test_pharma_duplicated_lines_do_not_duplicate_entities():
    service = _service()
    fixture = _fixture("RL-15-01")
    doubled = fixture["raw_text"] + " " + fixture["raw_text"]
    run = _run(service.register_result(
        OCRResult(
            document_id="RL-15-01-dup", provider="fake-test",
            raw_text=doubled),
        role="service"))
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    verified = [
        item for item in analyzed["items"]
        if item["decision"]["status"] == "verified"
    ]
    # Each copy verifies independently; both copies name the same
    # two canonical entities and no third entity appears.
    assert len(verified) == 4
    refs = {
        item["resolution"]["entity"]["candidate_ref"]
        for item in verified
    }
    assert refs == {"CANON-763389d03732", "CANON-6223de871d0c"}

"""Per-user ownership unit tests (Stage 17).

User A owns runs, corrections, and derived observations; user B is
answered exactly as if the data did not exist (404, never 403 with
a distinguishing body). Legacy rows without an owner keep their
previous readability. All against memory repositories.
"""

import asyncio

import pytest

from app.repositories.memory import MemoryUnitOfWork
from app.services import errors as service_errors
from app.services.observation_service import ObservationService
from app.services.ocr_provider import OCRResult
from app.services.ocr_service import OCRService
from app.services.registration import (
    alias_rows_for,
    build_registry,
    entity_row_for,
)
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.gate import VERIFICATION_RULES_VERSION
from pathlib import Path

SNAPSHOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "snapshots" / "canonical_v1.json"
)

A = "user-a"
B = "user-b"


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
    return (
        OCRService(unit_of_work, registry=registry,
                   adapters=[adapter]),
        ObservationService(
            unit_of_work, registry=registry, adapters=[adapter]),
        unit_of_work,
    )


def _run(coro):
    return asyncio.run(coro)


def _owned_run(service, text="Sodium Benzoate (E211)", owner=A):
    return _run(service.register_result(
        OCRResult(
            document_id="doc-owned", provider="fake-test",
            raw_text=text),
        owner=owner, role="service"))


# -- run ownership --------------------------------------------------------------


def test_owner_creates_reads_corrects_analyzes():
    service, _, _ = _service()
    run = _owned_run(service)
    assert run["owner_subject"] == A
    described = _run(service.describe(
        run["id"], owner=A, role="service"))
    assert described["run"]["id"] == run["id"]
    correction = _run(service.correct_run(
        run["id"], corrected_text="Sodium Benzoate!",
        reason="owned", actor="human:a", owner=A,
        role="service"))
    assert correction["owner_subject"] == A
    analyzed = _run(service.analyze_run(
        run["id"], owner=A, role="service"))
    assert len(analyzed["items"]) == 1


def test_stranger_read_correct_analyze_are_not_found():
    service, _, _ = _service()
    run = _owned_run(service)
    with pytest.raises(service_errors.NotFoundError):
        _run(service.describe(run["id"], owner=B, role="service"))
    with pytest.raises(service_errors.NotFoundError):
        _run(service.correct_run(
            run["id"], corrected_text="x", reason="r",
            actor="human:b", owner=B, role="service"))
    with pytest.raises(service_errors.NotFoundError):
        _run(service.analyze_run(run["id"], owner=B, role="service"))
    with pytest.raises(service_errors.NotFoundError):
        _run(service.observe(run["id"], owner=B, role="service"))


def test_derived_observations_remain_owned():
    service, observations, _ = _service()
    run = _owned_run(service, text="citric acid, water")
    analyzed = _run(service.analyze_run(
        run["id"], owner=A, role="service"))
    assert len(analyzed["items"]) == 2
    for item in analyzed["items"]:
        with pytest.raises(service_errors.NotFoundError):
            _run(observations.get(
                item["observation_id"], owner=B, role="service"))
        with pytest.raises(service_errors.NotFoundError):
            _run(observations.analyze(
                item["observation_id"], owner=B, role="service"))
        owned = _run(observations.get(
            item["observation_id"], owner=A, role="service"))
        assert owned["observation_id"] == item["observation_id"]


def test_rerun_is_owned_by_its_creator():
    service, _, _ = _service()
    first = _owned_run(service, owner=A)
    second = _run(service.register_result(
        OCRResult(
            document_id="doc-owned", provider="fake-test",
            raw_text="water"),
        owner=B, role="service"))
    assert first["id"] != second["id"]
    assert second["owner_subject"] == B
    with pytest.raises(service_errors.NotFoundError):
        _run(service.describe(first["id"], owner=B, role="service"))


def test_correction_row_carries_owner_and_actor():
    service, _, _ = _service()
    run = _owned_run(service)
    _run(service.correct_run(
        run["id"], corrected_text="Sodium Benzoate (E211).",
        reason="owned", actor="human:user-a", owner=A,
        role="service"))
    described = _run(service.describe(
        run["id"], owner=A, role="service"))
    assert described["correction"]["owner_subject"] == A
    assert described["correction"]["actor"] == "human:user-a"


# -- legacy rows ------------------------------------------------------------------


def test_legacy_unowned_rows_stay_readable():
    service, observations, _ = _service()
    run = _run(service.register_result(
        OCRResult(
            document_id="doc-legacy", provider="fake-test",
            raw_text="water"),
        role="service"))
    assert run["owner_subject"] is None
    analyzed = _run(service.analyze_run(
        run["id"], role="service"))
    observation_id = analyzed["items"][0]["observation_id"]
    # No owner anywhere: legacy readability preserved for any
    # caller, including a subject that owns other data.
    for owner in (None, A, B):
        got = _run(observations.get(
            observation_id, owner=owner, role="service"))
        assert got["observation_id"] == observation_id


# -- repository roles -----------------------------


def test_repositories_reject_wrong_roles():
    _, _, unit_of_work = _service()
    with pytest.raises(Exception):
        _run(unit_of_work.ocr.save_run(
            {"id": "x"}, role="authenticated"))
    with pytest.raises(Exception):
        _run(unit_of_work.ocr.save_correction(
            {"id": "y", "ocr_run_id": "x"}, role="authenticated"))
    with pytest.raises(Exception):
        _run(unit_of_work.matches.save_observation(
            {"id": "z"}, role="authenticated"))

"""Analysis ownership lineage unit tests (Stage 18).

Ownership flows observation -> normalization -> candidates/match
-> decision -> review. Every derived row carries the data owner's
subject; a stranger meets NotFoundError on every read path, while
legacy rows without an owner keep prior readability. Memory
repositories only.
"""

import asyncio

import pytest

from app.repositories.memory import MemoryUnitOfWork
from app.services import errors as service_errors
from app.services.observation_service import ObservationService
from app.services.registration import (
    alias_rows_for,
    build_registry,
    entity_row_for,
)
from app.services.review_service import ReviewService
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
    reviews = ReviewService(unit_of_work, adapters=[adapter])
    observations = ObservationService(
        unit_of_work, registry=registry, adapters=[adapter],
        review_service=reviews)
    return observations, reviews, unit_of_work


def _run(coro):
    return asyncio.run(coro)


def _analyze_as(owner, text="citric acid"):
    observations, reviews, unit_of_work = _service()
    created = _run(observations.create(
        text, scan_id="scan-%s" % owner, owner=owner,
        role="service"))
    observation_id = created["items"][0]["observation_id"]
    analyzed = _run(observations.analyze(
        observation_id, owner=owner, role="service"))
    return observations, reviews, unit_of_work, observation_id, analyzed


# -- lineage -------------------------------------------------------------------------


def test_derived_rows_carry_the_data_owner():
    _, _, unit_of_work, observation_id, analyzed = _analyze_as(A)
    tables = unit_of_work._store.tables
    match_id = analyzed["match_id"]
    normalization = tables["ingredient_normalizations"][
        tables["entity_matches"][match_id]["normalization_id"]]
    assert normalization["owner_subject"] == A
    for row in tables["ingredient_candidates"].values():
        if row["normalization_id"] == normalization["id"]:
            assert row["owner_subject"] == A
    assert tables["entity_matches"][match_id]["owner_subject"] == A
    decisions = [
        row for row in tables["verification_decisions"].values()
        if row.get("entity_match_id") == match_id
    ]
    assert decisions
    assert all(
        row["owner_subject"] == A for row in decisions)
    assert any(
        row.get("owner_subject") == A
        for row in tables["reviews"].values()
    )
    assert all(
        row["owner_subject"] == A
        for row in tables["reviews"].values()
        if row.get("owner_subject") is not None
    )


def test_stranger_cannot_read_analysis_views():
    service, _, _, observation_id, _ = _analyze_as(A)
    with pytest.raises(service_errors.NotFoundError):
        _run(service.get_verification(
            observation_id, owner=B, role="service"))
    with pytest.raises(service_errors.NotFoundError):
        _run(service.get_candidates(
            observation_id, owner=B, role="service"))
    with pytest.raises(service_errors.NotFoundError):
        _run(service.analyze(
            observation_id, owner=B, role="service"))
    owned = _run(service.get_verification(
        observation_id, owner=A, role="service"))
    assert owned["decision"]["status"] == "provisional"


# -- review visibility -----------------------------------------------------------------


def test_owner_sees_own_review_stranger_does_not():
    _, reviews, _, observation_id, analyzed = _analyze_as(A)
    review_id = analyzed["review_id"]
    assert review_id is not None
    detail = _run(reviews.get(
        review_id, owner=A, reviewer=False, role="service"))
    assert detail["review"]["id"] == review_id
    with pytest.raises(service_errors.NotFoundError):
        _run(reviews.get(
            review_id, owner=B, reviewer=False, role="service"))
    pending = _run(reviews.list_pending(
        owner=B, reviewer=False, role="service"))
    assert all(
        item["id"] != review_id for item in pending["items"])
    pending = _run(reviews.list_pending(
        owner=A, reviewer=False, role="service"))
    assert any(
        item["id"] == review_id for item in pending["items"])


def test_reviewer_sees_all_reviews():
    _, reviews, _, _, analyzed = _analyze_as(A)
    review_id = analyzed["review_id"]
    detail = _run(reviews.get(
        review_id, owner="some-reviewer", reviewer=True,
        role="service"))
    assert detail["review"]["id"] == review_id
    pending = _run(reviews.list_pending(
        owner="some-reviewer", reviewer=True, role="service"))
    assert any(
        item["id"] == review_id for item in pending["items"])


def test_legacy_review_rows_stay_visible():
    _, reviews, unit_of_work = _service()
    unit_of_work._store.insert("reviews", {
        "id": "REV-legacy", "candidate_key": "k",
        "raw_text": "r", "normalized_text": "n",
        "status": "queued", "priority": 1,
    })
    for owner in (None, A, B):
        pending = _run(reviews.list_pending(
            owner=owner, reviewer=False, role="service"))
        assert any(
            item["id"] == "REV-legacy" for item in pending["items"])

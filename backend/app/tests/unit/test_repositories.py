"""Repository contract tests (run against in-memory implementations).

Each test documents an invariant every implementation must honor:
idempotent retries, conditional-claim races, append-only events,
atomic batches, role enforcement, and full-chain provenance.
"""

import pytest

from app.repositories.memory import (
    MemoryClaimRepository,
    MemoryEvidenceRepository,
    MemoryMatchRepository,
    MemoryReviewRepository,
    MemoryUnitOfWork,
    MemoryVerificationRepository,
    ReviewClaimConflict,
)
from app.repositories.serialize import (
    candidate_rows,
    claim_id_for,
    claim_source_row,
    claim_to_row,
    decision_to_row,
    match_row,
    normalization_row,
    observation_row,
    validate_no_secrets,
    verification_event_row,
    verification_id_for,
)
from app.services.entity_resolver import Candidate, Resolution
from app.services.verification.models import (
    FieldEvidence,
    IdentityClaim,
    SourceMetadata,
    VerificationDecision,
)

SCAN_ID = "11111111-1111-1111-1111-111111111111"
ENTITY_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"


def _source_meta():
    return SourceMetadata(
        source_id="PUBCHEM", record_locator="CID:311",
        source_version="live", retrieved_at="2026-10-05",
        license_note="test", source_class="A",
    )


def _decision():
    return VerificationDecision(
        status="verified", identity_confidence="HIGH", gate_results=(),
        claims=(), evidence=(), source_refs=(), reason="gate passed",
        warnings=(), rules_version="1.0.0",
        snapshot_version="canonical_v1", entity_id=ENTITY_ID,
    )


async def test_verification_decision_idempotent_retry():
    repo = MemoryVerificationRepository()
    row = decision_to_row(_decision(), candidate_key="citric acid|")
    first = await repo.save_decision(row)
    second = await repo.save_decision(dict(row))
    assert first == second
    assert (await repo.get_decision(first))["status"] == "verified"
    assert await repo.list_decisions(status="verified") != []
    assert await repo.list_decisions(status="unknown") == []


async def test_verification_id_deterministic():
    first = verification_id_for("k|", "verified", "1.0.0", "v1", "h")
    assert first == verification_id_for("k|", "verified", "1.0.0", "v1", "h")
    assert first != verification_id_for("k|", "provisional", "1.0.0", "v1", "h")
    assert verification_id_for(
        "k|", "verified", "1.0.0", "v1", "h", "m1") == verification_id_for(
        "k|", "verified", "1.0.0", "v1", "h", "m1")
    assert verification_id_for(
        "k|", "verified", "1.0.0", "v1", "h", "m1") != verification_id_for(
        "k|", "verified", "1.0.0", "v1", "h", "m2")


async def test_claim_statuses_stay_independent():
    repo = MemoryClaimRepository()
    identity = IdentityClaim(
        entity_id=ENTITY_ID, field="identity", value="citric acid",
        status="verified", confidence="HIGH", evidence=(),
    )
    formula = IdentityClaim(
        entity_id=ENTITY_ID, field="formula", value="C6H8O7",
        status="verified", confidence="HIGH", evidence=(),
    )
    role = IdentityClaim(
        entity_id=ENTITY_ID, field="role", value="acidity regulator",
        status="unverified", confidence="UNKNOWN", evidence=(),
    )
    for claim in (identity, formula, role):
        await repo.save_claim(claim_to_row(claim))
    rows = await repo.list_by_entity(ENTITY_ID)
    by_field = {r["field_name"]: r["verification_status"] for r in rows}
    assert by_field == {
        "identity": "verified",
        "formula": "verified",
        "role": "unverified",
    }
    assert claim_id_for(ENTITY_ID, "identity", "citric acid") == (
        claim_id_for(ENTITY_ID, "identity", "citric acid"))


async def test_claim_update_appends_event_atomically():
    claims = MemoryClaimRepository()
    claim = IdentityClaim(
        entity_id=ENTITY_ID, field="identity", value="citric acid",
        status="provisional", confidence="LOW", evidence=(),
    )
    claim_id = await claims.save_claim(claim_to_row(claim))
    event = verification_event_row(
        claim_id=claim_id, previous_status="provisional",
        new_status="verified", reviewer_type="human",
        reason="second source agreed",
    )
    updated = await claims.update_claim_status(
        claim_id, "verified", "HIGH", event=event)
    assert updated["verification_status"] == "verified"
    assert updated["confidence"] == "HIGH"
    assert len(claims._store.table("verification_events")) == 1


async def test_evidence_links_idempotent_and_listed():
    repo = MemoryEvidenceRepository()
    source_id = await repo.ensure_source({
        "id": "a1111111-1111-1111-1111-111111111111",
        "name": "PUBCHEM",
    })
    assert await repo.ensure_source({"name": "PUBCHEM"}) == source_id
    item = FieldEvidence(
        field="formula", value="C6H8O7", unit=None,
        source=_source_meta(),
    )
    await repo.link_source(claim_source_row("c1", source_id, item))
    await repo.link_source(claim_source_row("c1", source_id, item))
    links = await repo.list_for_claim("c1")
    assert len(links) == 1
    assert links[0]["support_type"] == "direct"


async def test_match_chain_provenance_preserved():
    repo = MemoryMatchRepository()
    obs_id = await repo.save_observation(observation_row(
        observation_id="22222222-2222-2222-2222-222222222222",
        scan_id=SCAN_ID, sequence_number=0,
        raw_text="Sodiurn Benzoate"))
    norm_id = await repo.save_normalization(normalization_row(
        normalization_id="33333333-3333-3333-3333-333333333333",
        observation_id=obs_id, normalized_text="sodlum benzoate",
        status="complete"))
    match_id = "44444444-4444-4444-4444-444444444444"
    resolution = Resolution(
        raw_text="Sodlum Benzoate",
        normalized_text="sodlum benzoate",
        status="unresolved",
        candidates=[
            Candidate(
                candidate_ref="T10-1", display_name="sodlum benzoate",
                candidate_type="unknown",
                source="synthetic_test_fixture",
                match_method="exact_alias", match_score=0.5,
                reason="synthetic",
            )
        ],
    )
    match_id = await repo.save_match(match_row(
        resolution, match_id=match_id, normalization_id=norm_id))
    assert match_id
    saved = await repo.save_candidates(
        candidate_rows(resolution, normalization_id=norm_id))
    assert len(saved) == 1
    chain = await repo.get_chain(norm_id)
    assert chain["observation"]["raw_text"] == "Sodiurn Benzoate"
    assert chain["normalization"]["normalized_text"] == "sodlum benzoate"
    assert chain["match"]["match_status"] == "unresolved"
    assert len(chain["candidates"]) == 1
    assert chain["candidates"][0]["match_reasons"][
        "candidate_ref"] == "T10-1"


async def test_review_submit_transition_and_conflict():
    repo = MemoryReviewRepository()
    item = {
        "id": "REV-0001", "candidate_key": "k", "raw_text": "r",
        "normalized_text": "n", "identifier": None, "resolution": {},
        "verification_status": "conflicted", "evidence_context": {},
        "evidence_hash": "h", "priority": 0, "status": "queued",
        "reviewer": None,
    }
    assert await repo.submit_review(dict(item)) == "REV-0001"
    assert await repo.submit_review(dict(item)) == "REV-0001"
    event = {
        "id": "REV-0001:001", "review_id": "REV-0001",
        "event_type": "ReviewClaimed", "actor": "human:ana",
        "reason": "taking it", "previous_state": "queued",
        "new_state": "in_review", "evidence_context_hash": "h",
        "rules_version": "1.0.0", "snapshot_version": "v1",
    }
    moved = await repo.transition_review(
        "REV-0001", event, "in_review", expect_status="queued")
    assert moved["status"] == "in_review"
    assert moved["reviewer"] == "human:ana"
    with pytest.raises(ReviewClaimConflict):
        await repo.transition_review(
            "REV-0001", dict(event, id="REV-0001:099"),
            "in_review", expect_status="queued")
    assert await repo.append_event(dict(event)) is False
    pending = await repo.list_pending()
    assert [r["id"] for r in pending] == ["REV-0001"]
    assert len(await repo.list_events("REV-0001")) == 2


async def test_transaction_rolls_back_partial_batch():
    uow = MemoryUnitOfWork()
    try:
        with uow.transaction():
            await uow.verification.save_decision(
                decision_to_row(_decision(), candidate_key="k|"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert await uow.verification.list_decisions() == []


async def test_role_enforcement():
    repo = MemoryVerificationRepository()
    with pytest.raises(PermissionError):
        await repo.save_decision(
            decision_to_row(_decision(), candidate_key="k|"),
            role="authenticated")
    with pytest.raises(PermissionError):
        await repo.list_decisions(role="anon")
    with pytest.raises(PermissionError):
        await repo.save_decision(
            decision_to_row(_decision(), candidate_key="k|"), role="anon")


async def test_no_secret_keys_in_serialized_rows():
    with pytest.raises(ValueError):
        validate_no_secrets({"api_key": "x"})
    with pytest.raises(ValueError):
        validate_no_secrets({"nested": {"password": "x"}})
    with pytest.raises(ValueError):
        validate_no_secrets({"token": "sk-abc"})
    validate_no_secrets(decision_to_row(_decision(), candidate_key="k|"))
    validate_no_secrets({"note": "nothing sensitive here"})


async def test_hostile_strings_survive_as_data():
    payload = "'; DROP TABLE claims; --"
    row = observation_row(
        observation_id="55555555-5555-5555-5555-555555555555",
        scan_id=SCAN_ID, sequence_number=0, raw_text=payload)
    assert row["raw_text"] == payload
    validate_no_secrets(row)

    repo = MemoryMatchRepository()
    await repo.save_observation(row)
    with pytest.raises(KeyError):
        await repo.get_chain("missing-id")

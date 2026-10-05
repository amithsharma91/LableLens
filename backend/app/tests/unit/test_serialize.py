"""Serialization round-trip tests (no database needed)."""

import datetime

from app.repositories.serialize import (
    candidate_rows,
    claim_from_row,
    claim_id_for,
    claim_source_row,
    claim_to_row,
    decision_from_row,
    decision_to_row,
    match_row,
    normalization_row,
    observation_row,
    review_event_to_row,
    review_to_row,
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

ENTITY_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"


def _decision():
    return VerificationDecision(
        status="verified", identity_confidence="HIGH", gate_results=(),
        claims=(), evidence=(), source_refs=(), reason="gate passed",
        warnings=("note",), rules_version="1.0.0",
        snapshot_version="canonical_v1", entity_id=ENTITY_ID,
    )


def test_decision_round_trip_core():
    row = decision_to_row(_decision(), candidate_key="citric acid|")
    assert row["id"] == verification_id_for(
        "citric acid|", "verified", "1.0.0", "canonical_v1",
        row["evidence_context_hash"])
    back = decision_from_row(row)
    assert back["status"] == "verified"
    assert back["candidate_key"] == "citric acid|"
    assert back["warnings"] == ["note"]
    assert back["rules_version"] == "1.0.0"


def test_claim_round_trip_core():
    claim = IdentityClaim(
        entity_id=ENTITY_ID, field="formula", value="C6H8O7",
        status="verified", confidence="HIGH", evidence=(),
    )
    row = claim_to_row(claim)
    assert row["id"] == claim_id_for(ENTITY_ID, "formula", "C6H8O7")
    assert row["claim_type"] == "formula"
    assert row["claim_value_text"] == "C6H8O7"
    back = claim_from_row(row)
    assert (back["field"], back["value"], back["status"]) == (
        "formula", "C6H8O7", "verified")


def test_numeric_claim_value_routing():
    claim = IdentityClaim(
        entity_id=ENTITY_ID, field="molecular_weight", value=192.12,
        status="verified", confidence="HIGH", evidence=(),
    )
    row = claim_to_row(claim)
    assert row["claim_value_numeric"] == 192.12
    assert row["claim_value_text"] is None
    assert claim_from_row(row)["value"] == 192.12


def test_claim_source_row_metadata():
    evidence = FieldEvidence(
        field="formula", value="C6H8O7", unit=None,
        source=SourceMetadata(
            source_id="PUBCHEM", record_locator="CID:311",
            source_version="live", retrieved_at="2026-10-05",
            license_note="t", source_class="A"),
    )
    row = claim_source_row("c1", "s1", evidence, response_hash="ab12")
    assert row["support_type"] == "direct"
    assert row["source_value"] == "C6H8O7"
    assert row["response_hash"] == "ab12"
    # Date-only evidence timestamps widen to midnight UTC and bind as
    # real datetimes (asyncpg rejects timestamp strings).
    assert row["retrieved_at"] == datetime.datetime(
        2026, 10, 5, tzinfo=datetime.timezone.utc)
    assert claim_source_row(
        "c1", "s1", evidence, response_hash="ab12")["retrieved_at"] \
        == row["retrieved_at"]


def test_review_rows_preserve_history_inputs():
    item = {
        "review_id": "REV-0001", "candidate_key": "k", "raw_text": "r",
        "normalized_text": "n", "identifier": None, "resolution": {"a": 1},
        "verification_status": "conflicted", "evidence_context": {"e": 1},
        "evidence_hash": "h", "priority": 0, "status": "queued",
        "reviewer": None,
    }
    row = review_to_row(item)
    assert row["id"] == "REV-0001"
    assert row["resolution"] == {"a": 1}
    event = {
        "event_id": "REV-0001:001", "review_id": "REV-0001",
        "event_type": "ReviewCreated", "actor": "system:review-router",
        "reason": "routed", "previous_state": "", "new_state": "queued",
        "evidence_context_hash": "h", "rules_version": "1.0.0",
        "snapshot_version": "v",
    }
    assert review_event_to_row(event)["id"] == "REV-0001:001"


def test_verification_event_row_deterministic_id():
    first = verification_event_row(
        claim_id="c1", previous_status="provisional", new_status="verified")
    second = verification_event_row(
        claim_id="c1", previous_status="provisional", new_status="verified")
    assert first["id"] == second["id"]
    assert first["reviewer_type"] == "system"


def test_chain_rows_link_observations():
    obs = observation_row(
        observation_id="22222222-2222-2222-2222-222222222222",
        scan_id="11111111-1111-1111-1111-111111111111",
        sequence_number=0, raw_text="Sodiurn Benzoate")
    norm = normalization_row(
        normalization_id="33333333-3333-3333-3333-333333333333",
        observation_id=obs["id"], normalized_text="sodlum benzoate",
        status="complete")
    resolution = Resolution(
        raw_text="Sodlum Benzoate", normalized_text="sodlum benzoate",
        status="unresolved", candidates=[],
    )
    assert candidate_rows(resolution, normalization_id=norm["id"]) == []
    match = match_row(resolution, normalization_id=norm["id"])
    assert match["normalization_id"] == norm["id"]
    assert match["match_status"] == "unresolved"
    assert match["chemical_entity_id"] is None


def test_candidate_refs_stay_in_reasons_not_entities():
    resolution = Resolution(
        raw_text="citric acid", normalized_text="citric acid",
        status="exact_match",
        candidates=[
            Candidate(
                candidate_ref="T9-1", display_name="citric acid",
                candidate_type="single_molecule",
                source="synthetic_test_fixture",
                match_method="exact_normalized_name", match_score=0.95,
                reason="synthetic",
            )
        ],
    )
    rows = candidate_rows(resolution, normalization_id="n1")
    assert len(rows) == 1
    assert rows[0]["chemical_entity_id"] is None
    assert rows[0]["match_reasons"]["candidate_ref"] == "T9-1"
    assert rows[0]["candidate_score"] == 0.95

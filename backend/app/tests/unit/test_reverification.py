"""Tests for controlled re-verification after human review.

Proves the critical rule: human decisions re-enter the frozen V1-V7
gate (disambiguation + identifier/type inputs only). No path mutates
a verification status directly.
"""

import pytest

from app.services.entity_resolver import (
    Candidate,
    Resolution,
)
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.adapters.manual import ManualAdapter
from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
    Identifier,
    SourceMetadata,
    SourceRecord,
    VerificationDecision,
)
from app.services.verification.orchestrator import (
    reverify_candidate,
    verify_candidate,
)
from app.services.verification.review import (
    DECIDE_CONFIRM,
    ReviewQueue,
    ReviewSelection,
    candidate_key_for,
)


class FakeClock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        self.now += 1.0
        return self.now


def _meta(eid="E1", cls="A"):
    return SourceMetadata(
        source_id="SYNTH", record_locator="synth:" + eid,
        source_version="s", retrieved_at="2026-10-05",
        license_note="synthetic", source_class=cls,
    )


def _record(eid, name, rep="single_molecule", ids=(), fields=()):
    meta = _meta(eid)
    return SourceRecord(
        entity=CanonicalEntity(
            entity_id=eid, preferred_name=name,
            entity_type="chemical_entity",
            representation_type=rep,
            identifiers=tuple(
                Identifier(id_type=t, value=v, provenance_note="synthetic")
                for t, v in ids
            ),
            names=(), fields=tuple(fields), contexts=(),
            verification_status="verified", snapshot_version="synth",
            verified_at="2026-10-05", last_checked="2026-10-05",
            source=meta,
        ),
        source=meta,
    )


class _StaticSource(VerificationSource):
    def __init__(self, records):
        super().__init__()
        self._records = list(records)

    def lookup_identity(self, resolution):
        return list(self._records)


def _ambiguous_resolution(text="test substance E 330", identifier="E 330"):
    return Resolution(
        raw_text=text,
        normalized_text=text.lower(),
        identifier=identifier,
        status="ambiguous",
        candidates=[
            Candidate(
                candidate_ref="T9-A", display_name="candidate a",
                candidate_type="single_molecule",
                source="synthetic_test_fixture",
                match_method="exact_alias", match_score=0.85,
                reason="synthetic",
            ),
            Candidate(
                candidate_ref="T9-B", display_name="candidate b",
                candidate_type="single_molecule",
                source="synthetic_test_fixture",
                match_method="exact_alias", match_score=0.85,
                reason="synthetic",
            ),
        ],
    )


def _dual_records():
    return [
        _record("ENT-1", "test substance", ids=[("e_number", "E330")]),
        _record("ENT-2", "test substance", ids=[("e_number", "E330")]),
    ]


def _reviewed_selection(records, resolution, reviewer="human:ana",
                        ref="T9-A", queue=None, **decide_kwargs):
    queue = queue or ReviewQueue(clock=FakeClock())
    decision = VerificationDecision(
        status="provisional", identity_confidence="LOW", gate_results=(),
        claims=(), evidence=tuple(
            FieldEvidence(field="identity",
                          value=r.entity.preferred_name, unit=None,
                          source=r.source) for r in records
        ),
        source_refs=tuple(r.source for r in records),
        reason="synthetic provisional", warnings=(),
        rules_version="1.0.0", snapshot_version="",
        entity_id=None,
    )
    item = queue.submit(
        decision,
        resolution.to_dict(),
        records,
        has_alternatives=True,
    )
    queue.claim(item.review_id, reviewer)
    selection = queue.decide(
        item.review_id, decision=DECIDE_CONFIRM, reviewer=reviewer,
        reason="official sources agree", selected_candidate_ref=ref,
        **decide_kwargs,
    )
    return queue, item, selection


# --- reverify flows --------------------------------------------------------

def test_disambiguation_to_verified_through_gate():
    adapter = _StaticSource(_dual_records())
    resolution = _ambiguous_resolution()
    queue, item, selection = _reviewed_selection(
        _dual_records(), resolution)
    decision = reverify_candidate(resolution, adapter, selection)
    assert decision.status == "verified"
    assert decision.identity_confidence == "HIGH"
    assert all(g.result == "PASS" for g in decision.gate_results)
    assert any("human_review" in w for w in decision.warnings)
    queue.record_reverification(item.review_id, decision)
    assert len(queue.events_for(item.review_id)) == 5


def test_stale_evidence_rejects_selection():
    resolution = _ambiguous_resolution()
    _, _, selection = _reviewed_selection(_dual_records(), resolution)
    changed = [
        _record("ENT-1", "test substance", ids=[("e_number", "E330")]),
        _record("ENT-9", "test substance", ids=[("e_number", "E330")]),
    ]
    with pytest.raises(ValueError):
        reverify_candidate(
            resolution, _StaticSource(changed), selection)


def test_wrong_candidate_key_rejected():
    adapter = _StaticSource(_dual_records())
    resolution = _ambiguous_resolution()
    _, _, selection = _reviewed_selection(_dual_records(), resolution)
    other = _ambiguous_resolution("other substance E 330", "E 330")
    with pytest.raises(ValueError):
        reverify_candidate(other, adapter, selection)


def test_unknown_selection_ref_rejected():
    adapter = _StaticSource(_dual_records())
    resolution = _ambiguous_resolution()
    queue = ReviewQueue(clock=FakeClock())
    records = _dual_records()
    decision = VerificationDecision(
        status="provisional", identity_confidence="LOW", gate_results=(),
        claims=(), evidence=(), source_refs=(),
        reason="x", warnings=(), rules_version="1.0.0",
        snapshot_version="", entity_id=None,
    )
    item = queue.submit(decision, resolution.to_dict(), records,
                        has_alternatives=True)
    queue.claim(item.review_id, "human:ana")
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_CONFIRM,
                     reviewer="human:ana", reason="x",
                     selected_candidate_ref="T9-ZZZ")
    # Direct reverify guard as well.
    forged = ReviewSelection(
        review_id=item.review_id, reviewer="human:ana", reason="x",
        decided_at=0.0,
        candidate_key=candidate_key_for(
            resolution.normalized_text, resolution.identifier),
        selected_candidate_ref="T9-ZZZ",
        evidence_context_hash="stale",
        snapshot_version="", rules_version="1.0.0",
    )
    with pytest.raises(ValueError):
        reverify_candidate(resolution, adapter, forged)


def test_corrected_identifier_flows_through_gate():
    records = [
        _record("ENT-1", "test substance", ids=[("e_number", "E330")]),
        _record("ENT-2", "test substance", ids=[("e_number", "E330")]),
    ]
    adapter = _StaticSource(records)
    resolution = _ambiguous_resolution("test substance E 999", "E 999")
    queue, item, selection = _reviewed_selection(
        records, resolution, corrected_identifier="E 330")
    assert selection.corrected_identifier == "E 330"
    decision = reverify_candidate(resolution, adapter, selection)
    assert decision.status == "verified"
    v4 = [g for g in decision.gate_results
          if g.rule_id == "V4_identifier_validation"]
    assert v4 and v4[0].result == "PASS"


def test_corrected_type_flows_through_gate():
    records = [
        _record("ENT-1", "test blend", rep="mixture"),
        _record("ENT-2", "test blend", rep="mixture"),
    ]
    adapter = _StaticSource(records)
    resolution = Resolution(
        raw_text="test blend",
        normalized_text="test blend",
        status="ambiguous",
        candidates=[
            Candidate(
                candidate_ref="T9-M", display_name="test blend",
                candidate_type="single_molecule",
                source="synthetic_test_fixture",
                match_method="exact_alias", match_score=0.85,
                reason="synthetic",
            ),
            Candidate(
                candidate_ref="T9-N", display_name="test blend alt",
                candidate_type="mixture",
                source="synthetic_test_fixture",
                match_method="exact_alias", match_score=0.85,
                reason="synthetic",
            ),
        ],
    )
    _, _, selection = _reviewed_selection(
        records, resolution, ref="T9-N", corrected_type="mixture")
    decision = reverify_candidate(resolution, adapter, selection)
    assert decision.status in ("verified", "provisional")
    v5 = [g for g in decision.gate_results
          if g.rule_id == "V5_entity_type_validation"]
    assert v5 and v5[0].result == "PASS"


def test_conflict_survives_unfounded_confirmation():
    clash_a = _record("ENT-A", "test substance",
                      fields=[_field("formula", "C1")])
    clash_b = _record("ENT-B", "test substance",
                      fields=[_field("formula", "C2")])
    adapter = _StaticSource([clash_a, clash_b])
    resolution = _ambiguous_resolution()
    _, _, selection = _reviewed_selection([clash_a, clash_b], resolution)
    decision = reverify_candidate(resolution, adapter, selection)
    assert decision.status == "conflicted"


def _field(name, value):
    return FieldEvidence(field=name, value=value, unit=None,
                         source=_meta("E1"))


# --- claim boundaries --------------------------------------------------------

def test_identity_approval_approves_nothing_else():
    adapter = _StaticSource(_dual_records())
    resolution = _ambiguous_resolution()
    _, _, selection = _reviewed_selection(_dual_records(), resolution)
    assert selection.approved_fields == ("identity",)
    decision = reverify_candidate(resolution, adapter, selection)
    assert decision.status == "verified"
    non_identity = [c for c in decision.claims if c.field != "identity"]
    assert non_identity == []
    assert all(c.field == "identity" for c in decision.claims)


# --- manual adapter ------------------------------------------------------------

def test_manual_adapter_holds_selections_without_evidence():
    resolution = _ambiguous_resolution()
    _, _, selection = _reviewed_selection(_dual_records(), resolution)
    manual = ManualAdapter()
    assert manual.available is True
    assert manual.lookup_identity(resolution) == []
    manual.register_selection(selection)
    stored = manual.get_selection(selection.candidate_key)
    assert stored is not None
    assert stored.selected_candidate_ref == "T9-A"
    # Selections never become source records.
    assert manual.lookup_identity(resolution) == []
    assert manual.get_selection("nope|") is None


# --- obsolete absence ------------------------------------------------------------

def test_review_never_emits_obsolete():
    adapter = _StaticSource(_dual_records())
    for text in ("test substance E 330", "test substance"):
        resolution = _ambiguous_resolution(text, "E 330")
        _, _, selection = _reviewed_selection(_dual_records(), resolution)
        decision = reverify_candidate(resolution, adapter, selection)
        assert decision.status != "obsolete"


def test_verify_paths_never_emit_obsolete():
    adapter = _StaticSource(_dual_records())
    resolution = _ambiguous_resolution()
    assert verify_candidate(resolution, adapter).status != "obsolete"


# --- determinism -------------------------------------------------------------------

def test_reverify_deterministic():
    adapter = _StaticSource(_dual_records())
    resolution = _ambiguous_resolution()
    _, _, selection = _reviewed_selection(_dual_records(), resolution)
    first = reverify_candidate(resolution, adapter, selection).to_dict()
    second = reverify_candidate(resolution, adapter, selection).to_dict()
    assert first == second

"""Tests for the human-review queue, lifecycle, and audit trail.

No network, no randomness: deterministic IDs, priorities, and a
fake clock. Reviewer/reason validation and append-only history are
asserted throughout.
"""

import pytest

from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
    SourceMetadata,
    SourceRecord,
    VerificationDecision,
)
from app.services.verification.review import (
    DECIDE_CONFIRM,
    DECIDE_MARK_UNKNOWN,
    DECIDE_MORE_EVIDENCE,
    DECIDE_REJECT,
    EVENT_CLAIMED,
    EVENT_CREATED,
    EVENT_DECIDED,
    REVIEW_APPROVED,
    REVIEW_CLOSED_UNKNOWN,
    REVIEW_IN_REVIEW,
    REVIEW_NEEDS_MORE,
    REVIEW_QUEUED,
    REVIEW_REJECTED,
    ReviewQueue,
    candidate_key_for,
    current_context_hash,
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


def _record(eid="E1", name="test substance"):
    meta = _meta(eid)
    return SourceRecord(
        entity=CanonicalEntity(
            entity_id=eid, preferred_name=name,
            entity_type="chemical_entity",
            representation_type="single_molecule",
            identifiers=(), names=(), fields=(),
            contexts=(), verification_status="verified",
            snapshot_version="snap", verified_at="d", last_checked="d",
            source=meta,
        ),
        source=meta,
    )


def _evidence(records):
    return tuple(
        FieldEvidence(field="identity", value=r.entity.preferred_name,
                      unit=None, source=r.source)
        for r in records
    )


def _decision(status, records=(), confidence="LOW"):
    return VerificationDecision(
        status=status,
        identity_confidence=confidence,
        gate_results=(),
        claims=(),
        evidence=_evidence(list(records)),
        source_refs=tuple(r.source for r in records),
        reason="synthetic %s" % status,
        warnings=(),
        rules_version="1.0.0",
        snapshot_version="snap",
        entity_id=None,
    )


def _resolution_dict(text="test substance", identifier=None,
                     candidates=()):
    return {
        "raw_text": text,
        "normalized_text": text.lower(),
        "identifier": identifier,
        "status": "ambiguous",
        "entity": None,
        "alternatives": list(candidates),
    }


def _cand(ref):
    return {"candidate_ref": ref, "display_name": ref}


# --- routing -----------------------------------------------------------

def test_provisional_and_conflicted_always_routed():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    prov = queue.submit(_decision("provisional", recs),
                        _resolution_dict(), recs)
    conf = queue.submit(_decision("conflicted", recs),
                        _resolution_dict(), recs)
    assert prov is not None and conf is not None
    assert prov.review_id == "REV-0001"
    assert conf.review_id == "REV-0002"
    assert prov.priority == 1
    assert conf.priority == 0


def test_unknown_routing_needs_alternatives():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    assert queue.submit(_decision("unknown", recs),
                        _resolution_dict(), recs) is None
    routed = queue.submit(
        _decision("unknown", recs),
        _resolution_dict(candidates=[_cand("A"), _cand("B")]),
        recs, has_alternatives=True,
    )
    assert routed is not None
    assert routed.priority == 2


def test_unverified_routing_and_verified_never():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    assert queue.submit(_decision("unverified", recs),
                        _resolution_dict(), recs) is None
    assert queue.submit(
        _decision("unverified", recs),
        _resolution_dict(candidates=[_cand("A")]),
        recs, has_alternatives=True,
    ) is not None
    assert queue.submit(_decision("verified", recs),
                        _resolution_dict(), recs) is None


def test_pending_priority_order_deterministic():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    queue.submit(_decision("unverified", recs),
                 _resolution_dict(candidates=[_cand("A")]),
                 recs, has_alternatives=True)
    queue.submit(_decision("provisional", recs),
                 _resolution_dict(), recs)
    queue.submit(_decision("conflicted", recs),
                 _resolution_dict(), recs)
    queue.submit(_decision("unknown", recs),
                 _resolution_dict(candidates=[_cand("A")]),
                 recs, has_alternatives=True)
    order = [i.verification_status for i in queue.pending()]
    assert order == ["conflicted", "provisional", "unknown", "unverified"]


def test_fifo_within_priority():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    first = queue.submit(_decision("provisional", recs),
                         _resolution_dict(), recs)
    second = queue.submit(_decision("provisional", recs),
                          _resolution_dict(), recs)
    pending = queue.pending()
    assert [i.review_id for i in pending] == [first.review_id,
                                              second.review_id]


# --- lifecycle -----------------------------------------------------------

def _queued_item(queue=None):
    queue = queue or ReviewQueue(clock=FakeClock())
    recs = [_record()]
    item = queue.submit(_decision("conflicted", recs),
                        _resolution_dict(), recs)
    return queue, item


def test_claim_assigns_reviewer():
    queue, item = _queued_item()
    claimed = queue.claim(item.review_id, "human:ana")
    assert claimed.status == REVIEW_IN_REVIEW
    assert claimed.reviewer == "human:ana"


def test_claim_rejects_bad_reviewer_and_state():
    queue, item = _queued_item()
    with pytest.raises(ValueError):
        queue.claim(item.review_id, "")
    with pytest.raises(ValueError):
        queue.claim("REV-9999", "human:ana")
    queue.claim(item.review_id, "human:ana")
    with pytest.raises(ValueError):
        queue.claim(item.review_id, "human:bob")


def test_ai_cannot_be_reviewer():
    queue, item = _queued_item()
    for bad in ("ai", "AI", "ai:assistant", "llm:reviewer"):
        with pytest.raises(ValueError):
            queue.claim(item.review_id, bad)


def _in_review(queue=None):
    queue, item = _queued_item(queue)
    queue.claim(item.review_id, "human:ana")
    return queue, item


def test_confirm_requires_selection_reason_and_reviewer():
    queue, item = _in_review()
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_CONFIRM,
                     reviewer="human:ana", reason="ok")
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_CONFIRM,
                     reviewer="human:ana", reason="",
                     selected_candidate_ref="A")
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_CONFIRM,
                     reviewer="", reason="ok",
                     selected_candidate_ref="A")
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision="bogus",
                     reviewer="human:ana", reason="ok",
                     selected_candidate_ref="A")


def test_confirm_rejects_unknown_selection():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    item = queue.submit(
        _decision("conflicted", recs),
        _resolution_dict(candidates=[_cand("A"), _cand("B")]),
        recs,
    )
    queue.claim(item.review_id, "human:ana")
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_CONFIRM,
                     reviewer="human:ana", reason="looks right",
                     selected_candidate_ref="ZZZ")


def test_confirm_approves_identity_only():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    item = queue.submit(
        _decision("conflicted", recs),
        _resolution_dict(candidates=[_cand("A"), _cand("B")]),
        recs,
    )
    queue.claim(item.review_id, "human:ana")
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_CONFIRM,
                     reviewer="human:ana", reason="ok",
                     selected_candidate_ref="A",
                     approved_fields=("identity", "formula"))
    selection = queue.decide(
        item.review_id, decision=DECIDE_CONFIRM,
        reviewer="human:ana", reason="official source agrees",
        selected_candidate_ref="A",
    )
    assert selection is not None
    assert selection.approved_fields == ("identity",)
    assert selection.selected_candidate_ref == "A"
    assert selection.reviewer == "human:ana"
    assert queue.get(item.review_id).status == REVIEW_APPROVED


def test_reject_more_unknown_terminals():
    for decision_type, terminal in (
        (DECIDE_REJECT, REVIEW_REJECTED),
        (DECIDE_MORE_EVIDENCE, REVIEW_NEEDS_MORE),
        (DECIDE_MARK_UNKNOWN, REVIEW_CLOSED_UNKNOWN),
    ):
        queue, item = _in_review()
        out = queue.decide(item.review_id, decision=decision_type,
                           reviewer="human:ana", reason="stated reason")
        assert out is None
        assert queue.get(item.review_id).status == terminal


def test_decide_requires_in_review():
    queue, item = _queued_item()
    with pytest.raises(ValueError):
        queue.decide(item.review_id, decision=DECIDE_REJECT,
                     reviewer="human:ana", reason="x")


# --- audit ---------------------------------------------------------------

def test_events_append_only_with_versions():
    queue, item = _queued_item()
    queue.claim(item.review_id, "human:ana")
    queue.decide(item.review_id, decision=DECIDE_REJECT,
                 reviewer="human:ana", reason="not this entity")
    events = queue.events_for(item.review_id)
    assert [e.event_type for e in events] == [
        EVENT_CREATED, EVENT_CLAIMED, EVENT_DECIDED]
    assert [e.event_id for e in events] == [
        item.review_id + ":001", item.review_id + ":002",
        item.review_id + ":003"]
    assert events[0].previous_state == ""
    assert events[0].new_state == REVIEW_QUEUED
    assert events[1].actor == "human:ana"
    for event in events:
        assert event.evidence_context_hash == item.evidence_hash
        assert event.rules_version == "1.0.0"
        assert event.snapshot_version == "snap"
    assert len(queue.all_events()) == 3


def test_evidence_context_preserved():
    queue, item = _queued_item()
    context = item.evidence_context
    assert context["candidate_key"] == item.candidate_key
    assert context["snapshot_version"] == "snap"
    assert context["rules_version"] == "1.0.0"
    assert len(context["evidence"]) == 1


def test_context_hash_stable_and_sensitive():
    recs = [_record("E1")]
    key = candidate_key_for("test substance", None)
    first = current_context_hash(key, recs, snapshot_version="s",
                                 rules_version="1.0.0")
    again = current_context_hash(key, recs, snapshot_version="s",
                                 rules_version="1.0.0")
    assert first == again
    other = _record("E2")
    assert current_context_hash(key, [other], snapshot_version="s",
                                rules_version="1.0.0") != first


def test_reverification_history_retained():
    queue, item = _queued_item()
    queue.claim(item.review_id, "human:ana")
    queue.decide(item.review_id, decision=DECIDE_MORE_EVIDENCE,
                 reviewer="human:ana", reason="need second source")
    before = len(queue.all_events())
    new_decision = _decision("verified", [_record()], confidence="HIGH")
    event = queue.record_reverification(item.review_id, new_decision)
    assert event.event_type == "VerificationResultRecorded"
    assert len(queue.all_events()) == before + 2
    assert "verified" in event.reason


def test_malicious_strings_stored_as_data():
    queue = ReviewQueue(clock=FakeClock())
    recs = [_record()]
    item = queue.submit(_decision("conflicted", recs),
                        _resolution_dict(), recs)
    evil = "human:ana'); DROP TABLE reviews; --"
    queue.claim(item.review_id, evil)
    assert queue.get(item.review_id).reviewer == evil
    queue.decide(item.review_id, decision=DECIDE_REJECT,
                 reviewer=evil, reason="__import__('os').system('x')")
    events = queue.events_for(item.review_id)
    assert events[-1].reason == "__import__('os').system('x')"

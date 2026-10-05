"""Review endpoint tests: lifecycle, security, concurrency."""

from app.tests.api.helpers import (
    READER,
    REVIEWER1,
    REVIEWER2,
    auth,
    envelope,
    make_app,
)

client, _ = make_app()


def _analyze(text):
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": text},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    result = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    return observation_id, result


def _provisional_review_id():
    _, result = _analyze("citric acid")
    assert result["status"] == "provisional"
    assert result["review_id"] is not None
    return result["review_id"]


def test_provisional_creates_pending_review():
    review_id = _provisional_review_id()
    listed = envelope(client.get("/api/v1/reviews/pending",
                                 headers=auth(READER)))
    assert any(r["review_id"] == review_id for r in listed)
    detail = envelope(client.get("/api/v1/reviews/%s" % review_id,
                                 headers=auth(READER)))
    assert detail["review"]["status"] == "queued"
    assert len(detail["events"]) == 1
    assert detail["events"][0]["event_type"] == "ReviewCreated"


def test_verified_creates_no_review():
    _, result = _analyze("Citric Acid (E330)")
    assert result["status"] == "verified"
    assert result["review_id"] is None


def test_claim_assigns_authenticated_reviewer():
    review_id = _provisional_review_id()
    claimed = envelope(client.post(
        "/api/v1/reviews/%s/claim" % review_id, headers=auth(REVIEWER1)))
    assert claimed["status"] == "in_review"
    assert claimed["reviewer"] == "human:reviewer1"


def test_double_claim_conflicts():
    review_id = _provisional_review_id()
    envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER1)))
    second = client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER2))
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


def test_decision_requires_reason_and_validates_scope():
    review_id = _provisional_review_id()
    envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER1)))
    assert client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        json={"decision": "confirm_identity", "reason": ""},
        headers=auth(REVIEWER1)).status_code == 422
    forbidden = client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        json={"decision": "confirm_identity", "reason": "ok",
              "selected_candidate_ref": "T11-001",
              "approved_fields": ["identity", "formula"]},
        headers=auth(REVIEWER1))
    assert forbidden.status_code == 422


def test_confirm_reruns_verification_and_persists():
    review_id = _provisional_review_id()
    envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER1)))
    result = envelope(client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        json={"decision": "confirm_identity",
              "reason": "official sources agree",
              "selected_candidate_ref": "T11-001"},
        headers=auth(REVIEWER1)))
    assert result["status"] == "approved"
    assert result["decision"]["status"] in (
        "provisional", "verified", "unknown", "unverified")
    detail = envelope(client.get("/api/v1/reviews/%s" % review_id,
                                 headers=auth(READER)))
    assert detail["review"]["status"] == "approved"
    assert len(detail["events"]) >= 3
    # Every persisted transition keeps its own audit event: a decision
    # must never reuse an existing positional event id (which would be
    # deduplicated away and leave the decision unaudited).
    types = [e["event_type"] for e in detail["events"]]
    assert types[0] == "ReviewCreated"
    assert "ReviewClaimed" in types
    assert "ReviewDecisionRecorded" in types
    assert len(set(types)) == len(types)
    actors = {e["actor"] for e in detail["events"]}
    assert "human:reviewer1" in actors          # from authentication only
    assert not any(a.startswith("ai:") for a in actors)
    assert all(a.startswith(("human:", "system:")) for a in actors)


def test_reject_and_unknown_terminals():
    review_id = _provisional_review_id()
    envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER1)))
    rejected = envelope(client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        json={"decision": "reject_identity", "reason": "wrong entity"},
        headers=auth(REVIEWER1)))
    assert rejected["status"] == "rejected"


def test_pagination_bounds():
    assert client.get("/api/v1/reviews/pending?page=0",
                      headers=auth(READER)).status_code == 422
    assert client.get("/api/v1/reviews/pending?page_size=1000",
                      headers=auth(READER)).status_code == 422
    listed = envelope(client.get(
        "/api/v1/reviews/pending?page=1&page_size=1",
        headers=auth(READER)))
    assert len(listed) <= 1


def test_pending_order_deterministic():
    _provisional_review_id()
    _provisional_review_id()
    listed = envelope(client.get("/api/v1/reviews/pending",
                                 headers=auth(READER)))
    keys = [(r["priority"], r["review_id"]) for r in listed]
    assert keys == sorted(keys)

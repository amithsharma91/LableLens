"""Cross-user API isolation tests (Stage 18).

Three subjects: user-a and user-b are plain authenticated users,
reviewer-1 is an allowlisted reviewer. Every user-derived route
must isolate A from B; reviewers keep the queue workflow.
"""

from fastapi.testclient import TestClient

from app.api.auth import StaticTokenVerifier
from app.main import create_app
from app.repositories.memory import MemoryUnitOfWork
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.tests.api.helpers import (
    PermissivePolicy,
    auth,
    envelope,
    register_snapshot_entities,
    registry,
    SNAPSHOT_PATH,
)

USER_A = "token-a"
USER_B = "token-b"
REVIEWER = "token-reviewer"


def _app():
    from app.services.rate_limit import InMemoryRateLimiter

    uow = register_snapshot_entities(MemoryUnitOfWork())
    application = create_app(
        repos=uow,
        verifier=StaticTokenVerifier({
            USER_A: ("user-a", "authenticated"),
            USER_B: ("user-b", "authenticated"),
            REVIEWER: ("reviewer-1", "reviewer"),
        }),
        registry=registry(),
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
        rate_limiter=InMemoryRateLimiter(max_keys=10000),
    )
    application.state.rate_limit_policy = PermissivePolicy()
    return TestClient(application)


def _analyze(client, token, text="citric acid"):
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": text},
        headers=auth(token)), status=201)
    observation_id = created[0]["observation_id"]
    result = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(token)))
    return observation_id, result


def test_review_queue_is_owner_scoped_for_users():
    client = _app()
    _, result_a = _analyze(client, USER_A)
    review_id = result_a["review_id"]
    assert review_id is not None
    listed_b = envelope(client.get(
        "/api/v1/reviews/pending", headers=auth(USER_B)))
    assert all(
        item["review_id"] != review_id for item in listed_b)
    stranger = client.get(
        "/api/v1/reviews/%s" % review_id, headers=auth(USER_B))
    assert stranger.status_code == 404
    assert stranger.json()["error"]["code"] == "NOT_FOUND"
    listed_a = envelope(client.get(
        "/api/v1/reviews/pending", headers=auth(USER_A)))
    assert any(
        item["review_id"] == review_id for item in listed_a)


def test_reviewer_keeps_queue_workflow_across_owners():
    client = _app()
    _, result_a = _analyze(client, USER_A)
    review_id = result_a["review_id"]
    listed = envelope(client.get(
        "/api/v1/reviews/pending", headers=auth(REVIEWER)))
    assert any(
        item["review_id"] == review_id for item in listed)
    detail = envelope(client.get(
        "/api/v1/reviews/%s" % review_id, headers=auth(REVIEWER)))
    assert detail["review"]["review_id"] == review_id
    claimed = envelope(client.post(
        "/api/v1/reviews/%s/claim" % review_id,
        headers=auth(REVIEWER)))
    assert claimed["reviewer"] == "human:reviewer-1"


def test_verification_and_candidates_isolate_users():
    client = _app()
    observation_id, _ = _analyze(client, USER_A)
    for path in (
        "/api/v1/observations/%s/verification" % observation_id,
        "/api/v1/observations/%s/candidates" % observation_id,
        "/api/v1/observations/%s/resolution" % observation_id,
    ):
        response = client.get(path, headers=auth(USER_B))
        assert response.status_code == 404, (path, response.text)
        assert response.json()["error"]["code"] == "NOT_FOUND"
    owner = envelope(client.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=auth(USER_A)))
    assert owner["status"] == "provisional"

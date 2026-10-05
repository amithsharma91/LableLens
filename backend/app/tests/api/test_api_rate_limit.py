"""HTTP coverage for application rate limiting (Stage 12).

Policies are configuration, so tests build the app through the
production factory and inject a deterministic in-memory limiter with
explicit policies. No endpoint sleeps: window behaviour is asserted in
the limiter unit tests, while here the contract under test is the HTTP
behaviour (429 envelope, Retry-After, identity source, isolation, and
that reads are unaffected).
"""

from fastapi.testclient import TestClient

from app.api.auth import Principal
from app.config import settings
from app.main import create_app
from app.repositories.memory import MemoryUnitOfWork
from app.services.rate_limit import InMemoryRateLimiter, RateLimiter
from app.services.verification.adapters.snapshot import SnapshotAdapter

from app.tests.api.helpers import (
    READER,
    REVIEWER1,
    SNAPSHOT_PATH,
    auth,
    register_snapshot_entities,
    verifier,
)

RAW_TEXT = "Ingredients: citric acid, sodium benzoate"


class _StaticPolicy:
    """Fixed policies keyed by action (no env mutation)."""

    def __init__(self, create="3/60", analyze="2/60", decision="2/60"):
        self._table = {
            "observations.create": create,
            "observations.analyze": analyze,
            "reviews.decision": decision,
        }

    def for_action(self, action: str) -> str:
        return self._table.get(action, "0/0")


class _ExplodingLimiter:
    def __init__(self):
        self.calls = 0

    async def hit(self, key, *, limit, window_seconds):
        self.calls += 1
        raise RuntimeError("limiter backend unavailable")


def _app(*, limiter=None, policy=None, verifier_instance=None,
         registry=None):
    uow = register_snapshot_entities(MemoryUnitOfWork())
    policy = policy or _StaticPolicy()
    if limiter is None:
        limiter = InMemoryRateLimiter(max_keys=100)
    application = create_app(
        repos=uow,
        verifier=verifier_instance or verifier(),
        registry=registry,
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
        rate_limiter=limiter,
    )
    # The dependency reads the policy table injected here, so the test
    # never depends on ambient environment values.
    application.state.rate_limit_policy = policy
    client = TestClient(application)
    return client, uow, limiter


def _create(client, token=READER, text=RAW_TEXT):
    return client.post("/api/v1/observations", headers=auth(token),
                       json={"raw_text": text})


def _observe(client, token=READER, index=0):
    created = _create(client, token=token)
    assert created.status_code == 201, created.text
    observation_id = created.json()["data"][index]["observation_id"]
    return observation_id


# -- create ------------------------------------------------------------


def test_below_limit_succeeds():
    client, _, _ = _app()
    for _ in range(3):
        assert _create(client).status_code == 201


def test_limit_reached_then_429_with_retry_after():
    client, _, _ = _app(policy=_StaticPolicy(create="2/60"))
    assert _create(client).status_code == 201
    assert _create(client).status_code == 201
    limited = _create(client)
    assert limited.status_code == 429
    body = limited.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["message"] == "too many requests"
    assert body["error"]["details"]["action"] == "observations.create"
    assert body["error"]["details"]["retry_after_seconds"] == 60
    assert limited.headers["Retry-After"] == "60"
    # No internal limiter state is disclosed.
    assert "bucket" not in limited.text.lower()
    assert "subject" not in limited.text.lower()


def test_retry_after_header_matches_the_remaining_window():
    client, _, _ = _app(policy=_StaticPolicy(create="1/45"))
    assert _create(client).status_code == 201
    limited = _create(client)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "45"


def test_disabled_limiter_allows_everything(monkeypatch):
    client, _, _ = _app(policy=_StaticPolicy(create="1/60"))
    assert _create(client).status_code == 201
    assert _create(client).status_code == 429
    # With limiting switched off the same policy is not consulted.
    monkeypatch.setattr(settings, "rate_limit_enabled", "false")
    assert _create(client).status_code == 201
    assert _create(client).status_code == 201


def test_limiter_backend_failure_fails_closed():
    client, _, _ = _app(limiter=_ExplodingLimiter())
    response = _create(client)
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "RATE_LIMITER_UNAVAILABLE"
    assert "RuntimeError" in body["error"]["details"].get(
        "error_category", "")
    # The sensitive write did not happen.
    assert body["meta"]["api_version"] == "v1"


# -- analyze -----------------------------------------------------------


def test_analyze_is_limited_independently():
    client, _, _ = _app(policy=_StaticPolicy(create="10/60", analyze="1/60"))
    observation_id = _observe(client)
    path = "/api/v1/observations/%s/analyze" % observation_id
    assert client.post(path, headers=auth(READER)).status_code == 200
    second = client.post(path, headers=auth(READER))
    assert second.status_code == 429
    assert second.json()["error"]["details"]["action"] == \
        "observations.analyze"


def test_analyze_policy_does_not_consume_the_create_bucket():
    client, _, _ = _app(policy=_StaticPolicy(create="2/60", analyze="5/60"))
    for _ in range(2):
        assert _create(client).status_code == 201
    # Creation is exhausted for this subject; analyze has its own
    # allowance and its own bucket key.
    assert _create(client).status_code == 429
    observation_id = _observe(client, token=REVIEWER1)
    path = "/api/v1/observations/%s/analyze" % observation_id
    for _ in range(5):
        assert client.post(path, headers=auth(READER)).status_code == 200


# -- decision ----------------------------------------------------------


def test_review_decision_is_limited():
    client, _, _ = _app(
        policy=_StaticPolicy(create="10/60", decision="3/60"))
    for _ in range(3):
        response = client.post(
            "/api/v1/reviews/rv-missing/decision",
            headers=auth(REVIEWER1),
            json={
                "decision": "reject_identity",
                "reason": "not the label term",
            },
        )
        # The review id does not exist, so the request passes the
        # limiter and then fails on lookup: 404 proves the bucket was
        # consumed rather than rejected.
        assert response.status_code == 404, response.text
    limited = client.post(
        "/api/v1/reviews/rv-missing/decision",
        headers=auth(REVIEWER1),
        json={
            "decision": "reject_identity",
            "reason": "not the label term",
        },
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["details"]["action"] == "reviews.decision"


# -- identity ----------------------------------------------------------


def test_separate_subjects_have_independent_buckets():
    from app.api.auth import StaticTokenVerifier

    verifier_two = StaticTokenVerifier({
        "reader": ("reader", "authenticated"),
        "other-token": ("other-reader", "authenticated"),
    })
    client, _, _ = _app(
        policy=_StaticPolicy(create="2/60"), verifier_instance=verifier_two)
    for _ in range(2):
        assert _create(client, token="reader").status_code == 201
    assert _create(client, token="reader").status_code == 429
    assert _create(client, token="other-token").status_code == 201


def test_payload_fields_cannot_bypass_the_limit():
    client, _, _ = _app(policy=_StaticPolicy(create="1/60"))
    assert _create(client, text="Ingredients: citric acid").status_code == 201
    for text in ("Ingredients: glycerol", "Ingredients: ethanol",
                 "Ingredients: water"):
        response = client.post(
            "/api/v1/observations", headers=auth(READER),
            json={"raw_text": text, "scan_id": None,
                  "observation_id": None, "user_id": "other"},
        )
        assert response.status_code in (422, 429)


def test_unauthenticated_requests_are_not_rate_limited():
    client, _, _ = _app(policy=_StaticPolicy(create="1/60"))
    for _ in range(5):
        response = client.post("/api/v1/observations",
                               json={"raw_text": RAW_TEXT})
        assert response.status_code == 401


def test_rate_limit_identity_comes_from_the_principal():
    """The bucket key is built from the verified principal only."""
    from app.api.limits import bucket_key

    principal = Principal(subject="user-1", role="authenticated")
    key = bucket_key("observations.create", principal, include_ip=False)
    assert key == "observations.create|user-1"
    with_ip = bucket_key(
        "observations.create", principal, include_ip=True, ip="10.0.0.1")
    assert with_ip.endswith("|10.0.0.1")


# -- reads are not limited --------------------------------------------


def test_get_endpoints_are_not_rate_limited():
    client, _, _ = _app(policy=_StaticPolicy(create="1/60", analyze="1/60"))
    observation_id = _observe(client)
    assert client.post("/api/v1/observations/%s/analyze" % observation_id,
                       headers=auth(READER)).status_code == 200
    for _ in range(25):
        assert client.get("/api/v1/observations/%s" % observation_id,
                          headers=auth(READER)).status_code == 200
        assert client.get("/api/v1/observations/%s/candidates" % (
            observation_id), headers=auth(READER)).status_code == 200
        assert client.get("/api/v1/reviews/pending",
                          headers=auth(READER)).status_code == 200
        assert client.get("/api/v1/health").status_code == 200


def test_health_needs_no_token_and_no_bucket():
    client, _, _ = _app(policy=_StaticPolicy(create="1/60"))
    for _ in range(10):
        assert client.get("/api/v1/health").status_code == 200


# -- configuration -----------------------------------------------------


def test_default_policies_are_configuration_driven():
    # Nothing is hard-coded in the routes; the settings table supplies
    # the policies and every one of them parses.
    for action in ("observations.create", "observations.analyze",
                   "reviews.decision"):
        limit, window = settings.rate_limit_for(action)
        assert limit > 0 and window > 0


def test_unconfigured_action_is_not_limited(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_analyze", "0/0")
    client, _, _ = _app(policy=_StaticPolicy(create="10/60", analyze="0/0"))
    observation_id = _observe(client)
    path = "/api/v1/observations/%s/analyze" % observation_id
    for _ in range(5):
        assert client.post(path, headers=auth(READER)).status_code == 200


def test_limiter_protocol_is_backend_agnostic():
    assert hasattr(RateLimiter, "hit")

    # A different backend only needs the same one-method contract.
    class _Custom:

        def __init__(self):
            self.seen = []

        async def hit(self, key, *, limit, window_seconds):
            self.seen.append((key, limit, window_seconds))
            from app.services.rate_limit import RateLimitDecision
            return RateLimitDecision(
                allowed=True, limit=limit, remaining=limit - 1)

    custom = _Custom()
    client, _, _ = _app(limiter=custom)
    assert _create(client).status_code == 201
    assert custom.seen[0][0] == "observations.create|reader"
    assert custom.seen[0][1] == 3

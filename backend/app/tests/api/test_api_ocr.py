"""OCR endpoint tests (Stage 16 API).

Exercises the four OCR routes through the production factory with
in-memory repositories, static tokens, and the deterministic fake
OCR provider: authentication, envelopes, ingest/read/correct/
analyze flows, provider failure mapping, and rate-limit reuse.
No network, no database, no randomness.
"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.memory import MemoryUnitOfWork
from app.services.ocr_provider import FakeOCRProvider, OCRResult
from app.tests.api.helpers import (
    READER,
    REVIEWER1,
    auth,
    envelope,
    register_snapshot_entities,
    registry,
    verifier,
)
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.tests.api.helpers import SNAPSHOT_PATH


def _app(providers=None):
    from app.services.rate_limit import InMemoryRateLimiter

    uow = register_snapshot_entities(MemoryUnitOfWork())
    application = create_app(
        repos=uow,
        verifier=verifier(),
        registry=registry(),
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
        ocr_providers=providers or {},
        # Own limiter instance plus a permissive policy: these tests
        # must neither consume the process-wide shared buckets nor
        # be denied by them.
        rate_limiter=InMemoryRateLimiter(max_keys=10000),
    )
    application.state.rate_limit_policy = _permissive()
    return TestClient(application)


def _permissive():
    from app.tests.api.helpers import PermissivePolicy

    return PermissivePolicy()


def _ingest(client, **overrides):
    payload = {
        "document_id": "doc-1",
        "raw_text": "Sodium Benzoate",
        "provider": "client",
    }
    payload.update(overrides)
    return client.post("/api/v1/ocr/runs", json=payload,
                       headers=auth(READER))


def test_unauthenticated_ocr_routes_rejected():
    client = _app()
    assert client.post("/api/v1/ocr/runs", json={
        "document_id": "d", "raw_text": "x"}).status_code == 401
    assert client.get("/api/v1/ocr/runs/x").status_code == 401
    assert client.post("/api/v1/ocr/runs/x/correction", json={
        "corrected_text": "y", "reason": "r"}).status_code == 401
    assert client.post("/api/v1/ocr/runs/x/analyze").status_code == 401


def test_ingest_returns_run_envelope():
    data = envelope(_ingest(_app()), status=201)
    assert data["document_id"] == "doc-1"
    assert data["provider"] == "client"
    assert data["raw_text"] == "Sodium Benzoate"
    assert data["corrected_text"] is None
    assert data["run_id"]


def test_ingest_rejects_unknown_fields_and_bad_confidence():
    client = _app()
    assert client.post("/api/v1/ocr/runs", json={
        "document_id": "d", "raw_text": "x",
        "subject": "admin"}, headers=auth(READER)).status_code == 422
    assert client.post("/api/v1/ocr/runs", json={
        "document_id": "d", "raw_text": "x",
        "ocr_confidence": 2.0}, headers=auth(READER)).status_code == 422


def test_get_run_reports_correction_and_observations():
    client = _app()
    run_id = envelope(_ingest(client), status=201)["run_id"]
    data = envelope(client.get("/api/v1/ocr/runs/%s" % run_id,
                               headers=auth(READER)))
    assert data["run_id"] == run_id
    assert data["correction_reason"] is None
    assert data["observations"] == []
    envelope(client.post(
        "/api/v1/ocr/runs/%s/correction" % run_id,
        json={"corrected_text": "Sodium Benzoate!",
              "reason": "punctuation"},
        headers=auth(READER)))
    data = envelope(client.get("/api/v1/ocr/runs/%s" % run_id,
                               headers=auth(READER)))
    assert data["corrected_text"] == "Sodium Benzoate!"
    assert data["correction_reason"] == "punctuation"


def test_get_missing_run_is_404():
    client = _app()
    response = client.get(
        "/api/v1/ocr/runs/00000000-0000-4000-8000-000000000000",
        headers=auth(READER))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_correction_uses_reviewer_identity_and_refuses_repeat():
    client = _app()
    run_id = envelope(_ingest(client), status=201)["run_id"]
    first = envelope(client.post(
        "/api/v1/ocr/runs/%s/correction" % run_id,
        json={"corrected_text": "Sodium Benzoate",
              "reason": "ocr fix"},
        headers=auth(READER)))
    assert first["actor"] == "human:reader"
    assert first["corrected_text"] == "Sodium Benzoate"
    response = client.post(
        "/api/v1/ocr/runs/%s/correction" % run_id,
        json={"corrected_text": "other", "reason": "again"},
        headers=auth(READER))
    assert response.status_code == 422
    assert client.post(
        "/api/v1/ocr/runs/00000000-0000-4000-8000-000000000000/correction",
        json={"corrected_text": "x", "reason": "r"},
        headers=auth(READER)).status_code == 404


def test_analyze_returns_items_and_warnings():
    client = _app()
    run_id = envelope(_ingest(client), status=201)["run_id"]
    data = envelope(client.post(
        "/api/v1/ocr/runs/%s/analyze" % run_id, headers=auth(READER)))
    assert data["run_id"] == run_id
    assert data["corrected"] is False
    assert data["warnings"] == []
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "provisional"
    assert "identity_confidence" in data["items"][0]
    # No chemistry leaks into the OCR analyze envelope.
    assert "formula" not in data["items"][0]
    assert "smiles" not in data["items"][0]


def test_analyze_empty_ocr_warns_without_crash():
    client = _app()
    run_id = envelope(_ingest(client, raw_text="   "), status=201)[
        "run_id"]
    data = envelope(client.post(
        "/api/v1/ocr/runs/%s/analyze" % run_id, headers=auth(READER)))
    assert data["items"] == []
    assert data["warnings"]


def test_analyze_missing_run_is_404():
    client = _app()
    assert client.post(
        "/api/v1/ocr/runs/00000000-0000-4000-8000-000000000000/analyze",
        headers=auth(READER)).status_code == 404


def test_provider_extraction_path_uses_injected_provider():
    provider = FakeOCRProvider({
        "doc-9": OCRResult(
            document_id="doc-9", provider="fake-test",
            raw_text="citric acid", ocr_confidence=0.7)},
        name="fake-test")
    client = _app(providers={"fake-test": provider})
    data = envelope(client.post(
        "/api/v1/ocr/runs",
        json={"document_id": "doc-9", "provider": "fake-test"},
        headers=auth(READER)), status=201)
    assert data["raw_text"] == "citric acid"
    assert data["ocr_confidence"] == 0.7


def test_ocr_routes_reuse_observation_budgets():
    from app.services.rate_limit import InMemoryRateLimiter

    uow = register_snapshot_entities(MemoryUnitOfWork())
    application = create_app(
        repos=uow,
        verifier=verifier(),
        registry=registry(),
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))],
        rate_limiter=InMemoryRateLimiter(max_keys=100),
    )

    class Tight:
        def for_action(self, action):
            return "1/60"

    application.state.rate_limit_policy = Tight()
    client = TestClient(application)
    run_id = envelope(client.post(
        "/api/v1/ocr/runs",
        json={"document_id": "d", "raw_text": "water"},
        headers=auth(READER)), status=201)["run_id"]
    # Second ingest exceeds the shared observations.create budget.
    refused = client.post(
        "/api/v1/ocr/runs",
        json={"document_id": "d2", "raw_text": "water"},
        headers=auth(READER))
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "60"
    assert refused.json()["error"]["code"] == "RATE_LIMITED"
    # Analysis consumes the shared observations.analyze budget once.
    assert client.post(
        "/api/v1/ocr/runs/%s/analyze" % run_id,
        headers=auth(READER)).status_code == 200
    refused = client.post(
        "/api/v1/ocr/runs/%s/analyze" % run_id,
        headers=auth(READER))
    assert refused.status_code == 429


def test_cross_user_access_is_not_found_everywhere():
    # READER ("reader") owns the run; REVIEWER1 ("reviewer1") is a
    # stranger. Every route answers 404 with the standard NOT_FOUND
    # code -- never a body that distinguishes "foreign" from
    # "missing", so runs cannot be enumerated.
    client = _app()
    run_id = envelope(_ingest(client), status=201)["run_id"]
    stranger = auth(REVIEWER1)
    for response in (
        client.get("/api/v1/ocr/runs/%s" % run_id, headers=stranger),
        client.post(
            "/api/v1/ocr/runs/%s/correction" % run_id,
            json={"corrected_text": "x", "reason": "r"},
            headers=stranger),
        client.post("/api/v1/ocr/runs/%s/analyze" % run_id,
                    headers=stranger),
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"
    # The owner is unaffected throughout.
    assert envelope(client.get(
        "/api/v1/ocr/runs/%s" % run_id,
        headers=auth(READER)))["run_id"] == run_id


def test_cross_user_observation_read_is_not_found():
    client = _app()
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": "citric acid"},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    # Analyzed by the owner first, so a stranger 404 can only mean
    # ownership isolation (not "not yet analyzed").
    assert envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))["status"] == "provisional"
    stranger = auth(REVIEWER1)
    for path in (
        "/api/v1/observations/%s" % observation_id,
        "/api/v1/observations/%s/verification" % observation_id,
        "/api/v1/observations/%s/candidates" % observation_id,
    ):
        response = client.get(path, headers=stranger)
        assert response.status_code == 404, (path, response.text)
        assert response.json()["error"]["code"] == "NOT_FOUND"
    response = client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=stranger)
    assert response.status_code == 404, response.text
    assert envelope(client.get(
        "/api/v1/observations/%s" % observation_id,
        headers=auth(READER)))["observation"][
            "observation_id"] == observation_id


def test_unknown_provider_is_422_and_failing_provider_is_503():
    failing = FakeOCRProvider(failures=["doc-bad"], name="bad")
    client = _app(providers={"bad": failing})
    unknown = client.post(
        "/api/v1/ocr/runs",
        json={"document_id": "doc-x", "provider": "nope"},
        headers=auth(READER))
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "VALIDATION_ERROR"
    broken = client.post(
        "/api/v1/ocr/runs",
        json={"document_id": "doc-bad", "provider": "bad"},
        headers=auth(READER))
    assert broken.status_code == 503
    assert broken.json()["error"]["code"] == (
        "OCR_PROVIDER_UNAVAILABLE")

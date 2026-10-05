"""API security tests: spoofing, leakage, injection, size bounds."""

from app.tests.api.helpers import READER, REVIEWER1, auth, envelope, make_app

client, _ = make_app()


def test_reviewer_identity_cannot_be_spoofed():
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": "citric acid"},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    analyzed = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    assert analyzed["review_id"] is not None
    review_id = analyzed["review_id"]
    envelope(client.post("/api/v1/reviews/%s/claim" % review_id,
                         headers=auth(REVIEWER1)))
    # No reviewer/actor field is accepted anywhere: extra keys fail.
    spoofed = client.post(
        "/api/v1/reviews/%s/decision" % review_id,
        json={"decision": "reject_identity", "reason": "x",
              "reviewer": "human:owner", "actor": "human:owner"},
        headers=auth(REVIEWER1))
    assert spoofed.status_code == 422
    detail = envelope(client.get("/api/v1/reviews/%s" % review_id,
                                 headers=auth(READER)))
    assert detail["review"]["reviewer"] == "human:reviewer1"


def test_client_cannot_set_verified_status_directly():
    envelope(client.post(
        "/api/v1/observations", json={"raw_text": "Water"},
        headers=auth(READER)), status=201)
    payload = {
        "raw_text": "Water",
        "status": "verified",
        "verification_status": "verified",
        "match_status": "exact_match",
    }
    response = client.post("/api/v1/observations", json=payload,
                           headers=auth(READER))
    assert response.status_code in (201, 422)
    if response.status_code == 201:
        for item in response.json()["data"]:
            assert "match_status" not in item
            assert "verification_status" not in item


def test_no_service_role_or_secret_leakage():
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": "Citric Acid (E330)"},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    bodies = [
        client.get("/api/v1/observations/%s" % observation_id,
                   headers=auth(READER)).text,
        client.get("/api/v1/observations/%s/candidates" % observation_id,
                   headers=auth(READER)).text,
        client.get("/api/v1/observations/%s/verification" % observation_id,
                   headers=auth(READER)).text,
        client.get("/api/v1/reviews/pending", headers=auth(READER)).text,
        client.get("/openapi.json").text,
    ]
    for body in bodies:
        lowered = body.lower()
        assert "service_role" not in lowered
        assert "supabase_service_role_key" not in lowered
        assert "database_url" not in lowered
        assert "dev_api_tokens" not in lowered


def test_sql_injection_payload_stays_data():
    payload = "x'; DROP TABLE claims; --"
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": payload},
        headers=auth(READER)), status=201)
    assert created[0]["raw_text"] == payload
    detail = envelope(client.get(
        "/api/v1/observations/%s" % created[0]["observation_id"],
        headers=auth(READER)))
    assert detail["observation"]["raw_text"] == payload
    listed = envelope(client.get("/api/v1/reviews/pending",
                                 headers=auth(READER)))
    assert isinstance(listed, list)


def test_oversized_request_rejected():
    response = client.post(
        "/api/v1/observations", json={"raw_text": "y" * 5001},
        headers=auth(READER))
    assert response.status_code == 422
    response = client.post(
        "/api/v1/reviews/REV-0001/decision",
        json={"decision": "reject_identity", "reason": "z" * 2001},
        headers=auth(REVIEWER1))
    assert response.status_code in (404, 422)


def test_error_envelope_never_leaks_internals():
    response = client.get(
        "/api/v1/observations/00000000-0000-0000-0000-000000000000",
        headers=auth(READER))
    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"error", "meta"}
    assert set(payload["error"]) == {"code", "message", "details"}
    assert "Traceback" not in response.text
    assert "asyncpg" not in response.text.lower()
    assert "sqlalchemy" not in response.text.lower()


def test_request_id_echoed_on_errors():
    response = client.get("/api/v1/observations/00000000-0000-0000-0000-000000000000",
                          headers=auth(READER))
    assert response.headers["X-Request-ID"] == (
        response.json()["meta"]["request_id"])
    custom = client.get("/api/v1/reviews/pending",
                        headers={**auth(READER),
                                 "X-Request-ID": "test-correlation-1"})
    assert custom.headers["X-Request-ID"] == "test-correlation-1"


def test_openapi_documents_auth_and_operations():
    spec = client.get("/openapi.json").json()
    assert "/api/v1/observations" in spec["paths"]
    assert "/api/v1/reviews/pending" in spec["paths"]
    assert "/api/v1/reviews/{review_id}/decision" in spec["paths"]
    decision_op = spec["paths"]["/api/v1/reviews/{review_id}/decision"]["post"]
    codes = {str(s) for s in decision_op["responses"]}
    assert {"200", "401", "403", "404", "409", "422"} <= codes

"""Authentication boundary tests (no faked successes).

Every assertion exercises the real dependency: missing, malformed,
unknown, and overlong credentials fail; the role gate distinguishes
reviewers from readers.
"""

from app.tests.api.helpers import REVIEWER1, READER, auth, envelope, make_app

client, _ = make_app()


def test_missing_credentials_rejected_with_envelope():
    response = client.get("/api/v1/reviews/pending")
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert payload["meta"]["api_version"] == "v1"
    assert "request_id" in payload["meta"]
    assert response.headers["X-Request-ID"] == payload["meta"]["request_id"]


def test_malformed_credentials_rejected():
    for header in (
        {"Authorization": "Bearer"},
        {"Authorization": "Token abc"},
        {"Authorization": "Bearer "},
    ):
        response = client.get("/api/v1/reviews/pending", headers=header)
        assert response.status_code == 401, header


def test_unknown_token_rejected():
    response = client.get("/api/v1/reviews/pending",
                          headers=auth("no-such-token"))
    assert response.status_code == 401


def test_overlong_token_rejected():
    response = client.get("/api/v1/reviews/pending",
                          headers=auth("x" * 600))
    assert response.status_code == 401


def test_reader_can_read_but_not_review():
    data = envelope(client.get("/api/v1/reviews/pending",
                               headers=auth(READER)))
    assert data == []
    response = client.post("/api/v1/reviews/REV-0001/claim",
                           headers=auth(READER))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_reviewer_passes_role_gate_to_404():
    response = client.post("/api/v1/reviews/REV-9999/claim",
                           headers=auth(REVIEWER1))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

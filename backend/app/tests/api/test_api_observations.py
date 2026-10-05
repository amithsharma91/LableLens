"""Observation endpoint tests (raw text preserved verbatim)."""

import uuid

from app.tests.api.helpers import READER, auth, envelope, make_app

client, _ = make_app()


def _create(text, **kwargs):
    payload = {"raw_text": text}
    payload.update(kwargs)
    return client.post("/api/v1/observations", json=payload,
                       headers=auth(READER))


def test_create_multi_ingredient_text():
    data = envelope(_create("Sodlum Benzoate, Water"), status=201)
    assert len(data) == 2
    assert data[0]["raw_text"] == "Sodlum Benzoate"
    assert data[1]["raw_text"] == "Water"
    assert data[0]["normalized_text"] == "sodlum benzoate"
    assert data[0]["scan_id"] == data[1]["scan_id"]


def test_raw_observation_never_corrected():
    data = envelope(_create("Sodlum Benzoate"), status=201)
    assert data[0]["raw_text"] == "Sodlum Benzoate"
    detail = envelope(client.get(
        "/api/v1/observations/%s" % data[0]["observation_id"],
        headers=auth(READER)))
    assert detail["observation"]["raw_text"] == "Sodlum Benzoate"


def test_retrieve_unknown_observation():
    response = client.get("/api/v1/observations/%s" % uuid.uuid4(),
                          headers=auth(READER))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_empty_and_oversized_text_rejected():
    assert _create("").status_code == 422
    assert _create("   ").status_code in (201, 422)
    assert _create("x" * 5001).status_code == 422


def test_malformed_uuid_path_rejected():
    response = client.get("/api/v1/observations/not-a-uuid",
                          headers=auth(READER))
    assert response.status_code == 422


def test_idempotent_create_with_client_id():
    client_id = str(uuid.uuid4())
    first = envelope(_create("Citric Acid", observation_id=client_id),
                     status=201)
    second = envelope(_create("Citric Acid", observation_id=client_id),
                      status=201)
    assert first[0]["observation_id"] == client_id
    assert second[0]["observation_id"] == client_id


def test_analyze_and_candidates_flow():
    created = envelope(_create("Citric Acid (E330)"), status=201)
    observation_id = created[0]["observation_id"]
    before = client.get(
        "/api/v1/observations/%s/candidates" % observation_id,
        headers=auth(READER))
    assert before.status_code == 404
    result = envelope(client.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    assert result["status"] == "verified"
    assert result["identity_confidence"] == "HIGH"
    assert result["decision_id"]
    # The resolution projection is filled from Resolution.to_dict():
    # entity/match_status/alternatives must not be silently empty.
    resolution = result["resolution"]
    assert resolution["normalized_text"] == "citric acid E 330"
    assert resolution["match_status"] == "exact_match"
    assert resolution["normalization_id"]
    assert resolution["entity"]["candidate_ref"] == "T11-001"
    assert resolution["alternatives"] == []
    candidates = envelope(client.get(
        "/api/v1/observations/%s/candidates" % observation_id,
        headers=auth(READER)))
    assert candidates["match_status"] == "exact_match"
    assert candidates["entity"]["candidate_ref"] == "T11-001"
    assert candidates["alternatives"] == []
    assert candidates["raw_text"] == "Citric Acid (E330)"
    assert candidates["normalized_text"] == "citric acid E 330"

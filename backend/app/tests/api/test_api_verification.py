"""Verification/claim/evidence response tests."""

import uuid

from app.tests.api.helpers import READER, auth, envelope, make_app

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


def test_verified_detail_distinguishes_layers():
    observation_id, _ = _analyze("Citric Acid (E330)")
    detail = envelope(client.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=auth(READER)))
    assert detail["status"] == "verified"
    assert detail["identity_confidence"] == "HIGH"
    assert detail["rules_version"] == "1.0.0"
    assert detail["snapshot_version"] == "canonical_v1"
    assert len(detail["gate_results"]) == 7
    assert all("rule_id" in g and "result" in g for g in detail["gate_results"])
    by_field = {c["claim"]["field"]: c for c in detail["claims"]}
    assert by_field["identity"]["claim"]["status"] == "verified"
    assert by_field["formula"]["claim"]["status"] == "verified"
    formula_evidence = by_field["formula"]["evidence"]
    assert formula_evidence
    names = {e["source_name"] for e in formula_evidence}
    assert "SNAPSHOT:canonical_v1" in names
    assert all(e["response_hash"] is None or e["response_hash"]
               for e in formula_evidence)
    assert len(detail["history"]) == 1


def test_unknown_decision_shape():
    observation_id, result = _analyze("mystery blend")
    assert result["status"] == "unknown"
    detail = envelope(client.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=auth(READER)))
    assert detail["status"] == "unknown"
    assert detail["identity_confidence"] == "UNKNOWN"


def test_ambiguous_candidates_preserved():
    from app.services.entity_resolver import InMemoryRegistry, RegistryEntry

    from app.tests.api.helpers import (
        SNAPSHOT_PATH,
        register_snapshot_entities,
        verifier,
    )
    from app.main import create_app
    from app.repositories.memory import MemoryUnitOfWork
    from app.services.verification.adapters.snapshot import SnapshotAdapter
    from fastapi.testclient import TestClient

    registry = InMemoryRegistry(
        [
            RegistryEntry(
                ref="T11-A", preferred_name="test entry one",
                display_name="Test Entry One (api fixture)",
                aliases=["test shared alias"],
                entity_class="material",
                source="synthetic_test_fixture",
            ),
            RegistryEntry(
                ref="T11-B", preferred_name="test entry two",
                display_name="Test Entry Two (api fixture)",
                aliases=["test shared alias"],
                entity_class="material",
                source="synthetic_test_fixture",
            ),
        ],
        registry_id="api_ambiguous_registry",
        version="t11",
    )
    application = create_app(
        repos=register_snapshot_entities(MemoryUnitOfWork()),
        verifier=verifier(), registry=registry,
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))])
    local = TestClient(application)
    created = envelope(local.post(
        "/api/v1/observations", json={"raw_text": "test shared alias"},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    envelope(local.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER)))
    candidates = envelope(local.get(
        "/api/v1/observations/%s/candidates" % observation_id,
        headers=auth(READER)))
    assert candidates["match_status"] == "ambiguous"
    assert candidates["entity"] is None
    assert len(candidates["alternatives"]) == 2
    assert candidates["alternatives"][0]["candidate_ref"] == "T11-A"


def test_claim_endpoint_and_unknown_claim():
    observation_id, _ = _analyze("Citric Acid (E330)")
    detail = envelope(client.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=auth(READER)))
    claim_id = detail["claims"][0]["claim"]["claim_id"]
    single = envelope(client.get("/api/v1/claims/%s" % claim_id,
                                 headers=auth(READER)))
    assert single["claim"]["claim_id"] == claim_id
    assert single["evidence"]
    missing = client.get("/api/v1/claims/%s" % uuid.uuid4(),
                         headers=auth(READER))
    assert missing.status_code == 404


def test_verification_requires_analysis():
    created = envelope(client.post(
        "/api/v1/observations", json={"raw_text": "Water"},
        headers=auth(READER)), status=201)
    response = client.get(
        "/api/v1/observations/%s/verification" % created[0]["observation_id"],
        headers=auth(READER))
    assert response.status_code == 404


def test_unregistered_entity_is_rejected_before_persisting():
    """The claim FK is enforced in application code, not by surprise.

    Entity registration is a service-role import with no route, so an
    analysis whose evidence names an unknown canonical entity fails
    closed with 422 -- it never writes a claim row with a dangling or
    silently dropped entity link.
    """
    from app.main import create_app
    from app.repositories.memory import MemoryUnitOfWork
    from app.tests.api.helpers import SNAPSHOT_PATH, registry, verifier
    from app.services.verification.adapters.snapshot import SnapshotAdapter
    from fastapi.testclient import TestClient

    application = create_app(
        repos=MemoryUnitOfWork(),  # no canonical entities registered
        verifier=verifier(), registry=registry(),
        adapters=[SnapshotAdapter(str(SNAPSHOT_PATH))])
    local = TestClient(application)
    created = envelope(local.post(
        "/api/v1/observations", json={"raw_text": "Citric Acid (E330)"},
        headers=auth(READER)), status=201)
    observation_id = created[0]["observation_id"]
    response = local.post(
        "/api/v1/observations/%s/analyze" % observation_id,
        headers=auth(READER))
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "ENTITY_NOT_FOUND"
    # Nothing was persisted: no partial claim rows survive the failure.
    assert local.get(
        "/api/v1/observations/%s/verification" % observation_id,
        headers=auth(READER)).status_code == 404

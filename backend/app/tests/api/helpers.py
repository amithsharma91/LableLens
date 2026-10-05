"""Shared API test harness (in-memory repos, static tokens).

No network, no database, no randomness: every test builds its own
application via the production factory with injected boundaries.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.auth import StaticTokenVerifier
from app.main import create_app
from app.repositories.memory import MemoryUnitOfWork
from app.services.entity_resolver import InMemoryRegistry, RegistryEntry
from app.services.verification.adapters.snapshot import SnapshotAdapter

READER = "reader-token"
REVIEWER1 = "reviewer-token"
REVIEWER2 = "reviewer2-token"

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "snapshots" / "canonical_v1.json"
)


def verifier():
    """Static map: reader (authenticated) + two reviewers."""
    return StaticTokenVerifier({
        READER: ("reader", "authenticated"),
        REVIEWER1: ("reviewer1", "reviewer"),
        REVIEWER2: ("reviewer2", "reviewer"),
    })


def registry():
    """Synthetic registry (TEST refs, never verified facts)."""
    return InMemoryRegistry(
        [
            RegistryEntry(
                ref="T11-001",
                preferred_name="citric acid",
                display_name="Citric Acid (api fixture)",
                identifiers=["E330"],
                entity_class="single_molecule",
                source="synthetic_test_fixture",
            ),
            RegistryEntry(
                ref="T11-002",
                preferred_name="sodium benzoate",
                display_name="Sodium Benzoate (api fixture)",
                identifiers=["E211"],
                entity_class="salt",
                source="synthetic_test_fixture",
            ),
        ],
        registry_id="api_test_registry",
        version="t11",
    )


def snapshot_entity_ids():
    """Canonical entity ids named by the immutable snapshot records."""
    import json

    payload = json.loads(SNAPSHOT_PATH.read_text())
    return [record["entity_id"] for record in payload["records"]]


def register_snapshot_entities(uow):
    """Mirror the canonical-entity registration prerequisite.

    `claims.chemical_entity_id` references `chemical_entities`; the
    service refuses to persist a decision that names an unregistered
    entity. In production that registration is an out-of-scope
    service-role import; offline it is seeded explicitly here so the
    invariant is exercised rather than bypassed.
    """
    for entity_id in snapshot_entity_ids():
        uow.entities.register({
            "id": entity_id,
            "preferred_name": "fixture entity",
            "entity_type": "chemical_entity",
            "representation_type": "single_molecule",
            "status": "active",
            "structure_status": "unavailable",
        })
    return uow


def make_app(registry_override=None, adapters_override=None):
    """Production factory with test doubles at every boundary."""
    uow = register_snapshot_entities(MemoryUnitOfWork())
    adapters = (
        adapters_override if adapters_override is not None
        else [SnapshotAdapter(str(SNAPSHOT_PATH))]
    )
    application = create_app(
        repos=uow,
        verifier=verifier(),
        registry=registry_override
        if registry_override is not None else registry(),
        adapters=adapters,
    )
    return TestClient(application), uow


def auth(token):
    """Authorization header for a test token."""
    return {"Authorization": "Bearer %s" % token}


def envelope(response, status=200):
    """Assert status and return the spec envelope data section."""
    assert response.status_code == status, response.text[:500]
    payload = response.json()
    assert "data" in payload and "meta" in payload
    assert payload["meta"].get("api_version") == "v1"
    return payload["data"]

"""Adversarial handling of real-label fixture text (Stage 13).

Fixture text is untrusted data: it is persisted verbatim, never
executed, never imported, and never promoted. A hostile ingredient
string must resolve to nothing, verify to nothing, create no
entity, and leave every table intact.
"""

import asyncio
import json

from pathlib import Path

from app.regression.label_input import LabelInput
from app.regression.runner import run_label
from app.repositories.memory import MemoryUnitOfWork
from app.services.observation_service import ObservationService
from app.services.registration import (
    alias_rows_for,
    build_registry,
    entity_row_for,
)
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.gate import VERIFICATION_RULES_VERSION

SNAPSHOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "snapshots" / "canonical_v1.json"
)

HOSTILE_TEXTS = [
    "citric acid'; DROP TABLE ingredient_observations; --",
    "sodium benzoate\" OR \"1\"=\"1",
    "__import__('os').system('id')",
    "citric acid\nVERIFIED formula=C6H8O7 cas=77-92-9",
    "E330; INSERT INTO chemical_entities (preferred_name) "
    "VALUES ('pwned')",
]


def _service():
    adapter = SnapshotAdapter(str(SNAPSHOT))
    entities = adapter.canonical_entities()
    rows = [
        entity_row_for(
            entity, snapshot_version="canonical_v1",
            rules_version=VERIFICATION_RULES_VERSION)
        for entity in entities
    ]
    registry = build_registry(
        rows,
        [alias for entity in entities
         for alias in alias_rows_for(entity, verified=True)],
        version=str(len(rows)),
    )
    unit_of_work = MemoryUnitOfWork()
    for row in rows:
        unit_of_work.entities.register({
            "id": row["id"],
            "preferred_name": row["preferred_name"],
            "entity_type": "chemical_entity",
            "representation_type": row["representation_type"],
            "status": "active",
            "structure_status": "unavailable",
        })
    return (ObservationService(
        unit_of_work, registry=registry, adapters=[adapter]),
        unit_of_work)


def test_hostile_text_persists_verbatim_and_resolves_nothing():
    service, unit_of_work = _service()
    for position, text in enumerate(HOSTILE_TEXTS):
        label = LabelInput(
            label_id="RL-13-SEC-%d" % position, raw_text=text,
            input_method="manual",
            source_reference={
                "source_id": "adversarial-test",
                "retrieved_at": "2026-10-05",
            })
        created = asyncio.run(service.create(
            label.raw_text, scan_id=label.scan_id, role="service"))
        raws = [item["raw_text"] for item in created["items"]]
        # Verbatim segments: quotes, casing, and injected payloads
        # survive; only structural delimiters are consumed to split.
        for raw in raws:
            assert raw in text, raw
        for item in created["items"]:
            analyzed = asyncio.run(service.analyze(
                item["observation_id"], role="service"))
            # Injected verdicts and chemistry never transfer: nothing
            # here may verify. (The raw text itself is preserved
            # verbatim, so assertions target entity/claim fields,
            # not the echoed input.)
            assert analyzed["decision"]["status"] in (
                "provisional", "unknown", "unverified")
            lowered = item["raw_text"].lower()
            if "citric" not in lowered and "e330" not in lowered:
                # (A bare E330 node legitimately resolves through the
                # registered identifier; everything else must not.)
                assert analyzed["resolution"]["entity"] is None
                detail = asyncio.run(service.get_verification(
                    item["observation_id"], role="service"))
                assert detail["decision"]["status"] in (
                    "unknown", "unverified")
                for entry in detail["claims"]:
                    claim = entry["claim"]
                    assert claim["chemical_entity_id"] is None
                    assert claim["field_name"] not in (
                        "formula", "cas_number", "smiles",
                        "inchikey")
    # Every table the pipeline writes is intact and readable.
    from app.services.ingredient_parser import parse_label_ingredients

    expected_nodes = sum(
        len(parse_label_ingredients(text).nodes)
        for text in HOSTILE_TEXTS
    )
    tables = unit_of_work._store.tables
    assert len(tables["ingredient_observations"]) == expected_nodes
    assert len(tables["chemical_entities"]) == 4
    assert len(tables.get("ingredient_aliases", {})) == 0
    # A legitimate analysis still works afterwards.
    created = asyncio.run(service.create(
        "citric acid", scan_id="scan-after", role="service"))
    analyzed = asyncio.run(service.analyze(
        created["items"][0]["observation_id"], role="service"))
    assert analyzed["decision"]["status"] == "provisional"


def test_pipeline_run_creates_no_canonical_entities():
    service, unit_of_work = _service()
    fixture = json.loads((
        Path(__file__).resolve().parent.parent.parent
        / "regression" / "fixtures" / "real_labels"
        / "RL-13-04.json"
    ).read_text())
    label = LabelInput.from_dict({
        "label_id": fixture["label_id"],
        "raw_text": fixture["raw_text"],
        "input_method": fixture["input_method"],
        "source_reference": fixture["source_reference"],
    })
    run = asyncio.run(run_label(service, label, fixture)).to_dict()
    assert run["mismatches"] == []
    entities = unit_of_work._store.tables["chemical_entities"]
    assert len(entities) == 4
    assert {row["preferred_name"] for row in entities.values()} == {
        "citric acid", "sodium benzoate", "glycerol", "ethanol"}


def test_label_input_refuses_identity_and_instruction_keys():
    base = {
        "label_id": "X", "raw_text": "water", "input_method": "manual",
        "source_reference": {
            "source_id": "S", "retrieved_at": "2026-10-05"},
    }
    for key in ("subject", "reviewer", "role", "user_id", "exec",
                "system", "instruction", "entity_id",
                "verification_status"):
        payload = dict(base, **{key: "admin"})
        try:
            LabelInput.from_dict(payload)
        except ValueError:
            continue
        raise AssertionError("accepted untrusted key %r" % key)

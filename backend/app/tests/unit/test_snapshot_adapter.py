"""Tests for the local canonical snapshot adapter.

Uses the real ``snapshots/canonical_v1.json`` for load/lookup
tests (genuine provenance) and synthetic temp files for rejection,
bounds, and security tests.
"""

import json
import socket
from pathlib import Path
from unittest import mock

import pytest

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.snapshot import (
    SnapshotAdapter,
    SnapshotError,
)

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "snapshots" / "canonical_v1.json"
)

CITRIC_ID = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"


def _resolution(text, identifier=None):
    return Resolution(
        raw_text=text, normalized_text=text.lower(), identifier=identifier
    )


def test_valid_snapshot_loads():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    assert adapter.snapshot_version == "canonical_v1"
    assert adapter.rules_version == "1.0.0"
    assert adapter.record_count == 4
    assert adapter.available is True


def test_name_lookup():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    hits = adapter.lookup_identity(_resolution("citric acid"))
    assert len(hits) == 1
    assert hits[0].entity.entity_id == CITRIC_ID
    assert hits[0].source.source_id == "PUBCHEM"
    assert hits[0].source.source_class == "A"


def test_identifier_lookup():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    hits = adapter.lookup_identity(_resolution("E330", identifier="E 330"))
    assert [h.entity.entity_id for h in hits] == [CITRIC_ID]


def test_unknown_entity_rejected_safely():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    assert adapter.lookup_identity(_resolution("xyz blend")) == []
    assert adapter.lookup_identity(_resolution("")) == []


def test_snapshot_version_preserved_on_records():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    hits = adapter.lookup_identity(_resolution("glycerol"))
    assert hits[0].entity.snapshot_version == "canonical_v1"


def _write_tmp(tmp_path, payload):
    target = tmp_path / "snap.json"
    if isinstance(payload, bytes):
        target.write_bytes(payload)
    else:
        target.write_text(payload)
    return target


def _base_record(**overrides):
    record = {
        "entity_id": "ENT-1",
        "preferred_name": "test substance",
        "entity_type": "chemical_entity",
        "representation_type": "single_molecule",
        "verification_status": "verified",
        "provenance": {
            "source_id": "SYNTH",
            "record_locator": "synth",
            "source_version": "s",
            "retrieved_at": "2026-10-05",
            "license_note": "synthetic",
            "source_class": "A",
        },
    }
    record.update(overrides)
    return record


def _minimal_record(**overrides):
    return {
        "snapshot_version": "test_v1",
        "verification_rule_version": "1.0.0",
        "records": [_base_record(**overrides)],
    }


def test_malformed_snapshots_rejected(tmp_path):
    good = _minimal_record()
    bad_payloads = [
        b"\x00\x01 not json",
        json.dumps(["not", "an", "object"]),
        json.dumps({"no_records": []}),
        json.dumps({"snapshot_version": "x", "records": "nope"}),
        json.dumps(
            {
                "snapshot_version": "x",
                "verification_rule_version": "1.0.0",
                "records": [{"incomplete": True}],
            }
        ),
        json.dumps(
            {
                "snapshot_version": "x",
                "verification_rule_version": "1.0.0",
                "records": [
                    dict(good["records"][0], representation_type="vapor")
                ],
            }
        ),
        json.dumps(
            {
                "snapshot_version": "x",
                "verification_rule_version": "1.0.0",
                "records": [
                    dict(good["records"][0], verification_status="rumor")
                ],
            }
        ),
    ]
    for payload in bad_payloads:
        with pytest.raises(SnapshotError):
            SnapshotAdapter(_write_tmp(tmp_path, payload))


def test_mixture_with_smiles_rejected(tmp_path):
    record = _base_record(
        representation_type="mixture",
        fields={"smiles": {"value": "CCC"}},
    )
    payload = json.dumps(
        {
            "snapshot_version": "x",
            "verification_rule_version": "1.0.0",
            "records": [record],
        }
    )
    with pytest.raises(SnapshotError):
        SnapshotAdapter(_write_tmp(tmp_path, payload))


def test_bounds_enforced(tmp_path):
    huge = {"snapshot_version": "x" * 5000, "records": []}
    with pytest.raises(SnapshotError):
        SnapshotAdapter(
            _write_tmp(tmp_path, json.dumps(huge)),
        )
    big = "y" * 3000
    record = _base_record(preferred_name=big)
    payload = json.dumps(
        {
            "snapshot_version": "x",
            "verification_rule_version": "1.0.0",
            "records": [record],
        }
    )
    with pytest.raises(SnapshotError):
        SnapshotAdapter(_write_tmp(tmp_path, payload))
    oversized = _write_tmp(tmp_path, b" " * (1_048_576 + 8))
    with pytest.raises(SnapshotError):
        SnapshotAdapter(oversized)


def test_malicious_strings_remain_data(tmp_path):
    record = _base_record(
        preferred_name="__import__('os').system('rm -rf /')"
    )
    payload = json.dumps(
        {
            "snapshot_version": "x",
            "verification_rule_version": "1.0.0",
            "records": [record],
        }
    )
    adapter = SnapshotAdapter(_write_tmp(tmp_path, payload))
    assert adapter.lookup_identity(_resolution("water")) == []
    assert adapter.lookup_identity(
        _resolution("'; DROP TABLE claims; --")
    ) == []


def test_no_network_dependency():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    with mock.patch(
        "socket.socket", side_effect=AssertionError("network used")
    ):
        assert socket.socket is not None  # patch target exists
        hits = adapter.lookup_identity(_resolution("ethanol"))
    assert len(hits) == 1
    assert hits[0].entity.preferred_name == "ethanol"


def test_lookup_order_deterministic():
    adapter = SnapshotAdapter(SNAPSHOT_PATH)
    first = [h.entity.entity_id for h in adapter.lookup_identity(
        _resolution("citric acid")
    )]
    second = [h.entity.entity_id for h in adapter.lookup_identity(
        _resolution("citric acid")
    )]
    assert first == second

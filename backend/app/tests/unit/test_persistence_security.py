"""Persistence security tests (no live database needed).

Proves: no credentials flow into stored rows, hostile strings stay
data through serialization, and repository authorization hooks
reject unauthorized roles where testable without a database.
"""

from app.repositories.memory import MemoryVerificationRepository
from app.repositories.serialize import (
    decision_to_row,
    validate_no_secrets,
)
from app.services.verification.models import VerificationDecision


def _decision():
    return VerificationDecision(
        status="unknown", identity_confidence="UNKNOWN", gate_results=(),
        claims=(), evidence=(), source_refs=(), reason="no source",
        warnings=(), rules_version="1.0.0", snapshot_version="",
        entity_id=None,
    )


def test_service_role_key_never_serialized():
    row = decision_to_row(_decision(), candidate_key="k|")
    payload = str(row)
    for token in ("service_role", "SUPABASE_SERVICE_ROLE_KEY", "sk-"):
        assert token not in payload
    validate_no_secrets(row)


def test_credentials_rejected_before_storage():
    for bad in (
        {"api_key": "abc"},
        {"nested": {"service_role_key": "x"}},
        {"token": "sk-live-123"},
        {"password": "hunter2"},
    ):
        try:
            validate_no_secrets(bad)
        except ValueError:
            continue
        raise AssertionError("accepted %r" % (bad,))


def test_reviewer_strings_treated_as_data():
    evil = "human:ana'); DROP TABLE reviews; --"
    row = {
        "id": "REV-0001", "candidate_key": "k", "raw_text": "r",
        "normalized_text": "n", "identifier": None, "resolution": {},
        "verification_status": "queued", "evidence_context": {},
        "evidence_hash": "h", "priority": 0, "status": "queued",
        "reviewer": evil,
    }
    validate_no_secrets(row)
    assert row["reviewer"] == evil


def test_malicious_reason_survives_serialization():
    row = decision_to_row(_decision(), candidate_key="k|")
    row["reason"] = "x'; DELETE FROM claims WHERE '1'='1"
    validate_no_secrets(row)
    assert "DELETE FROM" in row["reason"]


async def test_unauthorized_writes_rejected():
    repo = MemoryVerificationRepository()
    row = decision_to_row(_decision(), candidate_key="k|")
    for role in ("anon", "authenticated", "", "admin"):
        try:
            await repo.save_decision(dict(row), role=role)
        except PermissionError:
            continue
        raise AssertionError("role %r wrote" % role)


async def test_unauthorized_reads_rejected():
    repo = MemoryVerificationRepository()
    try:
        await repo.list_decisions(role="anon")
    except PermissionError:
        return
    raise AssertionError("anon read allowed")


async def test_service_role_writes_and_reads():
    repo = MemoryVerificationRepository()
    row = decision_to_row(_decision(), candidate_key="k|")
    saved = await repo.save_decision(dict(row), role="service")
    assert (await repo.get_decision(saved, role="service"))["id"] == saved
    assert (await repo.get_decision(saved, role="authenticated"))["id"] == saved

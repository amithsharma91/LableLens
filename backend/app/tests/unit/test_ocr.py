"""OCR boundary unit tests (Stage 16).

Covers the OCRResult contract, provider behavior, the run/correction
model, failure modes, confidence separation, idempotency, and
provider independence -- all against memory repositories and the
frozen downstream pipeline.
"""

import asyncio

import pytest

from app.repositories.memory import MemoryUnitOfWork
from app.services import errors as service_errors
from app.services.ocr_provider import (
    FakeOCRProvider,
    OCRDocument,
    OCRResult,
    ProviderFailure,
)
from app.services.ocr_service import (
    OCRService,
    observation_id_for_run,
    scan_id_for_run,
)
from app.services.registration import (
    alias_rows_for,
    build_registry,
    entity_row_for,
)
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.gate import VERIFICATION_RULES_VERSION
from pathlib import Path

SNAPSHOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "snapshots" / "canonical_v1.json"
)


def _service(providers=None):
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
    service = OCRService(
        unit_of_work, registry=registry, adapters=[adapter],
        providers=providers)
    return service, unit_of_work


def _result(document_id="doc-1", raw_text="citric acid", **overrides):
    payload = {
        "document_id": document_id,
        "provider": "fake-test",
        "raw_text": raw_text,
    }
    payload.update(overrides)
    return OCRResult(**payload)


def _run(coro):
    return asyncio.run(coro)


# -- OCRResult contract ------------------------------------------------------


def test_result_requires_document_provider_and_text_type():
    with pytest.raises(ValueError):
        OCRResult(document_id=" ", provider="p", raw_text="x")
    with pytest.raises(ValueError):
        OCRResult(document_id="d", provider=" ", raw_text="x")
    with pytest.raises(ValueError):
        OCRResult(document_id="d", provider="p", raw_text=None)
    with pytest.raises(ValueError):
        OCRDocument(document_id=" ")


def test_empty_raw_text_is_representable():
    result = _result(raw_text="")
    assert result.raw_text == ""


def test_confidence_bounds_are_enforced():
    assert _result(ocr_confidence=0.0).ocr_confidence == 0.0
    assert _result(ocr_confidence=1.0).ocr_confidence == 1.0
    for bad in (-0.1, 1.1, float("nan"), True, "high"):
        with pytest.raises(ValueError):
            _result(ocr_confidence=bad)


def test_result_is_immutable():
    result = _result()
    with pytest.raises(Exception):
        result.raw_text = "changed"


def test_metadata_must_be_mappings():
    with pytest.raises(ValueError):
        _result(page_metadata=["p1"])
    with pytest.raises(ValueError):
        _result(source_reference="somewhere")
    result = _result(
        page_metadata={"page": 1}, source_reference={"scan": "s"})
    assert result.page_metadata == {"page": 1}


# -- provider behavior ---------------------------------------------------------


def test_fake_provider_returns_canned_result():
    provider = FakeOCRProvider({
        "doc-1": _result(document_id="doc-1", raw_text="water")})
    result = _run(provider.extract(OCRDocument(document_id="doc-1")))
    assert result.raw_text == "water"
    assert provider.calls == ["doc-1"]


def test_fake_provider_unknown_document_fails():
    provider = FakeOCRProvider()
    with pytest.raises(ProviderFailure):
        _run(provider.extract(OCRDocument(document_id="nope")))


def test_fake_provider_registered_failure_fails():
    provider = FakeOCRProvider(
        {"doc-1": _result(document_id="doc-1")},
        failures=["doc-1"])
    with pytest.raises(ProviderFailure):
        _run(provider.extract(OCRDocument(document_id="doc-1")))


def test_provider_result_is_relabeled_to_the_runner():
    provider = FakeOCRProvider(
        {"doc-1": _result(
            document_id="doc-1", provider="someone-else")},
        name="fake-test")
    result = _run(provider.extract(OCRDocument(document_id="doc-1")))
    assert result.provider == "fake-test"


# -- run persistence -------------------------------------------------------------


def test_registered_run_is_immutable_and_complete():
    service, unit_of_work = _service()
    run = _run(service.register_result(
        _result(raw_text="Sodium Benzoate"), role="service"))
    assert run["raw_text"] == "Sodium Benzoate"
    assert run["provider"] == "fake-test"
    stored = unit_of_work._store.tables["ocr_runs"][run["id"]]
    assert stored["raw_text"] == "Sodium Benzoate"
    assert "citric" not in json_keys(stored)


def json_keys(mapping):
    return ",".join(sorted(mapping))


def test_run_carries_no_chemistry_or_evidence():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="citric acid"), role="service"))
    forbidden = (
        "normalized", "entity", "candidate", "formula", "smiles",
        "inchi", "cas", "evidence", "claim", "verified",
    )
    for key in run:
        assert key not in forbidden, key
    for key in forbidden:
        assert key not in run


def test_unknown_provider_is_rejected_before_any_write():
    service, unit_of_work = _service()
    with pytest.raises(service_errors.ServiceError):
        _run(service.extract_with(
            "no-such-provider", "doc-1", role="service"))
    assert unit_of_work._store.tables.get("ocr_runs", {}) == {}


def test_provider_failure_persists_nothing():
    provider = FakeOCRProvider(failures=["doc-9"])
    service, unit_of_work = _service(providers={"p": provider})
    with pytest.raises(ProviderFailure):
        _run(service.extract_with("p", "doc-9", role="service"))
    assert unit_of_work._store.tables.get("ocr_runs", {}) == {}
    assert provider.calls == ["doc-9"]


def test_provider_exception_becomes_provider_failure():
    class Broken:
        name = "broken"

        async def extract(self, document):
            raise RuntimeError("boom")

    service, unit_of_work = _service(providers={"broken": Broken()})
    with pytest.raises(ProviderFailure):
        _run(service.extract_with("broken", "doc-1", role="service"))
    assert unit_of_work._store.tables.get("ocr_runs", {}) == {}


def test_extract_with_registered_provider_persists():
    provider = FakeOCRProvider({
        "doc-2": _result(document_id="doc-2", raw_text="glycerol")})
    service, _ = _service(providers={"p": provider})
    run = _run(service.extract_with("p", "doc-2", role="service"))
    assert run["raw_text"] == "glycerol"
    assert run["document_id"] == "doc-2"


# -- correction boundary -----------------------------------------------------------


def test_correction_keeps_raw_and_is_auditable():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="Sodium Benzoatc (E211)"), role="service"))
    correction = _run(service.correct_run(
        run["id"], corrected_text="Sodium Benzoate (E211)",
        reason="ocr substitution c->e", actor="human:reviewer-1",
        role="service"))
    assert correction["corrected_text"] == "Sodium Benzoate (E211)"
    assert correction["reason"] == "ocr substitution c->e"
    assert correction["actor"] == "human:reviewer-1"
    stored = _run(service.describe(run["id"], role="service"))
    assert stored["run"]["raw_text"] == "Sodium Benzoatc (E211)"
    assert stored["correction"]["corrected_text"] == (
        "Sodium Benzoate (E211)")


def test_correction_refusals():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="x"), role="service"))
    with pytest.raises(service_errors.ServiceError):
        _run(service.correct_run(
            run["id"], corrected_text=" ", reason="r",
            actor="human:a", role="service"))
    with pytest.raises(service_errors.ServiceError):
        _run(service.correct_run(
            run["id"], corrected_text="y", reason=" ",
            actor="human:a", role="service"))
    with pytest.raises(service_errors.ServiceError):
        _run(service.correct_run(
            run["id"], corrected_text="y", reason="r",
            actor=" ", role="service"))
    with pytest.raises(service_errors.NotFoundError):
        _run(service.correct_run(
            "00000000-0000-4000-8000-000000000000",
            corrected_text="y", reason="r", actor="human:a",
            role="service"))
    _run(service.correct_run(
        run["id"], corrected_text="y", reason="r",
        actor="human:a", role="service"))
    with pytest.raises(service_errors.ServiceError):
        _run(service.correct_run(
            run["id"], corrected_text="z", reason="again",
            actor="human:a", role="service"))


# -- failure modes -------------------------------------------------------------------


def test_empty_ocr_returns_warning_outcome_without_crash():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text=""), role="service"))
    observed = _run(service.observe(run["id"], role="service"))
    assert observed["items"] == []
    assert "empty_ocr_text" in observed["warnings"]
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    assert analyzed["items"] == []
    assert analyzed["warnings"]


def test_whitespace_only_ocr_returns_warning_outcome():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="   \n  "), role="service"))
    observed = _run(service.observe(run["id"], role="service"))
    assert observed["items"] == []
    assert observed["warnings"]


def test_malformed_ocr_never_crashes_and_invents_nothing():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="(((citric acid, E330"), role="service"))
    observed = _run(service.observe(run["id"], role="service"))
    assert observed["items"]
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    for item in analyzed["items"]:
        assert item["resolution"]["entity"] is None or (
            item["decision"]["status"] in (
                "provisional", "unknown", "unverified"))


def test_multiline_duplicated_mixed_whitespace_ocr():
    service, _ = _service()
    raw = ("Sodium  Benzoate\n\nSodium Benzoate\t(E211)\n"
           "   water   water")
    run = _run(service.register_result(
        _result(raw_text=raw), role="service"))
    observed = _run(service.observe(run["id"], role="service"))
    assert observed["items"]
    raws = [item["raw_text"] for item in observed["items"]]
    assert any("Sodium" in text for text in raws)


# -- OCR -> parser -> normalizer -> resolver ----------------------------------


def test_ocr_text_flows_through_parser_normalizer_resolver():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="Sodium Benzoate"), role="service"))
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    assert len(analyzed["items"]) == 1
    item = analyzed["items"][0]
    assert item["raw_text"] == "Sodium Benzoate"
    assert item["resolution"]["normalized_text"] == "sodium benzoate"
    assert item["resolution"]["match_status"] == "exact_match"
    assert item["decision"]["status"] == "provisional"


def test_corrupted_identifier_never_verifies():
    # The intact name still resolves to a candidate, but the
    # corrupted code blocks verification: partial agreement is not
    # agreement. Nothing is invented and nothing is verified.
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="Glycerol (E42Z)"), role="service"))
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    item = analyzed["items"][0]
    assert item["resolution"]["entity"] is not None
    assert item["decision"]["status"] == "unverified"
    assert item["decision"]["identity_confidence"] == "UNKNOWN"


def test_corrupted_name_stays_unresolved_until_corrected():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="Sodium Benzoatc (E211)"), role="service"))
    before = _run(service.analyze_run(run["id"], role="service"))
    # The intact identifier still yields a candidate, but the
    # corrupted name blocks verification.
    assert before["items"][0]["decision"]["status"] == "unverified"
    assert before["items"][0]["decision"][
        "identity_confidence"] == "UNKNOWN"
    _run(service.correct_run(
        run["id"], corrected_text="Sodium Benzoate (E211)",
        reason="ocr substitution", actor="human:r", role="service"))
    after = _run(service.analyze_run(run["id"], role="service"))
    assert after["corrected"] is True
    item = after["items"][0]
    assert item["raw_text"] == "Sodium Benzoate (E211)"
    assert item["resolution"]["match_status"] == "exact_match"
    # The system never fixed this itself: the raw observation rows
    # still carry the corrupted text.
    described = _run(service.describe(run["id"], role="service"))
    raws = [row["raw_text"] for row in described["observations"]
            if "Benzoatc" in (row["raw_text"] or "")]
    assert raws


# -- confidence separation ------------------------------------------------------------


def test_low_ocr_confidence_cannot_suppress_verification():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="Sodium Benzoate (E211)",
                ocr_confidence=0.05),
        role="service"))
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    assert analyzed["items"][0]["decision"]["status"] == "verified"
    assert analyzed["items"][0]["decision"][
        "identity_confidence"] == "HIGH"


def test_high_ocr_confidence_cannot_create_identity():
    service, _ = _service()
    run = _run(service.register_result(
        _result(raw_text="mystery goo", ocr_confidence=0.99),
        role="service"))
    analyzed = _run(service.analyze_run(run["id"], role="service"))
    assert analyzed["items"][0]["decision"]["status"] == "unknown"
    assert analyzed["items"][0]["decision"][
        "identity_confidence"] == "UNKNOWN"


def test_observation_rows_carry_ocr_confidence_verbatim():
    service, unit_of_work = _service()
    run = _run(service.register_result(
        _result(raw_text="water", ocr_confidence=0.42),
        role="service"))
    observed = _run(service.observe(run["id"], role="service"))
    rows = unit_of_work._store.tables["ingredient_observations"]
    assert rows[observed["items"][0]["observation_id"]][
        "ocr_confidence"] == 0.42
    assert rows[observed["items"][0]["observation_id"]][
        "ocr_run_id"] == run["id"]


# -- idempotency + provider independence -------------------------------------------


def test_observe_and_rerun_are_stable():
    service, unit_of_work = _service()
    run = _run(service.register_result(
        _result(raw_text="citric acid, water"), role="service"))
    first = _run(service.analyze_run(run["id"], role="service"))
    counts_first = {
        name: len(rows)
        for name, rows in unit_of_work._store.tables.items()
    }
    second = _run(service.analyze_run(run["id"], role="service"))
    assert [item["observation_id"] for item in second["items"]] == [
        item["observation_id"] for item in first["items"]]
    counts_second = {
        name: len(rows)
        for name, rows in unit_of_work._store.tables.items()
    }
    assert counts_second == counts_first


def test_rerun_creates_a_distinct_run():
    service, unit_of_work = _service()
    first = _run(service.register_result(
        _result(document_id="doc-x", raw_text="water"),
        role="service"))
    second = _run(service.register_result(
        _result(document_id="doc-x", raw_text="water"),
        role="service"))
    assert first["id"] != second["id"]
    assert len(unit_of_work._store.tables["ocr_runs"]) == 2


def test_two_providers_over_same_mapping_agree():
    mapping = {"doc-7": _result(
        document_id="doc-7", raw_text="Sodium Benzoate")}
    left = FakeOCRProvider(dict(mapping), name="same")
    right = FakeOCRProvider(dict(mapping), name="same")
    first, _ = _service(providers={"p": left})
    second, _ = _service(providers={"p": right})
    run_left = _run(first.extract_with("p", "doc-7", role="service"))
    run_right = _run(second.extract_with("p", "doc-7", role="service"))
    out_left = _run(first.analyze_run(run_left["id"], role="service"))
    out_right = _run(second.analyze_run(run_right["id"], role="service"))
    assert out_left["items"][0]["decision"] == out_right["items"][0][
        "decision"]


def test_stable_run_observation_ids():
    run_id = "11111111-1111-4111-8111-111111111111"
    assert scan_id_for_run(run_id) == scan_id_for_run(run_id)
    assert observation_id_for_run(run_id, "raw", 0) != (
        observation_id_for_run(run_id, "corrected", 0))
    assert observation_id_for_run(run_id, "raw", 0) == (
        observation_id_for_run(run_id, "raw", 0))


def test_protocol_shape():
    provider = FakeOCRProvider()
    assert callable(provider.extract)
    assert provider.name == "fake-test"
    assert isinstance(provider.calls, list)

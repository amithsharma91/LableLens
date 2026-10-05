"""Tests for the PubChem evidence adapter (mocked transport only).

Fixture payloads mirror the real PUG-REST shapes verified live on
2026-10-05 (property records, synonym lists, PUGREST.NotFound body).
"""

import json

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.http import (
    HttpClient,
    ProviderTimeout,
    RateLimiter,
)
from app.services.verification.adapters.pubchem import PubChemAdapter
from app.services.verification.cache import EvidenceCache


def _props(**overrides):
    payload = {
        "CID": 311,
        "MolecularFormula": "C6H8O7",
        "MolecularWeight": "192.12",
        "SMILES": "C(C(=O)O)C(CC(=O)O)(C(=O)O)O",
        "InChI": "InChI=1S/C6H8O7/c7-3(8)1-6(13,5(11)12)2-4(9)10/h13H",
        "InChIKey": "KRKNYBCHXYNGOX-UHFFFAOYSA-N",
        "IUPACName": "2-hydroxypropane-1,2,3-tricarboxylic acid",
        "Title": "Citric Acid",
    }
    payload.update(overrides)
    return {"PropertyTable": {"Properties": [payload]}}


def _synonyms(names):
    return {"InformationList": {"Information": [{"Synonym": names}]}}


CITRIC_BODY = json.dumps(_props()).encode()
CITRIC_SYNS = json.dumps(_synonyms(["Citric Acid", "E330", "INS-330"])).encode()
NOT_FOUND = (
    404,
    "application/json",
    b'{"Fault": {"Code": "PUGREST.NotFound", "Message": "No CID found"}}',
)


class FakeTransport:
    """URL-substring router recording every call (no network)."""

    def __init__(self):
        self.routes = []
        self.calls = []

    def add(self, needle, status, content_type, body):
        self.routes.append((needle, status, content_type, body))

    def __call__(self, url, timeout):
        self.calls.append(url)
        for needle, status, content_type, body in self.routes:
            if needle in url:
                if isinstance(body, BaseException):
                    raise body
                return status, content_type, (
                    body if isinstance(body, bytes) else json.dumps(body).encode()
                )
        return NOT_FOUND


def _adapter(transport, **kwargs):
    kwargs.setdefault("date_provider", lambda: "2026-10-05")
    client = HttpClient(
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        transport=transport,
        limiter=RateLimiter(min_interval=0),
        sleeper=lambda s: None,
    )
    return PubChemAdapter(client, **kwargs)


def _resolution(text, identifier=None, candidate_type="single_molecule"):
    from app.services.entity_resolver import Candidate

    return Resolution(
        raw_text=text,
        normalized_text=text.lower(),
        identifier=identifier,
        status="exact_match",
        candidates=[
            Candidate(
                candidate_ref="T8-1",
                display_name=text,
                candidate_type=candidate_type,
                source="synthetic_test_fixture",
                match_method="exact_normalized_name",
                match_score=0.95,
                reason="synthetic",
            )
        ],
    )


def _routes_citric(transport):
    transport.add("/compound/name/citric%20acid/", 200, "application/json",
                  CITRIC_BODY)
    transport.add("/compound/cid/311/synonyms/", 200, "application/json",
                  CITRIC_SYNS)


def test_exact_name_lookup_builds_evidence():
    transport = FakeTransport()
    _routes_citric(transport)
    records = _adapter(transport).lookup_identity(_resolution("citric acid"))
    assert len(records) == 1
    entity = records[0].entity
    assert entity.entity_id == "PUBCHEM:CID-311"
    assert entity.preferred_name == "Citric Acid"
    assert records[0].source.source_id == "PUBCHEM"
    assert records[0].source.source_class == "A"
    by_field = {f.field: f.value for f in entity.fields}
    assert by_field["formula"] == "C6H8O7"
    assert by_field["molecular_weight"] == "192.12"
    assert by_field["inchikey"] == "KRKNYBCHXYNGOX-UHFFFAOYSA-N"


def test_title_mismatch_discarded():
    transport = FakeTransport()
    transport.add("/compound/name/", 200, "application/json",
                  json.dumps(_props(Title="Benzoic Acid")).encode())
    records = _adapter(transport).lookup_identity(_resolution("citric acid"))
    assert records == []


def test_404_returns_no_records():
    transport = FakeTransport()
    records = _adapter(transport).lookup_identity(
        _resolution("xyz proprietary blend"))
    assert records == []


def test_400_returns_no_records():
    transport = FakeTransport()
    transport.add("/compound/name/", 400, "application/json", b"{}")
    records = _adapter(transport).lookup_identity(_resolution("citric acid"))
    assert records == []


def test_malformed_json_noticed():
    transport = FakeTransport()
    transport.add("/compound/name/", 200, "application/json", b"{oops")
    adapter = _adapter(transport)
    assert adapter.lookup_identity(_resolution("citric acid")) == []
    assert adapter.drain_notices() != []


def test_oversized_response_noticed():
    transport = FakeTransport()
    transport.add("/compound/name/", 200, "application/json", CITRIC_BODY)
    adapter = _adapter(transport)
    adapter._client.max_bytes = 10
    assert adapter.lookup_identity(_resolution("citric acid")) == []
    assert adapter.drain_notices() != []


def test_timeout_noticed_after_bounded_retries():
    transport = FakeTransport()
    transport.add("/compound/name/", 0, "", ProviderTimeout("slow"))
    adapter = _adapter(transport)
    assert adapter.lookup_identity(_resolution("citric acid")) == []
    assert len(transport.calls) == 3
    assert adapter.drain_notices() != []


def test_transient_5xx_recovered():
    calls = []

    def handler(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            return 503, "application/json", b"{}"
        return 200, "application/json", CITRIC_BODY

    adapter = _adapter(handler)
    records = adapter.lookup_identity(_resolution("citric acid"))
    assert len(records) == 1
    assert len(calls) == 2


def test_retry_exhaustion_noticed():
    transport = FakeTransport()
    transport.add("/compound/name/", 500, "application/json", b"{}")
    adapter = _adapter(transport)
    assert adapter.lookup_identity(_resolution("citric acid")) == []
    assert len(transport.calls) == 3


def test_cid_lookup():
    transport = FakeTransport()
    transport.add("/compound/cid/311/", 200, "application/json", CITRIC_BODY)
    res = _resolution("311", identifier="311")
    records = _adapter(transport).lookup_identity(res)
    assert len(records) == 1
    assert records[0].entity.entity_id == "PUBCHEM:CID-311"


def test_code_evidenced_via_synonyms():
    transport = FakeTransport()
    transport.add("/compound/name/E", 200, "application/json",
                  CITRIC_BODY)
    transport.add("/compound/cid/311/synonyms/", 200, "application/json",
                  CITRIC_SYNS)
    records = _adapter(transport).lookup_identity(
        _resolution("E330", identifier="E 330"))
    assert len(records) == 1
    idents = {i.value for i in records[0].entity.identifiers}
    assert "E330" in idents


def test_code_without_synonym_support_rejected():
    transport = FakeTransport()
    transport.add("/compound/name/E", 200, "application/json",
                  CITRIC_BODY)
    transport.add("/compound/cid/311/synonyms/", 200, "application/json",
                  json.dumps(_synonyms(["Citric Acid"])).encode())
    records = _adapter(transport).lookup_identity(
        _resolution("E330", identifier="E 330"))
    assert records == []


def test_name_hit_code_evidenced():
    transport = FakeTransport()
    _routes_citric(transport)
    res = _resolution("citric acid", identifier="E 330")
    records = _adapter(transport).lookup_identity(res)
    assert len(records) == 1
    idents = {(i.id_type, i.value) for i in records[0].entity.identifiers}
    assert ("e_number", "E330") in idents


def test_cache_hit_avoids_http():
    transport = FakeTransport()
    _routes_citric(transport)
    cache = EvidenceCache()
    adapter = _adapter(transport, cache=cache)
    res = _resolution("citric acid")
    first = adapter.lookup_identity(res)
    calls_after_first = len(transport.calls)
    assert calls_after_first > 0
    second = adapter.lookup_identity(res)
    assert len(transport.calls) == calls_after_first
    assert [r.entity.entity_id for r in second] == [
        r.entity.entity_id for r in first]
    assert cache.stats()["hits"] >= 1


def test_offline_serves_cache_and_misses_safely():
    transport = FakeTransport()
    _routes_citric(transport)
    cache = EvidenceCache()
    online = _adapter(transport, cache=cache)
    online.lookup_identity(_resolution("citric acid"))
    offline = _adapter(transport, cache=cache, offline=True)
    records = offline.lookup_identity(_resolution("citric acid"))
    assert len(records) == 1
    assert offline.lookup_identity(_resolution("glycerol")) == []
    assert any("offline" in n for n in offline.drain_notices())


def test_provenance_and_hash_present():
    transport = FakeTransport()
    _routes_citric(transport)
    cache = EvidenceCache()
    adapter = _adapter(transport, cache=cache)
    adapter.lookup_identity(_resolution("citric acid"))
    entry = cache.get("pubchem", "pubchem:name", "citric acid")
    assert entry is not None
    assert entry.response_hash
    assert entry.source_version == "live PUG-REST"
    assert entry.request_identity.startswith("/compound/name/")

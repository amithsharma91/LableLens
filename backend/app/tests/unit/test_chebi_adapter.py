"""Tests for the ChEBI evidence adapter (mocked transport only).

Fixture payloads mirror the real ChEBI 2.0 REST shapes verified live
on 2026-10-05 (es_search hits, compound detail, 404 detail body).
"""

import json

from app.services.entity_resolver import Candidate, Resolution
from app.services.verification.adapters.chebi import ChebiAdapter
from app.services.verification.adapters.http import HttpClient, RateLimiter
from app.services.verification.cache import EvidenceCache


def _es_hit(name="citric acid", **overrides):
    source = {
        "chebi_accession": "CHEBI:30769",
        "name": name,
        "ascii_name": "citric acid",
        "definition": "A tricarboxylic acid.",
        "smiles": "O=C(O)CC(O)(CC(=O)O)C(=O)O",
        "formula": "C6H8O7",
        "inchikey": "KRKNYBCHXYNGOX-UHFFFAOYSA-N",
        "inchi": "InChI=1S/C6H8O7/c7-3(8)1-6(13,5(11)12)2-4(9)10/h13H",
        "mass": 192.123,
    }
    source.update(overrides)
    return {
        "_index": "chebi-test",
        "_id": "30769",
        "_score": 75.0,
        "_source": source,
    }


def _detail(**overrides):
    detail = {
        "id": 30769,
        "chebi_accession": "CHEBI:30769",
        "name": "citric acid",
        "names": {
            "SYNONYM": [
                {"name": "E330", "ascii_name": "E330"},
                {"name": "INS-330", "ascii_name": "INS-330"},
            ]
        },
        "chemical_data": {"formula": "C6H8O7"},
    }
    detail.update(overrides)
    return detail


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
        return 404, "application/json", b'{"detail": "No compound matches"}'


def _adapter(transport, **kwargs):
    kwargs.setdefault("date_provider", lambda: "2026-10-05")
    client = HttpClient(
        "https://www.ebi.ac.uk",
        transport=transport,
        limiter=RateLimiter(min_interval=0),
        sleeper=lambda s: None,
    )
    return ChebiAdapter(client, **kwargs)


def _resolution(text, identifier=None, candidate_type="single_molecule"):
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
    transport.add("es_search", 200, "application/json", [_es_hit()])
    transport.add("/compound/30769/", 200, "application/json", _detail())


def test_exact_search_hit_builds_evidence():
    transport = FakeTransport()
    _routes_citric(transport)
    records = _adapter(transport).lookup_identity(_resolution("citric acid"))
    assert len(records) == 1
    entity = records[0].entity
    assert entity.entity_id == "CHEBI:CHEBI-30769"
    assert entity.preferred_name == "citric acid"
    assert records[0].source.source_id == "CHEBI"
    by_field = {f.field: f.value for f in entity.fields}
    assert by_field["formula"] == "C6H8O7"
    assert by_field["molecular_weight"] == "192.12"
    assert by_field["inchikey"] == "KRKNYBCHXYNGOX-UHFFFAOYSA-N"


def test_non_exact_hits_discarded():
    transport = FakeTransport()
    transport.add("es_search", 200, "application/json",
                  [_es_hit(name="citrate (1-)",
                           ascii_name="citrate (1-)")])
    records = _adapter(transport).lookup_identity(_resolution("citric acid"))
    assert records == []


def test_empty_search_returns_no_records():
    transport = FakeTransport()
    records = _adapter(transport).lookup_identity(
        _resolution("xyz proprietary blend"))
    assert records == []


def test_malformed_search_noticed():
    transport = FakeTransport()
    transport.add("es_search", 200, "application/json", {"unexpected": True})
    adapter = _adapter(transport)
    assert adapter.lookup_identity(_resolution("citric acid")) == []
    assert adapter.drain_notices() != []


def test_code_evidenced_via_detail_synonyms():
    transport = FakeTransport()
    _routes_citric(transport)
    res = _resolution("citric acid", identifier="E 330")
    records = _adapter(transport).lookup_identity(res)
    assert len(records) == 1
    idents = {(i.id_type, i.value) for i in records[0].entity.identifiers}
    assert ("chebi_id", "CHEBI:30769") in idents
    assert ("e_number", "E 330") in idents


def test_code_without_support_keeps_name_evidence():
    transport = FakeTransport()
    transport.add("es_search", 200, "application/json", [_es_hit()])
    transport.add("/compound/30769/", 200, "application/json",
                  _detail(names={"SYNONYM": []}))
    res = _resolution("citric acid", identifier="E 330")
    records = _adapter(transport).lookup_identity(res)
    assert len(records) == 1
    assert all(i.id_type != "e_number"
               for i in records[0].entity.identifiers)


def test_code_only_lookup_unsupported():
    transport = FakeTransport()
    adapter = _adapter(transport)
    records = adapter.lookup_identity(_resolution("E330", identifier="E 330"))
    assert records == []
    assert any("code-only" in n for n in adapter.drain_notices())


def test_offline_cache_replay():
    transport = FakeTransport()
    _routes_citric(transport)
    cache = EvidenceCache()
    _adapter(transport, cache=cache).lookup_identity(
        _resolution("citric acid"))
    calls = len(transport.calls)
    assert calls > 0
    offline = _adapter(transport, cache=cache, offline=True)
    records = offline.lookup_identity(_resolution("citric acid"))
    assert len(records) == 1
    assert len(transport.calls) == calls
    assert offline.lookup_identity(_resolution("glycerol")) == []


def test_lookup_determinism():
    transport = FakeTransport()
    _routes_citric(transport)
    adapter = _adapter(transport)
    res = _resolution("citric acid")
    first = [r.to_dict() for r in adapter.lookup_identity(res)]
    second = [r.to_dict() for r in adapter.lookup_identity(res)]
    assert first == second

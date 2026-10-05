"""Tests for the deterministic evidence cache."""

import json

from app.services.verification.cache import EvidenceCache
from app.services.verification.evidence import EvidenceItem, EvidenceSet


class FakeClock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def _items():
    return (
        EvidenceItem(
            source="PubChem",
            source_id="PUBCHEM",
            provider="pubchem",
            retrieved_at="2026-10-05",
            field="formula",
            source_value="C6H8O7",
            locator="CID:311",
        ),
    )


def test_put_get_round_trip_identical():
    cache = EvidenceCache(clock=FakeClock())
    cache.put(
        provider="pubchem",
        lookup_kind="pubchem:name",
        lookup_key="Citric Acid",
        request_identity="/compound/name/citric",
        response_body=b'{"a": 1}',
        evidence=_items(),
        locator="CID:311",
    )
    entry = cache.get("pubchem", "pubchem:name", "citric  acid")
    assert entry is not None
    import hashlib

    assert entry.response_hash == hashlib.sha256(b'{"a": 1}').hexdigest()
    rebuilt = cache.to_evidence_set(entry)
    assert rebuilt.items == _items()
    assert rebuilt.locator == "CID:311"
    assert cache.stats() == {"hits": 1, "misses": 0, "entries": 1}


def test_miss_and_stats():
    cache = EvidenceCache(clock=FakeClock())
    assert cache.get("pubchem", "pubchem:name", "nope") is None
    assert cache.stats()["misses"] == 1


def test_key_normalization():
    cache = EvidenceCache(clock=FakeClock())
    cache.put(
        provider="pubchem",
        lookup_kind="k",
        lookup_key="  Citric   ACID ",
        request_identity="r",
        response_body=b"x",
    )
    assert cache.get("pubchem", "k", "citric acid") is not None
    assert cache.get("other", "k", "citric acid") is None


def test_expiry_and_invalidate():
    clock = FakeClock()
    cache = EvidenceCache(ttl_seconds=60, clock=clock)
    cache.put(
        provider="p",
        lookup_kind="k",
        lookup_key="key",
        request_identity="r",
        response_body=b"x",
    )
    assert cache.get("p", "k", "key") is not None
    clock.now += 61
    assert cache.get("p", "k", "key") is None
    cache.put(
        provider="p",
        lookup_kind="k",
        lookup_key="key",
        request_identity="r",
        response_body=b"x",
    )
    assert cache.invalidate("p", "k", "key") is True
    assert cache.invalidate("p", "k", "key") is False


def test_max_entries_eviction():
    clock = FakeClock()
    cache = EvidenceCache(ttl_seconds=10_000, clock=clock, max_entries=2)
    for i in range(3):
        clock.now += 1
        cache.put(
            provider="p",
            lookup_kind="k",
            lookup_key="key%d" % i,
            request_identity="r",
            response_body=b"x",
        )
    assert cache.stats()["entries"] == 2


def test_entry_json_serializable():
    cache = EvidenceCache(clock=FakeClock())
    entry = cache.put(
        provider="pubchem",
        lookup_kind="k",
        lookup_key="key",
        request_identity="r",
        response_body=b"x",
        evidence=_items(),
    )
    json.dumps(entry.to_dict())
    json.dumps(EvidenceSet(
        provider="p", lookup_key="k", retrieved_at="t",
        response_hash="h", locator="l", items=_items(),
        notices=(),
    ).to_dict())

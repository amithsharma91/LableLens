"""Deterministic evidence cache (evidence storage, not authority).

Purpose: avoid repeated official requests, support offline mode,
reproducibility, and client-side rate limiting. A cache hit replays
the exact stored evidence items -- it never upgrades, verifies, or
refreshes them. Freshness metadata decides reuse, never truth.

TTL policy (documented defaults, evidence-class aware):
stable chemistry identity fields are long-lived; the cache still
expires them so refresh remains possible. Expiry never deletes
provenance: expired entries are simply not served.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from app.services.verification.evidence import EvidenceItem, EvidenceSet

__all__ = [
    "CacheEntry",
    "EvidenceCache",
    "DEFAULT_TTL_SECONDS",
    "STABLE_TTL_SECONDS",
]

# Default time-to-live: 7 days. Stable identity evidence: 90 days.
# These bound reuse, not truth -- expired entries are not served.
DEFAULT_TTL_SECONDS = 7 * 24 * 3600
STABLE_TTL_SECONDS = 90 * 24 * 3600


def _freeze(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CacheEntry:
    """One stored evidence lookup with full retrieval metadata."""

    provider: str = ""
    lookup_kind: str = ""
    lookup_key: str = ""
    request_identity: str = ""  # endpoint + lookup key, no secrets
    locator: str = ""  # evidence locator, round-trips replays
    retrieved_at: float = 0.0
    response_hash: str = ""  # sha256 of the raw response body
    source_version: str = ""
    expires_at: float = 0.0
    freshness_class: str = "stable"
    evidence: Tuple[EvidenceItem, ...] = ()
    notices: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """JSON-serialisable view."""
        return {
            "provider": self.provider,
            "lookup_kind": self.lookup_kind,
            "lookup_key": self.lookup_key,
            "request_identity": self.request_identity,
            "locator": self.locator,
            "retrieved_at": self.retrieved_at,
            "response_hash": self.response_hash,
            "source_version": self.source_version,
            "expires_at": self.expires_at,
            "freshness_class": self.freshness_class,
            "evidence": [e.to_dict() for e in self.evidence],
            "notices": list(self.notices),
        }


class EvidenceCache:
    """Small in-memory evidence store with TTL expiry.

    Keys are (provider, lookup_kind, lookup_key) triples. Lookup is
    case/whitespace-normalised so identical evidence requests hit the
    same entry deterministically. No network access here by design.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
        max_entries: int = 1000,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._store: Dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def cache_key(
        provider: str, lookup_kind: str, lookup_key: str
    ) -> str:
        """Deterministic key for an evidence request."""
        norm = " ".join((lookup_key or "").split()).lower()
        return _freeze([provider, lookup_kind, norm])

    def get(
        self, provider: str, lookup_kind: str, lookup_key: str
    ) -> Optional[CacheEntry]:
        """Return a live entry, or None on miss/expiry."""
        entry = self._store.get(
            self.cache_key(provider, lookup_kind, lookup_key)
        )
        if entry is None or entry.expires_at <= self._clock():
            if entry is not None:
                del self._store[
                    self.cache_key(provider, lookup_kind, lookup_key)
                ]
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def put(
        self,
        *,
        provider: str,
        lookup_kind: str,
        lookup_key: str,
        request_identity: str,
        response_body: bytes,
        source_version: str = "",
        freshness_class: str = "stable",
        ttl_seconds: Optional[float] = None,
        evidence: Tuple[EvidenceItem, ...] = (),
        notices: Tuple[str, ...] = (),
        locator: str = "",
    ) -> CacheEntry:
        """Store evidence with its response hash and expiry."""
        now = self._clock()
        entry = CacheEntry(
            provider=provider,
            lookup_kind=lookup_kind,
            lookup_key=lookup_key,
            request_identity=request_identity,
            locator=locator or request_identity,
            retrieved_at=now,
            response_hash=hashlib.sha256(response_body).hexdigest(),
            source_version=source_version,
            expires_at=now
            + (ttl_seconds if ttl_seconds is not None else self._ttl),
            freshness_class=freshness_class,
            evidence=evidence,
            notices=notices,
        )
        if len(self._store) >= self._max_entries:
            oldest = min(self._store, key=lambda k: self._store[k].expires_at)
            del self._store[oldest]
        self._store[
            self.cache_key(provider, lookup_kind, lookup_key)
        ] = entry
        return entry

    def invalidate(
        self, provider: str, lookup_kind: str, lookup_key: str
    ) -> bool:
        """Drop one entry. Returns True when something was dropped."""
        key = self.cache_key(provider, lookup_kind, lookup_key)
        if key in self._store:
            del self._store[key]
            return True
        return False

    def stats(self) -> dict:
        """Hit/miss counters for tests and diagnostics."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "entries": len(self._store),
        }

    def to_evidence_set(self, entry: CacheEntry) -> EvidenceSet:
        """Rebuild the evidence set exactly as originally stored."""
        return EvidenceSet(
            provider=entry.provider,
            lookup_key=entry.lookup_key,
            retrieved_at=str(entry.retrieved_at),
            response_hash=entry.response_hash,
            locator=entry.locator,
            items=entry.evidence,
            notices=entry.notices,
        )

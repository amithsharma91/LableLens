"""Application-level rate limiting for sensitive API operations.

This is LabelLens throttling of its own endpoints. It is not, and is
not described as, any provider's API quota: PubChem/ChEBI limits live
with those services and are a separate concern.

Design:

* :class:`RateLimiter` is the abstraction, so the backend can become
  Redis or a database-backed store later without touching routes or
  domain logic. Only :class:`InMemoryRateLimiter` ships here.
* The identity is always the authenticated principal. Client-supplied
  fields never form a bucket key, so a caller cannot widen or redirect
  someone else's bucket by editing a payload.
* Buckets are fixed windows keyed by action + subject (+ optionally
  the peer address). Window expiry is lazy, so a limiter that is
  never asked about a key does no work.
* Storage is bounded: at most ``max_keys`` buckets are tracked and the
  least-recently-used bucket is evicted beyond that. A bounded
  limiter degrades accuracy, never correctness -- it never lets a
  request through that policy would deny for a tracked key.

Single process, single instance: state lives in this process's memory.
That is documented, tested, and explicitly not distributed protection.
Running multiple API replicas multiplies the effective limit.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol

__all__ = [
    "RateLimitAction",
    "RateLimitDecision",
    "RateLimiter",
    "InMemoryRateLimiter",
    "parse_policy",
    "unlimited",
]


class RateLimitAction:
    """Rate-limited operations (the only three high-risk writes)."""

    OBSERVATION_CREATE = "observations.create"
    OBSERVATION_ANALYZE = "observations.analyze"
    REVIEW_DECISION = "reviews.decision"
    ALL = (
        OBSERVATION_CREATE,
        OBSERVATION_ANALYZE,
        REVIEW_DECISION,
    )


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of one rate-limit check.

    ``allowed=False`` carries only what the client needs: the window
    retry hint. No internal bucket state, key contents, or counters
    for other identities are exposed.
    """

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int = 0

    @property
    def limited(self) -> bool:
        return not self.allowed


def unlimited() -> RateLimitDecision:
    """Decision used when no policy applies (documented no-op)."""
    return RateLimitDecision(
        allowed=True, limit=0, remaining=0, retry_after_seconds=0)


class RateLimiter(Protocol):
    """Counts one request against a key (infrastructure contract)."""

    async def hit(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Record a hit and report whether it is within policy."""


def parse_policy(raw: str) -> tuple:
    """Parse a ``"count/window_seconds"`` policy string.

    Returns ``(0, 0)`` for anything unparseable or non-positive, which
    the caller treats as "not configured" -- never as "deny".
    """
    text = str(raw or "").strip()
    if not text:
        return (0, 0)
    count_text, _, window_text = text.partition("/")
    try:
        limit = int(count_text)
        window = int(window_text or 0)
    except ValueError:
        return (0, 0)
    if limit <= 0 or window <= 0:
        return (0, 0)
    return (limit, window)


class InMemoryRateLimiter:
    """Fixed-window limiter with bounded, lazily expired buckets."""

    def __init__(
        self,
        *,
        max_keys: int = 10_000,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._max_keys = max(1, int(max_keys))
        self._clock = clock or time.monotonic
        # Insertion order is access order, so the first key is the least
        # recently used one.
        self._buckets: Dict[str, tuple] = {}

    async def hit(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        if limit <= 0 or window_seconds <= 0:
            return unlimited()
        now = self._clock()
        started, count = self._buckets.get(key, (now, 0))
        elapsed = now - started
        if elapsed >= window_seconds or elapsed < 0:
            # Window expired (or the clock moved backwards): start a
            # fresh window rather than inheriting a stale count.
            started, count = now, 0
        if count >= limit:
            retry = int(math.ceil(window_seconds - elapsed))
            self._buckets[key] = (started, count)
            self._evict()
            return RateLimitDecision(
                allowed=False,
                limit=limit,
                remaining=0,
                retry_after_seconds=max(1, retry),
            )
        count += 1
        self._buckets[key] = (started, count)
        self._evict()
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=0,
        )

    def reset(self, key: Optional[str] = None) -> None:
        """Clear one bucket, or all of them (tests/administration)."""
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)

    def tracked_keys(self) -> int:
        """Number of live buckets (bounded-state assertions)."""
        return len(self._buckets)

    def _evict(self) -> None:
        while len(self._buckets) > self._max_keys:
            oldest = next(iter(self._buckets))
            del self._buckets[oldest]

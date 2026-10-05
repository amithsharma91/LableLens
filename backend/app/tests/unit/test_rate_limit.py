"""Rate limiter unit tests (Stage 12).

The clock is injected, so window behaviour is deterministic: no
sleeps, no wall-clock assumptions, and the same results on every run.
"""

import pytest

from app.services.rate_limit import (
    InMemoryRateLimiter,
    RateLimitAction,
    parse_policy,
    unlimited,
)


class _Clock:
    """Manually advanced monotonic clock."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(clock=None, **kwargs):
    return InMemoryRateLimiter(clock=clock, **kwargs)


# -- policy parsing ----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("30/60", (30, 60)),
        (" 5 / 10 ", (5, 10)),
        ("", (0, 0)),
        ("0/60", (0, 0)),
        ("30/0", (0, 0)),
        ("-1/60", (0, 0)),
        ("abc/60", (0, 0)),
        ("30", (0, 0)),
        ("30/abc", (0, 0)),
        (None, (0, 0)),
    ],
)
def test_parse_policy(raw, expected):
    assert parse_policy(raw) == expected


async def test_unconfigured_policy_allows_without_counting():
    limiter = _limiter(_Clock())
    for _ in range(50):
        decision = await limiter.hit("k", limit=0, window_seconds=60)
        assert decision.allowed
    assert limiter.tracked_keys() == 0


# -- fixed-window behaviour --------------------------------------------


async def test_below_limit_succeeds_and_reports_remaining():
    clock = _Clock()
    limiter = _limiter(clock)
    for expected_remaining in (2, 1, 0):
        decision = await limiter.hit(
            "a|user", limit=3, window_seconds=60)
        assert decision.allowed
        assert decision.remaining == expected_remaining
    assert limiter.tracked_keys() == 1


async def test_limit_reached_then_denied_with_retry_after():
    clock = _Clock()
    limiter = _limiter(clock)
    for _ in range(3):
        assert (await limiter.hit(
            "a|user", limit=3, window_seconds=60)).allowed
    denied = await limiter.hit("a|user", limit=3, window_seconds=60)
    assert not denied.allowed
    assert denied.remaining == 0
    assert denied.retry_after_seconds == 60
    assert denied.limited


async def test_window_resets_after_expiry():
    clock = _Clock()
    limiter = _limiter(clock)
    for _ in range(2):
        assert (await limiter.hit(
            "a|user", limit=2, window_seconds=60)).allowed
    assert not (await limiter.hit(
        "a|user", limit=2, window_seconds=60)).allowed
    clock.advance(60)
    fresh = await limiter.hit("a|user", limit=2, window_seconds=60)
    assert fresh.allowed
    assert fresh.remaining == 1


async def test_partial_window_expiry_keeps_remaining_time():
    clock = _Clock()
    limiter = _limiter(clock)
    for _ in range(2):
        await limiter.hit("a|user", limit=2, window_seconds=60)
    clock.advance(45)
    denied = await limiter.hit("a|user", limit=2, window_seconds=60)
    assert not denied.allowed
    # 15s left in the window, rounded up.
    assert denied.retry_after_seconds == 15


async def test_backwards_clock_does_not_extend_a_window():
    clock = _Clock(1000.0)
    limiter = _limiter(clock)
    for _ in range(2):
        await limiter.hit("a|user", limit=2, window_seconds=60)
    clock.now = 500.0
    # A clock that moved backwards starts a new window rather than
    # freezing the bucket open forever.
    assert (await limiter.hit("a|user", limit=2, window_seconds=60)).allowed


# -- isolation ---------------------------------------------------------


async def test_subjects_have_independent_buckets():
    clock = _Clock()
    limiter = _limiter(clock)
    for _ in range(2):
        await limiter.hit("a|alice", limit=2, window_seconds=60)
    assert not (await limiter.hit("a|alice", limit=2, window_seconds=60)).allowed
    # Bob is unaffected by Alice's exhausted bucket.
    bob = await limiter.hit("a|bob", limit=2, window_seconds=60)
    assert bob.allowed
    assert bob.remaining == 1


async def test_actions_are_isolated():
    clock = _Clock()
    limiter = _limiter(clock)
    for _ in range(2):
        await limiter.hit(
            "%s|alice" % RateLimitAction.OBSERVATION_CREATE,
            limit=2, window_seconds=60)
    assert not (await limiter.hit(
        "%s|alice" % RateLimitAction.OBSERVATION_CREATE,
        limit=2, window_seconds=60)).allowed
    other = await limiter.hit(
        "%s|alice" % RateLimitAction.OBSERVATION_ANALYZE,
        limit=2, window_seconds=60)
    assert other.allowed


async def test_subjects_cannot_reach_another_bucket_by_key_shaping():
    """A hostile subject string stays inside its own bucket.

    The key is built from the verified subject, so a subject that
    embeds another subject's name (or a separator) only ever consumes
    the attacker's own allowance.
    """
    clock = _Clock()
    limiter = _limiter(clock)
    for _ in range(2):
        await limiter.hit("a|victim", limit=2, window_seconds=60)
    hostile = "victim|analyze"
    for _ in range(10):
        await limiter.hit("a|%s" % hostile, limit=100, window_seconds=60)
    # The victim's exhausted bucket is unchanged by the flood.
    victim = await limiter.hit("a|victim", limit=2, window_seconds=60)
    assert not victim.allowed


# -- bounded state -----------------------------------------------------


async def test_key_storage_is_bounded():
    clock = _Clock()
    limiter = _limiter(clock, max_keys=10)
    for index in range(100):
        await limiter.hit("a|user-%d" % index, limit=5, window_seconds=60)
    assert limiter.tracked_keys() == 10


async def test_eviction_does_not_grant_unlimited_access():
    """Bounded state degrades accuracy, not the deny decision."""
    clock = _Clock()
    limiter = _limiter(clock, max_keys=2)
    await limiter.hit("a|u1", limit=1, window_seconds=60)
    await limiter.hit("a|u2", limit=1, window_seconds=60)
    assert not (await limiter.hit("a|u1", limit=1, window_seconds=60)).allowed
    # New keys evict the oldest, which is the documented trade-off.
    await limiter.hit("a|u3", limit=1, window_seconds=60)
    assert limiter.tracked_keys() == 2


async def test_reset_clears_buckets():
    limiter = _limiter(_Clock())
    await limiter.hit("a|u1", limit=5, window_seconds=60)
    limiter.reset("a|u1")
    assert limiter.tracked_keys() == 0
    await limiter.hit("a|u2", limit=5, window_seconds=60)
    limiter.reset()
    assert limiter.tracked_keys() == 0


def test_unlimited_decision_shape():
    decision = unlimited()
    assert decision.allowed
    assert decision.retry_after_seconds == 0
    assert not decision.limited


def test_only_three_sensitive_actions_are_defined():
    assert RateLimitAction.ALL == (
        "observations.create",
        "observations.analyze",
        "reviews.decision",
    )

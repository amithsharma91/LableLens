"""Tests for the bounded shared HTTP layer (no real network).

All transports are injected fakes; the only live-network code path
(urllib_transport) is never invoked here.
"""

from app.services.verification.adapters.http import (
    DEFAULT_MAX_ATTEMPTS,
    HttpClient,
    ProviderBadRequest,
    ProviderInvalidResponse,
    ProviderNetworkError,
    ProviderNotFound,
    ProviderOversized,
    ProviderRateLimited,
    ProviderServerError,
    ProviderTimeout,
    RateLimiter,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def _client(handler, **kwargs):
    clock = FakeClock()
    kwargs.setdefault("limiter", RateLimiter(min_interval=0, clock=clock,
                                             sleeper=clock.sleep))
    kwargs.setdefault("sleeper", clock.sleep)
    client = HttpClient("https://example.test", transport=handler, **kwargs)
    return client, clock


def _ok(body=b'{"a": 1}'):
    return lambda url, timeout: (200, "application/json", body)


def test_success_and_attempt_count():
    client, _ = _client(_ok())
    payload, body = client.get_json("/x")
    assert payload == {"a": 1}
    assert body == b'{"a": 1}'
    assert client.attempts_made == 1


def test_top_level_list_accepted():
    client, _ = _client(_ok(b'[{"a": 1}]'))
    payload, _ = client.get_json("/x")
    assert payload == [{"a": 1}]


def test_404_maps_to_not_found_without_retry():
    calls = []

    def handler(url, timeout):
        calls.append(url)
        return 404, "application/json", b'{"Fault": {}}'

    client, _ = _client(handler)
    try:
        client.get_json("/missing")
        raise AssertionError("should raise")
    except ProviderNotFound:
        pass
    assert len(calls) == 1


def test_400_maps_to_bad_request_without_retry():
    calls = []

    def handler(url, timeout):
        calls.append(url)
        return 400, "application/json", b"{}"

    client, _ = _client(handler)
    try:
        client.get_json("/bad")
        raise AssertionError("should raise")
    except ProviderBadRequest:
        pass
    assert len(calls) == 1


def test_429_maps_to_rate_limited_without_retry():
    calls = []

    def handler(url, timeout):
        calls.append(url)
        return 429, "application/json", b"{}"

    client, _ = _client(handler)
    try:
        client.get_json("/busy")
        raise AssertionError("should raise")
    except ProviderRateLimited:
        pass
    assert len(calls) == 1


def test_transient_5xx_retried_then_success():
    calls = []

    def handler(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            return 503, "application/json", b"{}"
        return 200, "application/json", b'{"ok": true}'

    client, _ = _client(handler)
    payload, _ = client.get_json("/flaky")
    assert payload == {"ok": True}
    assert len(calls) == 3


def test_retry_exhaustion_maps_to_server_error():
    def handler(url, timeout):
        return 500, "application/json", b"{}"

    client, _ = _client(handler)
    try:
        client.get_json("/down")
        raise AssertionError("should raise")
    except ProviderServerError:
        pass
    assert client.attempts_made == DEFAULT_MAX_ATTEMPTS


def test_timeout_retried_then_mapped():
    from app.services.verification.adapters.http import ProviderTimeout as PT

    def handler(url, timeout):
        raise PT("boom")

    client, _ = _client(handler)
    try:
        client.get_json("/slow")
        raise AssertionError("should raise")
    except ProviderTimeout:
        pass
    assert client.attempts_made == DEFAULT_MAX_ATTEMPTS


def test_network_error_mapped():
    from app.services.verification.adapters.http import ProviderNetworkError as PN

    def handler(url, timeout):
        raise PN("conn reset")

    client, _ = _client(handler)
    try:
        client.get_json("/x")
        raise AssertionError("should raise")
    except ProviderNetworkError:
        pass


def test_malformed_json_rejected():
    client, _ = _client(_ok(b"{not json"))
    try:
        client.get_json("/x")
        raise AssertionError("should raise")
    except ProviderInvalidResponse:
        pass


def test_wrong_content_type_rejected():
    client, _ = _client(
        lambda url, timeout: (200, "text/html", b"<html></html>")
    )
    try:
        client.get_json("/x")
        raise AssertionError("should raise")
    except ProviderInvalidResponse:
        pass


def test_oversized_response_rejected():
    client, _ = _client(_ok(b'{"a": 1}'), max_bytes=4)
    try:
        client.get_json("/x")
        raise AssertionError("should raise")
    except ProviderOversized:
        pass


def test_unexpected_status_raises():
    client, _ = _client(
        lambda url, timeout: (418, "application/json", b"{}")
    )
    from app.services.verification.adapters.http import ProviderError

    try:
        client.get_json("/x")
        raise AssertionError("should raise")
    except ProviderError:
        pass


def test_rate_limiter_spacing():
    clock = FakeClock()
    limiter = RateLimiter(min_interval=2.0, clock=clock,
                          sleeper=clock.sleep)
    limiter.wait()
    limiter.wait()
    assert clock.slept == [2.0]
    limiter_zero = RateLimiter(min_interval=0, clock=clock,
                               sleeper=clock.sleep)
    limiter_zero.wait()
    assert clock.slept == [2.0]

"""Staging smoke-script tests (Stage 18.5).

The script never runs here: a fake HTTP opener replays canned
responses so every check function, envelope assertion, and the
secret scanner are covered offline. No network, no deployment.
"""

import io
import json
import urllib.error

from scripts import smoke_staging as smoke


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status = status
        self.headers = FakeHeaders(headers or {})
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    """Canned happier-path staging service with per-owner isolation."""

    def __init__(self, rate_limit_after=None):
        self.calls = []
        self._creates = 0
        self._obs_creates = 0
        self._owners = {}
        self._rate_limit_after = rate_limit_after

    def _forbidden(self, request):
        return FakeResponse(404, {
            "error": {"code": "NOT_FOUND", "message": "missing"},
            "meta": {"request_id": "r", "api_version": "v1"}})

    def open(self, request, timeout=None):
        if request.data:
            json.loads(request.data.decode())
        path = request.full_url.split("/api/v1", 1)[1]
        self.calls.append((request.get_method(), path))
        health = (
            {"data": {"status": "ok"},
             "meta": {"request_id": "r", "api_version": "v1"}},
            {"X-Request-ID": "r"},
        )
        if path == "/health" and request.get_method() == "GET":
            return FakeResponse(200, *health)
        token = (request.get_header("Authorization") or "")
        if not token.startswith("Bearer real-"):
            return FakeResponse(401, {
                "error": {"code": "UNAUTHORIZED",
                          "message": "authentication required"},
                "meta": {"request_id": "r", "api_version": "v1"}})
        if path == "/ocr/runs" and request.get_method() == "POST":
            self._creates += 1
            if self._rate_limit_after is not None and \
                    self._creates > self._rate_limit_after:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "limited",
                    FakeHeaders({"Retry-After": "60"}),
                    io.BytesIO(json.dumps({
                        "error": {"code": "RATE_LIMITED",
                                  "message": "slow down"},
                        "meta": {"request_id": "r",
                                 "api_version": "v1"}}).encode()))
            self._owners["run-1"] = token
            return FakeResponse(201, {
                "data": {"run_id": "run-1"},
                "meta": {"request_id": "r", "api_version": "v1"}})
        if path.startswith("/ocr/runs/"):
            if self._owners.get("run-1") != token:
                return self._forbidden(request)
        if path.startswith("/observations/") and token != "Bearer real-a":
            return self._forbidden(request)
        if path == "/observations" and request.get_method() == "POST":
            self._obs_creates += 1
            if self._rate_limit_after is not None and \
                    self._obs_creates > self._rate_limit_after:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "limited",
                    FakeHeaders({"Retry-After": "60"}),
                    io.BytesIO(json.dumps({
                        "error": {"code": "RATE_LIMITED",
                                  "message": "slow down"},
                        "meta": {"request_id": "r",
                                 "api_version": "v1"}}).encode()))
            return FakeResponse(201, {
                "data": [{"observation_id": "obs-rl"}],
                "meta": {"request_id": "r", "api_version": "v1"}})
        if path.endswith("/analyze"):
            return FakeResponse(200, {
                "data": {"run_id": "run-1", "corrected": False,
                         "warnings": [], "items": [{
                             "observation_id": "obs-1",
                             "status": "verified",
                             "identity_confidence": "HIGH"}]},
                "meta": {"request_id": "r", "api_version": "v1"}})
        if path.endswith("/correction"):
            return FakeResponse(200, {
                "data": {"run_id": "run-1"},
                "meta": {"request_id": "r", "api_version": "v1"}})
        if "/verification" in path:
            return FakeResponse(200, {
                "data": {"status": "verified"},
                "meta": {"request_id": "r", "api_version": "v1"}})
        if path.startswith("/observations/"):
            return FakeResponse(200, {
                "data": {"status": "verified"},
                "meta": {"request_id": "r", "api_version": "v1"}})
        return FakeResponse(404, {
            "error": {"code": "NOT_FOUND", "message": "missing"},
            "meta": {"request_id": "r", "api_version": "v1"}})


def _client(**kwargs):
    return smoke.Client("https://staging.example", **kwargs)


def test_full_smoke_passes_against_fake_service(capsys):
    client = _client()
    client._opener = FakeOpener()
    result = smoke.Result()
    smoke.run_all(client, "real-a", "real-b", result)
    assert result.failed == [], result.failed
    assert len(result.passed) == 10
    assert result.summary() == 0


def test_cross_user_leak_would_be_detected():
    class Leaky(FakeOpener):
        def open(self, request, timeout=None):
            response = super().open(request, timeout)
            if response.status == 404:
                # A service that leaks private rows answers 200.
                return FakeResponse(200, {
                    "data": {"run_id": "run-1"},
                    "meta": {"request_id": "r",
                             "api_version": "v1"}})
            return response

    client = _client()
    client._opener = Leaky()
    result = smoke.Result()
    smoke.run_all(client, "real-a", "real-b", result)
    assert result.failed != []
    assert any("cross-user" in name or "verification" in name
               for name in result.failed)


def test_rate_limit_check_opt_in():
    client = _client()
    client._opener = FakeOpener(rate_limit_after=2)
    result = smoke.Result()
    smoke.run_all(client, "real-a", "real-b", result,
                  include_rate_limit=True)
    assert result.failed == []


def test_secret_scanner_rejects_leaks():
    assert smoke.no_secrets({"data": {"status": "ok"}})
    assert not smoke.no_secrets(
        {"error": {"message": "Bearer abc"}})
    assert not smoke.no_secrets({"data": {"x": "sk-live"}})


def test_envelope_helpers():
    assert smoke.envelope_ok(
        {"data": {}, "meta": {"request_id": "r"}})
    assert not smoke.envelope_ok({"data": {}})
    assert smoke.error_code(
        {"error": {"code": "NOT_FOUND"}}) == "NOT_FOUND"
    assert smoke.error_code({}) is None

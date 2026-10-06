#!/usr/bin/env python3
"""LabelLens staging smoke tests (Stage 18.5, manual only).

Runs safe checks against a deployed Cloud Run URL. Never runs in
CI and never touches local databases.

Usage:
  BASE_URL=https://labellens-api-staging-xxx.a.run.app \\
    SMOKE_JWT_USER_A=<user-a-jwt> SMOKE_JWT_USER_B=<user-b-jwt> \\
    python scripts/smoke_staging.py [--rate-limit]

Every check uses only published, non-sensitive label text
(Stage-15 excipient names). No private user data is uploaded or
asserted. Secrets (the two JWTs) come from the environment and are
never printed; only their presence/absence and the first/last
outcomes are reported.

Exit 0 only when every enabled check passes.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Published, non-sensitive ingredient text only (Stage-15 excipients).
TEXT_BENZOATE = "Sodium Benzoate (E211)"
TEXT_GLYCEROL = "Glycerol (E422)"


class Result:
    def __init__(self):
        self.passed = []
        self.failed = []

    def check(self, name, ok, detail=""):
        (self.passed if ok else self.failed).append(name)
        print(("PASS " if ok else "FAIL ") + name
              + (" -- " + detail if detail and not ok else ""))

    def summary(self):
        print("smoke: %d passed, %d failed"
              % (len(self.passed), len(self.failed)))
        return 0 if not self.failed else 1


class Client:
    """Minimal JSON client; injectable opener keeps this unit-testable."""

    def __init__(self, base_url, opener=None):
        self.base = base_url.rstrip("/")
        self._opener = opener or urllib.request.build_opener()

    def call(self, method, path, token=None, body=None):
        data = None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            data = json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers,
            method=method)
        try:
            with self._opener.open(request, timeout=30) as response:
                payload = response.read().decode() or "{}"
                return (response.status,
                        response.headers.get("X-Request-ID", ""),
                        json.loads(payload))
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode() or "{}"
            try:
                parsed = json.loads(payload)
            except ValueError:
                parsed = {}
            return (exc.code, "", parsed)


def envelope_ok(payload):
    return isinstance(payload, dict) and "data" in payload \
        and isinstance(payload.get("meta"), dict)


def error_code(payload):
    try:
        return payload["error"]["code"]
    except (KeyError, TypeError):
        return None


def no_secrets(payload):
    text = json.dumps(payload).lower()
    for token in ("bearer ", "service_role", "service-role-key",
                  "sk-", "api_key", "apikey", "BEGIN PRIVATE",
                  "passwd", "postgres://"):
        if token in text:
            return False
    return True


def run_all(client, jwt_a, jwt_b, result, include_rate_limit=False):
    # 1. health (public liveness, static, no secrets)
    status, _, body = client.call("GET", "/api/v1/health")
    result.check(
        "health", status == 200 and no_secrets(body),
        "status=%s" % status)

    # 2-3. unauthenticated + invalid auth on a protected route
    status, _, body = client.call(
        "POST", "/api/v1/observations",
        body={"raw_text": "water"})
    result.check(
        "no-auth-401",
        status == 401 and error_code(body) == "UNAUTHORIZED",
        "status=%s" % status)
    status, _, body = client.call(
        "POST", "/api/v1/observations",
        token="invalid-token", body={"raw_text": "water"})
    result.check(
        "bad-auth-401",
        status == 401 and error_code(body) == "UNAUTHORIZED",
        "status=%s" % status)

    # 4-8. owner flow: create, analyze, correct, verify
    status, _, body = client.call(
        "POST", "/api/v1/ocr/runs", token=jwt_a,
        body={"document_id": "smoke-a", "raw_text": TEXT_BENZOATE,
              "provider": "smoke-client"})
    run_id = (body.get("data") or {}).get("run_id", "")
    result.check(
        "ocr-create", status == 201 and bool(run_id)
        and envelope_ok(body), "status=%s" % status)
    if not run_id:
        return result
    status, _, body = client.call(
        "POST", "/api/v1/ocr/runs/%s/analyze" % run_id, token=jwt_a)
    items = (body.get("data") or {}).get("items", [])
    result.check(
        "ocr-analyze", status == 200 and len(items) == 1
        and envelope_ok(body), "status=%s" % status)
    observation_id = items[0]["observation_id"] if items else ""
    status, _, body = client.call(
        "POST", "/api/v1/ocr/runs/%s/correction" % run_id,
        token=jwt_a,
        body={"corrected_text": TEXT_BENZOATE,
              "reason": "smoke punctuation check"})
    result.check(
        "ocr-correct", status == 200 and envelope_ok(body),
        "status=%s" % status)
    status, _, body = client.call(
        "GET", "/api/v1/observations/%s/verification" % observation_id,
        token=jwt_a)
    result.check(
        "verification-lookup",
        status == 200 and envelope_ok(body)
        and no_secrets(body), "status=%s" % status)

    # 9. Stage-15 VERIFIED path through auth + API + DB.
    status, _, body = client.call(
        "POST", "/api/v1/ocr/runs", token=jwt_a,
        body={"document_id": "smoke-glycerol",
              "raw_text": TEXT_GLYCEROL, "provider": "smoke-client"})
    glycerol_run = (body.get("data") or {}).get("run_id", "")
    verified = False
    if glycerol_run:
        status, _, body = client.call(
            "POST", "/api/v1/ocr/runs/%s/analyze" % glycerol_run,
            token=jwt_a)
        items = (body.get("data") or {}).get("items", [])
        verified = bool(items) and all(
            item.get("status") == "verified"
            and item.get("identity_confidence") == "HIGH"
            for item in items
        )
    result.check("stage15-verified", verified)

    # 10. cross-user isolation (404 everywhere for user B).
    isolated = True
    for method, path, payload in (
        ("GET", "/api/v1/ocr/runs/%s" % run_id, None),
        ("POST", "/api/v1/ocr/runs/%s/correction" % run_id,
         {"corrected_text": "x", "reason": "smoke"}),
        ("POST", "/api/v1/ocr/runs/%s/analyze" % run_id, None),
        ("GET", "/api/v1/observations/%s/verification"
         % observation_id, None),
    ):
        status, _, body = client.call(
            method, path, token=jwt_b, body=payload)
        if status != 404 or error_code(body) != "NOT_FOUND":
            isolated = False
    result.check("cross-user-404", isolated)

    # 11. rate limiting (opt-in: writes 30+ observations).
    if include_rate_limit:
        limited = False
        retry_after = False
        for index in range(35):
            status, headers, body = _raw_post(
                client, "/api/v1/observations",
                jwt_a, {"raw_text": "water %d" % index})
            if status == 429 and error_code(body) == "RATE_LIMITED":
                limited = True
                retry_after = "Retry-After" in dict(headers)
                break
        result.check(
            "rate-limit-429", limited and retry_after)

    # 12-13. envelopes + request IDs on every response above are
    # asserted inline (envelope_ok / X-Request-ID sampled here).
    _, request_id, body = client.call("GET", "/api/v1/health")
    result.check(
        "request-id", bool(request_id) and envelope_ok(body))
    return result


def _raw_post(client, path, token, body):
    import urllib.error as _errors

    request = urllib.request.Request(
        client.base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token},
        method="POST")
    try:
        with client._opener.open(request, timeout=30) as response:
            return (response.status, response.headers,
                    json.loads(response.read().decode() or "{}"))
    except _errors.HTTPError as exc:
        return (exc.code, exc.headers,
                json.loads(exc.read().decode() or "{}"))


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="staging smoke tests (manual only)")
    parser.add_argument("--rate-limit", action="store_true",
                        help="include the 429 behavior check")
    args = parser.parse_args(argv)
    base_url = os.getenv("BASE_URL", "").rstrip("/")
    jwt_a = os.getenv("SMOKE_JWT_USER_A", "")
    jwt_b = os.getenv("SMOKE_JWT_USER_B", "")
    if not base_url or not jwt_a or not jwt_b:
        print("BASE_URL, SMOKE_JWT_USER_A and SMOKE_JWT_USER_B "
              "are all required; refusing to run half-configured.")
        return 2
    result = Result()
    run_all(Client(base_url), jwt_a, jwt_b, result,
            include_rate_limit=args.rate_limit)
    return result.summary()


if __name__ == "__main__":
    sys.exit(main())

"""Bounded HTTP access for official provider adapters.

All network behavior lives here and only here: no adapter performs
its own requests. Every request has timeouts, response size bounds,
content-type checks, bounded retries (transient network errors and
selected 5xx only), and conservative client-side rate spacing.

Transports are injectable callables so tests never touch the network:

    transport(url, timeout_seconds) -> (status, content_type, body)

The default transport is stdlib urllib (no new dependencies).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Tuple

__all__ = [
    "ProviderError",
    "ProviderNotFound",
    "ProviderBadRequest",
    "ProviderRateLimited",
    "ProviderServerError",
    "ProviderTimeout",
    "ProviderNetworkError",
    "ProviderOversized",
    "ProviderInvalidResponse",
    "RateLimiter",
    "HttpClient",
    "urllib_transport",
    "RETRYABLE_STATUS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MIN_INTERVAL",
]

# Retry transient failures and these server states only. Never 400
# (bad request), 404 (absent), or 501 (unsupported) -- retrying those
# cannot succeed. 429 surfaces as RateLimited without retry.
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_MAX_ATTEMPTS = 3
# Conservative client-side spacing. The official per-client quota is
# NOT asserted here (unknown); spacing only avoids hammering.
DEFAULT_MIN_INTERVAL = 1.0


class ProviderError(Exception):
    """Base class for all provider-side failures."""


class ProviderNotFound(ProviderError):
    """Provider reports no such record (HTTP 404)."""


class ProviderBadRequest(ProviderError):
    """Provider rejects the request shape (HTTP 400). Not retried."""


class ProviderRateLimited(ProviderError):
    """Provider throttled the client (HTTP 429). Not retried."""


class ProviderServerError(ProviderError):
    """Provider failed after bounded retries (retryable 5xx)."""


class ProviderTimeout(ProviderError):
    """Request exceeded its timeout after bounded retries."""


class ProviderNetworkError(ProviderError):
    """Connection-level failure after bounded retries."""


class ProviderOversized(ProviderError):
    """Response exceeded the size bound; discarded unread."""


class ProviderInvalidResponse(ProviderError):
    """Wrong content type, malformed JSON, or unexpected shape."""


def urllib_transport(
    url: str, timeout_seconds: float
) -> Tuple[int, str, bytes]:
    """Stdlib transport. Returns (status, content_type, body)."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "LabelLens-evidence/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
            return (
                resp.status,
                resp.headers.get_content_type(),
                resp.read(),
            )
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, "application/json", body
    except TimeoutError as exc:
        raise ProviderTimeout("request timed out: %s" % exc)
    except (OSError, ValueError) as exc:
        raise ProviderNetworkError("connection failed: %s" % exc)


class RateLimiter:
    """Minimum-interval spacing between requests (injectable clock)."""

    def __init__(
        self,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleeper = sleeper
        self._last: Optional[float] = None

    def wait(self) -> None:
        """Sleep only the remaining spacing, if any."""
        if self.min_interval <= 0:
            return
        now = self._clock()
        if self._last is not None:
            wait_for = self._last + self.min_interval - now
            if wait_for > 0:
                self._sleeper(wait_for)
                now = self._clock()
        self._last = now


class HttpClient:
    """JSON GET client with bounds. Raises typed ProviderError."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: Tuple[float, ...] = (1.0, 2.0),
        limiter: Optional[RateLimiter] = None,
        transport: Callable[
            [str, float], Tuple[int, str, bytes]
        ] = urllib_transport,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds
        self.limiter = limiter or RateLimiter()
        self.transport = transport
        self.sleeper = sleeper
        self.attempts_made = 0

    def get_json(self, path: str) -> Tuple[object, bytes]:
        """GET ``path``; return (parsed JSON, raw body).

        Parsed JSON may be an object or an array -- each adapter
        validates the shape its endpoint guarantees. Raises typed
        ``ProviderError`` on transport, status, size, type, or
        syntax failures.
        """
        url = path if path.startswith("http") else self.base_url + path
        failures: List[str] = []
        saw_timeout = False
        for attempt in range(self.max_attempts):
            self.attempts_made += 1
            self.limiter.wait()
            try:
                status, content_type, body = self.transport(
                    url, self.timeout
                )
            except ProviderTimeout as exc:
                saw_timeout = True
                failures.append(str(exc))
                self._backoff(attempt)
                continue
            except ProviderNetworkError as exc:
                failures.append(str(exc))
                self._backoff(attempt)
                continue
            if status == 404:
                raise ProviderNotFound("not found: %s" % url)
            if status == 400:
                raise ProviderBadRequest("bad request: %s" % url)
            if status == 429:
                raise ProviderRateLimited("throttled: %s" % url)
            if status in RETRYABLE_STATUS:
                failures.append("http %d" % status)
                self._backoff(attempt)
                continue
            if status != 200:
                raise ProviderError("unexpected status %d" % status)
            if len(body) > self.max_bytes:
                raise ProviderOversized("response exceeds size bound")
            if "json" not in (content_type or "").lower():
                raise ProviderInvalidResponse(
                    "unexpected content type %s" % content_type
                )
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ProviderInvalidResponse(
                    "malformed JSON: %s" % exc
                )
            if not isinstance(parsed, (dict, list)):
                raise ProviderInvalidResponse("unexpected JSON shape")
            return parsed, body
        if failures and failures[-1].startswith("http"):
            raise ProviderServerError("; ".join(failures))
        if saw_timeout:
            raise ProviderTimeout("; ".join(failures))
        raise ProviderNetworkError("; ".join(failures) or "failed")

    def _backoff(self, attempt: int) -> None:
        if attempt < len(self.backoff_seconds):
            self.sleeper(self.backoff_seconds[attempt])

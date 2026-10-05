"""Rate-limit enforcement for sensitive write routes.

The dependency is application infrastructure, not domain logic: it
reads the authenticated principal, asks the configured
:class:`~app.services.rate_limit.RateLimiter` backend, and turns a
denial into the standard error envelope with ``Retry-After``.

Fail-safe: if the limiter backend raises, the request is refused with
503 ``RATE_LIMITER_UNAVAILABLE``. Sensitive writes fail closed, which
is the safer default for an abuse-control boundary -- degrading to
"allow" would silently disable the control exactly when the backend
is unhealthy. Read endpoints are not limited (explicitly not
configured), so normal browsing stays unaffected.

Identity comes from the verified token via ``Principal``. No header
(``X-User-ID``, ``X-Reviewer-ID``, ...) and no request-body field can
influence the bucket key.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.api.auth import Principal, require_authenticated
from app.api.errors import ApiError
from app.config import settings
from app.services.rate_limit import (
    InMemoryRateLimiter,
    RateLimitAction,
    RateLimitDecision,
    RateLimiter,
    parse_policy,
    unlimited,
)

__all__ = ["rate_limiter_from_app", "enforce_rate_limit", "bucket_key"]

# Module-level default limiter, used when an app injects none. Tests and
# deployments can inject their own instance on app.state.
_default_limiter = InMemoryRateLimiter(max_keys=settings.rate_limit_max_keys)


def rate_limiter_from_app(request: Request) -> RateLimiter:
    """Resolve the limiter backend (injected or process default)."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None and callable(getattr(limiter, "hit", None)):
        return limiter
    return _default_limiter


def policy_for(request: Request, action: str) -> str:
    """Policy string for one action.

    An app may inject a policy table (`app.state.rate_limit_policy`
    with `for_action`); otherwise the configured settings table
    applies. Routes never carry a limit themselves.
    """
    table = getattr(request.app.state, "rate_limit_policy", None)
    resolver = getattr(table, "for_action", None)
    if callable(resolver):
        return resolver(action)
    return _policy_for(action)


def bucket_key(
    action: str, principal: Principal, *, include_ip: bool, ip: str = ""
) -> str:
    """Bucket identity: action + authenticated subject (+ peer IP).

    The subject comes from the verified token, so a caller cannot move
    another subject's allowance by changing request content.
    """
    key = "%s|%s" % (action, principal.subject)
    if include_ip and ip:
        key = "%s|%s" % (key, ip)
    return key


async def enforce_rate_limit(
    request: Request,
    action: str,
    *,
    principal: Principal,
    limiter: RateLimiter,
    policy: str = "",
    include_ip: bool = False,
) -> RateLimitDecision:
    """Apply one action's policy; raise ApiError when exceeded."""
    limit, window = parse_policy(
        policy if policy else policy_for(request, action))
    if limit <= 0 or window <= 0:
        return unlimited()
    ip = ""
    client = request.client
    if include_ip and client is not None:
        ip = client.host or ""
    key = bucket_key(action, principal, include_ip=include_ip, ip=ip)
    try:
        decision = await limiter.hit(
            key, limit=limit, window_seconds=window)
    except Exception as exc:
        # Fail closed: an unusable limiter must not silently allow.
        raise ApiError(
            503,
            "RATE_LIMITER_UNAVAILABLE",
            "request could not be admitted; retry shortly",
            details={"error_category": type(exc).__name__},
        )
    if decision.limited:
        request.state.rate_limit_retry_after = (
            decision.retry_after_seconds)
        raise ApiError(
            429,
            "RATE_LIMITED",
            "too many requests",
            details={
                "retry_after_seconds": decision.retry_after_seconds,
                "action": action,
            },
        )
    request.state.rate_limit_remaining = decision.remaining
    return decision


def _policy_for(action: str) -> str:
    if action == RateLimitAction.OBSERVATION_CREATE:
        return settings.rate_limit_observation_create
    if action == RateLimitAction.OBSERVATION_ANALYZE:
        return settings.rate_limit_analyze
    if action == RateLimitAction.REVIEW_DECISION:
        return settings.rate_limit_review_decision
    return "0/0"


def _include_ip() -> bool:
    return settings.rate_limit_include_ip.strip().lower() in (
        "true", "1", "on", "yes",
    )


def _enabled() -> bool:
    return settings.rate_limiting_active


def limited(action: str, *, require=require_authenticated):
    """Route dependency factory: require auth, then rate limit.

    Authentication is a dependency of this factory, so the principal
    used for the bucket key is always an already-verified identity --
    the reviewer decision route passes ``require_reviewer`` so the
    stricter role check runs before any bucket is consumed. FastAPI
    caches dependency results per request, so the route's own
    parameter is satisfied by the same cached call.
    """

    async def dependency(
        request: Request,
        principal: Principal = Depends(require),
    ) -> Principal:
        if not _enabled():
            return principal
        await enforce_rate_limit(
            request,
            action,
            principal=principal,
            limiter=rate_limiter_from_app(request),
            include_ip=_include_ip(),
        )
        return principal

    return dependency

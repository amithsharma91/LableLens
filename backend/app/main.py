"""Application assembly (Stage 11 API).

`create_app` wires routers, error handlers, authentication, and the
service layer. Production wiring (Postgres repositories bound per
request, snapshot evidence adapter) is the default; tests pass an
in-memory bundle plus a static token map instead. Routes never touch
SQL: services take repository bundles, and only the two dependencies
below know how those bundles are built.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.errors import RequestIdMiddleware, register_handlers
from app.api.v1 import health, observations, reviews, verification
from app.config import settings
from app.services.observation_service import ObservationService
from app.services.review_service import ReviewService

__all__ = ["create_app", "app"]


def _default_snapshot_path() -> str:
    if settings.snapshot_path:
        return settings.snapshot_path
    candidate = (
        Path(__file__).resolve().parents[2] / "snapshots"
        / "canonical_v1.json"
    )
    return str(candidate) if candidate.exists() else ""


def _dev_verifier():
    from app.api.auth import StaticTokenVerifier

    mapping = {}
    for entry in settings.dev_api_tokens.split(","):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) == 3 and all(parts):
            token, subject, role = parts
            mapping[token] = (subject, role)
    if not mapping:
        return None
    return StaticTokenVerifier(mapping)


class ServiceScopeMiddleware(BaseHTTPMiddleware):
    """Bind a service bundle to each request.

    Memory bundles are shared (process state); Postgres bundles open
    one connection + transaction per request on the serving loop, so
    connections never cross event loops and writes commit atomically.
    """

    async def dispatch(self, request, call_next):
        factory = request.app.state.service_factory
        if factory is None:
            # No repository boundary was injected: pass through so
            # endpoints that need no services (health, OpenAPI) still
            # work; data routes fail with a controlled 500 via
            # app.api.dependencies.services().
            request.state.services = None
            return await call_next(request)
        async with factory() as bundle:
            request.state.services = bundle
            return await call_next(request)


def _shared_factory(bundle):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def scope():
        yield bundle

    return scope


def _postgres_factory(engine, registry, adapters):
    """Per-request connection + transaction scope (Postgres wiring)."""
    from contextlib import asynccontextmanager

    from app.repositories.postgres import (
        PostgresClaimRepository,
        PostgresEntityRepository,
        PostgresEvidenceRepository,
        PostgresMatchRepository,
        PostgresReviewRepository,
        PostgresVerificationRepository,
    )

    @asynccontextmanager
    async def scope():
        async with engine.connect() as connection:
            async with connection.begin():
                repos = SimpleNamespace(
                    matches=PostgresMatchRepository(connection),
                    claims=PostgresClaimRepository(connection),
                    evidence=PostgresEvidenceRepository(connection),
                    verification=PostgresVerificationRepository(connection),
                    reviews=PostgresReviewRepository(connection),
                    entities=PostgresEntityRepository(connection),
                )
                built_reviews = ReviewService(
                    repos, adapters=list(adapters))
                yield SimpleNamespace(
                    observations=ObservationService(
                        repos, registry=registry, adapters=list(adapters),
                        review_service=built_reviews),
                    reviews=built_reviews,
                )

    return scope


def create_app(
    *,
    repos=None,
    verifier=None,
    registry=None,
    adapters=None,
    review_service=None,
    observation_service=None,
    engine=None,
) -> FastAPI:
    """Build the FastAPI application with injected boundaries."""
    application = FastAPI(title="LabelLens API", version=settings.version)

    # Middleware order (last added is outermost):
    #   RequestId -> CORS -> ServiceScope -> routes
    # Preflight requests are answered by CORS before a service scope --
    # and therefore a database connection -- is ever opened.
    application.add_middleware(ServiceScopeMiddleware)

    origins = [
        origin.strip()
        for origin in settings.allowed_origins.split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestIdMiddleware)
    register_handlers(application)

    application.state.token_verifier = (
        verifier if verifier is not None else _dev_verifier())

    if repos is not None or engine is not None:
        from app.services.verification.adapters.snapshot import (
            SnapshotAdapter,
            SnapshotError,
        )

        snapshot = None
        path = _default_snapshot_path()
        if path:
            try:
                snapshot = SnapshotAdapter(path)
            except (SnapshotError, OSError):
                # Evidence is additive: an unusable snapshot degrades
                # to "no evidence" (all candidates unresolved) rather
                # than taking the process down at import time.
                snapshot = None
        local_adapters = (
            list(adapters) if adapters is not None else
            ([snapshot] if snapshot is not None else [])
        )
        if engine is not None:
            application.state.service_factory = _postgres_factory(
                engine, registry, local_adapters)
        else:
            built_reviews = review_service or ReviewService(
                repos, adapters=local_adapters)
            built_observations = observation_service or ObservationService(
                repos, registry=registry, adapters=local_adapters,
                review_service=built_reviews)
            application.state.service_factory = _shared_factory(
                SimpleNamespace(
                    observations=built_observations,
                    reviews=built_reviews,
                ))
    else:
        application.state.service_factory = None

    application.include_router(health.router, prefix="/api/v1",
                               tags=["health"])
    application.include_router(observations.router, prefix="/api/v1",
                               tags=["observations"])
    application.include_router(verification.router, prefix="/api/v1",
                               tags=["verification"])
    application.include_router(reviews.router, prefix="/api/v1",
                               tags=["reviews"])

    @application.get("/")
    async def root():
        return {
            "message": "LabelLens API is running. "
                       "See /docs for generated documentation."
        }

    return application


app = create_app()

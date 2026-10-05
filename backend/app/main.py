"""Application assembly (Stage 11 API).

`create_app` wires routers, error handlers, authentication, and the
service layer. Production wiring (Postgres repositories bound per
request, snapshot evidence adapter) is the default; tests pass an
in-memory bundle plus a static token map instead. Routes never touch
SQL: services take repository bundles, and only the two dependencies
below know how those bundles are built.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.errors import RequestIdMiddleware, register_handlers
from app.api.v1 import health, observations, ocr, reviews, verification
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


def _configured_verifier():
    """Configured verifier; production fails closed at construction."""
    from app.api.auth import build_token_verifier

    return build_token_verifier(settings)


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


class _RegistryHolder:
    """Late-bound resolver registry (loaded at startup when needed)."""

    def __init__(self, registry=None) -> None:
        self._registry = registry

    @property
    def registry(self):
        return self._registry

    def set(self, registry) -> None:
        self._registry = registry


async def _load_pg_registry(engine):
    """Project registered canonical entities into a registry.

    On any failure the registry stays empty: unresolved candidates are
    the safe state, whereas a partial load could make a name resolvable
    without a matching canonical entity.
    """
    from app.repositories.postgres import PostgresEntityRepository
    from app.services.registration import build_registry

    log = logging.getLogger("labellens.registry")
    connection = await engine.connect()
    try:
        entities = await PostgresEntityRepository(
            connection).list_entities(role="service")
        aliases = await PostgresEntityRepository(
            connection).list_aliases(role="service")
    except Exception as exc:
        log.error(
            "canonical registry unavailable; resolver stays empty "
            "category=%s",
            type(exc).__name__,
        )
        return None
    finally:
        await connection.close()
    projected = build_registry(entities, aliases, version=str(len(entities)))
    log.info(
        "canonical registry loaded entities=%d aliases=%d",
        len(entities), len(aliases),
    )
    return projected


def _postgres_factory(engine, registry, adapters, ocr_providers=None):
    """Per-request connection + transaction scope (Postgres wiring)."""
    from contextlib import asynccontextmanager

    from app.repositories.postgres import (
        PostgresClaimRepository,
        PostgresEntityRepository,
        PostgresEvidenceRepository,
        PostgresMatchRepository,
        PostgresOCRRepository,
        PostgresReviewRepository,
        PostgresVerificationRepository,
    )
    from app.services.ocr_service import OCRService

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
                    ocr=PostgresOCRRepository(connection),
                )
                built_reviews = ReviewService(
                    repos, adapters=list(adapters))
                built_observations = ObservationService(
                    repos, registry=registry.registry,
                    adapters=list(adapters),
                    review_service=built_reviews)
                yield SimpleNamespace(
                    observations=built_observations,
                    reviews=built_reviews,
                    ocr=OCRService(
                        repos, registry=registry.registry,
                        adapters=list(adapters),
                        providers=ocr_providers,
                        review_service=built_reviews),
                )

    return scope


def _registry_lifespan(engine, registry):
    """Startup hook: project registered canonical entities (Postgres).

    With a Postgres engine the resolver registry is built from
    `chemical_entities` + `ingredient_aliases`, the single
    authoritative registration path. On failure the registry stays
    empty: unresolved candidates are the safe state, whereas a partial
    load could make a name resolvable without a matching canonical
    entity.
    """
    from contextlib import asynccontextmanager

    from app.services.registration import empty_registry

    @asynccontextmanager
    async def lifespan(application):
        if isinstance(registry, _RegistryHolder) and engine is not None:
            if registry.registry is None:
                loaded = await _load_pg_registry(engine)
                registry.set(loaded if loaded is not None else empty_registry())
        yield

    return lifespan


def create_app(
    *,
    repos=None,
    verifier=None,
    registry=None,
    adapters=None,
    review_service=None,
    observation_service=None,
    engine=None,
    rate_limiter=None,
    ocr_providers=None,
) -> FastAPI:
    """Build the FastAPI application with injected boundaries.

    `registry` is the resolver's canonical-entity registry. With a
    Postgres engine it is loaded from `chemical_entities` at startup
    (the one authoritative registration path); if that load fails the
    registry stays empty, which resolves nothing rather than
    inventing candidates. A re-run of the import requires a restart
    to become visible to the resolver.
    """
    # One holder shared by the startup hook and the request factory, so
    # the registry loaded at startup is the one every request sees.
    if engine is not None and not isinstance(registry, _RegistryHolder):
        registry = _RegistryHolder(registry)
    application = FastAPI(
        title="LabelLens API",
        version=settings.version,
        lifespan=_registry_lifespan(engine, registry),
    )

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
        verifier if verifier is not None else _configured_verifier())
    if rate_limiter is not None:
        application.state.rate_limiter = rate_limiter

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
                engine, registry, local_adapters,
                ocr_providers=ocr_providers)
        else:
            from app.services.ocr_service import OCRService

            built_reviews = review_service or ReviewService(
                repos, adapters=local_adapters)
            built_observations = observation_service or ObservationService(
                repos, registry=registry, adapters=local_adapters,
                review_service=built_reviews)
            application.state.service_factory = _shared_factory(
                SimpleNamespace(
                    observations=built_observations,
                    reviews=built_reviews,
                    ocr=OCRService(
                        repos, registry=registry,
                        adapters=local_adapters,
                        providers=ocr_providers,
                        review_service=built_reviews),
                ))
    else:
        application.state.service_factory = None

    application.include_router(health.router, prefix="/api/v1",
                               tags=["health"])
    application.include_router(observations.router, prefix="/api/v1",
                               tags=["observations"])
    application.include_router(ocr.router, prefix="/api/v1",
                               tags=["ocr"])
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

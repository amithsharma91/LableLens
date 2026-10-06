"""Production ASGI entrypoint (staging).

Unlike ``app.main:app`` (import-safe, database-free), this module
wires the real staging dependencies and fails fast with a clear
error when required production configuration is missing:

* ``DATABASE_URL`` must be set explicitly (the settings default
  points at localhost and is never used silently here).
* ``ENVIRONMENT`` must be ``production`` so Stage-12
  authentication rules apply (real Supabase JWT verification,
  ``DEV_API_TOKENS`` refused, reviewer allowlist semantics).
* Database connectivity is verified once at startup
  (``SELECT 1`` inside the ASGI lifespan, awaited): an unreachable
  database refuses to boot instead of serving degraded
  verification silently. No event loop is ever run at import or
  build time, so this module is safe to load under Uvicorn (or
  any running loop).

Uvicorn target: ``app.serve:app``.
"""

from __future__ import annotations

import os

__all__ = ["app_from_env"]


def __getattr__(name: str):
    # Lazy `app` so importing this module (tests, tooling) never
    # boots the production stack: only the ASGI server resolves
    # `app.serve:app`, which constructs -- and fail-closes -- then.
    if name == "app":
        return app_from_env()
    raise AttributeError(name)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            "%s is required for the production entrypoint "
            "(refusing to start with a default)" % name)
    return value


def app_from_env(*, config=None):
    """Build the staging application from the environment.

    Synchronous factory: constructs objects only, never runs an
    event loop, so it is safe to call (and this module safe to
    import) while a loop is already running -- exactly the Render/
    Uvicorn startup condition that ``asyncio.run`` violated.

    `config` accepts a fresh ``Settings`` for tests; production
    uses the global settings object.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.main import create_app

    if config is None:
        from app.config import settings as config

    if config.environment.strip().lower() != "production":
        raise RuntimeError(
            "ENVIRONMENT must be 'production' for the staging "
            "entrypoint (got %r): development authentication rules "
            "must never serve staging traffic" % config.environment)
    database_url = _require_env("DATABASE_URL")
    # NullPool: one physical connection per request, closed again.
    # Single-instance staging cannot hold stale pooled connections
    # across scale-to-zero idle periods; per-request scope already
    # opens exactly one connection, so nothing is lost.
    engine = create_async_engine(database_url, poolclass=NullPool)
    providers = None
    if config.ocr_space_api_key.strip():
        from app.services.ocr_space import OCRSpaceProvider

        providers = {
            "ocr-space": OCRSpaceProvider(
                config.ocr_space_api_key.strip(),
                endpoint=config.ocr_space_endpoint,
            )
        }
    application = create_app(
        engine=engine, ocr_providers=providers, config=config)
    _wrap_lifespan(application, engine, database_url)
    return application


def _wrap_lifespan(application, engine, database_url: str) -> None:
    """Run the SELECT 1 check inside the ASGI lifespan, awaited.

    Uvicorn/Starlette dispatch lifespan through
    ``application.router.lifespan_context`` (read dynamically at
    Starlette 1.7.0, ``routing.py``), so replacing it preserves the
    registry projection that ``create_app`` wired while adding, in
    order: awaited connectivity gate (startup fails loudly on a
    dead database) and engine disposal (clean shutdown). No second
    engine is created; the same object is shared and closed once.
    """
    from contextlib import asynccontextmanager

    previous = application.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        await _check_connectivity(engine, database_url)
        try:
            if previous is None:
                yield
            else:
                async with previous(app):
                    yield
        finally:
            await engine.dispose()

    application.router.lifespan_context = lifespan


async def _check_connectivity(engine, database_url: str) -> None:
    from sqlalchemy import text

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(
            "database unreachable at startup (%s: %s); refusing "
            "to serve degraded verification"
            % (type(exc).__name__, _safe_detail(database_url)))
    # NOTE: only the host is ever named, never credentials.


def _safe_detail(database_url: str) -> str:
    from sqlalchemy.engine import make_url

    try:
        url = make_url(database_url)
        return "%s host=%s db=%s" % (
            url.drivername, url.host, url.database)
    except Exception:
        return "unparseable database URL"

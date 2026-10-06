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
  (``SELECT 1``): an unreachable database refuses to boot
  instead of serving degraded verification silently.

Uvicorn target: ``app.serve:app``.
"""

from __future__ import annotations

import asyncio
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


def app_from_env(*, check_connectivity: bool = True, config=None):
    """Build the staging application from the environment.

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
    if check_connectivity:
        asyncio.run(_check_connectivity(engine, database_url))
    return create_app(engine=engine, ocr_providers=providers,
                      config=config)


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

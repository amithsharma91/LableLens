"""Centralized database access boundary (Stage 10).

Service code never builds engines or connections itself: it asks
this module for an engine (from an explicit URL, never a committed
secret) and runs work inside :func:`atomic`, which yields a single
transactional connection. Repositories bind to that connection, so
multi-write transitions commit or roll back together.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

__all__ = ["engine_from_url", "engine_from_env", "atomic"]


def engine_from_url(url: str, *, echo: bool = False) -> AsyncEngine:
    """Build an async engine. URL comes from the caller/environment."""
    if not url:
        raise ValueError("a database URL is required")
    return create_async_engine(url, echo=echo)


def engine_from_env(
    *, variable: str = "TEST_DATABASE_URL", echo: bool = False
) -> AsyncEngine:
    """Build an engine from an environment variable (no committed secrets)."""
    return engine_from_url(os.environ[variable], echo=echo)


@asynccontextmanager
async def atomic(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Yield one transactional connection (commit/rollback together)."""
    async with engine.connect() as connection:
        async with connection.begin():
            yield connection

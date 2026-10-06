"""Production entrypoint tests (Stage 18.5, Render fix).

`app.serve` must refuse unsafe startup loudly and never silently
enter development mode. Settings are rebuilt per test from the
patched environment (pydantic-settings reads env at
construction), so no module reload is needed. The factory itself
never runs an event loop; the SELECT 1 gate lives in the ASGI
lifespan and is exercised through TestClient startup.
"""

import os

import pytest

from app.config import Settings
from app.serve import _safe_detail, app_from_env


def _config(monkeypatch, env):
    for key in (
        "DATABASE_URL",
        "ENVIRONMENT",
        "DEV_API_TOKENS",
        "SUPABASE_URL",
        "SUPABASE_JWT_ISSUER",
        "SUPABASE_JWT_JWKS_URL",
        "SUPABASE_JWT_AUDIENCE",
        "OCR_SPACE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


def test_missing_database_url_fails_clearly(monkeypatch):
    config = _config(monkeypatch, {"ENVIRONMENT": "production"})
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        app_from_env(config=config)


def test_non_production_environment_fails_clearly(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "development",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
    })
    with pytest.raises(RuntimeError, match="ENVIRONMENT"):
        app_from_env(config=config)


def test_production_without_auth_config_fails_closed(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
    })
    # No Supabase issuer/JWKS and no dev tokens: the verifier
    # builder refuses instead of serving an open boundary.
    with pytest.raises(RuntimeError, match="Supabase"):
        app_from_env(config=config)


def test_dev_tokens_forbidden_in_production(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
        "SUPABASE_URL": "https://example.supabase.co",
        "DEV_API_TOKENS": "token:sub:reader",
    })
    with pytest.raises(RuntimeError, match="DEV_API_TOKENS"):
        app_from_env(config=config)


async def test_factory_loads_with_running_loop(monkeypatch):
    """Regression for the Render startup crash.

    ``asyncio.run()`` inside ``app_from_env()`` raised
    ``RuntimeError: cannot be called from a running event loop``
    under Uvicorn. This test itself runs inside a loop
    (asyncio_mode=auto); merely building the application here
    proves the factory never runs one.
    """
    import asyncio

    assert asyncio.get_running_loop() is not None
    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
        "SUPABASE_URL": "https://example.supabase.co",
    })
    application = app_from_env(config=config)
    assert application.title == "LabelLens API"
    await asyncio.sleep(0)


def test_unreachable_database_fails_at_startup(monkeypatch):
    """The SELECT 1 gate is awaited in the ASGI lifespan.

    A dead database refuses TestClient startup (the same lifespan
    Uvicorn drives) with the fail-closed message -- proving the
    check runs asynchronously at startup, not at build time.
    """
    from fastapi.testclient import TestClient

    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": (
            "postgresql+asyncpg://u@127.0.0.1:1/db?ssl=require"
        ),
        "SUPABASE_URL": "https://example.supabase.co",
    })
    application = app_from_env(config=config)
    with pytest.raises(RuntimeError, match="database unreachable"):
        with TestClient(application):
            pass  # pragma: no cover - startup must raise first


def test_startup_succeeds_against_live_database(monkeypatch):
    """Lifespan SELECT 1 passes and health answers on live Postgres.

    Requires TEST_DATABASE_URL; skipped -- never faked -- without
    a database. Asserts the full startup path end to end.
    """
    live_url = os.getenv("TEST_DATABASE_URL", "")
    if not live_url:
        pytest.skip("no live test database configured")
    from fastapi.testclient import TestClient

    from app.config import settings as global_settings

    monkeypatch.setenv("DATABASE_URL", live_url)
    config = Settings(
        ENVIRONMENT="production",
        DATABASE_URL=live_url,
        SUPABASE_URL=global_settings.supabase_url or "",
        SUPABASE_JWT_ISSUER=global_settings.supabase_jwt_issuer or "",
        SUPABASE_JWT_JWKS_URL=(
            global_settings.supabase_jwt_jwks_url or ""),
        SUPABASE_JWT_AUDIENCE=(
            global_settings.supabase_jwt_audience or ""),
        DEV_API_TOKENS="",
    )
    if not config.supabase_configured:
        pytest.skip("no Supabase JWT configuration available")
    application = app_from_env(config=config)
    with TestClient(application) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ok"


def test_safe_detail_never_names_credentials():
    detail = _safe_detail(
        "postgresql+asyncpg://user:s3cret@db.example.com:5432/app"
    )
    assert "s3cret" not in detail
    assert "user" not in detail
    assert "db.example.com" in detail

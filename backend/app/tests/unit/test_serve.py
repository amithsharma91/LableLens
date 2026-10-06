"""Production entrypoint tests (Stage 18.5).

`app.serve` must refuse unsafe startup loudly and never silently
enter development mode. Settings are rebuilt per test from the
patched environment (pydantic-settings reads env at
construction), so no module reload is needed. No database is
touched except the refused-port connectivity check (fast, local,
deterministic).
"""

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
        app_from_env(check_connectivity=False, config=config)


def test_non_production_environment_fails_clearly(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "development",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
    })
    with pytest.raises(RuntimeError, match="ENVIRONMENT"):
        app_from_env(check_connectivity=False, config=config)


def test_production_without_auth_config_fails_closed(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
    })
    # No Supabase issuer/JWKS and no dev tokens: the verifier
    # builder refuses instead of serving an open boundary.
    with pytest.raises(RuntimeError, match="Supabase"):
        app_from_env(check_connectivity=False, config=config)


def test_dev_tokens_forbidden_in_production(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://u@/db",
        "SUPABASE_URL": "https://example.supabase.co",
        "DEV_API_TOKENS": "token:sub:reader",
    })
    with pytest.raises(RuntimeError, match="DEV_API_TOKENS"):
        app_from_env(check_connectivity=False, config=config)


def test_unreachable_database_fails_fast(monkeypatch):
    config = _config(monkeypatch, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": (
            "postgresql+asyncpg://u@127.0.0.1:1/db?ssl=require"
        ),
        "SUPABASE_URL": "https://example.supabase.co",
    })
    with pytest.raises(RuntimeError, match="database unreachable"):
        app_from_env(check_connectivity=True, config=config)


def test_safe_detail_never_names_credentials():
    detail = _safe_detail(
        "postgresql+asyncpg://user:s3cret@db.example.com:5432/app"
    )
    assert "s3cret" not in detail
    assert "user" not in detail
    assert "db.example.com" in detail

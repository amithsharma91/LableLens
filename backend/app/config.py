import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Settings(BaseSettings):
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "info")
    allowed_origins: str = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000"
    )

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/labellens"
    )

    snapshot_path: str = os.getenv("SNAPSHOT_PATH", "")

    dev_api_tokens: str = os.getenv("DEV_API_TOKENS", "")

    # -- Supabase JWT verification (production identity) ----------------
    # Nothing here is hard-coded: the project URL is configuration, and
    # the issuer / JWKS endpoint are derived from it exactly as the
    # Supabase documentation describes (`<SUPABASE_URL>/auth/v1`, and
    # `<iss>/.well-known/jwks.json`). Either can be overridden
    # explicitly for a non-standard deployment.
    supabase_url: str = ""
    supabase_jwt_issuer: str = ""
    supabase_jwt_jwks_url: str = ""
    # Comma-separated accepted `aud` values; "*" disables the audience
    # check explicitly (never the default).
    supabase_jwt_audience: str = os.getenv(
        "SUPABASE_JWT_AUDIENCE", "authenticated"
    )
    supabase_jwt_algorithms: str = os.getenv(
        "SUPABASE_JWT_ALGORITHMS", "ES256,RS256"
    )
    supabase_jwt_leeway_seconds: int = _int_env(
        "SUPABASE_JWT_LEEWAY_SECONDS", 60
    )
    # Supabase's edge caches JWKS for 10 minutes; stay under it so a
    # rotated key is picked up promptly.
    supabase_jwt_jwks_ttl_seconds: int = _int_env(
        "SUPABASE_JWT_JWKS_TTL_SECONDS", 300
    )
    # Floor between forced refreshes (bounds work an unknown `kid`
    # can trigger).
    supabase_jwt_jwks_min_refresh_seconds: int = _int_env(
        "SUPABASE_JWT_JWKS_MIN_REFRESH_SECONDS", 30
    )
    supabase_jwt_jwks_max_keys: int = _int_env(
        "SUPABASE_JWT_JWKS_MAX_KEYS", 16
    )
    supabase_jwt_fetch_timeout_seconds: float = _float_env(
        "SUPABASE_JWT_FETCH_TIMEOUT_SECONDS", 5.0
    )
    # Operator-controlled reviewer allowlist (subjects, comma
    # separated). Never derived from user-controlled token claims.
    supabase_reviewer_subjects: str = os.getenv(
        "SUPABASE_REVIEWER_SUBJECTS", ""
    )

    # -- Application rate limiting (single process) --------------------
    rate_limit_enabled: str = os.getenv("RATE_LIMIT_ENABLED", "true")
    rate_limit_observation_create: str = os.getenv(
        "RATE_LIMIT_OBSERVATION_CREATE", "30/60"
    )
    rate_limit_analyze: str = os.getenv("RATE_LIMIT_ANALYZE", "20/60")
    rate_limit_review_decision: str = os.getenv(
        "RATE_LIMIT_REVIEW_DECISION", "20/60"
    )
    # Additionally key buckets by client IP (subject remains the
    # primary identity). Off by default: behind a proxy the peer
    # address is the proxy's.
    rate_limit_include_ip: str = os.getenv(
        "RATE_LIMIT_INCLUDE_IP", "false"
    )
    rate_limit_max_keys: int = _int_env("RATE_LIMIT_MAX_KEYS", 10_000)

    # -- OCR provider (Stage 17) -------------------------------------
    # A real OCR vendor is intentionally unwired by default: no key,
    # no calls. When set, the OCR.space adapter authenticates with
    # this key only; the key is never logged, returned, or persisted.
    ocr_space_api_key: str = os.getenv("OCR_SPACE_API_KEY", "")
    ocr_space_endpoint: str = os.getenv(
        "OCR_SPACE_ENDPOINT",
        "https://api.ocr.space/parse/image",
    )

    # -- Canonical entity registration (service-role import) ----------
    # Interlock: the import refuses to run unless this is set to the
    # literal `service-role`. It is never set by the API process.
    entity_import_confirm: str = os.getenv("ENTITY_IMPORT_CONFIRM", "")
    expected_snapshot_version: str = os.getenv(
        "EXPECTED_SNAPSHOT_VERSION", ""
    )

    version: str = "0.1.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def _derive_supabase_endpoints(self) -> "Settings":
        """Derive issuer/JWKS from SUPABASE_URL when not given.

        Documented layout (supabase.com/docs/guides/auth/jwts):
        `iss` is `<SUPABASE_URL>/auth/v1` and the public keys live at
        `<iss>/.well-known/jwks.json`. Explicit configuration always
        wins, so a self-hosted or proxied deployment is supported.
        """
        self.supabase_url = (self.supabase_url or "").strip().rstrip("/")
        if not self.supabase_jwt_issuer.strip() and self.supabase_url:
            self.supabase_jwt_issuer = "%s/auth/v1" % self.supabase_url
        if not self.supabase_jwt_jwks_url.strip() \
                and self.supabase_jwt_issuer.strip():
            self.supabase_jwt_jwks_url = (
                "%s/.well-known/jwks.json" % self.supabase_jwt_issuer.strip())
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def jwt_audiences(self) -> tuple:
        raw = self.supabase_jwt_audience.strip()
        if not raw:
            return ()
        if raw == "*":
            return ()
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    @property
    def jwt_algorithms(self) -> tuple:
        return tuple(
            part.strip().upper()
            for part in self.supabase_jwt_algorithms.split(",")
            if part.strip()
        )

    @property
    def reviewer_subjects(self) -> frozenset:
        return frozenset(
            part.strip()
            for part in self.supabase_reviewer_subjects.split(",")
            if part.strip()
        )

    @property
    def supabase_configured(self) -> bool:
        return bool(
            self.supabase_jwt_issuer and self.supabase_jwt_jwks_url
        )

    def rate_limit_for(self, action: str) -> tuple:
        """Return (limit, window_seconds) for one action."""
        table = {
            "observations.create": self.rate_limit_observation_create,
            "observations.analyze": self.rate_limit_analyze,
            "reviews.decision": self.rate_limit_review_decision,
        }
        raw = table.get(action, "0/0")
        limit_text, _, window_text = str(raw).partition("/")
        try:
            limit = int(limit_text)
            window = int(window_text or 0)
        except ValueError:
            return (0, 0)
        if limit <= 0 or window <= 0:
            return (0, 0)
        return (limit, window)

    @property
    def rate_limiting_active(self) -> bool:
        return self.rate_limit_enabled.strip().lower() not in (
            "false", "0", "off", "no",
        )


settings = Settings()

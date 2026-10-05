import os
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    version: str = "0.1.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

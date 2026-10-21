import sys
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    api_key: str = Field(..., alias="API_KEY")

    base_url: str = Field(default="http://localhost:8000", alias="BASE_URL")
    cache_ttl_seconds: int = Field(default=300, alias="CACHE_TTL_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_version: str = Field(default="dev", alias="APP_VERSION")
    git_sha: str = Field(default="dev", alias="GIT_SHA")
    pod_name: str = Field(default="local", alias="POD_NAME")
    startup_delay_seconds: int = Field(default=0, alias="STARTUP_DELAY_SECONDS")
    fail_if_dependency_down_at_startup: bool = Field(
        default=False, alias="FAIL_IF_DEPENDENCY_DOWN_AT_STARTUP"
    )
    chaos_enabled: bool = Field(default=False, alias="CHAOS_ENABLED")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @property
    def sync_database_url(self) -> str:
        # Used for sync tools like Alembic
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        return url

    @property
    def db_target(self) -> str:
        try:
            parsed = urlparse(self.database_url)
            host = parsed.hostname or "unknown"
            port = parsed.port or 5432
            return f"{host}:{port}"
        except Exception:
            return "unknown-db-host"

    @property
    def redis_target(self) -> str:
        try:
            parsed = urlparse(self.redis_url)
            host = parsed.hostname or "unknown"
            port = parsed.port or 6379
            return f"{host}:{port}"
        except Exception:
            return "unknown-redis-host"

    def redacted_dict(self) -> dict:
        data = self.model_dump()
        # Redact api_key
        data["api_key"] = "***REDACTED***"
        # Redact database password in database_url
        try:
            parsed = urlparse(self.database_url)
            if parsed.password:
                netloc = f"{parsed.username}:***@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                redacted_db = parsed._replace(netloc=netloc).geturl()
                data["database_url"] = redacted_db
        except Exception:
            data["database_url"] = "***REDACTED***"

        return data


def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        # Required configuration missing; fail fast with clear output
        err_json = f'{{"timestamp": "{None}", "level": "FATAL", "message": "Failed config: {e}"}}'
        print(err_json, file=sys.stderr)
        raise SystemExit(1) from e

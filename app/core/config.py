from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    database_url: str = Field(default="sqlite+aiosqlite:///./data/monitor.db")
    auto_create_schema: bool = Field(default=False)

    checker_default_timeout_seconds: float = Field(default=5.0)
    checker_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    )
    checker_max_response_chars: int = Field(default=500)
    transient_retry_attempts: int = Field(default=1)
    transient_retry_backoff_seconds: float = Field(default=0.5)
    state_transition_delay_seconds: int = Field(default=0)
    status_notification_interval_seconds: int = Field(default=900)

    scheduler_sync_seconds: int = Field(default=30)
    job_jitter_seconds: int = Field(default=3)
    url_check: str | None = Field(default=None)

    clickup_base_url: str = Field(default="https://api.clickup.com/api/v3")
    clickup_api_token: str | None = Field(default=None)
    clickup_workspace_id: str | None = Field(default=None)
    clickup_channel_id: str | None = Field(default=None)
    clickup_dm_user_id: str | None = Field(default=None)
    clickup_timeout_seconds: float = Field(default=10.0)

    @property
    def clickup_enabled(self) -> bool:
        has_target = bool(self.clickup_channel_id or self.clickup_dm_user_id)
        return bool(self.clickup_api_token and self.clickup_workspace_id and has_target)

    @property
    def clickup_mode(self) -> str:
        if self.clickup_channel_id:
            return "channel"
        if self.clickup_dm_user_id:
            return "dm"
        return "none"


def to_sync_database_url(database_url: str) -> str:
    """Convert async DB URL to sync URL for tools like Alembic."""

    return (
        database_url.replace("+aiosqlite", "")
        .replace("+asyncpg", "")
        .replace("+psycopg", "")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

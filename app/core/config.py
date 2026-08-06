import re
from functools import lru_cache
from typing import Self
from urllib.parse import urlparse, urlunparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_and_validate_url(url_str: str) -> str:
    cleaned = url_str.strip()
    if not cleaned:
        raise ValueError("URL entry cannot be empty")

    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise ValueError(f"Invalid URL: '{cleaned}'") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"Invalid URL scheme '{scheme}' for '{cleaned}'. Only http and https are allowed."
        )

    netloc = parsed.netloc.lower()
    if not netloc:
        raise ValueError(f"Invalid URL netloc for '{cleaned}'")

    path = parsed.path
    if not path or path == "/":
        path = "/"
    elif path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    normalized = urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))
    return normalized


def parse_url_checks(
    raw_url_checks: str | list[str] | None = None,
    raw_url_check: str | None = None,
) -> list[str]:
    raw_input: str | None = None

    if isinstance(raw_url_checks, list):
        raw_input = ",".join(raw_url_checks)
    elif isinstance(raw_url_checks, str) and raw_url_checks.strip():
        raw_input = raw_url_checks
    elif isinstance(raw_url_check, str) and raw_url_check.strip():
        raw_input = raw_url_check

    if not raw_input:
        return []

    entries = [part.strip() for part in raw_input.split(",") if part.strip()]
    if not entries:
        return []

    validated_urls: list[str] = []
    seen: set[str] = set()

    for entry in entries:
        norm_url = normalize_and_validate_url(entry)
        if norm_url not in seen:
            seen.add(norm_url)
            validated_urls.append(norm_url)

    return validated_urls


def get_env_monitor_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.split(":")[0]
    clean_host = re.sub(r"[^a-zA-Z0-9]", "-", host).strip("-").lower()
    path = parsed.path.strip("/")
    if path:
        clean_path = re.sub(r"[^a-zA-Z0-9]", "-", path).strip("-").lower()
        slug = f"{clean_host}-{clean_path}"
    else:
        slug = clean_host
    slug = re.sub(r"-+", "-", slug)
    return f"env-url-check-{slug}"


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
    url_check: str | None = Field(
        default=None,
        alias="URL_CHECK",
        description="Deprecated single URL fallback if URL_CHECKS is omitted.",
    )
    url_checks: str | None = Field(
        default=None,
        alias="URL_CHECKS",
        description="Comma-separated URLs to monitor (takes precedence over URL_CHECK).",
    )

    clickup_base_url: str = Field(default="https://api.clickup.com/api/v3")
    clickup_api_token: str | None = Field(default=None)
    clickup_workspace_id: str | None = Field(default=None)
    clickup_channel_id: str | None = Field(default=None)
    clickup_dm_user_id: str | None = Field(default=None)
    clickup_timeout_seconds: float = Field(default=10.0)

    @model_validator(mode="after")
    def validate_env_urls(self) -> Self:
        # Triggers URL parsing and validation upon settings instantiation.
        # Raises ValueError if any non-empty URL in URL_CHECKS or URL_CHECK is invalid.
        _ = self.parsed_url_checks
        return self

    @property
    def parsed_url_checks(self) -> list[str]:
        return parse_url_checks(self.url_checks, self.url_check)

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


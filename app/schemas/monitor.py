from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.models.enums import AlertType, MonitorHealthStatus


class MonitorBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: AnyHttpUrl
    method: str = Field(default="GET", min_length=3, max_length=10)

    interval_seconds: int = Field(default=30, ge=5, le=3600)
    timeout_seconds: float = Field(default=5.0, gt=0.1, le=60.0)

    expected_status_min: int = Field(default=200, ge=100, le=599)
    expected_status_max: int = Field(default=399, ge=100, le=599)
    content_substring: str | None = Field(default=None, max_length=2000)

    failure_threshold: int = Field(default=3, ge=1, le=20)
    recovery_threshold: int = Field(default=2, ge=1, le=20)
    cooldown_seconds: int = Field(default=900, ge=0, le=86_400)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()

    @field_validator("expected_status_max")
    @classmethod
    def validate_status_range(cls, value: int, info) -> int:
        min_value = info.data.get("expected_status_min", 100)
        if value < min_value:
            raise ValueError("expected_status_max must be >= expected_status_min")
        return value


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: AnyHttpUrl | None = None
    method: str | None = Field(default=None, min_length=3, max_length=10)

    interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    timeout_seconds: float | None = Field(default=None, gt=0.1, le=60.0)

    expected_status_min: int | None = Field(default=None, ge=100, le=599)
    expected_status_max: int | None = Field(default=None, ge=100, le=599)
    content_substring: str | None = Field(default=None, max_length=2000)

    failure_threshold: int | None = Field(default=None, ge=1, le=20)
    recovery_threshold: int | None = Field(default=None, ge=1, le=20)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86_400)

    active: bool | None = None

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.upper()


class MonitorRead(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    method: str

    interval_seconds: int
    timeout_seconds: float
    expected_status_min: int
    expected_status_max: int
    content_substring: str | None

    failure_threshold: int
    recovery_threshold: int
    cooldown_seconds: int

    active: bool
    last_checked_at: datetime | None
    last_status: MonitorHealthStatus
    consecutive_failures: int
    consecutive_successes: int
    last_notification_at: datetime | None
    last_alert_type: AlertType | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MonitorPauseResumeResponse(BaseModel):
    id: uuid.UUID
    active: bool
    last_status: MonitorHealthStatus

    model_config = {"from_attributes": True}

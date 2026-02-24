from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AlertType, MonitorHealthStatus


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False, default="GET")

    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    expected_status_min: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    expected_status_max: Mapped[int] = mapped_column(Integer, nullable=False, default=399)
    content_substring: Mapped[str | None] = mapped_column(Text, nullable=True)

    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    recovery_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[MonitorHealthStatus] = mapped_column(
        Enum(MonitorHealthStatus, native_enum=False),
        nullable=False,
        default=MonitorHealthStatus.UNKNOWN,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_notification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_alert_type: Mapped[AlertType | None] = mapped_column(
        Enum(AlertType, native_enum=False),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    check_results = relationship("CheckResult", back_populates="monitor", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="monitor", cascade="all, delete-orphan")

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    monitor = relationship("Monitor", back_populates="check_results")

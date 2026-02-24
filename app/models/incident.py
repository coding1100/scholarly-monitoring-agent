from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import IncidentStatus


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False),
        nullable=False,
        default=IncidentStatus.OPEN,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    opened_check_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("check_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_check_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("check_results.id", ondelete="SET NULL"),
        nullable=True,
    )

    clickup_chat_channel_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_notification_error: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    monitor = relationship("Monitor", back_populates="incidents")

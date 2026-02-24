from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import IncidentStatus


class IncidentRead(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    status: IncidentStatus
    started_at: datetime
    resolved_at: datetime | None

    opened_check_result_id: uuid.UUID | None
    resolved_check_result_id: uuid.UUID | None

    clickup_chat_channel_id: str | None
    last_notification_error: str | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

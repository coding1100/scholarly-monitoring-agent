from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CheckResultRead(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    checked_at: datetime
    success: bool

    status_code: int | None
    latency_ms: int | None
    error_type: str | None
    error_message: str | None
    reason: str
    response_excerpt: str | None

    model_config = {"from_attributes": True}

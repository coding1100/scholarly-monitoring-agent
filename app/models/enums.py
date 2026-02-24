from __future__ import annotations

import enum


class MonitorHealthStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    FAILING = "failing"
    PAUSED = "paused"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class AlertType(str, enum.Enum):
    FAILURE = "failure"
    RECOVERY = "recovery"

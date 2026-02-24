from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from app.models.enums import AlertType


class IncidentAction(str, Enum):
    NONE = "none"
    OPEN = "open"
    RESOLVE = "resolve"
    NOTIFY_PENDING_FAILURE = "notify_pending_failure"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_http_response(
    *,
    status_code: int,
    body_text: str,
    expected_min: int,
    expected_max: int,
    content_substring: str | None,
) -> tuple[bool, str]:
    if status_code < expected_min or status_code > expected_max:
        return False, f"status_code_out_of_range:{status_code}"

    if content_substring and content_substring not in body_text:
        return False, "content_substring_missing"

    return True, "ok"


def can_send_notification(
    *,
    last_notification_at: datetime | None,
    last_alert_type: AlertType | None,
    target_alert_type: AlertType,
    cooldown_seconds: int,
    now: datetime,
) -> bool:
    if last_notification_at is None:
        return True

    if last_alert_type != target_alert_type:
        return True

    now_utc = ensure_utc_datetime(now)
    last_notification_at_utc = ensure_utc_datetime(last_notification_at)
    elapsed = (now_utc - last_notification_at_utc).total_seconds()
    return elapsed >= cooldown_seconds


def decide_incident_action(
    *,
    check_success: bool,
    has_open_incident: bool,
    consecutive_failures: int,
    consecutive_successes: int,
    failure_threshold: int,
    recovery_threshold: int,
    can_send_failure_notification: bool,
) -> IncidentAction:
    if check_success:
        if has_open_incident and consecutive_successes >= recovery_threshold:
            return IncidentAction.RESOLVE
        return IncidentAction.NONE

    if has_open_incident:
        if can_send_failure_notification:
            return IncidentAction.NOTIFY_PENDING_FAILURE
        return IncidentAction.NONE

    if consecutive_failures >= failure_threshold:
        return IncidentAction.OPEN

    return IncidentAction.NONE


def ensure_utc_datetime(value: datetime) -> datetime:
    """
    Normalize datetimes to timezone-aware UTC.

    SQLite often returns naive datetimes even for timezone=True columns.
    """

    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def effective_transition_threshold(
    *,
    configured_threshold: int,
    interval_seconds: int,
    transition_window_seconds: int,
) -> int:
    """
    Compute effective threshold with a minimum sustained time window.

    Example: 900s window with 10s interval requires at least 90 consecutive checks.
    """

    safe_configured_threshold = max(1, configured_threshold)
    safe_interval_seconds = max(1, interval_seconds)
    safe_window_seconds = max(0, transition_window_seconds)

    if safe_window_seconds == 0:
        return safe_configured_threshold

    minimum_checks_for_window = math.ceil(safe_window_seconds / safe_interval_seconds)
    return max(safe_configured_threshold, minimum_checks_for_window)

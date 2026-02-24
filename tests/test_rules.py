from __future__ import annotations

from datetime import timedelta, timezone

from app.models.enums import AlertType
from app.services.rules import (
    IncidentAction,
    can_send_notification,
    decide_incident_action,
    effective_transition_threshold,
    evaluate_http_response,
    utcnow,
)


def test_evaluate_http_response_ok() -> None:
    success, reason = evaluate_http_response(
        status_code=200,
        body_text="service healthy",
        expected_min=200,
        expected_max=399,
        content_substring="healthy",
    )

    assert success is True
    assert reason == "ok"


def test_evaluate_http_response_content_missing() -> None:
    success, reason = evaluate_http_response(
        status_code=200,
        body_text="service ready",
        expected_min=200,
        expected_max=399,
        content_substring="healthy",
    )

    assert success is False
    assert reason == "content_substring_missing"


def test_can_send_notification_when_alert_type_changes() -> None:
    now = utcnow()

    allowed = can_send_notification(
        last_notification_at=now,
        last_alert_type=AlertType.FAILURE,
        target_alert_type=AlertType.RECOVERY,
        cooldown_seconds=900,
        now=now,
    )

    assert allowed is True


def test_can_send_notification_respects_cooldown_for_same_type() -> None:
    now = utcnow()

    blocked = can_send_notification(
        last_notification_at=now - timedelta(seconds=100),
        last_alert_type=AlertType.FAILURE,
        target_alert_type=AlertType.FAILURE,
        cooldown_seconds=900,
        now=now,
    )

    assert blocked is False


def test_can_send_notification_handles_naive_db_timestamp() -> None:
    now = utcnow()
    naive_last_notification = (now - timedelta(seconds=100)).replace(tzinfo=None)

    blocked = can_send_notification(
        last_notification_at=naive_last_notification,
        last_alert_type=AlertType.FAILURE,
        target_alert_type=AlertType.FAILURE,
        cooldown_seconds=900,
        now=now,
    )

    assert blocked is False


def test_can_send_notification_handles_naive_now() -> None:
    now = utcnow()
    aware_last_notification = now - timedelta(seconds=1200)
    naive_now = now.replace(tzinfo=None)

    allowed = can_send_notification(
        last_notification_at=aware_last_notification.astimezone(timezone.utc),
        last_alert_type=AlertType.FAILURE,
        target_alert_type=AlertType.FAILURE,
        cooldown_seconds=900,
        now=naive_now,
    )

    assert allowed is True


def test_decide_incident_action_open_on_threshold() -> None:
    action = decide_incident_action(
        check_success=False,
        has_open_incident=False,
        consecutive_failures=3,
        consecutive_successes=0,
        failure_threshold=3,
        recovery_threshold=2,
        can_send_failure_notification=True,
    )

    assert action == IncidentAction.OPEN


def test_decide_incident_action_resolve_on_recovery_threshold() -> None:
    action = decide_incident_action(
        check_success=True,
        has_open_incident=True,
        consecutive_failures=0,
        consecutive_successes=2,
        failure_threshold=3,
        recovery_threshold=2,
        can_send_failure_notification=False,
    )

    assert action == IncidentAction.RESOLVE


def test_decide_incident_action_notify_open_incident_when_cooldown_allows() -> None:
    action = decide_incident_action(
        check_success=False,
        has_open_incident=True,
        consecutive_failures=5,
        consecutive_successes=0,
        failure_threshold=3,
        recovery_threshold=2,
        can_send_failure_notification=True,
    )

    assert action == IncidentAction.NOTIFY_PENDING_FAILURE


def test_effective_transition_threshold_uses_15_min_window() -> None:
    threshold = effective_transition_threshold(
        configured_threshold=1,
        interval_seconds=10,
        transition_window_seconds=900,
    )
    assert threshold == 90


def test_effective_transition_threshold_keeps_higher_configured_value() -> None:
    threshold = effective_transition_threshold(
        configured_threshold=120,
        interval_seconds=10,
        transition_window_seconds=900,
    )
    assert threshold == 120


def test_effective_transition_threshold_allows_disable_with_zero_window() -> None:
    threshold = effective_transition_threshold(
        configured_threshold=3,
        interval_seconds=10,
        transition_window_seconds=0,
    )
    assert threshold == 3

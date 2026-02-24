from __future__ import annotations

from app.core.config import get_settings
from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.check_result import CheckResult
from app.models.enums import AlertType, IncidentStatus, MonitorHealthStatus
from app.models.incident import Incident
from app.models.monitor import Monitor
from app.services.checker import WebsiteChecker
from app.services.clickup import ClickUpNotifier
from app.services.rules import (
    IncidentAction,
    can_send_notification,
    decide_incident_action,
    effective_transition_threshold,
    utcnow,
)


def open_incident_query(monitor_id) -> Select[tuple[Incident]]:
    return (
        select(Incident)
        .where(Incident.monitor_id == monitor_id, Incident.status == IncidentStatus.OPEN)
        .order_by(desc(Incident.started_at))
        .limit(1)
    )


async def run_monitor_cycle(
    *,
    session: AsyncSession,
    monitor: Monitor,
    checker: WebsiteChecker,
    notifier: ClickUpNotifier,
) -> None:
    settings = get_settings()
    notification_interval_seconds = settings.status_notification_interval_seconds
    check_outcome = await checker.run(monitor)
    now = utcnow()

    check_result = CheckResult(
        monitor_id=monitor.id,
        checked_at=now,
        success=check_outcome.success,
        status_code=check_outcome.status_code,
        latency_ms=check_outcome.latency_ms,
        error_type=check_outcome.error_type,
        error_message=check_outcome.error_message,
        reason=check_outcome.reason,
        response_excerpt=check_outcome.response_excerpt,
    )
    session.add(check_result)
    await session.flush()

    monitor.last_checked_at = now

    if check_outcome.success:
        monitor.consecutive_successes += 1
        monitor.consecutive_failures = 0
        if monitor.active:
            monitor.last_status = MonitorHealthStatus.HEALTHY
    else:
        monitor.consecutive_failures += 1
        monitor.consecutive_successes = 0
        if monitor.active:
            monitor.last_status = MonitorHealthStatus.FAILING

    open_incident_result = await session.execute(open_incident_query(monitor.id))
    open_incident = open_incident_result.scalar_one_or_none()

    can_notify_failure = can_send_notification(
        last_notification_at=monitor.last_notification_at,
        last_alert_type=monitor.last_alert_type,
        target_alert_type=AlertType.FAILURE,
        cooldown_seconds=notification_interval_seconds,
        now=now,
    )

    effective_failure_threshold = effective_transition_threshold(
        configured_threshold=monitor.failure_threshold,
        interval_seconds=monitor.interval_seconds,
        transition_window_seconds=settings.state_transition_delay_seconds,
    )
    effective_recovery_threshold = effective_transition_threshold(
        configured_threshold=monitor.recovery_threshold,
        interval_seconds=monitor.interval_seconds,
        transition_window_seconds=settings.state_transition_delay_seconds,
    )

    action = decide_incident_action(
        check_success=check_outcome.success,
        has_open_incident=open_incident is not None,
        consecutive_failures=monitor.consecutive_failures,
        consecutive_successes=monitor.consecutive_successes,
        failure_threshold=effective_failure_threshold,
        recovery_threshold=effective_recovery_threshold,
        can_send_failure_notification=can_notify_failure,
    )

    if action == IncidentAction.OPEN:
        incident = Incident(
            monitor_id=monitor.id,
            status=IncidentStatus.OPEN,
            started_at=now,
            opened_check_result_id=check_result.id,
        )
        session.add(incident)
        await session.flush()
        await _notify_failure_if_allowed(
            monitor=monitor,
            incident=incident,
            check_result=check_result,
            notifier=notifier,
            now=now,
            can_notify=can_notify_failure,
        )
        return

    if action == IncidentAction.NOTIFY_PENDING_FAILURE and open_incident is not None:
        await _notify_failure_if_allowed(
            monitor=monitor,
            incident=open_incident,
            check_result=check_result,
            notifier=notifier,
            now=now,
            can_notify=can_notify_failure,
        )
        return

    if action == IncidentAction.RESOLVE and open_incident is not None:
        open_incident.status = IncidentStatus.RESOLVED
        open_incident.resolved_at = now
        open_incident.resolved_check_result_id = check_result.id
        await _notify_recovery_if_allowed(
            monitor=monitor,
            incident=open_incident,
            check_result=check_result,
            notifier=notifier,
            now=now,
            notification_interval_seconds=notification_interval_seconds,
        )
        return

    if check_outcome.success and open_incident is None:
        await _notify_recovery_status_if_allowed(
            monitor=monitor,
            check_result=check_result,
            notifier=notifier,
            now=now,
            notification_interval_seconds=notification_interval_seconds,
        )
        return


async def _notify_failure_if_allowed(
    *,
    monitor: Monitor,
    incident: Incident,
    check_result: CheckResult,
    notifier: ClickUpNotifier,
    now,
    can_notify: bool,
) -> None:
    if not can_notify:
        incident.last_notification_error = "suppressed_by_cooldown"
        return

    if not notifier.enabled:
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.FAILURE
        incident.last_notification_error = "clickup_disabled"
        return

    try:
        channel_id = await notifier.send_failure_alert(
            monitor=monitor,
            incident=incident,
            check_result=check_result,
        )
        incident.clickup_chat_channel_id = channel_id
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.FAILURE
        incident.last_notification_error = None
    except Exception as exc:
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.FAILURE
        incident.last_notification_error = str(exc)
        logger.exception(
            "clickup_failure_chat_notification_error",
            monitor_id=str(monitor.id),
            incident_id=str(incident.id),
        )


async def _notify_recovery_if_allowed(
    *,
    monitor: Monitor,
    incident: Incident,
    check_result: CheckResult,
    notifier: ClickUpNotifier,
    now,
    notification_interval_seconds: int,
) -> None:
    can_notify = can_send_notification(
        last_notification_at=monitor.last_notification_at,
        last_alert_type=monitor.last_alert_type,
        target_alert_type=AlertType.RECOVERY,
        cooldown_seconds=notification_interval_seconds,
        now=now,
    )
    if not can_notify:
        incident.last_notification_error = "recovery_suppressed_by_cooldown"
        return

    if not notifier.enabled:
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.RECOVERY
        incident.last_notification_error = "clickup_disabled"
        return

    try:
        channel_id = await notifier.send_recovery_alert(
            monitor=monitor,
            incident=incident,
            check_result=check_result,
        )
        if channel_id and not incident.clickup_chat_channel_id:
            incident.clickup_chat_channel_id = channel_id
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.RECOVERY
        incident.last_notification_error = None
    except Exception as exc:
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.RECOVERY
        incident.last_notification_error = str(exc)
        logger.exception(
            "clickup_recovery_chat_notification_error",
            monitor_id=str(monitor.id),
            incident_id=str(incident.id),
            channel_id=incident.clickup_chat_channel_id,
        )


async def _notify_recovery_status_if_allowed(
    *,
    monitor: Monitor,
    check_result: CheckResult,
    notifier: ClickUpNotifier,
    now,
    notification_interval_seconds: int,
) -> None:
    can_notify = can_send_notification(
        last_notification_at=monitor.last_notification_at,
        last_alert_type=monitor.last_alert_type,
        target_alert_type=AlertType.RECOVERY,
        cooldown_seconds=notification_interval_seconds,
        now=now,
    )
    if not can_notify:
        return

    if not notifier.enabled:
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.RECOVERY
        return

    try:
        await notifier.send_recovery_alert(
            monitor=monitor,
            incident=None,
            check_result=check_result,
        )
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.RECOVERY
    except Exception:
        monitor.last_notification_at = now
        monitor.last_alert_type = AlertType.RECOVERY
        logger.exception(
            "clickup_recovery_status_chat_notification_error",
            monitor_id=str(monitor.id),
        )

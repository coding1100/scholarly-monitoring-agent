from __future__ import annotations

import uuid
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import Settings, get_env_monitor_name, get_settings, normalize_and_validate_url
from app.core.logging import logger
from app.db.session import AsyncSessionFactory
from app.models.enums import MonitorHealthStatus
from app.models.monitor import Monitor
from app.services.checker import WebsiteChecker
from app.services.clickup import ClickUpNotifier
from app.services.monitoring import run_monitor_cycle

ENV_URL_CHECK_MONITOR_NAME = "env-url-check"


@dataclass(slots=True)
class MonitorScheduleConfig:
    id: uuid.UUID
    interval_seconds: int
    name: str
    url: str

    @property
    def source_type(self) -> str:
        return (
            "environment"
            if self.name == ENV_URL_CHECK_MONITOR_NAME or self.name.startswith("env-url-check-")
            else "database"
        )


class MonitorJobScheduler:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.checker = WebsiteChecker(self.settings)
        self.notifier = ClickUpNotifier(self.settings)
        self._sync_job_id = "sync_monitors"

    async def start(self) -> None:
        self.scheduler.add_job(
            self.sync_monitors,
            "interval",
            seconds=self.settings.scheduler_sync_seconds,
            id=self._sync_job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        await self.sync_monitors()
        logger.info("worker_scheduler_started")

    async def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        await self.checker.close()
        await self.notifier.close()
        logger.info("worker_scheduler_stopped")

    async def sync_monitors(self) -> None:
        await self._sync_env_url_check_monitors()
        monitor_configs = await self._fetch_active_monitors()
        wanted_job_ids: set[str] = set()

        for config in monitor_configs:
            job_id = self._monitor_job_id(config.id)
            wanted_job_ids.add(job_id)
            await self._upsert_monitor_job(config=config, job_id=job_id)

        for job in self.scheduler.get_jobs():
            if job.id == self._sync_job_id:
                continue
            if job.id not in wanted_job_ids:
                self.scheduler.remove_job(job.id)
                logger.info("monitor_job_removed", job_id=job.id)

    async def _upsert_monitor_job(self, *, config: MonitorScheduleConfig, job_id: str) -> None:
        existing = self.scheduler.get_job(job_id)
        if existing is None:
            self.scheduler.add_job(
                self.run_monitor_job,
                "interval",
                seconds=config.interval_seconds,
                jitter=self.settings.job_jitter_seconds,
                id=job_id,
                args=[str(config.id)],
                max_instances=1,
                coalesce=True,
                misfire_grace_time=max(5, config.interval_seconds),
                replace_existing=False,
            )
            logger.info(
                "monitor_job_added",
                monitor_id=str(config.id),
                url=config.url,
                source_type=config.source_type,
                interval_seconds=config.interval_seconds,
            )
            return

        trigger = existing.trigger
        current_interval = None
        if hasattr(trigger, "interval"):
            current_interval = int(trigger.interval.total_seconds())

        if current_interval != config.interval_seconds:
            self.scheduler.reschedule_job(
                job_id,
                trigger="interval",
                seconds=config.interval_seconds,
                jitter=self.settings.job_jitter_seconds,
            )
            logger.info(
                "monitor_job_rescheduled",
                monitor_id=str(config.id),
                url=config.url,
                source_type=config.source_type,
                interval_seconds=config.interval_seconds,
            )

    async def run_monitor_job(self, monitor_id: str) -> None:
        parsed_id = uuid.UUID(monitor_id)
        async with AsyncSessionFactory() as session:
            monitor = await session.get(Monitor, parsed_id)
            if monitor is None or not monitor.active:
                return
            try:
                await run_monitor_cycle(
                    session=session,
                    monitor=monitor,
                    checker=self.checker,
                    notifier=self.notifier,
                )
                await session.commit()
                source_type = (
                    "environment"
                    if monitor.name == ENV_URL_CHECK_MONITOR_NAME
                    or monitor.name.startswith("env-url-check-")
                    else "database"
                )
                logger.info(
                    "monitor_job_executed",
                    monitor_id=monitor_id,
                    url=monitor.url,
                    source_type=source_type,
                    success=True,
                    status=str(monitor.last_status.value),
                )
            except Exception:
                await session.rollback()
                logger.exception("monitor_job_execution_error", monitor_id=monitor_id)

    async def _fetch_active_monitors(self) -> list[MonitorScheduleConfig]:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(Monitor.id, Monitor.interval_seconds, Monitor.name, Monitor.url).where(
                    Monitor.active.is_(True)
                )
            )
            rows = result.all()
        return [
            MonitorScheduleConfig(
                id=row.id,
                interval_seconds=row.interval_seconds,
                name=row.name,
                url=row.url,
            )
            for row in rows
        ]

    @staticmethod
    def _monitor_job_id(monitor_id: uuid.UUID) -> str:
        return f"monitor:{monitor_id}"

    async def _sync_env_url_check_monitors(self) -> None:
        configured_urls = self.settings.parsed_url_checks

        async with AsyncSessionFactory() as session:
            stmt = select(Monitor).where(
                (Monitor.name == ENV_URL_CHECK_MONITOR_NAME)
                | (Monitor.name.like("env-url-check-%"))
            )
            result = await session.execute(stmt)
            existing_env_monitors = list(result.scalars().all())

            existing_by_name = {m.name: m for m in existing_env_monitors}
            existing_by_url: dict[str, Monitor] = {}
            for m in existing_env_monitors:
                if m.url:
                    try:
                        norm = normalize_and_validate_url(m.url)
                        existing_by_url[norm] = m
                    except ValueError:
                        pass

            legacy_monitor = existing_by_name.get(ENV_URL_CHECK_MONITOR_NAME)
            configured_names: set[str] = set()

            for url in configured_urls:
                target_name = get_env_monitor_name(url)
                configured_names.add(target_name)

                monitor = existing_by_name.get(target_name) or existing_by_url.get(url)

                if monitor is None and legacy_monitor is not None:
                    try:
                        legacy_url_norm = normalize_and_validate_url(legacy_monitor.url)
                        if legacy_url_norm == url:
                            monitor = legacy_monitor
                            logger.info(
                                "env_url_check_legacy_monitor_migrated",
                                old_name=ENV_URL_CHECK_MONITOR_NAME,
                                new_name=target_name,
                                url=url,
                            )
                    except ValueError:
                        pass

                if monitor is None:
                    monitor = Monitor(
                        name=target_name,
                        url=url,
                        method="GET",
                        interval_seconds=30,
                        timeout_seconds=self.settings.checker_default_timeout_seconds,
                        expected_status_min=200,
                        expected_status_max=399,
                        failure_threshold=3,
                        recovery_threshold=2,
                        cooldown_seconds=self.settings.status_notification_interval_seconds,
                        active=True,
                        last_status=MonitorHealthStatus.UNKNOWN,
                    )
                    session.add(monitor)
                    await session.commit()
                    existing_by_name[target_name] = monitor
                    existing_by_url[url] = monitor
                    logger.info(
                        "env_url_check_monitor_created",
                        url=url,
                        monitor_id=str(monitor.id),
                    )
                else:
                    changed = False
                    if monitor.name != target_name:
                        monitor.name = target_name
                        changed = True
                    if monitor.url != url:
                        monitor.url = url
                        monitor.consecutive_failures = 0
                        monitor.consecutive_successes = 0
                        monitor.last_status = MonitorHealthStatus.UNKNOWN
                        changed = True
                    if not monitor.active:
                        monitor.active = True
                        monitor.last_status = MonitorHealthStatus.UNKNOWN
                        monitor.consecutive_failures = 0
                        monitor.consecutive_successes = 0
                        changed = True

                    if changed:
                        await session.commit()
                        logger.info(
                            "env_url_check_monitor_updated",
                            url=url,
                            monitor_id=str(monitor.id),
                            active=monitor.active,
                        )

            for monitor in existing_env_monitors:
                if monitor.name not in configured_names:
                    if monitor.active:
                        monitor.active = False
                        monitor.last_status = MonitorHealthStatus.PAUSED
                        await session.commit()
                        logger.info(
                            "env_url_check_monitor_paused",
                            url=monitor.url,
                            monitor_id=str(monitor.id),
                        )

        logger.info(
            "environment_monitors_synchronized",
            environment_monitor_count=len(configured_urls),
        )


from __future__ import annotations

import uuid
from typing import Any
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.models.enums import MonitorHealthStatus
from app.models.monitor import Monitor
import app.db.session as session_module
from app.worker.scheduler import MonitorJobScheduler


from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
async def setup_test_db(monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """Setup a fresh isolated SQLite in-memory database for each test and patch AsyncSessionFactory."""
    db_url = "sqlite+aiosqlite:///:memory:"

    test_engine = create_async_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(session_module, "AsyncSessionFactory", async_session)
    monkeypatch.setattr("app.worker.scheduler.AsyncSessionFactory", async_session)

    async with async_session() as session:
        yield session

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_creates_two_environment_monitors() -> None:
    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)

    await scheduler.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    assert len(monitors) == 2
    names = {m.name for m in monitors}
    urls = {m.url for m in monitors}
    ids = {m.id for m in monitors}

    assert names == {"env-url-check-scholarlyhelp-com", "env-url-check-mindrind-net"}
    assert urls == {"https://scholarlyhelp.com/", "https://mindrind.net/"}
    assert len(ids) == 2


@pytest.mark.asyncio
async def test_scheduler_duplicate_prevention_on_restart_and_reorder() -> None:
    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)

    # First sync
    await scheduler.sync_monitors()

    # Second sync (restart simulation)
    await scheduler.sync_monitors()

    # Reorder URLs sync
    reordered_settings = Settings(
        URL_CHECKS="https://mindrind.net/,https://scholarlyhelp.com/"
    )
    scheduler_reordered = MonitorJobScheduler(settings=reordered_settings)
    await scheduler_reordered.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    assert len(monitors) == 2


@pytest.mark.asyncio
async def test_scheduler_migrates_legacy_env_url_check_monitor() -> None:
    # Insert legacy env-url-check monitor
    legacy_id = uuid.uuid4()
    async with session_module.AsyncSessionFactory() as session:
        legacy_monitor = Monitor(
            id=legacy_id,
            name="env-url-check",
            url="https://scholarlyhelp.com/",
            method="GET",
            active=True,
            last_status=MonitorHealthStatus.HEALTHY,
        )
        session.add(legacy_monitor)
        await session.commit()

    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)
    await scheduler.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    assert len(monitors) == 2
    migrated = next(m for m in monitors if m.url == "https://scholarlyhelp.com/")
    assert migrated.id == legacy_id
    assert migrated.name == "env-url-check-scholarlyhelp-com"


@pytest.mark.asyncio
async def test_scheduler_preserves_api_created_monitors() -> None:
    api_monitor_id = uuid.uuid4()
    async with session_module.AsyncSessionFactory() as session:
        api_monitor = Monitor(
            id=api_monitor_id,
            name="My API Monitor",
            url="https://api.example.com/health",
            method="GET",
            active=True,
            last_status=MonitorHealthStatus.HEALTHY,
        )
        session.add(api_monitor)
        await session.commit()

    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)
    await scheduler.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    assert len(monitors) == 3
    api_m = next(m for m in monitors if m.id == api_monitor_id)
    assert api_m.name == "My API Monitor"
    assert api_m.active is True


@pytest.mark.asyncio
async def test_scheduler_pauses_removed_environment_url() -> None:
    # Sync with 2 URLs
    settings_2 = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler_2 = MonitorJobScheduler(settings=settings_2)
    await scheduler_2.sync_monitors()

    # Now update config with only 1 URL
    settings_1 = Settings(URL_CHECKS="https://scholarlyhelp.com/")
    scheduler_1 = MonitorJobScheduler(settings=settings_1)
    await scheduler_1.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    scholarly = next(m for m in monitors if m.url == "https://scholarlyhelp.com/")
    mindrind = next(m for m in monitors if m.url == "https://mindrind.net/")

    assert scholarly.active is True
    assert mindrind.active is False
    assert mindrind.last_status == MonitorHealthStatus.PAUSED


@pytest.mark.asyncio
async def test_scheduler_jobs_created_per_monitor() -> None:
    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)

    await scheduler.start()

    jobs = scheduler.scheduler.get_jobs()
    # 1 sync job + 2 monitor jobs = 3 jobs
    assert len(jobs) == 3
    job_ids = {j.id for j in jobs}
    assert "sync_monitors" in job_ids

    await scheduler.stop()


@pytest.mark.asyncio
async def test_integration_both_urls_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)
    await scheduler.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    # Mock HTTP response to 200 OK for both URLs
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="OK")

    transport = httpx.MockTransport(mock_handler)
    mock_client = httpx.AsyncClient(transport=transport)
    scheduler.checker._client = mock_client

    for m in monitors:
        await scheduler.run_monitor_job(str(m.id))

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        updated_monitors = list(result.scalars().all())

    for m in updated_monitors:
        assert m.last_status == MonitorHealthStatus.HEALTHY
        assert m.consecutive_failures == 0


@pytest.mark.asyncio
async def test_integration_independent_monitor_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(URL_CHECKS="https://scholarlyhelp.com/,https://mindrind.net/")
    scheduler = MonitorJobScheduler(settings=settings)
    await scheduler.sync_monitors()

    async with session_module.AsyncSessionFactory() as session:
        result = await session.execute(select(Monitor))
        monitors = list(result.scalars().all())

    scholarly_m = next(m for m in monitors if "scholarlyhelp" in m.url)
    mindrind_m = next(m for m in monitors if "mindrind" in m.url)

    # Mock HTTP transport: scholarlyhelp returns 200, mindrind returns 500
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if "scholarlyhelp.com" in str(request.url):
            return httpx.Response(200, text="Healthy Service")
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(mock_handler)
    mock_client = httpx.AsyncClient(transport=transport)
    scheduler.checker._client = mock_client

    # Run check cycles 3 times (reaching failure_threshold = 3)
    for _ in range(3):
        await scheduler.run_monitor_job(str(scholarly_m.id))
        await scheduler.run_monitor_job(str(mindrind_m.id))

    async with session_module.AsyncSessionFactory() as session:
        scholarly_refreshed = await session.get(Monitor, scholarly_m.id)
        mindrind_refreshed = await session.get(Monitor, mindrind_m.id)

    assert scholarly_refreshed is not None
    assert mindrind_refreshed is not None

    assert scholarly_refreshed.last_status == MonitorHealthStatus.HEALTHY
    assert scholarly_refreshed.consecutive_failures == 0

    assert mindrind_refreshed.last_status == MonitorHealthStatus.FAILING
    assert mindrind_refreshed.consecutive_failures == 3

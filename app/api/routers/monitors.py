from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session_dependency
from app.models.check_result import CheckResult
from app.models.enums import MonitorHealthStatus
from app.models.monitor import Monitor
from app.schemas.check_result import CheckResultRead
from app.schemas.monitor import (
    MonitorCreate,
    MonitorPauseResumeResponse,
    MonitorRead,
    MonitorUpdate,
)

router = APIRouter(prefix="/monitors", tags=["monitors"])


async def _get_monitor_or_404(session: AsyncSession, monitor_id: uuid.UUID) -> Monitor:
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found",
        )
    return monitor


@router.post("", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    payload: MonitorCreate,
    session: AsyncSession = Depends(db_session_dependency),
) -> Monitor:
    monitor = Monitor(
        name=payload.name,
        url=str(payload.url),
        method=payload.method,
        interval_seconds=payload.interval_seconds,
        timeout_seconds=payload.timeout_seconds,
        expected_status_min=payload.expected_status_min,
        expected_status_max=payload.expected_status_max,
        content_substring=payload.content_substring,
        failure_threshold=payload.failure_threshold,
        recovery_threshold=payload.recovery_threshold,
        cooldown_seconds=payload.cooldown_seconds,
        active=True,
    )

    session.add(monitor)
    await session.commit()
    await session.refresh(monitor)
    return monitor


@router.get("", response_model=list[MonitorRead])
async def list_monitors(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session_dependency),
) -> list[Monitor]:
    stmt = (
        select(Monitor)
        .order_by(desc(Monitor.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{monitor_id}", response_model=MonitorRead)
async def get_monitor(
    monitor_id: uuid.UUID,
    session: AsyncSession = Depends(db_session_dependency),
) -> Monitor:
    return await _get_monitor_or_404(session, monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorRead)
async def update_monitor(
    monitor_id: uuid.UUID,
    payload: MonitorUpdate,
    session: AsyncSession = Depends(db_session_dependency),
) -> Monitor:
    monitor = await _get_monitor_or_404(session, monitor_id)
    updates = payload.model_dump(exclude_unset=True)

    if "url" in updates and updates["url"] is not None:
        updates["url"] = str(updates["url"])

    min_status = updates.get("expected_status_min", monitor.expected_status_min)
    max_status = updates.get("expected_status_max", monitor.expected_status_max)
    if max_status < min_status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_status_max must be >= expected_status_min",
        )

    for field, value in updates.items():
        setattr(monitor, field, value)

    await session.commit()
    await session.refresh(monitor)
    return monitor


@router.post("/{monitor_id}/pause", response_model=MonitorPauseResumeResponse)
async def pause_monitor(
    monitor_id: uuid.UUID,
    session: AsyncSession = Depends(db_session_dependency),
) -> Monitor:
    monitor = await _get_monitor_or_404(session, monitor_id)
    monitor.active = False
    monitor.last_status = MonitorHealthStatus.PAUSED
    await session.commit()
    await session.refresh(monitor)
    return monitor


@router.post("/{monitor_id}/resume", response_model=MonitorPauseResumeResponse)
async def resume_monitor(
    monitor_id: uuid.UUID,
    session: AsyncSession = Depends(db_session_dependency),
) -> Monitor:
    monitor = await _get_monitor_or_404(session, monitor_id)
    monitor.active = True
    monitor.last_status = MonitorHealthStatus.UNKNOWN
    monitor.consecutive_failures = 0
    monitor.consecutive_successes = 0
    await session.commit()
    await session.refresh(monitor)
    return monitor


@router.get("/{monitor_id}/history", response_model=list[CheckResultRead])
async def monitor_history(
    monitor_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(db_session_dependency),
) -> list[CheckResult]:
    await _get_monitor_or_404(session, monitor_id)
    stmt = (
        select(CheckResult)
        .where(CheckResult.monitor_id == monitor_id)
        .order_by(desc(CheckResult.checked_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

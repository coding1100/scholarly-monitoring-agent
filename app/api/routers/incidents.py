from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session_dependency
from app.models.enums import IncidentStatus
from app.models.incident import Incident
from app.schemas.incident import IncidentRead

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/open", response_model=list[IncidentRead])
async def list_open_incidents(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(db_session_dependency),
) -> list[Incident]:
    stmt = (
        select(Incident)
        .where(Incident.status == IncidentStatus.OPEN)
        .order_by(desc(Incident.started_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("", response_model=list[IncidentRead])
async def list_incidents(
    status: IncidentStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session_dependency),
) -> list[Incident]:
    stmt = select(Incident)
    if status is not None:
        stmt = stmt.where(Incident.status == status)

    stmt = stmt.order_by(desc(Incident.started_at)).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())

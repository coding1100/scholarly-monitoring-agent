from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "environment": settings.app_env}

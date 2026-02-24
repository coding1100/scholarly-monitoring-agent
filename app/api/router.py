from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.health import router as health_router
from app.api.routers.incidents import router as incidents_router
from app.api.routers.monitors import router as monitors_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(monitors_router)
api_router.include_router(incidents_router)

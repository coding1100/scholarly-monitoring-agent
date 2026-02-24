from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import logger, setup_logging
from app.db.session import dispose_engine, ensure_data_dir, init_schema_if_needed


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    ensure_data_dir()
    await init_schema_if_needed()
    logger.info("api_startup")
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("api_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Site Watch Agent API",
        version="0.1.0",
        description="Control plane API for website monitoring and incident management.",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.state.settings = settings
    return app


app = create_app()

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import logger
from app.db.base import Base


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def ensure_data_dir() -> None:
    """Create local sqlite directory if needed."""

    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(parents=True, exist_ok=True)


async def init_schema_if_needed() -> None:
    """Optional local bootstrap for schema creation."""

    if not settings.auto_create_schema:
        return

    ensure_data_dir()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("schema_initialized", auto_create_schema=True)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    session = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()

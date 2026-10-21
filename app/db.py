import asyncio
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger("linkpulse")

_engine = None
_sessionmaker = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_health(timeout: float = 1.0) -> tuple[bool, Optional[str]]:
    """Checks PostgreSQL connectivity with timeout.
    Returns (True, None) if healthy, or (False, error_message) if unhealthy.
    """
    settings = get_settings()
    engine = get_engine()
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        target = settings.db_target
        err_msg = f"Failed to connect to PostgreSQL at {target}: {exc}"
        logger.error(err_msg, extra={"target": target, "error": str(exc)})
        return False, str(exc)

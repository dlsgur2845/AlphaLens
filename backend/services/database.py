"""PostgreSQL 비동기 데이터베이스 연결 관리."""
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

logger = logging.getLogger(__name__)

engine = None
async_session_factory = None


class Base(DeclarativeBase):
    pass


async def init_db():
    """DB 엔진 초기화. database_url이 비어있으면 스킵."""
    global engine, async_session_factory
    if not settings.database_url:
        logger.info("DATABASE_URL not set, skipping DB initialization")
        return
    engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=10)
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    logger.info("Database engine initialized")


async def close_db():
    """DB 엔진 종료."""
    global engine
    if engine:
        await engine.dispose()
        logger.info("Database engine closed")


@asynccontextmanager
async def get_session():
    """비동기 세션 컨텍스트 매니저."""
    if async_session_factory is None:
        raise RuntimeError("Database not initialized")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def is_db_available() -> bool:
    """DB 사용 가능 여부."""
    return engine is not None

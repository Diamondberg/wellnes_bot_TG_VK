"""
Подключение к PostgreSQL.

Использование:
    from db.engine import async_session_maker

    async with async_session_maker() as session:
        # ... работа с БД ...
        await session.commit()
"""

import logging
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings

logger = logging.getLogger(__name__)


# Асинхронный движок к PostgreSQL.
# echo=False — не логируем каждый SQL-запрос (включи True для отладки).
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # проверять соединение перед использованием
    pool_size=5,
    max_overflow=10,
)


# Фабрика сессий — каждый "with" даст новую сессию.
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # после commit() объекты остаются доступными
)


async def check_connection() -> bool:
    """
    Проверка что БД доступна. Используется при старте приложения.
    Возвращает True если ОК, иначе кидает исключение.
    """
    from sqlalchemy import text

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        value = result.scalar()
        if value != 1:
            raise RuntimeError(f"DB sanity check failed, got {value!r}")
    logger.info("✅ Подключение к PostgreSQL установлено")
    return True

"""
FastAPI Dependencies (зависимости).

Это "помощники", которые FastAPI автоматически вызывает перед endpoint'ом
и подсовывает результат как параметр функции.

Например:
    @router.post("/test/submit")
    async def submit(
        data: SubmitIn,
        session: AsyncSession = Depends(get_db_session),
        tenant: Tenant = Depends(get_current_tenant),
    ):
        ...

FastAPI сам:
  1. Создаст session через get_db_session() (с автоматическим закрытием)
  2. Найдёт tenant через get_current_tenant() (с кэшем — см. ниже)
  3. Передаст всё это в наш endpoint
"""

import logging
from functools import lru_cache
from typing import AsyncIterator

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.engine import async_session_maker
from db.models import Tenant
from db.repository import get_tenant_by_code

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  Сессия БД
# ════════════════════════════════════════════════════════════
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    Создаёт сессию БД для одного HTTP-запроса.

    Используется через:
        session: AsyncSession = Depends(get_db_session)

    Сессия автоматически закрывается после завершения запроса.
    Если в endpoint'е была ошибка — транзакция откатывается.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ════════════════════════════════════════════════════════════
#  Tenant (арендатор)
# ════════════════════════════════════════════════════════════
async def get_current_tenant(
    session: AsyncSession = Depends(get_db_session),
) -> Tenant:
    """
    Возвращает текущего арендатора.

    Сейчас: всегда тот, чей TENANT_CODE прописан в .env.
    В будущем (SaaS): будет определяться по домену запроса / API-ключу.

    Если tenant не найден в БД — это серьёзная ошибка конфигурации,
    возвращаем 500.
    """
    tenant = await get_tenant_by_code(session, settings.tenant_code)
    if tenant is None:
        logger.error(
            f"❌ Tenant с кодом '{settings.tenant_code}' не найден в БД! "
            "Возможно ты не запустил check_setup.py после миграции."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant configuration error",
        )
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is temporarily disabled by administrator",
        )
    return tenant

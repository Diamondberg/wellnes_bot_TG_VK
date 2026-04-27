"""
Health-check endpoint.

Endpoint:
    GET /api/health   → {"status": "ok", "db": "ok"}

Проверяет:
    - что FastAPI вообще отвечает
    - что подключение к БД живое (быстрый SELECT 1)

Если БД недоступна — вернёт HTTP 503 с пояснением.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from db.engine import async_session_maker

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Схема ответа ───────────────────────────────────────────
class HealthResponse(BaseModel):
    """Что возвращает /api/health."""
    status: str
    db: str
    server_time_utc: str
    version: str = "0.1.0"


# ─── Endpoint ───────────────────────────────────────────────
@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка работоспособности",
)
async def health_check() -> HealthResponse:
    """
    Проверяет: жив ли API и доступна ли БД.

    Возвращает 200 OK если всё хорошо.
    Возвращает 503 Service Unavailable если БД лежит.
    """
    # Проверяем БД быстрым запросом
    db_status = "ok"
    try:
        async with async_session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            if value != 1:
                db_status = f"unexpected: {value}"
    except Exception as e:
        logger.error(f"❌ DB health check failed: {e}")
        # Если БД не отвечает — возвращаем 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {type(e).__name__}",
        )

    return HealthResponse(
        status="ok",
        db=db_status,
        server_time_utc=datetime.now(timezone.utc).isoformat(),
    )

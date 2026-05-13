"""
FastAPI приложение — точка входа.

Это "обвязка" для всех наших endpoint'ов. Здесь:
  - создаётся приложение FastAPI
  - подключаются роутеры (по одному файлу на группу endpoint'ов)
  - настраивается CORS (чтобы Mini App с другого домена могла к нам стучаться)
  - настраивается логирование

При импорте (для uvicorn) этот файл должен отработать БЕЗ обращения к БД,
потому что БД может быть недоступна в момент импорта (например, в тестах).
Подключения к БД создаются на лету через Depends().
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, questions, test, vk_auth

# ─── Логирование ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Lifecycle: что делать при старте/остановке ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Хук на старт/остановку приложения."""
    logger.info("🚀 FastAPI стартует...")
    yield
    logger.info("🛑 FastAPI останавливается...")


# ─── Создание приложения ────────────────────────────────────
app = FastAPI(
    title="Wellness Test API",
    description="REST API для Mini App теста здоровья",
    version="0.1.0",
    lifespan=lifespan,
    # Удобные URL для документации:
    docs_url="/docs",          # интерактивный Swagger UI
    redoc_url="/redoc",        # альтернативная документация (ReDoc)
    openapi_url="/openapi.json",
)


# ─── CORS ───────────────────────────────────────────────────
# Mini App открывается на другом домене (https://wellnessbot.ru),
# а API на отдельном домене или порту. Без CORS браузер не пустит.
# Сейчас пускаем всех (*), в проде сузим до конкретных доменов.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # TODO в проде: ["https://wellnessbot.ru"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Подключение роутеров ───────────────────────────────────
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(questions.router, prefix="/api", tags=["questions"])
app.include_router(test.router, prefix="/api", tags=["test"])
app.include_router(vk_auth.router, prefix="/api", tags=["vk"])


# ─── Корневой endpoint ──────────────────────────────────────
@app.get("/")
async def root():
    """Корень — просто подсказка где документация."""
    return {
        "name": "Wellness Test API",
        "docs": "/docs",
        "health": "/api/health",
    }

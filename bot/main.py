"""
bot/main.py — собирает aiogram-инстанс и роутер.

Здесь только инфраструктура:
  - создаём Bot с правильными настройками (HTML parse_mode, опциональный прокси)
  - создаём Dispatcher
  - подключаем роутер из handlers.py
  - функция start_polling() — запускает бота

Сами хендлеры — в handlers.py. Это разделение позволит позже легко
добавить webhook вместо polling, не трогая логику.
"""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from core.config import settings
from bot.handlers import router

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """
    Создать и сконфигурировать Bot.

    Если в .env указан PROXY_URL — бот ходит к Telegram через прокси.
    Это нужно если сервер в стране где TG заблокирован.
    """
    if settings.proxy_url:
        session = AiohttpSession(proxy=settings.proxy_url)
        logger.info(f"🔐 Бот идёт через прокси: {settings.proxy_url.split('@')[-1]}")
    else:
        session = AiohttpSession()
        logger.info("🌐 Бот идёт напрямую (без прокси)")

    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    return bot


def create_dispatcher() -> Dispatcher:
    """Создать Dispatcher и подключить все роутеры."""
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def start_polling() -> None:
    """
    Запустить бота в режиме long-polling.

    Используется на разработке и в простом продакшене.
    На большом проде можно перейти на webhook через FastAPI.
    """
    bot = create_bot()
    dp = create_dispatcher()

    # Сбрасываем накопившиеся апдейты — на случай если бот лежал
    # и юзеры ему что-то слали. После рестарта стартуем «с чистого листа».
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logger.info(f"🤖 Бот запущен: @{me.username} (id={me.id})")
    logger.info(f"🔗 Mini App URL: {settings.mini_app_url}")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен")

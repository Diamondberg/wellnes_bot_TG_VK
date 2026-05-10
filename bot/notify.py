"""
bot/notify.py — отправка уведомлений рефереру через TG-бота.

Эту функцию вызывает API-роутер /api/test/submit когда:
  - У теста есть реферер (Пётр)
  - У реферера в БД есть tg_user_id (значит он когда-то открывал бота)

В этом случае шлём ему короткое уведомление в TG что его друг прошёл тест.

ВАЖНО: эта функция создаёт СВОЙ инстанс Bot для одного запроса.
Это не оптимально (каждый раз новый HTTP-клиент), но безопасно — мы не шарим
один и тот же Bot между API-процессом и bot-процессом, которые могут
жить в разных Python-процессах.

В будущем если станет лишним overhead — можно сделать отдельный микросервис
«notification-service», или использовать очередь (Redis/RabbitMQ).
"""

import logging
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from core.config import settings

logger = logging.getLogger(__name__)


async def send_referrer_notification_tg(
    referrer_tg_id: int,
    referrer_name: str,
    referred_first_name: str,
) -> bool:
    """
    Отправить рефереру TG-сообщение что его друг прошёл тест.

    Вернёт True если отправлено, False если ошибка (юзер заблокировал бота,
    бот не настроен и т.п.). Не падает.

    Параметры:
      referrer_tg_id      — TG user_id Петра
      referrer_name       — ФИО Петра (для приветствия)
      referred_first_name — имя Ивана (только имя, без полного ФИО)
    """
    if not referrer_tg_id:
        return False

    if not settings.bot_token:
        logger.info("📨 Bot token не настроен — пропускаем TG-уведомление")
        return False

    # Создаём временный Bot для одного сообщения.
    # Используем те же настройки что в bot/main.py — на случай прокси.
    if settings.proxy_url:
        session = AiohttpSession(proxy=settings.proxy_url)
    else:
        session = AiohttpSession()

    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    text = (
        f"🎁 <b>Спасибо за заботу, {escape(referrer_name)}!</b>\n\n"
        f"По вашей рекомендации <b>{escape(referred_first_name)}</b> "
        f"прошёл наш Wellness Test 🌿\n\n"
        f"Это здорово — благодаря вам ещё один человек "
        f"обратил внимание на своё здоровье ❤️\n\n"
        f"<i>Если хотите узнать про бонусы за приглашённых — "
        f"свяжитесь с консультантом: {settings.consultant_contact_url}</i>"
    )

    try:
        await bot.send_message(
            chat_id=referrer_tg_id,
            text=text,
            disable_web_page_preview=True,
        )
        logger.info(f"✅ TG-уведомление рефереру {referrer_tg_id} отправлено")
        return True

    except TelegramForbiddenError:
        # Юзер заблокировал бота или удалил аккаунт — нормальная ситуация
        logger.info(
            f"📨 TG-уведомление рефереру {referrer_tg_id} не доставлено: "
            f"юзер заблокировал бота"
        )
        return False

    except TelegramBadRequest as e:
        # Невалидный chat_id, юзер не существует и т.п.
        logger.warning(
            f"📨 TG-уведомление рефереру {referrer_tg_id} не доставлено: {e}"
        )
        return False

    except Exception as e:
        logger.error(f"❌ Не удалось отправить TG-уведомление рефереру: {e}")
        return False

    finally:
        await bot.session.close()

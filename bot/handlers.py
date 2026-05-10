"""
bot/handlers.py — все хендлеры TG-бота.

Логика минимальная:
  /start              → приветствие + кнопка «🚀 Открыть тест» (Mini App)
  /start invite_12345 → то же, но с пробросом invite-кода в Mini App через start_param
  /help               → короткая справка
  любое другое        → подсказка нажать /start

Технически:
  - Когда юзер кликает /start invite_12345, мы передаём этот код в Mini App
    через GET-параметр URL (?startapp=invite_12345). Mini App это прочитает.
  - Дополнительно сохраняем юзера в БД (с tg_user_id), чтобы потом мы могли
    написать ему уведомление когда его реферал пройдёт тест.
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from core.config import settings
from db.engine import async_session_maker
from db import repository as repo

logger = logging.getLogger(__name__)
router = Router(name="main_router")


# ════════════════════════════════════════════════════════════
#  Утилиты
# ════════════════════════════════════════════════════════════
def _build_mini_app_url(start_param: str | None = None) -> str:
    """
    Построить URL Mini App, опционально с параметром start_param.

    Telegram WebApp передаёт параметры через query: ?tgWebAppStartParam=...
    Mini App потом достаёт их через Telegram.WebApp.initDataUnsafe.start_param

    На самом деле, когда юзер кликает кнопку с WebAppInfo, TG автоматически
    подставит start_param из аргумента команды /start. Но если бы мы делали
    это через прямую t.me-ссылку, нужен был бы параметр ?startapp=...
    """
    base = settings.mini_app_url.rstrip("/")
    if start_param:
        # Для теста в браузере добавляем ?invite=N — фронт умеет читать оба варианта
        return f"{base}/?invite={start_param}"
    return f"{base}/"


def _build_open_app_keyboard(start_param: str | None = None) -> InlineKeyboardMarkup:
    """Кнопка «🚀 Открыть тест», открывающая Mini App."""
    url = _build_mini_app_url(start_param)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть тест",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


async def _ensure_tg_user_seen(tg_user_id: int, username: str | None, first_name: str | None) -> None:
    """
    Запомнить что этот TG-юзер хоть раз открывал бота.

    Это нужно чтобы потом, когда его реферал пройдёт тест, мы могли
    отправить ему уведомление в TG (без `/start` бот не имеет права писать).

    Логика:
      - Ищем юзера по tg_user_id в БД (в текущем tenant'е)
      - Если есть — обновляем username/first_name (могли поменяться)
      - Если нет — пока НЕ создаём (создание полноценной записи в users
        требует ФИО+телефон+lead_number, а у нас только TG-данные).
        Запись появится когда юзер пройдёт тест в Mini App.

    Альтернатива: завести таблицу `tg_seen_users` для голых TG-id без полноценной
    регистрации. Это пригодится если хочется писать кому угодно. Но пока MVP —
    обходимся существующей схемой.
    """
    async with async_session_maker() as session:
        # Получим tenant
        tenant = await repo.get_tenant_by_code(session, settings.tenant_code)
        if tenant is None:
            logger.warning(f"⚠️ Tenant {settings.tenant_code} не найден в БД")
            return

        user = await repo.get_user_by_platform_id(
            session,
            tenant_id=tenant.id,
            platform="telegram",
            platform_user_id=tg_user_id,
        )

        # Если юзер уже зарегистрирован (прошёл тест) — обновим контакты от TG
        if user is not None:
            changed = False
            if username and user.tg_username != username:
                user.tg_username = username
                changed = True
            if first_name and user.tg_first_name != first_name:
                user.tg_first_name = first_name
                changed = True
            if changed:
                await session.commit()


# ════════════════════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    """
    Главный хендлер /start.

    Поддерживает аргумент:
      /start              → обычное приветствие
      /start invite_12345 → реферальный заход, передаём invite в Mini App
    """
    user = message.from_user
    if user is None:
        return

    # Логируем заход и обновляем TG-данные если юзер уже в БД
    try:
        await _ensure_tg_user_seen(user.id, user.username, user.first_name)
    except Exception as e:
        # Не падаем если БД недоступна — приветствие важнее
        logger.error(f"❌ Не удалось обновить TG-данные юзера: {e}")

    # Достаём аргумент команды (всё что после /start)
    arg = command.args  # для "/start invite_12345" → "invite_12345"
    start_param = None
    referrer_id = None

    if arg:
        # Ожидаем формат "invite_<число>"
        if arg.startswith("invite_"):
            try:
                referrer_id = int(arg.replace("invite_", ""))
                start_param = arg  # передадим в Mini App как есть
                logger.info(f"🎁 /start с invite-кодом от реферера {referrer_id} (юзер {user.id})")
            except ValueError:
                logger.warning(f"⚠️ Неожиданный формат /start arg: {arg!r}")
        else:
            logger.info(f"ℹ️ /start с неизвестным arg: {arg!r}")

    # Текст приветствия немного разный для реф-захода vs обычного
    if referrer_id:
        text = (
            "👋 <b>Привет!</b>\n\n"
            "Вас пригласил друг пройти небольшой тест на состояние здоровья 🌿\n\n"
            "⏱ Это займёт всего 2 минуты — 36 простых вопросов.\n"
            "Без диагнозов, без стресса, просто понять — на что обратить внимание.\n\n"
            "Жмите кнопку ниже, чтобы начать ↓"
        )
    else:
        text = (
            "👋 <b>Здравствуйте!</b>\n\n"
            "Я — Wellness Test Bot. Помогу вам пройти короткий тест "
            "на состояние основных систем организма 🌿\n\n"
            "⏱ Это займёт всего 2 минуты.\n\n"
            "Жмите кнопку ниже, чтобы открыть тест ↓"
        )

    await message.answer(
        text,
        reply_markup=_build_open_app_keyboard(start_param),
    )


# ════════════════════════════════════════════════════════════
#  /help
# ════════════════════════════════════════════════════════════
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Короткая справка."""
    text = (
        "ℹ️ <b>Wellness Test Bot</b>\n\n"
        "Я помогу пройти короткий тест на состояние здоровья.\n\n"
        "📋 <b>Команды:</b>\n"
        "/start — открыть тест\n"
        "/help — эта справка\n\n"
        "🌿 Берегите своё здоровье!"
    )
    await message.answer(
        text,
        reply_markup=_build_open_app_keyboard(),
    )


# ════════════════════════════════════════════════════════════
#  Все остальные сообщения — мягкая подсказка
# ════════════════════════════════════════════════════════════
@router.message(F.text)
async def fallback(message: Message) -> None:
    """
    Если юзер написал что-то в свободной форме — мягко перенаправляем
    на /start. Не пересылаем админу (это уже отдельная фича).
    """
    await message.answer(
        "🤔 Я понимаю только команду /start.\n\n"
        "Жмите кнопку ниже, чтобы открыть тест ↓",
        reply_markup=_build_open_app_keyboard(),
    )

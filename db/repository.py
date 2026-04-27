"""
Repository — единая точка работы с БД.

Зачем выносить в отдельный модуль:
  - Все запросы в одном месте → легко искать
  - API не знает про SQLAlchemy, работает только с функциями репозитория
  - Когда захотим добавить кэширование/логирование/аудит — точечно здесь
  - Тесты можно писать на репозиторий отдельно от API

Соглашения:
  - Все функции async
  - Принимают AsyncSession первым параметром (передаётся через DI)
  - НЕ делают commit — это делает вызывающий код. Так можно объединять
    несколько операций в одну транзакцию.
  - Возвращают модели SQLAlchemy (User, Answer, ...) или None
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Tenant, User, Answer, Referral


# ════════════════════════════════════════════════════════════
#  Tenant
# ════════════════════════════════════════════════════════════
async def get_tenant_by_code(session: AsyncSession, code: str) -> Optional[Tenant]:
    """Найти арендатора по его коду."""
    result = await session.execute(
        select(Tenant).where(Tenant.code == code)
    )
    return result.scalar_one_or_none()


# ════════════════════════════════════════════════════════════
#  User
# ════════════════════════════════════════════════════════════
async def get_user_by_phone(
    session: AsyncSession,
    tenant_id: int,
    phone: str,
) -> Optional[User]:
    """Найти пользователя по телефону в рамках tenant'а."""
    result = await session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.phone == phone,
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_platform_id(
    session: AsyncSession,
    tenant_id: int,
    platform: str,
    platform_user_id: int,
) -> Optional[User]:
    """
    Найти пользователя по его ID на платформе.
    platform: "telegram" / "vk" / "max"
    """
    field_map = {
        "telegram": User.tg_user_id,
        "vk": User.vk_user_id,
        "max": User.max_user_id,
    }
    if platform not in field_map:
        raise ValueError(f"Неизвестная платформа: {platform}")

    result = await session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            field_map[platform] == platform_user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_next_lead_number(session: AsyncSession, tenant_id: int) -> int:
    """Следующий номер заявки в рамках tenant'а."""
    result = await session.execute(
        select(func.max(User.lead_number)).where(User.tenant_id == tenant_id)
    )
    max_num = result.scalar()
    return (max_num or 0) + 1


async def upsert_user(
    session: AsyncSession,
    tenant_id: int,
    full_name: str,
    phone: str,
    platform: str,
    platform_user_id: int,
    platform_username: Optional[str] = None,
    platform_first_name: Optional[str] = None,
    referrer_user_id: Optional[int] = None,
) -> User:
    """
    Создать или обновить пользователя.

    Логика:
      1. Ищем по телефону в этом tenant'е
      2. Если есть — обновляем (новые данные перетирают старые)
      3. Если нет — создаём с новым lead_number
      4. ID платформы сохраняем (один человек может прийти и через TG и через VK)
    """
    user = await get_user_by_phone(session, tenant_id, phone)

    # Поля для платформы
    platform_fields = {
        "telegram": ("tg_user_id", "tg_username", "tg_first_name"),
        "vk": ("vk_user_id", None, None),
        "max": ("max_user_id", None, None),
    }
    if platform not in platform_fields:
        raise ValueError(f"Неизвестная платформа: {platform}")

    pid_field, uname_field, fname_field = platform_fields[platform]

    if user is None:
        # ─── Создаём нового ────────────────────────────────
        lead_number = await get_next_lead_number(session, tenant_id)
        user = User(
            tenant_id=tenant_id,
            full_name=full_name,
            phone=phone,
            lead_number=lead_number,
            first_platform=platform,
            consent_at=datetime.now(timezone.utc),
            referrer_id=referrer_user_id,
        )
        # Заполняем поля платформы
        setattr(user, pid_field, platform_user_id)
        if uname_field and platform_username:
            setattr(user, uname_field, platform_username)
        if fname_field and platform_first_name:
            setattr(user, fname_field, platform_first_name)
        session.add(user)
        await session.flush()  # чтобы получить user.id
    else:
        # ─── Обновляем существующего ───────────────────────
        user.full_name = full_name
        # Если ID платформы ещё не был известен — записываем
        if getattr(user, pid_field) is None:
            setattr(user, pid_field, platform_user_id)
        if uname_field and platform_username:
            setattr(user, uname_field, platform_username)
        if fname_field and platform_first_name:
            setattr(user, fname_field, platform_first_name)
        # Реферера НЕ перезаписываем — он определяется при первой регистрации
        await session.flush()

    return user


# ════════════════════════════════════════════════════════════
#  Answer
# ════════════════════════════════════════════════════════════
async def replace_user_answers(
    session: AsyncSession,
    user_id: int,
    answers: List[dict],
) -> None:
    """
    Заменить все ответы пользователя на новые.

    Согласно нашему решению: при повторном прохождении старые ответы
    УДАЛЯЮТСЯ (а не накапливаются как попытки).

    answers: список словарей вида:
        {"question_number": 1, "answer": "yes", "system": "nervous"}
    Один вопрос может породить несколько строк (если он влияет на 2+ систем).
    """
    # Удаляем старые
    await session.execute(
        delete(Answer).where(Answer.user_id == user_id)
    )
    # Вставляем новые
    if answers:
        session.add_all([
            Answer(
                user_id=user_id,
                question_number=a["question_number"],
                answer=a["answer"],
                system=a["system"],
            )
            for a in answers
        ])
    await session.flush()


# ════════════════════════════════════════════════════════════
#  Referral
# ════════════════════════════════════════════════════════════
async def link_referral(
    session: AsyncSession,
    tenant_id: int,
    referrer_user_id: int,
    platform: str,
    referred_platform_id: int,
    referred_user_id: Optional[int] = None,
) -> Referral:
    """
    Создать или обновить реферальную связь.

    Если запись уже есть (один человек кликнул по ссылке несколько раз) —
    просто обновляем referred_user_id (на случай если он раньше не был известен).
    """
    # Ищем существующую связь
    result = await session.execute(
        select(Referral).where(
            Referral.tenant_id == tenant_id,
            Referral.platform == platform,
            Referral.referred_platform_id == referred_platform_id,
        )
    )
    referral = result.scalar_one_or_none()

    if referral is None:
        referral = Referral(
            tenant_id=tenant_id,
            referrer_user_id=referrer_user_id,
            platform=platform,
            referred_platform_id=referred_platform_id,
            referred_user_id=referred_user_id,
            completed=referred_user_id is not None,
        )
        session.add(referral)
    else:
        if referred_user_id is not None:
            referral.referred_user_id = referred_user_id
            referral.completed = True

    await session.flush()
    return referral


async def get_referrer_for_user(
    session: AsyncSession,
    user_id: int,
) -> Optional[User]:
    """Кто пригласил этого пользователя (если кто-то)."""
    user_result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or user.referrer_id is None:
        return None

    ref_result = await session.execute(
        select(User).where(User.id == user.referrer_id)
    )
    return ref_result.scalar_one_or_none()

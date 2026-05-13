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


async def get_distributor(
    session: AsyncSession,
    tenant_id: int,
) -> Optional[User]:
    """
    Найти дистрибьютора в этом tenant'е.

    Дистрибьютор — единственная запись в users с is_distributor=True.
    К нему привязываются все "холодные" лиды (без реф-ссылки или
    по битой реф-ссылке).

    Если в БД нет записи с is_distributor=True — возвращает None.
    Тогда API упадёт обратно на старое поведение (referrer_id=NULL).
    """
    result = await session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.is_distributor == True,  # noqa: E712 (SQLAlchemy сравнение)
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def get_next_lead_number(session: AsyncSession, tenant_id: int) -> int:
    """
    Следующий номер заявки в рамках tenant'а.

    ВАЖНО: считаем только реальных лидов (is_distributor=False).
    У дистрибьютора lead_number=0 — он не должен влиять на нумерацию.
    """
    result = await session.execute(
        select(func.max(User.lead_number)).where(
            User.tenant_id == tenant_id,
            User.is_distributor == False,  # noqa: E712
        )
    )
    max_num = result.scalar()
    return (max_num or 0) + 1


async def find_referrer_by_any_platform_id(
    session: AsyncSession,
    tenant_id: int,
    platform_user_id: int,
) -> Optional[User]:
    """
    Универсальный поиск юзера по ID в ЛЮБОЙ платформе (tg/vk/max).

    Используется для реферера: реф-ссылка может прийти от юзера на одной
    платформе, а получатель открыть её на другой. Если получатель в VK,
    а отправитель сидит только в TG — ищем его tg_user_id в БД.
    """
    from sqlalchemy import or_
    result = await session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            or_(
                User.tg_user_id == platform_user_id,
                User.vk_user_id == platform_user_id,
                User.max_user_id == platform_user_id,
            ),
        ).limit(1)
    )
    return result.scalar_one_or_none()


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
    email: Optional[str] = None,
) -> User:
    """
    Создать или обновить пользователя.

    ВАЖНО: якорь — это (tenant_id, platform, platform_user_id).
    НЕ телефон. Телефон/email — обычные поля.

    Логика:
      1. Ищем по (platform, platform_user_id) в этом tenant'е.
      2. Если есть — обновляем (новые данные перетирают старые).
      3. Если нет — создаём новую запись с новым lead_number.
      4. Один человек, который проходит тест в TG и в VK, получит ДВЕ записи.
         Их можно «поженить» отдельно (вручную или будущей фичей).

    Поведение для email:
      - При создании — пишем то, что передали (может быть None).
      - При обновлении — пишем только если переданное значение не None.
        То есть если юзер раз указал email, а во второй раз не указал —
        старый email НЕ затирается.

    Поведение для referrer_user_id:
      - Реферер НЕ перезаписывается при повторном прохождении.
        Один раз привязан — навсегда.
    """
    user = await get_user_by_platform_id(
        session, tenant_id, platform, platform_user_id
    )

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
            email=email,
            lead_number=lead_number,
            first_platform=platform,
            consent_at=datetime.now(timezone.utc),
            referrer_id=referrer_user_id,
        )
        setattr(user, pid_field, platform_user_id)
        if uname_field and platform_username:
            setattr(user, uname_field, platform_username)
        if fname_field and platform_first_name:
            setattr(user, fname_field, platform_first_name)
        session.add(user)
        await session.flush()
    else:
        # ─── Обновляем существующего ───────────────────────
        user.full_name = full_name
        user.phone = phone
        if email:
            user.email = email
        if uname_field and platform_username:
            setattr(user, uname_field, platform_username)
        if fname_field and platform_first_name:
            setattr(user, fname_field, platform_first_name)
        # Реферера НЕ перезаписываем
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
) -> Optional[Referral]:
    """
    Создать или обновить реферальную связь.

    Если запись уже есть (один человек кликнул по ссылке несколько раз) —
    просто обновляем referred_user_id (на случай если он раньше не был известен).

    ВАЖНО: если referrer_user_id указывает на дистрибьютора —
    реферальную связь НЕ создаём. Зачем хранить «холодный → дистрибьютор»
    в таблице referrals — это и так понятно по полю User.referrer_id.
    Чтобы таблица referrals содержала только РЕАЛЬНЫЕ цепочки между юзерами.
    """
    # Проверка: не пытаемся ли мы связать с дистрибьютором?
    referrer_result = await session.execute(
        select(User.is_distributor).where(User.id == referrer_user_id)
    )
    is_distributor = referrer_result.scalar()
    if is_distributor:
        # Не создаём запись — это «холодный» лид, не реальная цепочка
        return None

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

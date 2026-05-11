"""
Endpoint сабмита теста.

POST /api/test/submit
  Принимает данные пользователя и 36 ответов от Mini App.
  Сохраняет в БД, считает результат.
  В фоне: шлёт email админу, копию юзеру (если email есть),
  и УВЕДОМЛЕНИЯ РЕФЕРЕРУ — но только если реферер не дистрибьютор.
  Возвращает Mini App результат для показа.

Логика реферера:
  - Если referrer_platform_id пустой → реферер = дистрибьютор
  - Если referrer_platform_id указан, но юзер не найден → реферер = дистрибьютор
  - Если referrer_platform_id указан и юзер найден → реферер = он
  - Защита от самореференса: если invite_id совпадает с user_id → дистрибьютор
"""

import logging
import re
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_current_tenant
from api.schemas import (
    TestSubmitIn,
    TestSubmitOut,
    SystemResultOut,
)
from bot.notify import send_referrer_notification_tg
from core.notifier import (
    send_lead_email,
    send_referrer_notification_email,
    send_user_report,
)
from core.questions import get_question
from core.reports import (
    UserSnapshot,
    generate_excel_report,
    generate_txt_report,
)
from core.test_engine import AnswerInput, calculate_result
from core.utils import build_report_paths
from db import repository as repo
from db.models import Tenant, User

logger = logging.getLogger(__name__)
router = APIRouter()


# ════════════════════════════════════════════════════════════
#  Утилиты
# ════════════════════════════════════════════════════════════
PHONE_RE = re.compile(r"^(\+7|7|8)?\d{10,14}$")


def normalize_phone(raw: str) -> str:
    return re.sub(r"[\s\(\)\-]", "", raw)


def validate_phone(raw: str) -> bool:
    return bool(PHONE_RE.match(normalize_phone(raw)))


def _first_name_from_full_name(full_name: str) -> str:
    """
    Достать имя из ФИО для приватного уведомления рефереру.
    «Иванов Иван Иванович» → «Иван».
    Если что-то не парсится — возвращаем целиком (защита от сюрпризов).
    """
    parts = full_name.strip().split()
    if len(parts) >= 2:
        # Вторая часть — обычно имя (если ФИО введено в формате Фамилия Имя ...)
        return parts[1]
    return full_name.strip()


# ════════════════════════════════════════════════════════════
#  Снимок реферера (для безопасной передачи в фоновую задачу)
# ════════════════════════════════════════════════════════════
class ReferrerSnapshot:
    """
    Маленький DTO с данными реферера для уведомлений.
    Создаётся в основной таске, передаётся в фоновую — чтобы фоновая
    не дёргала БД ещё раз.

    Поле is_distributor — чтобы фоновая задача знала: дистрибьютору
    уведомления НЕ слать.
    """
    __slots__ = ("name", "email", "tg_user_id", "is_distributor")

    def __init__(
        self,
        name: str,
        email: str | None,
        tg_user_id: int | None,
        is_distributor: bool,
    ):
        self.name = name
        self.email = email
        self.tg_user_id = tg_user_id
        self.is_distributor = is_distributor


# ════════════════════════════════════════════════════════════
#  Background-задача: отчёты + уведомления
# ════════════════════════════════════════════════════════════
async def _send_reports_in_background(
    user_snapshot: UserSnapshot,
    answers: list,
    result,
    user_email: str | None,
    referrer_snapshot: ReferrerSnapshot | None,
) -> None:
    """
    Запускается ПОСЛЕ того как API вернул ответ Mini App.
    Делает:
      1. Генерирует TXT и Excel
      2. Сохраняет локально
      3. Шлёт email админу (TXT + Excel)
      4. Если у юзера есть email — шлёт ему HTML
      5. Если есть РЕАЛЬНЫЙ реферер (не дистрибьютор) — шлём ему уведомления
    """
    try:
        txt_bytes = generate_txt_report(user_snapshot, answers, result)
        xlsx_bytes = generate_excel_report(user_snapshot, answers, result)

        # Локальное сохранение
        txt_path, xlsx_path = build_report_paths(
            full_name=user_snapshot.full_name,
            lead_number=user_snapshot.lead_number,
            when=datetime.now(),
        )
        txt_path.write_bytes(txt_bytes)
        xlsx_path.write_bytes(xlsx_bytes)
        logger.info(f"💾 Отчёты сохранены: {txt_path.name}")

        # Email админу
        await send_lead_email(
            user=user_snapshot,
            result=result,
            txt_bytes=txt_bytes,
            xlsx_bytes=xlsx_bytes,
            txt_filename=txt_path.name,
            xlsx_filename=xlsx_path.name,
        )

        # Email юзеру
        if user_email:
            try:
                await send_user_report(
                    user_email=user_email,
                    user=user_snapshot,
                    result=result,
                )
            except Exception as e:
                logger.error(
                    f"❌ Не удалось отправить отчёт юзеру ({user_email}): {e}",
                    exc_info=True,
                )

        # ─── Уведомления рефереру ──────────────────────────
        # ВАЖНО: дистрибьютору не шлём (он и так получает основное письмо админу).
        if referrer_snapshot is not None and not referrer_snapshot.is_distributor:
            referred_first_name = _first_name_from_full_name(user_snapshot.full_name)

            # Email — если у реферера есть email
            if referrer_snapshot.email:
                try:
                    await send_referrer_notification_email(
                        referrer_email=referrer_snapshot.email,
                        referrer_name=referrer_snapshot.name,
                        referred_first_name=referred_first_name,
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Email рефереру не ушёл ({referrer_snapshot.email}): {e}",
                        exc_info=True,
                    )

            # TG — если реферер когда-то открывал нашего бота
            if referrer_snapshot.tg_user_id:
                try:
                    await send_referrer_notification_tg(
                        referrer_tg_id=referrer_snapshot.tg_user_id,
                        referrer_name=referrer_snapshot.name,
                        referred_first_name=referred_first_name,
                    )
                except Exception as e:
                    logger.error(
                        f"❌ TG-уведомление рефереру не ушло (id={referrer_snapshot.tg_user_id}): {e}",
                        exc_info=True,
                    )

    except Exception as e:
        logger.error(f"❌ Ошибка в фоновой обработке: {e}", exc_info=True)


# ════════════════════════════════════════════════════════════
#  Endpoint
# ════════════════════════════════════════════════════════════
@router.post(
    "/test/submit",
    response_model=TestSubmitOut,
    status_code=status.HTTP_200_OK,
    summary="Принять результаты теста от Mini App",
)
async def submit_test(
    payload: TestSubmitIn,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    tenant: Tenant = Depends(get_current_tenant),
) -> TestSubmitOut:
    """
    Шаги:
      1. Валидация
      2. Поиск реферера (или fallback на дистрибьютора)
      3. Создание/обновление юзера + сохранение ответов + реф-связи
      4. Подсчёт результата
      5. Коммит
      6. Снимок реферера для фоновой задачи
      7. Запуск фоновой отправки отчётов и уведомлений
      8. Возврат результата Mini App
    """
    # ─── 1. Валидация ──────────────────────────────────────
    if not payload.consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Требуется согласие на обработку персональных данных (152-ФЗ)",
        )

    if not validate_phone(payload.phone):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Неверный формат телефона. Пример: +79991234567",
        )

    phone_clean = normalize_phone(payload.phone)
    full_name = payload.full_name.strip()
    user_email = str(payload.email).strip().lower() if payload.email else None

    # ─── 2. Реферер (с fallback на дистрибьютора) ─────────
    # Шаг 2.1: пробуем найти реферера по invite-id из ссылки
    real_referrer: User | None = None
    if payload.referrer_platform_id is not None:
        real_referrer = await repo.get_user_by_platform_id(
            session,
            tenant_id=tenant.id,
            platform=payload.platform.platform,
            platform_user_id=payload.referrer_platform_id,
        )

        if real_referrer is not None:
            # Защита от самореференса: юзер передал свой же ID
            if (
                real_referrer.tg_user_id == payload.platform.user_id
                and payload.platform.platform == "telegram"
            ):
                logger.warning(
                    f"⚠️ Самореференс отклонён: юзер {payload.platform.user_id} "
                    f"передал свой же tg_id как реферер"
                )
                real_referrer = None
            else:
                logger.info(
                    f"🎁 Реферер найден: {real_referrer.full_name} "
                    f"(id={real_referrer.id}) для нового лида с {phone_clean}"
                )
        else:
            logger.info(
                f"🎁 Реферер с {payload.platform.platform}_id="
                f"{payload.referrer_platform_id} в БД не найден — битая ссылка"
            )

    # Шаг 2.2: если реферера нет — fallback на дистрибьютора
    distributor = await repo.get_distributor(session, tenant_id=tenant.id)
    if real_referrer is None:
        effective_referrer = distributor
        if effective_referrer is None:
            logger.warning(
                "⚠️ Дистрибьютор не найден в БД — лид сохранится без реферера. "
                "Создайте запись в users с is_distributor=true."
            )
    else:
        effective_referrer = real_referrer

    # Дополнительная защита: если реферер — это сам дистрибьютор, но юзер
    # с тем же tg_user_id что у дистрибьютора. Чтобы не привязывать
    # дистрибьютора к самому себе как реферера.
    if (
        effective_referrer is not None
        and effective_referrer.is_distributor
        and effective_referrer.tg_user_id == payload.platform.user_id
        and payload.platform.platform == "telegram"
    ):
        logger.info(
            "ℹ️ Сам дистрибьютор проходит тест — реферер не назначается"
        )
        effective_referrer = None

    referrer_user_id = effective_referrer.id if effective_referrer else None

    # ─── 3. Создаём/обновляем юзера ───────────────────────
    user = await repo.upsert_user(
        session,
        tenant_id=tenant.id,
        full_name=full_name,
        phone=phone_clean,
        platform=payload.platform.platform,
        platform_user_id=payload.platform.user_id,
        platform_username=payload.platform.username,
        platform_first_name=payload.platform.first_name,
        referrer_user_id=referrer_user_id,
        email=user_email,
    )

    # ─── 4. Записываем ответы ─────────────────────────────
    db_answers = []
    for ans in payload.answers:
        try:
            question = get_question(ans.question_number)
        except ValueError:
            logger.warning(f"⚠️ Неизвестный номер вопроса: {ans.question_number}")
            continue
        for sys_code in question.systems:
            db_answers.append({
                "question_number": ans.question_number,
                "answer": ans.answer,
                "system": sys_code,
            })

    await repo.replace_user_answers(session, user_id=user.id, answers=db_answers)

    # ─── 5. Реф-связь (только если реферер — реальный юзер, не дистрибьютор) ──
    # link_referral сама проверяет is_distributor и пропускает связь
    if referrer_user_id is not None:
        await repo.link_referral(
            session,
            tenant_id=tenant.id,
            referrer_user_id=referrer_user_id,
            platform=payload.platform.platform,
            referred_platform_id=payload.platform.user_id,
            referred_user_id=user.id,
        )

    # ─── 6. Подсчёт ────────────────────────────────────────
    engine_answers = [
        AnswerInput(question_number=a.question_number, answer=a.answer)
        for a in payload.answers
    ]
    result = calculate_result(engine_answers)

    # ─── 7. Коммит ─────────────────────────────────────────
    await session.commit()

    ref_info = "—"
    if effective_referrer is not None:
        ref_info = (
            f"{effective_referrer.full_name}"
            f"{' (DIST)' if effective_referrer.is_distributor else ''}"
        )

    logger.info(
        f"✅ Заявка #{user.lead_number} сохранена: {full_name} | {phone_clean} "
        f"| email={user_email or '—'} | referrer={ref_info} "
        f"| critical={result.critical_count}, warning={result.warning_count}"
    )

    # ─── 8. Снимок реферера (для фоновой задачи) ──────────
    referrer_snapshot: ReferrerSnapshot | None = None
    if effective_referrer is not None:
        referrer_snapshot = ReferrerSnapshot(
            name=effective_referrer.full_name,
            email=effective_referrer.email,
            tg_user_id=effective_referrer.tg_user_id,
            is_distributor=effective_referrer.is_distributor,
        )

    # ─── 9. Snapshot текущего юзера для отчётов ──────────
    # В письме админу — показываем РЕАЛЬНОГО реферера, не дистрибьютора.
    # Если эффективный реферер — дистрибьютор, в snapshot оставляем None,
    # а notifier нарисует пометку «Зашёл напрямую».
    snapshot_referrer = effective_referrer
    if snapshot_referrer is not None and snapshot_referrer.is_distributor:
        snapshot_referrer = None  # для письма админу: «Зашёл напрямую»

    user_snapshot = UserSnapshot(
        lead_number=user.lead_number,
        full_name=full_name,
        phone=phone_clean,
        platform=payload.platform.platform,
        platform_user_id=payload.platform.user_id,
        platform_username=payload.platform.username,
        referrer_name=snapshot_referrer.full_name if snapshot_referrer else None,
        referrer_phone=snapshot_referrer.phone if snapshot_referrer else None,
        referrer_email=snapshot_referrer.email if snapshot_referrer else None,
        referrer_tg_username=snapshot_referrer.tg_username if snapshot_referrer else None,
        referrer_tg_user_id=snapshot_referrer.tg_user_id if snapshot_referrer else None,
        referrer_vk_user_id=snapshot_referrer.vk_user_id if snapshot_referrer else None,
        referrer_max_user_id=snapshot_referrer.max_user_id if snapshot_referrer else None,
    )

    final_email = user.email or user_email

    # ─── 10. Фоновая задача ────────────────────────────────
    background_tasks.add_task(
        _send_reports_in_background,
        user_snapshot,
        engine_answers,
        result,
        final_email,
        referrer_snapshot,
    )

    # ─── 11. Ответ Mini App ────────────────────────────────
    return TestSubmitOut(
        lead_number=user.lead_number,
        systems=[
            SystemResultOut(
                code=sr.system_code,
                name=sr.system_name,
                score=sr.score,
                max_score=sr.max_score,
                percentage=int(round(sr.percentage)),
                status=sr.status.value,
            )
            for sr in result.systems
        ],
    )

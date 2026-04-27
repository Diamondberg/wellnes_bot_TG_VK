"""
Endpoint сабмита теста.

POST /api/test/submit
  Принимает данные пользователя и 36 ответов от Mini App.
  Сохраняет в БД, считает результат, отправляет email админу (в фоне).
  Возвращает Mini App результат для показа.
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
from core.notifier import send_lead_email
from core.questions import get_question
from core.reports import (
    UserSnapshot,
    generate_excel_report,
    generate_txt_report,
)
from core.test_engine import AnswerInput, calculate_result
from core.utils import build_report_paths
from db import repository as repo
from db.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter()


# ════════════════════════════════════════════════════════════
#  Утилиты
# ════════════════════════════════════════════════════════════
PHONE_RE = re.compile(r"^(\+7|7|8)?\d{10,14}$")


def normalize_phone(raw: str) -> str:
    """Очищает телефон: убирает скобки/дефисы/пробелы."""
    return re.sub(r"[\s\(\)\-]", "", raw)


def validate_phone(raw: str) -> bool:
    """Проверка формата телефона."""
    return bool(PHONE_RE.match(normalize_phone(raw)))


# ════════════════════════════════════════════════════════════
#  Background-задача: отчёты + email
# ════════════════════════════════════════════════════════════
async def _send_reports_in_background(
    user_snapshot: UserSnapshot,
    answers: list,
    result,
) -> None:
    """
    Запускается ПОСЛЕ того как API вернул ответ Mini App.
    Делает три вещи: TXT, XLSX, email.

    Если что-то пошло не так — только логирует. Юзер уже получил свой
    result, повторно не дёргаем.
    """
    try:
        txt_bytes = generate_txt_report(user_snapshot, answers, result)
        xlsx_bytes = generate_excel_report(user_snapshot, answers, result)

        # Сохраняем локально
        txt_path, xlsx_path = build_report_paths(
            full_name=user_snapshot.full_name,
            lead_number=user_snapshot.lead_number,
            when=datetime.now(),
        )
        txt_path.write_bytes(txt_bytes)
        xlsx_path.write_bytes(xlsx_bytes)
        logger.info(f"💾 Отчёты сохранены: {txt_path.name}")

        # Шлём email админу
        await send_lead_email(
            user=user_snapshot,
            result=result,
            txt_bytes=txt_bytes,
            xlsx_bytes=xlsx_bytes,
            txt_filename=txt_path.name,
            xlsx_filename=xlsx_path.name,
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
    Главный endpoint API.

    Шаги:
      1. Валидация телефона и согласия
      2. Если есть referrer_platform_id — найти реферера в БД
      3. Создать/обновить пользователя в БД
      4. Записать ответы (старые удаляются — повторное прохождение)
      5. Создать реферальную связь (если есть)
      6. Подсчитать результат
      7. Закоммитить в БД
      8. Запустить отправку отчётов в фоне
      9. Вернуть результат Mini App
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

    # ─── 2. Реферер (если есть) ────────────────────────────
    referrer_user_id = None
    if payload.referrer_platform_id is not None:
        # Находим реферера по его ID на ТОЙ ЖЕ платформе
        referrer = await repo.get_user_by_platform_id(
            session,
            tenant_id=tenant.id,
            platform=payload.platform.platform,
            platform_user_id=payload.referrer_platform_id,
        )
        if referrer is not None:
            referrer_user_id = referrer.id
            logger.info(
                f"🎁 Реферер найден: {referrer.full_name} (id={referrer.id}) "
                f"для нового лида с телефоном {phone_clean}"
            )
        else:
            logger.info(
                f"🎁 Реферер с {payload.platform.platform}_id={payload.referrer_platform_id} "
                f"в БД не найден — новый юзер пришёл по битой ссылке"
            )

    # ─── 3. Создаём/обновляем пользователя ─────────────────
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
    )

    # ─── 4. Записываем ответы (старые удаляются) ──────────
    # Каждый ответ может породить несколько строк (один вопрос → много систем).
    db_answers = []
    for ans in payload.answers:
        try:
            question = get_question(ans.question_number)
        except ValueError:
            # Пропускаем неизвестные номера, не падаем
            logger.warning(f"⚠️ Пришёл неизвестный номер вопроса: {ans.question_number}")
            continue
        for sys_code in question.systems:
            db_answers.append({
                "question_number": ans.question_number,
                "answer": ans.answer,
                "system": sys_code,
            })

    await repo.replace_user_answers(session, user_id=user.id, answers=db_answers)

    # ─── 5. Реферальная связь ──────────────────────────────
    if referrer_user_id is not None:
        await repo.link_referral(
            session,
            tenant_id=tenant.id,
            referrer_user_id=referrer_user_id,
            platform=payload.platform.platform,
            referred_platform_id=payload.platform.user_id,
            referred_user_id=user.id,
        )

    # ─── 6. Подсчёт результата ─────────────────────────────
    engine_answers = [
        AnswerInput(question_number=a.question_number, answer=a.answer)
        for a in payload.answers
    ]
    result = calculate_result(engine_answers)

    # ─── 7. Коммит в БД ────────────────────────────────────
    await session.commit()
    logger.info(
        f"✅ Заявка #{user.lead_number} сохранена: {full_name} | {phone_clean} "
        f"| critical={result.critical_count}, warning={result.warning_count}"
    )

    # ─── 8. Готовим snapshot для отчётов и шлём в фон ──────
    # Достанем реферера если есть (для красивого email админу)
    referrer_name = None
    referrer_phone = None
    if referrer_user_id is not None:
        referrer_for_snapshot = await repo.get_referrer_for_user(session, user.id)
        if referrer_for_snapshot is not None:
            referrer_name = referrer_for_snapshot.full_name
            referrer_phone = referrer_for_snapshot.phone

    user_snapshot = UserSnapshot(
        lead_number=user.lead_number,
        full_name=full_name,
        phone=phone_clean,
        platform=payload.platform.platform,
        platform_user_id=payload.platform.user_id,
        platform_username=payload.platform.username,
        referrer_name=referrer_name,
        referrer_phone=referrer_phone,
    )

    # Запускаем отправку отчётов в фоне (юзер не ждёт)
    background_tasks.add_task(
        _send_reports_in_background,
        user_snapshot,
        engine_answers,
        result,
    )

    # ─── 9. Возвращаем результат Mini App ──────────────────
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

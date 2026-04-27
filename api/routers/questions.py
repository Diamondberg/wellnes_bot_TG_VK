"""
Endpoint для отдачи списка вопросов и систем.

GET /api/questions  →  все 36 вопросов + 6 систем
"""

import logging

from fastapi import APIRouter, Response

from api.schemas import QuestionsResponse, QuestionOut, SystemOut
from core.questions import QUESTIONS, SYSTEMS, total_questions

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Endpoint ───────────────────────────────────────────────
@router.get(
    "/questions",
    response_model=QuestionsResponse,
    summary="Получить все вопросы и системы",
    description=(
        "Возвращает полный набор данных, нужный Mini App для отображения теста: "
        "36 вопросов и 6 систем организма с их кодами и названиями."
    ),
)
async def get_questions(response: Response) -> QuestionsResponse:
    """
    Отдаёт вопросы из core/questions.py.

    Вопросы захардкожены и не меняются часто, поэтому:
      - не трогаем БД
      - разрешаем браузеру кэшировать на 1 час (но HTTP cache headers ниже)
    """
    # Cache-Control: max-age=3600 → браузер закэширует на час.
    # public — ок кэшировать на CDN.
    response.headers["Cache-Control"] = "public, max-age=3600"

    systems_out = [
        SystemOut(code=sys_info.code, name=sys_info.name)
        for sys_info in SYSTEMS.values()
    ]

    questions_out = [
        QuestionOut(
            number=q.number,
            text=q.text,
            systems=list(q.systems),
        )
        for q in QUESTIONS
    ]

    return QuestionsResponse(
        total=total_questions(),
        systems=systems_out,
        questions=questions_out,
    )

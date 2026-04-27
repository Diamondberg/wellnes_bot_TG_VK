"""
Pydantic-схемы для API.

Здесь живут все DTO (Data Transfer Objects) — структуры, которые ходят
по HTTP между фронтом (Mini App) и нашим API.

Зачем отдельный файл:
  - Типы видны в одном месте
  - Pydantic автоматически валидирует входящие запросы
  - FastAPI на их основе строит OpenAPI-схему (Swagger UI)
  - Не путать с SQLAlchemy-моделями (db/models.py) — те для БД

Naming convention:
  - *In   — то что приходит от клиента (входящие запросы)
  - *Out  — то что отдаём клиенту (исходящие ответы)
  - Без суффикса — общие структуры (используются и там и там)
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════
#  Вопросы и системы (для GET /api/questions)
# ════════════════════════════════════════════════════════════
class SystemOut(BaseModel):
    """Описание одной системы организма (для Mini App)."""
    code: str = Field(..., description="Внутренний идентификатор", examples=["cardio"])
    name: str = Field(..., description="Название", examples=["Сердечно-сосудистая система"])


class QuestionOut(BaseModel):
    """Один вопрос теста."""
    number: int = Field(..., ge=1, le=36, description="Номер вопроса (1..36)")
    text: str = Field(..., description="Формулировка вопроса с эмодзи")
    systems: List[str] = Field(
        ...,
        description="Коды систем, на которые влияет ответ 'Да'",
        examples=[["cardio", "muscular"]],
    )


class QuestionsResponse(BaseModel):
    """Полный набор данных, которые нужны Mini App для отображения теста."""
    total: int = Field(..., description="Сколько всего вопросов")
    systems: List[SystemOut]
    questions: List[QuestionOut]


# ════════════════════════════════════════════════════════════
#  Сабмит теста (для POST /api/test/submit)
# ════════════════════════════════════════════════════════════
class AnswerIn(BaseModel):
    """Один ответ на вопрос — из Mini App."""
    question_number: int = Field(..., ge=1, le=36)
    answer: str = Field(..., description="'yes' или 'no'", examples=["yes"])


class PlatformInfoIn(BaseModel):
    """Откуда пришёл пользователь (на какой платформе он сейчас)."""
    platform: str = Field(
        ...,
        description="'telegram' / 'vk' / 'max'",
        pattern="^(telegram|vk|max)$",
    )
    user_id: int = Field(..., description="ID пользователя на платформе")
    username: Optional[str] = Field(None, description="@username (если есть)")
    first_name: Optional[str] = Field(None, description="Имя из платформы")


class TestSubmitIn(BaseModel):
    """
    Что Mini App присылает в POST /api/test/submit.
    """
    full_name: str = Field(..., min_length=2, max_length=255, description="ФИО клиента")
    phone: str = Field(..., min_length=10, max_length=20, description="Телефон в любом формате")
    consent: bool = Field(..., description="Согласие на обработку ПД (152-ФЗ)")
    answers: List[AnswerIn] = Field(..., min_length=36, max_length=36)
    platform: PlatformInfoIn

    # Реферальный код, если перешёл по invite-ссылке.
    # Это user_id рефереРА на той же платформе (не наш User.id из БД).
    referrer_platform_id: Optional[int] = Field(
        None,
        description="ID того кто пригласил (на той же платформе)",
    )


class SystemResultOut(BaseModel):
    """Краткий результат по одной системе — отдаётся клиенту."""
    code: str
    name: str
    score: int
    max_score: int
    percentage: int = Field(..., description="0..100, округлён до целого")
    status: str = Field(..., description="'good' / 'warning' / 'critical'")


class TestSubmitOut(BaseModel):
    """
    Что API возвращает Mini App после успешного сабмита.
    """
    lead_number: int = Field(..., description="Номер заявки клиента (#42)")
    systems: List[SystemResultOut] = Field(..., description="Результаты по 6 системам")

"""
Движок теста.

Здесь живёт бизнес-логика:
  - что значит "ответ Да"
  - как считать баллы по системам
  - как интерпретировать результат (хорошо/средне/плохо)
  - как формировать результат для клиента и для админа

Этот модуль НЕ ЗНАЕТ:
  - про БД (работает с ответами как со списком объектов)
  - про Telegram/VK/MAX (просто возвращает структуры данных)
  - про email/Excel (это в core/reports.py)

Такая чистота позволяет:
  1) тестировать логику отдельно от инфраструктуры
  2) использовать её ОДИНАКОВО на всех платформах
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Iterable

from core.questions import SYSTEMS, QUESTIONS_PER_SYSTEM, get_question


# ════════════════════════════════════════════════════════════
#  Константы
# ════════════════════════════════════════════════════════════

# Какие строки считаются ответом "Да" (нормализуем регистр и пробелы)
YES_ANSWERS = frozenset({"yes", "да", "1", "true", "y"})


# Пороги для интерпретации (% положительных ответов в системе)
THRESHOLD_GOOD = 50      # <= 50% → "всё в порядке"
THRESHOLD_WARNING = 80   # 51..80% → "требуется внимание"
                         # > 80%  → "требуется консультация"


# ════════════════════════════════════════════════════════════
#  Типы данных
# ════════════════════════════════════════════════════════════
class SystemStatus(str, Enum):
    """Статус по системе организма."""
    GOOD = "good"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def emoji(self) -> str:
        return {"good": "✅", "warning": "⚠️", "critical": "🔴"}[self.value]

    @property
    def label_ru(self) -> str:
        return {
            "good": "Всё в порядке",
            "warning": "Требуется внимание",
            "critical": "Требуется консультация",
        }[self.value]


@dataclass(frozen=True)
class AnswerInput:
    """
    Один ответ на вопрос — на вход движку.

    `system` — необязательно, потому что один вопрос может относиться
    к нескольким системам, и при подсчёте мы это сами разрулим.
    """
    question_number: int
    answer: str  # "yes" / "no" / синонимы


@dataclass(frozen=True)
class SystemResult:
    """Результат по одной системе."""
    system_code: str
    system_name: str
    score: int         # сколько ответов "Да" по вопросам этой системы
    max_score: int     # сколько всего вопросов привязано к этой системе
    percentage: float  # 0..100
    status: SystemStatus
    recommendation: str

    def __repr__(self) -> str:
        return (
            f"<{self.system_name}: {self.score}/{self.max_score} "
            f"({self.percentage:.0f}%) {self.status.value}>"
        )


@dataclass(frozen=True)
class TestResult:
    """Полный результат прохождения теста (по всем системам)."""
    systems: List[SystemResult]

    def get(self, system_code: str) -> SystemResult:
        """Получить результат по конкретной системе."""
        for s in self.systems:
            if s.system_code == system_code:
                return s
        raise KeyError(f"Нет системы '{system_code}' в результате")

    @property
    def critical_count(self) -> int:
        """Сколько систем в критическом состоянии — для сегментации лидов."""
        return sum(1 for s in self.systems if s.status == SystemStatus.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for s in self.systems if s.status == SystemStatus.WARNING)


# ════════════════════════════════════════════════════════════
#  Функции
# ════════════════════════════════════════════════════════════
def is_yes(answer: str) -> bool:
    """
    Является ли строка положительным ответом.

    Принимает разные написания: "yes", "Да", "да ", "1", "true" и т.д.
    """
    return str(answer).strip().lower() in YES_ANSWERS


def _classify(percentage: float) -> SystemStatus:
    """Перевести процент в статус по нашим порогам."""
    if percentage <= THRESHOLD_GOOD:
        return SystemStatus.GOOD
    elif percentage <= THRESHOLD_WARNING:
        return SystemStatus.WARNING
    else:
        return SystemStatus.CRITICAL


def calculate_result(answers: Iterable[AnswerInput]) -> TestResult:
    """
    Главная функция движка.

    Принимает: список ответов (любая последовательность AnswerInput)
    Возвращает: TestResult с разбивкой по 6 системам

    Алгоритм:
        1. Для каждого ответа "Да" определяем, к каким системам относится вопрос
        2. Прибавляем 1 балл к каждой такой системе
        3. Делим на максимум возможных баллов системы → процент
        4. Классифицируем процент → статус
    """
    # Считаем баллы. Изначально по каждой системе ноль.
    scores: Dict[str, int] = {sys_code: 0 for sys_code in SYSTEMS.keys()}

    for ans in answers:
        if not is_yes(ans.answer):
            continue  # "Нет" не даёт баллов
        try:
            question = get_question(ans.question_number)
        except ValueError:
            # Неизвестный номер вопроса — игнорируем (не падаем)
            continue
        for sys_code in question.systems:
            scores[sys_code] += 1

    # Формируем результат по каждой системе
    results: List[SystemResult] = []
    for sys_code, sys_info in SYSTEMS.items():
        score = scores[sys_code]
        max_score = QUESTIONS_PER_SYSTEM.get(sys_code, 0)
        percentage = (score / max_score * 100.0) if max_score > 0 else 0.0
        status = _classify(percentage)

        # Подбираем рекомендацию по статусу
        if status == SystemStatus.GOOD:
            recommendation = sys_info.rec_good
        elif status == SystemStatus.WARNING:
            recommendation = sys_info.rec_warning
        else:
            recommendation = sys_info.rec_critical

        results.append(SystemResult(
            system_code=sys_code,
            system_name=sys_info.name,
            score=score,
            max_score=max_score,
            percentage=percentage,
            status=status,
            recommendation=recommendation,
        ))

    return TestResult(systems=results)

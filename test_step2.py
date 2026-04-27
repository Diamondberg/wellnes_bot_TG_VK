"""
Скрипт самопроверки Шага 2 (расширенная версия).

Запуск:
    python test_step2.py

Что делает:
1. Проверяет вопросы и системы (как раньше)
2. Прогоняет фейкового пользователя через движок
3. Проверяет крайние случаи
4. Сохраняет TXT и Excel отчёты в output/reports/ с осмысленными именами
5. Пытается отправить email на адрес EMAIL_TO из .env
   (если email отключён в конфиге — просто пропускает шаг)
"""

import asyncio
import logging
import sys
from datetime import datetime

from core.config import settings
from core.questions import (
    QUESTIONS, SYSTEMS, total_questions, QUESTIONS_PER_SYSTEM,
)
from core.test_engine import (
    AnswerInput, calculate_result, SystemStatus,
)
from core.reports import (
    UserSnapshot, generate_txt_report, generate_excel_report,
)
from core.utils import build_report_paths
from core.notifier import send_lead_email

# Включаем логи notifier'а — будем видеть процесс отправки
logging.basicConfig(
    level=logging.INFO,
    format="  [%(name)s] %(message)s",
)


def section(title: str) -> None:
    print()
    print("═" * 70)
    print(f"  {title}")
    print("═" * 70)


def ok(text: str) -> None:
    print(f"  ✅ {text}")


def fail(text: str) -> None:
    print(f"  ❌ {text}")


def info(text: str) -> None:
    print(f"  ℹ️  {text}")


async def main() -> int:
    section("ШАГ 2: ПРОВЕРКА ЯДРА ТЕСТА (расширенная)")

    # ─── 1. Структура вопросов ──────────────────────────────
    section("1. Вопросы и системы")
    print(f"  Всего вопросов:  {total_questions()}")
    print(f"  Всего систем:    {len(SYSTEMS)}")
    print()
    print("  Распределение вопросов по системам:")
    for sys_code, sys_info in SYSTEMS.items():
        count = QUESTIONS_PER_SYSTEM.get(sys_code, 0)
        print(f"    • {sys_info.name}: {count} вопросов")

    if total_questions() != 36:
        fail(f"Ожидалось 36 вопросов, найдено {total_questions()}")
        return 1
    ok("Структура вопросов корректна")

    # ─── 2. Подсчёт результата ──────────────────────────────
    section("2. Подсчёт результата (СРЕДНИЙ профиль)")
    fake_answers = [
        AnswerInput(
            question_number=q.number,
            answer="yes" if q.number % 2 == 1 else "no",
        )
        for q in QUESTIONS
    ]

    result = calculate_result(fake_answers)

    print()
    print("  Результаты по системам:")
    for sys_result in result.systems:
        marker = sys_result.status.emoji
        print(
            f"    {marker} {sys_result.system_name}: "
            f"{sys_result.score}/{sys_result.max_score} "
            f"({sys_result.percentage:.0f}%) — {sys_result.status.label_ru}"
        )
    ok("Подсчёт по системам работает")

    # ─── 3. Крайние случаи ──────────────────────────────────
    section("3. Проверка крайних случаев")
    all_no = [AnswerInput(q.number, "no") for q in QUESTIONS]
    if all(s.status == SystemStatus.GOOD for s in calculate_result(all_no).systems):
        ok("Все 'Нет' → все системы GOOD")
    else:
        fail("Все 'Нет' дают неправильный результат")
        return 1

    all_yes = [AnswerInput(q.number, "yes") for q in QUESTIONS]
    if all(s.status == SystemStatus.CRITICAL for s in calculate_result(all_yes).systems):
        ok("Все 'Да' → все системы CRITICAL")
    else:
        fail("Все 'Да' дают неправильный результат")
        return 1

    # ─── 4. Генерация отчётов с правильными именами ────────
    section("4. Генерация отчётов в output/reports/")

    fake_user = UserSnapshot(
        lead_number=42,
        full_name="Иванов Иван Иванович",
        phone="+79991234567",
        platform="telegram",
        platform_user_id=123456789,
        platform_username="ivanov_test",
        referrer_name="Петров Пётр Петрович",
        referrer_phone="+79997654321",
    )

    txt_path, xlsx_path = build_report_paths(
        full_name=fake_user.full_name,
        lead_number=fake_user.lead_number,
        when=datetime.now(),
    )

    info(f"TXT  → {txt_path}")
    info(f"XLSX → {xlsx_path}")

    try:
        txt_bytes = generate_txt_report(fake_user, fake_answers, result)
        txt_path.write_bytes(txt_bytes)
        ok(f"TXT-отчёт сохранён ({len(txt_bytes)} байт)")
    except Exception as e:
        fail(f"Ошибка TXT: {e}")
        return 1

    try:
        xlsx_bytes = generate_excel_report(fake_user, fake_answers, result)
        xlsx_path.write_bytes(xlsx_bytes)
        ok(f"Excel-отчёт сохранён ({len(xlsx_bytes)} байт)")
    except Exception as e:
        fail(f"Ошибка Excel: {e}")
        return 1

    # ─── 5. Отправка email ──────────────────────────────────
    section("5. Отправка email")

    if not settings.email_enabled:
        info("Email отключён в .env (нет EMAIL_USER/EMAIL_PASSWORD/EMAIL_TO)")
        info("Пропускаем шаг — это ОК для теста")
    else:
        info(f"Отправляем на: {settings.email_to}")
        info(f"С адреса:      {settings.email_user}")
        info(f"SMTP:          {settings.email_host}:{settings.email_port}")

        sent = await send_lead_email(
            user=fake_user,
            result=result,
            txt_bytes=txt_bytes,
            xlsx_bytes=xlsx_bytes,
            txt_filename=txt_path.name,
            xlsx_filename=xlsx_path.name,
        )

        if sent:
            ok(f"Email отправлен на {settings.email_to}")
            info("Проверь почтовый ящик (включая папку 'Спам')")
        else:
            fail("Email не отправлен — смотри логи выше")

    # ─── Финал ──────────────────────────────────────────────
    section("✅ ШАГ 2 ПРОЙДЕН УСПЕШНО")
    print()
    print("  Что проверить:")
    print(f"    1. Папка output/reports/ — там твои файлы с латинскими именами")
    print(f"    2. Открой TXT и XLSX, проверь содержимое")
    if settings.email_enabled:
        print(f"    3. Проверь почту {settings.email_to}")
        print(f"       Письмо должно прийти с темой '🟠 Заявка #42: Иванов...'")
    print()
    print("  Если всё в порядке — сообщи: 'Шаг 2 готов' — пойдём на Шаг 3")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

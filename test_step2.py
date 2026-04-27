"""
Скрипт самопроверки Шага 2.

Запуск:
    python test_step2.py

Что делает:
1. Проверяет что вопросы и системы загрузились
2. Прогоняет фейковый "профиль здоровья" через движок
3. Проверяет что подсчёт баллов работает
4. Генерирует TXT-отчёт → сохраняет в test_output_report.txt
5. Генерирует Excel-отчёт → сохраняет в test_output_report.xlsx

После запуска ты можешь открыть эти файлы и посмотреть, как они выглядят.
"""

import sys
from pathlib import Path

from core.questions import (
    QUESTIONS, SYSTEMS, total_questions, QUESTIONS_PER_SYSTEM,
)
from core.test_engine import (
    AnswerInput, calculate_result, SystemStatus,
)
from core.reports import (
    UserSnapshot, generate_txt_report, generate_excel_report,
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


def main() -> int:
    section("ШАГ 2: ПРОВЕРКА ЯДРА ТЕСТА")

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

    # ─── 2. Подсчёт результата (фейковый пользователь) ──────
    section("2. Подсчёт результата")
    print("  Имитируем пользователя со СРЕДНИМ профилем здоровья:")
    print("  → отвечает 'Да' на каждый второй вопрос (нечётные номера)")

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

    if not result.systems or len(result.systems) != 6:
        fail(f"Ожидалось 6 систем в результате, получено {len(result.systems)}")
        return 1
    ok("Подсчёт по системам работает")

    # ─── 3. Сегментация лидов ───────────────────────────────
    section("3. Сегментация лида")
    print(f"  Критических систем: {result.critical_count}")
    print(f"  Warning систем:     {result.warning_count}")

    # Тесты крайних случаев
    print()
    print("  Проверка крайних случаев:")

    # Все "Нет" → все системы должны быть GOOD
    all_no = [AnswerInput(q.number, "no") for q in QUESTIONS]
    result_no = calculate_result(all_no)
    all_good = all(s.status == SystemStatus.GOOD for s in result_no.systems)
    if all_good:
        ok("При всех 'Нет' все системы в статусе GOOD")
    else:
        fail("При всех 'Нет' не все системы GOOD!")
        return 1

    # Все "Да" → все системы должны быть CRITICAL
    all_yes = [AnswerInput(q.number, "yes") for q in QUESTIONS]
    result_yes = calculate_result(all_yes)
    all_critical = all(s.status == SystemStatus.CRITICAL for s in result_yes.systems)
    if all_critical:
        ok("При всех 'Да' все системы в статусе CRITICAL")
    else:
        fail("При всех 'Да' не все системы CRITICAL!")
        return 1

    # ─── 4. Генерация TXT-отчёта ────────────────────────────
    section("4. Генерация TXT-отчёта")
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

    try:
        txt_data = generate_txt_report(fake_user, fake_answers, result)
        out_txt = Path("test_output_report.txt")
        out_txt.write_bytes(txt_data)
        ok(f"TXT-отчёт сохранён: {out_txt.absolute()}")
        ok(f"Размер: {len(txt_data)} байт")
    except Exception as e:
        fail(f"Ошибка генерации TXT: {e}")
        return 1

    # ─── 5. Генерация Excel-отчёта ──────────────────────────
    section("5. Генерация Excel-отчёта")
    try:
        xlsx_data = generate_excel_report(fake_user, fake_answers, result)
        out_xlsx = Path("test_output_report.xlsx")
        out_xlsx.write_bytes(xlsx_data)
        ok(f"Excel-отчёт сохранён: {out_xlsx.absolute()}")
        ok(f"Размер: {len(xlsx_data)} байт")
    except ImportError as e:
        fail(f"Не установлен openpyxl: {e}")
        print("\n  Установи: pip install openpyxl")
        return 1
    except Exception as e:
        fail(f"Ошибка генерации Excel: {e}")
        return 1

    # ─── Финал ──────────────────────────────────────────────
    section("✅ ШАГ 2 ПРОЙДЕН УСПЕШНО")
    print()
    print("  Что проверить вручную:")
    print(f"    1. Открой test_output_report.txt в блокноте")
    print(f"    2. Открой test_output_report.xlsx в Excel/LibreOffice")
    print(f"    3. Проверь что данные читаются и выглядят разумно")
    print()
    print("  После проверки сообщи: 'Шаг 2 готов' — пойдём на Шаг 3")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Утилиты общего назначения.

Тут пока только две функции:
  - transliterate(): русский → латиница (для имён файлов)
  - build_report_paths(): формирование путей для отчётов
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Tuple


# ════════════════════════════════════════════════════════════
#  Транслитерация (ГОСТ 7.79-2000, упрощённая)
# ════════════════════════════════════════════════════════════
_TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    " ": "_", "-": "_",
}


def transliterate(text: str) -> str:
    """
    Перевести русский текст в латиницу.
    Заменяет всё что не [a-zA-Z0-9_] на подчёркивание.
    Лишние подчёркивания схлопывает.

    >>> transliterate("Иванов Иван Иванович")
    'Ivanov_Ivan_Ivanovich'
    >>> transliterate("Пётр-Сергеевич")
    'Pyotr_Sergeevich'
    """
    if not text:
        return ""

    result = []
    for ch in text:
        lower_ch = ch.lower()
        if lower_ch in _TRANSLIT_MAP:
            translit = _TRANSLIT_MAP[lower_ch]
            # Сохраняем регистр первой буквы
            if ch.isupper() and translit:
                translit = translit[0].upper() + translit[1:]
            result.append(translit)
        elif ch.isalnum() or ch == "_":
            result.append(ch)
        else:
            result.append("_")

    # Схлопываем подряд идущие подчёркивания и убираем по краям
    out = "".join(result)
    out = re.sub(r"_+", "_", out)
    out = out.strip("_")
    return out


# ════════════════════════════════════════════════════════════
#  Формирование путей для отчётов
# ════════════════════════════════════════════════════════════
DEFAULT_REPORTS_DIR = Path("output") / "reports"


def build_report_paths(
    full_name: str,
    lead_number: int,
    base_dir: Path = DEFAULT_REPORTS_DIR,
    when: datetime = None,
) -> Tuple[Path, Path]:
    """
    Сформировать пути к TXT- и Excel-файлам отчёта.

    Создаёт папку base_dir если её нет.

    Формат имени:
        ГГГГ-ММ-ДД_ЧЧ-ММ_<lead_number>_<ФИО_латиницей>.<ext>
    Пример:
        output/reports/2026-04-27_05-30_42_Ivanov_Ivan_Ivanovich.txt

    Возвращает: (путь_к_txt, путь_к_xlsx)
    """
    if when is None:
        when = datetime.now()

    base_dir.mkdir(parents=True, exist_ok=True)

    name_latin = transliterate(full_name) or "user"
    timestamp = when.strftime("%Y-%m-%d_%H-%M")
    base_name = f"{timestamp}_{lead_number}_{name_latin}"

    return (
        base_dir / f"{base_name}.txt",
        base_dir / f"{base_name}.xlsx",
    )


# ════════════════════════════════════════════════════════════
#  Самопроверка при импорте
# ════════════════════════════════════════════════════════════
def _self_check() -> None:
    assert transliterate("Иванов Иван Иванович") == "Ivanov_Ivan_Ivanovich"
    assert transliterate("Пётр") == "Pyotr"
    assert transliterate("ООО Здоровье+") == "OOO_Zdorove"
    assert transliterate("") == ""


_self_check()

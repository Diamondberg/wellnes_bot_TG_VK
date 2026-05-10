"""
run_bot.py — точка входа для запуска TG-бота.

Запуск:
    python run_bot.py

Бот живёт ОТДЕЛЬНЫМ процессом от API. Они общаются через общую БД
(PostgreSQL): API пишет туда, бот при необходимости читает.

Для уведомлений рефереру в TG, API создаёт временный Bot-инстанс
(см. bot/notify.py) — то есть API _может_ слать сообщения через бота,
не дёргая bot-процесс. Так проще на MVP.
"""

import asyncio
import logging
import sys

from bot.main import start_polling


def setup_logging() -> None:
    """Настройка логирования для бота."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # aiogram сам по себе шумный на DEBUG — приглушаем
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    try:
        await start_polling()
    except (KeyboardInterrupt, SystemExit):
        logging.info("🛑 Остановка по сигналу")
    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

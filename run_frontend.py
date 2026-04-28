"""
Простой статический сервер для frontend во время разработки.

Запускает HTTP-сервер на порту 8001 в папке frontend/.
Открой в браузере: http://127.0.0.1:8001/

Зачем нужен:
  - Браузер блокирует часть фич если открыть HTML напрямую (file://)
  - Mini App SDK (Telegram WebApp) требует http(s) контекст
  - В проде frontend будет на nginx, а локально — этим скриптом

Запуск:
    python run_frontend.py
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

PORT = 8001
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Тише в логах — не пишем каждый запрос на картинку."""
    def log_message(self, format, *args):
        # Логируем только HTML-страницы и ошибки
        msg = format % args
        if ".html" in msg or "404" in msg or "500" in msg or "GET / " in msg:
            sys.stderr.write(f"[{self.log_date_time_string()}] {msg}\n")


def main() -> int:
    if not FRONTEND_DIR.exists():
        print(f"❌ Папки {FRONTEND_DIR} не существует.")
        return 1

    if not (FRONTEND_DIR / "index.html").exists():
        print(f"❌ В папке {FRONTEND_DIR} нет index.html")
        return 1

    # Меняем текущую директорию на frontend/ — сервер будет отдавать файлы оттуда
    os.chdir(FRONTEND_DIR)

    print("═" * 60)
    print("  WELLNESS TEST — FRONTEND DEV SERVER")
    print("═" * 60)
    print(f"  Папка:     {FRONTEND_DIR}")
    print(f"  Адрес:     http://127.0.0.1:{PORT}/")
    print(f"  Остановка: Ctrl+C")
    print("═" * 60)

    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler) as httpd:
            print(f"\n  🚀 Сервер запущен на http://127.0.0.1:{PORT}/\n")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n  🛑 Сервер остановлен")
        return 0
    except OSError as e:
        if e.errno == 10048 or "Address already in use" in str(e):
            print(f"\n❌ Порт {PORT} уже занят. Закрой другую программу или поменяй PORT в скрипте.")
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())

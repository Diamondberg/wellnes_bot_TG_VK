"""
Запуск FastAPI приложения локально.

Использование:
    python run_api.py

Запускает uvicorn с автоматической перезагрузкой кода при изменении файлов.
Для прода будем запускать иначе (через systemd + gunicorn/uvicorn workers).
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",   # только локально (для dev)
        port=8000,
        reload=True,        # auto-reload при изменении файлов
        log_level="info",
    )

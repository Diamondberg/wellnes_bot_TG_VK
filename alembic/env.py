"""
Конфигурация окружения Alembic.

Особенности:
1. Читаем DATABASE_URL из core.config (т.е. из .env)
2. Поддержка async (asyncpg)
3. Автогенерация миграций видит все модели через Base.metadata
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Добавляем корень проекта в sys.path, чтобы импорты вида "from db.models" работали
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings  # noqa: E402
from db.models import Base  # noqa: E402

# Alembic Config object
config = context.config

# Подставляем URL из нашего конфига
config.set_main_option("sqlalchemy.url", settings.database_url)

# Настройка логирования Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные всех моделей — для autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Миграции в offline-режиме (генерация SQL без подключения к БД)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Запуск миграций в async-режиме."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Миграции в online-режиме (с подключением к БД)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

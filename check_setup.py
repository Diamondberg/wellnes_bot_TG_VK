"""
Скрипт самопроверки Шага 1.

Запуск:
    python check_setup.py

Что проверяет:
1. Что .env существует и читается
2. Что все обязательные переменные заполнены
3. Что подключение к PostgreSQL работает
4. Что таблицы созданы (после `alembic upgrade head`)
5. Что есть запись в tenants для нашего TENANT_CODE
"""

import asyncio
import sys


def step(num: int, text: str) -> None:
    print(f"\n[{num}] {text}")


def ok(text: str) -> None:
    print(f"    ✅ {text}")


def fail(text: str) -> None:
    print(f"    ❌ {text}")


async def main() -> int:
    print("═" * 60)
    print("  ПРОВЕРКА ШАГА 1: Фундамент + БД")
    print("═" * 60)

    # ─── 1. Конфиг ──────────────────────────────────────────
    step(1, "Чтение .env через core.config")
    try:
        from core.config import settings
        ok(f"BOT_TOKEN: {settings.bot_token[:10]}...")
        ok(f"ADMIN_ID: {settings.admin_id}")
        ok(f"DATABASE_URL: {settings.database_url.split('@')[-1]}")
        ok(f"TENANT_CODE: {settings.tenant_code}")
        ok(f"TENANT_NAME: {settings.tenant_name}")
        ok(f"Email уведомления: {'включены' if settings.email_enabled else 'выключены'}")
    except Exception as e:
        fail(f"Не удалось загрузить конфиг: {e}")
        print("\n💡 Проверь:")
        print("   1. Существует ли файл .env (не .env.example!)")
        print("   2. Заполнены ли BOT_TOKEN, ADMIN_ID, DATABASE_URL")
        return 1

    # ─── 2. Подключение к БД ────────────────────────────────
    step(2, "Подключение к PostgreSQL")
    try:
        from db.engine import check_connection
        await check_connection()
        ok("PostgreSQL отвечает")
    except Exception as e:
        fail(f"Не удалось подключиться: {e}")
        print("\n💡 Проверь:")
        print("   1. Запущен ли PostgreSQL (Службы Windows → postgresql-x64-16)")
        print("   2. Создана ли база wellness_bot (через pgAdmin)")
        print("   3. Правильный ли пароль в DATABASE_URL")
        return 1

    # ─── 3. Существование таблиц ────────────────────────────
    step(3, "Проверка что таблицы созданы")
    try:
        from sqlalchemy import text
        from db.engine import async_session_maker

        expected_tables = {"tenants", "users", "answers", "referrals", "alembic_version"}

        async with async_session_maker() as session:
            result = await session.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public'"
            ))
            actual_tables = {row[0] for row in result.fetchall()}

        missing = expected_tables - actual_tables
        if missing:
            fail(f"Не хватает таблиц: {missing}")
            print("\n💡 Накати миграцию:")
            print("   alembic upgrade head")
            return 1
        ok(f"Найдены все таблицы: {sorted(actual_tables)}")
    except Exception as e:
        fail(f"Ошибка проверки таблиц: {e}")
        return 1

    # ─── 4. Проверка/создание записи Tenant ─────────────────
    step(4, f"Проверка записи Tenant с code='{settings.tenant_code}'")
    try:
        from sqlalchemy import select
        from db.engine import async_session_maker
        from db.models import Tenant

        async with async_session_maker() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.code == settings.tenant_code)
            )
            tenant = result.scalar_one_or_none()

            if tenant is None:
                # Создаём запись арендатора из конфига
                tenant = Tenant(
                    code=settings.tenant_code,
                    name=settings.tenant_name,
                    inn=settings.tenant_inn,
                    contact_tg=settings.tenant_contact_tg,
                    contact_email=settings.tenant_contact_email,
                    privacy_url=settings.tenant_privacy_url,
                    referral_terms_url=settings.tenant_referral_terms_url,
                    admin_telegram_id=settings.admin_id,
                    admin_email=settings.email_to,
                )
                session.add(tenant)
                await session.commit()
                ok(f"Создана запись Tenant: {tenant.name}")
            else:
                ok(f"Запись существует: {tenant.name} (id={tenant.id})")
    except Exception as e:
        fail(f"Ошибка работы с Tenant: {e}")
        return 1

    # ─── Финал ──────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  ✅ ШАГ 1 ПРОЙДЕН УСПЕШНО")
    print("═" * 60)
    print("\nЧто дальше:")
    print("  • Сообщи: 'Шаг 1 готов' — пойдём на Шаг 2 (ядро теста)")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

"""
Конфигурация проекта.

Загружает переменные из .env, валидирует их через pydantic.
Если какой-то обязательной переменной нет — приложение упадёт ПРИ СТАРТЕ
с понятной ошибкой (а не где-то посреди работы).

Использование:
    from core.config import settings
    print(settings.bot_token)
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки проекта в одном месте."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # BOT_TOKEN == bot_token
        extra="ignore",        # игнорировать лишние переменные в .env
    )

    # ─── Telegram ───────────────────────────────────────────
    bot_token: str = Field(..., description="Токен Telegram-бота")
    admin_id: int = Field(..., description="Telegram ID админа для уведомлений")

    # ─── База данных ────────────────────────────────────────
    database_url: str = Field(
        ...,
        description="URL подключения к PostgreSQL (asyncpg)",
    )

    # ─── Email (опционально) ────────────────────────────────
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_user: Optional[str] = None
    email_password: Optional[str] = None
    email_to: Optional[str] = None

    # ─── Прокси (опционально) ───────────────────────────────
    proxy_url: Optional[str] = None

    # ─── Арендатор (Tenant) ─────────────────────────────────
    tenant_code: str = "default"
    tenant_name: str = "ИП Иванов И.И."
    tenant_inn: str = "000000000000"
    tenant_contact_tg: str = "Diamondberg"
    tenant_contact_email: str = "admin@example.com"
    tenant_privacy_url: str = "https://example.com/privacy"
    tenant_referral_terms_url: str = "https://example.com/referral"

    # ─── Свойства-помощники ─────────────────────────────────
    @property
    def email_enabled(self) -> bool:
        """Включены ли email-уведомления (есть все необходимые поля)."""
        return all([self.email_user, self.email_password, self.email_to])


# Единственный экземпляр настроек на всё приложение.
# При импорте этого модуля произойдёт чтение .env и валидация.
settings = Settings()

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
    # ─── VK Mini App ────────────────────────────────────────
    vk_app_id: int = Field(..., description="ID VK Mini App (публичный)")
    vk_group_id: int = Field(..., description="ID группы ВК (публичный)")
    vk_secure_key: str = Field(..., description="Secure key приложения VK (секрет)")
    vk_service_token: str = Field(..., description="Service token приложения VK (секрет)")
    vk_community_token: str = Field(..., description="Community access token группы (секрет, права messages+manage)")
    vk_mini_app_url: str = Field(
        default="https://vk.com/app54517827",
        description="Публичная ссылка на VK Mini App (для реферальных ссылок)",
    )
    
    bot_token: str = Field(..., description="Токен Telegram-бота")
    bot_username: str = Field(
        default="WellnessTest_bot",
        description="Юзернейм бота БЕЗ @. Используется в реферальных ссылках.",
    )
    admin_id: int = Field(..., description="Telegram ID админа для уведомлений")

    # URL Mini App (фронта). На локалке это ngrok-ссылка типа https://abc.ngrok-free.app/
    # На проде — поддомен типа https://app.wellnesstest.ru/
    # Бот использует этот URL чтобы открыть Mini App кнопкой WebApp.
    mini_app_url: str = Field(
        default="http://127.0.0.1:5500",
        description="HTTPS URL Mini App (TG требует HTTPS для WebApp)",
    )

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

    # ─── Контакт консультанта ───────────────────────────────
    consultant_contact_url: str = Field(
        default="https://t.me/Diamondberg",
        description="URL для связи с консультантом (TG/WhatsApp/etc)",
    )

    # ─── Баннер магазина в письме ───────────────────────────
    shop_banner_url: str = Field(
        default="https://tentorium.ru",
        description="URL магазина/группы/канала в баннере письма",
    )
    shop_banner_title: str = Field(
        default="Пока вы ждёте звонка консультанта",
        description="Заголовок баннера магазина",
    )
    shop_banner_text: str = Field(
        default="Загляните в наш интернет-магазин — там много полезного для здоровья",
        description="Подзаголовок баннера",
    )
    shop_banner_button: str = Field(
        default="Перейти в магазин →",
        description="Текст на кнопке баннера",
    )
    shop_banner_emoji: str = Field(
        default="🛒",
        description="Эмодзи в шапке баннера",
    )

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

    @property
    def email_smtp_configured(self) -> bool:
        """SMTP настроен (для писем юзеру/рефереру — без email_to)."""
        return all([self.email_user, self.email_password])
    
    def vk_referral_link(self, platform_user_id: int) -> str:
        """
        Реферальная ссылка для VK Mini App.
        Пример: https://vk.com/app54517827#invite_12345
        """
        return f"{self.vk_mini_app_url}#invite_{platform_user_id}"

    def referral_link(self, platform_user_id: int) -> str:
        """
        Сгенерировать реферальную ссылку для пользователя.
        Пример: https://t.me/WellnessTest_bot?start=invite_12345
        """
        return f"https://t.me/{self.bot_username}?start=invite_{platform_user_id}"
    
    


settings = Settings()

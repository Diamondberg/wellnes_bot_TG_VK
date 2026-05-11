"""
Модели базы данных.

Архитектура:
    Tenant (1) ──< User (N) ──< Answer (N)
                   │
                   └──< Referral (N)

Ключевые решения:
1. tenant_id — везде. Задел под SaaS. Сейчас всегда один tenant ("default").
2. Пользователи мэтчатся по телефону В РАМКАХ tenant'а. Один человек =
   одна запись, даже если он зашёл и через TG, и через VK.
3. tg_user_id / vk_user_id / max_user_id — отдельные поля. Любое может быть NULL.
4. Реферальные связи — через внутренний User.id, не через TG-ID.
   Это позволит мэтчить рефералов с разных платформ.
5. email — опциональное поле. Если юзер указал — шлём ему копию отчёта на почту.
   Не уникальное (один email теоретически может быть у разных людей).
6. is_distributor — особая запись: владелец бота. К нему привязываются
   "холодные" лиды (без реф-ссылки или по битой ссылке). Корень реф-сети.
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


# ═══════════════════════════════════════════════════════════
#  TENANT — арендатор системы (для будущего SaaS)
# ═══════════════════════════════════════════════════════════
class Tenant(Base):
    """
    Арендатор бота. Сейчас будет один с code='default',
    создаваемый автоматически из .env при старте.
    Когда будет SaaS — здесь появятся реальные клиенты.
    """
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str] = mapped_column(String(20), nullable=False)
    contact_tg: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    privacy_url: Mapped[str] = mapped_column(String(512), nullable=False)
    referral_terms_url: Mapped[str] = mapped_column(String(512), nullable=False)

    # Куда слать уведомления о новых лидах
    admin_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    admin_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Связи
    users: Mapped[List["User"]] = relationship(back_populates="tenant")

    def __repr__(self) -> str:
        return f"<Tenant {self.code!r} ({self.name})>"


# ═══════════════════════════════════════════════════════════
#  USER — пользователь, прошедший тест
# ═══════════════════════════════════════════════════════════
class User(Base):
    """
    Лид. Один человек = одна запись (мэтчинг по телефону + tenant_id).

    Особый случай — `is_distributor=True`. Это запись владельца бота.
    Создаётся вручную SQL-скриптом при деплое. К ней привязываются
    «холодные» лиды (зашли через поиск/рекламу, без реф-ссылки).
    """
    __tablename__ = "users"
    __table_args__ = (
        # Один телефон в рамках одного арендатора
        UniqueConstraint("tenant_id", "phone", name="uq_user_tenant_phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ─── Контактные данные ─────────────────────────────────
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Email — необязательное. Если указан, шлём юзеру копию отчёта.
    # Без unique: теоретически один email может быть у разных людей
    # (семейный ящик и т.п.), и нам это не критично — мэтчим по телефону.
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ─── Идентификаторы на платформах (любой может быть NULL) ─
    tg_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    tg_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tg_first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    vk_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    max_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    # С какой платформы человек пришёл первый раз
    first_platform: Mapped[str] = mapped_column(String(16), nullable=False, default="telegram")

    # ─── Заявка ────────────────────────────────────────────
    lead_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Кто пригласил (реферер). Ссылка на User.id ВНУТРИ ЭТОГО ЖЕ tenant'а.
    referrer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ─── Дистрибьютор (корень реф-сети) ────────────────────
    # Это пометка для одной особой записи — владельца бота.
    # У дистрибьютора lead_number=0, и он НЕ получает уведомления
    # рефереру (потому что и так получает основные письма админу).
    is_distributor: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # ─── Согласие на обработку ПД (152-ФЗ) ─────────────────
    consent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ─── Метаданные ────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Связи
    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    answers: Mapped[List["Answer"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    referrer: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[id], foreign_keys=[referrer_id]
    )

    def __repr__(self) -> str:
        if self.is_distributor:
            return f"<User #{self.lead_number} {self.full_name} (DISTRIBUTOR)>"
        return f"<User #{self.lead_number} {self.full_name} ({self.phone})>"


# ═══════════════════════════════════════════════════════════
#  ANSWER — ответ на конкретный вопрос
# ═══════════════════════════════════════════════════════════
class Answer(Base):
    """
    Ответ пользователя на один вопрос теста.

    Согласно решению: при повторном прохождении старые ответы УДАЛЯЮТСЯ
    (а не накапливаются как попытки). Поэтому одна строка = один актуальный ответ.
    """
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("user_id", "question_number", "system",
                         name="uq_answer_user_question_system"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    answer: Mapped[str] = mapped_column(String(8), nullable=False)  # "yes" / "no"
    system: Mapped[str] = mapped_column(String(32), nullable=False)  # код системы организма

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Связи
    user: Mapped["User"] = relationship(back_populates="answers")

    def __repr__(self) -> str:
        return f"<Answer q{self.question_number}={self.answer} sys={self.system}>"


# ═══════════════════════════════════════════════════════════
#  REFERRAL — связь "кто пригласил кого"
# ═══════════════════════════════════════════════════════════
class Referral(Base):
    """
    Реферальная связь.

    Создаётся в двух случаях:
    1. Юзер прошёл тест по реф-ссылке — связь сохраняется уже с user.id
    2. (Будущее) Юзер кликнул по реф-ссылке, но не зарегистрировался —
       связь сохраняется только с platform+user_id

    Поле completed=True означает что приглашённый прошёл тест до конца.
    """
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Кто пригласил
    referrer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # На какой платформе произошёл клик
    platform: Mapped[str] = mapped_column(String(16), nullable=False)

    # ID приглашённого на платформе (может быть до того как он прошёл тест)
    referred_platform_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Внутренний ID приглашённого (NULL пока не зарегистрировался)
    referred_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Прошёл ли приглашённый тест до конца
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Referral {self.referrer_user_id} → {self.referred_user_id or '?'} "
            f"({self.platform}, completed={self.completed})>"
        )

"""add user email

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-02 12:00:00.000000

Добавляет опциональное поле email в таблицу users.

ВАЖНО: значение поля `down_revision` ниже — пустая строка-плейсхолдер.
Перед запуском замените её на ID последней существующей миграции в проекте
(см. `alembic history` или последний файл в alembic/versions/).
Если эта миграция первая — оставьте down_revision = None.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9fb2d67267d0"  # ← заменить на ID предыдущей миграции
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавить колонку email."""
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Убрать колонку email."""
    op.drop_column("users", "email")

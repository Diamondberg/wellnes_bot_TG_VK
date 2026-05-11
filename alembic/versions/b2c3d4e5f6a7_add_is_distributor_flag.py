"""add is_distributor flag to users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-11 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляем поле is_distributor в таблицу users.

    Зачем: помечаем одну запись как «дистрибьютор» (владелец бота).
    К нему привязываются все «холодные» лиды (зашедшие не по реф-ссылке
    или по битой реф-ссылке). Это «корень» реферальной сети.

    Логика в API:
      - Если referrer_platform_id не передан → реферер = дистрибьютор
      - Если передан, но юзер не найден → реферер = дистрибьютор
      - Если дистрибьютор сам себя пытается реферить → реферер = дистрибьютор

    Уведомления:
      - Дистрибьютору НЕ шлём «спасибо за заботу» (он и так получает
        основное письмо админу)
      - В письме админу — пометка «🌐 Зашёл напрямую» вместо блока
        «🎁 Реферал от» когда реферер = дистрибьютор
    """
    op.add_column(
        "users",
        sa.Column(
            "is_distributor",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Откат — убираем поле."""
    op.drop_column("users", "is_distributor")

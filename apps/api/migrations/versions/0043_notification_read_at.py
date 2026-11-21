"""Ilova ichidagi bildirishnomalar markazi: o'qilganlik (B6.3, ADR-064)

``notifications.read_at`` — foydalanuvchi ilovada o'qigan vaqt (NULL — o'qilmagan). Yetkazish holati (``status``: Telegram'ga
yuborildi / yuborilmadi) o'qilganlikdan alohida; ``skipped`` qatorlar (bazaviy ro'yxat yangilanishi) markazda ko'rinmaydi.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-21 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications", sa.Column("read_at", postgresql.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("notifications", "read_at")

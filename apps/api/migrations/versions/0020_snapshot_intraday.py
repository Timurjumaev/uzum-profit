"""Kun ichidagi snapshot va "yakunlangan deb birinchi ko'rilgan" vaqt (B4.70, ADR-057 Q7)

``sku_daily.zero_seen`` — shu kun ichida biror sinxronda Uzum qoldig'i (FBO faol + FBS) 0 ko'rilgan; bugungi qator endi har
mahsulot sinxronida yangilanadi (avval kuniga bir marta, 23:50 da). ``sale_items.completed_seen_at`` — qator birinchi marta
Yakunlangan holatda ko'rilgan vaqt (Uzum yakunlanish sanasini bermaydi); bu migratsiyadan oldingi qatorlar uchun noma'lum
(``NULL``) — taxmin bilan to'ldirilmaydi.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-12 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sku_daily",
        sa.Column("zero_seen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "sale_items",
        sa.Column("completed_seen_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "completed_seen_at")
    op.drop_column("sku_daily", "zero_seen")

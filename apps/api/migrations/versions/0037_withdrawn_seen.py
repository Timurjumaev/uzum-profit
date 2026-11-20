"""Yechib olingan deb birinchi ko'rilgan vaqt (B5.7, to'lov hodisalarini ma'lumotdan o'rganish)

``sale_items.withdrawn_seen_at`` — qator birinchi marta yechib olingan (``withdrawnProfit`` > 0) ko'rilgan vaqt. Uzum to'lov
sanasini bermaydi (``realcheck payout``: qatorda faqat ``withdrawnProfit``); to'lov hodisalari (sana, summa) shu belgidan
tiklanadi. Bu migratsiyadan oldin yechilgan qatorlar birinchi sinxronda bir paytda belgilanadi (boshlang'ich holat — haqiqiy
to'lov sanasi emas); ular tahlilda alohida hisoblanadi.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-20 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sale_items",
        sa.Column("withdrawn_seen_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "withdrawn_seen_at")

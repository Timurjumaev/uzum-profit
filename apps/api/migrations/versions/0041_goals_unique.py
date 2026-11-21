"""Oylik maqsadlar (B5.8, M12): bir oy, bir do'kon (yoki butun tashkilot) va ko'rsatkich uchun bitta maqsad

``goals`` jadvali (B0) endi ishlatiladi: shu ustun to'plamida noyoblik (``shop_id`` NULL — butun tashkilot, NULL'lar teng
sanaladi), ko'rsatkich — tushum / sof foyda / dona, maqsad musbat, davr — kalendar oyi bo'lishi API'da tekshiriladi.
Tovar bo'yicha maqsad (``item_id``) — "Keyinga" (ADR-063), ishlatilmaydi.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-21 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_goals_org_id_shop_id_item_id_metric_period_start"),
        "goals",
        ["org_id", "shop_id", "item_id", "metric", "period_start"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_check_constraint(
        op.f("ck_goals_metric"), "goals", sa.text("metric IN ('revenue', 'net_profit', 'units')")
    )
    op.create_check_constraint(op.f("ck_goals_target"), "goals", sa.text("target > 0"))


def downgrade() -> None:
    op.drop_constraint(op.f("ck_goals_target"), "goals", type_="check")
    op.drop_constraint(op.f("ck_goals_metric"), "goals", type_="check")
    op.drop_constraint(
        op.f("uq_goals_org_id_shop_id_item_id_metric_period_start"), "goals", type_="unique"
    )

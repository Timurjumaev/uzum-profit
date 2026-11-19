"""Tovarning odatiy partiya hajmi (B5.2, F27)

- ``items.order_batch`` — dona, ixtiyoriy (bo'sh — 1): tavsiya buyurtma miqdori shunga yuqoriga yaxlitlanadi.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-19 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("items", sa.Column("order_batch", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_items_order_batch"), "items", "order_batch IS NULL OR order_batch >= 1"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_items_order_batch"), "items", type_="check")
    op.drop_column("items", "order_batch")

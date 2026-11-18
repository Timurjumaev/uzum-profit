"""Jo'natmadagi tannarx belgisi (TM9.7, ADR-068; 09 §17 G11)

- ``fbo_dispatch_items.cost_mark`` — Excel'dagi tannarx qayerdan: ``estimated`` (F21 lot narxi taxminiy, F22),
  ``manual`` (sotuvchi kiritdi — noma'lum / taxminiy o'rniga). Bo'sh — aniq lot narxi (eski yozuvlar ham).

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-18 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fbo_dispatch_items", sa.Column("cost_mark", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_fbo_dispatch_items_cost_mark_allowed"),
        "fbo_dispatch_items",
        "cost_mark IN ('estimated', 'manual')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_fbo_dispatch_items_cost_mark_allowed"), "fbo_dispatch_items", type_="check"
    )
    op.drop_column("fbo_dispatch_items", "cost_mark")

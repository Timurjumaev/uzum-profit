"""Omborim: boshqa SKU'ga o'tkazish va brak zarari (TM5, ADR-061 §6–§7)

- ``purchase_lines.source_line_id`` — o'tkazilgan qator: shu xariddagi manba qator donalari boshqa SKU'ga uning birlik
  tannarxi bilan o'tadi (F20, ``upcore.purchasing.apply_transfers``).
- ``stock_moves.reason`` (``defect`` — sanashdan keyin topilgan brak, F51), ``stock_moves.cost`` (lot narxidagi qiymat —
  tannarx dvigateli yozadi), ``stock_moves.sku_id`` (qaysi SKU omboridan).

Mavjud yozuvlar o'zgarmaydi.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-13 04:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("purchase_lines", sa.Column("source_line_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_purchase_lines_source_line_id",
        "purchase_lines",
        "purchase_lines",
        ["org_id", "source_line_id"],
        ["org_id", "id"],
    )
    op.add_column("stock_moves", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("stock_moves", sa.Column("cost", sa.Numeric(18, 2), nullable=True))
    op.add_column("stock_moves", sa.Column("sku_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_stock_moves_sku_id", "stock_moves", "mp_skus", ["org_id", "sku_id"], ["org_id", "id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_stock_moves_sku_id", "stock_moves", type_="foreignkey")
    op.drop_column("stock_moves", "sku_id")
    op.drop_column("stock_moves", "cost")
    op.drop_column("stock_moves", "reason")
    op.drop_constraint("fk_purchase_lines_source_line_id", "purchase_lines", type_="foreignkey")
    op.drop_column("purchase_lines", "source_line_id")

"""reports (B2.9)

O'qish API'lari (dashboard, P&L, SKU) ``daily_sku_metrics`` ustida: P&L kataklari uchun Yakunlangan qatorlar soni
va shundan tannarxsizlari (``upcore.pnl.build_cells(totals=...)``, F15 "N ta sotuv tannarxsiz"), tannarxi ma'lum
dona (M6 unit-iqtisod). Mavjud qatorlarda 0 — tungi ``calc.nightly`` (to'liq qayta qurish) to'ldiradi.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("lines", "lines_uncosted", "units_costed")


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column(
            "daily_sku_metrics", sa.Column(column, sa.Integer(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("daily_sku_metrics", column)

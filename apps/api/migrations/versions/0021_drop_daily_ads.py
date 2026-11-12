"""``daily_sku_metrics.ads`` olib tashlanadi (B4.75 PR-6, audit K13)

Ustun har qayta qurishda yozilardi, lekin hech qayerda o'qilmasdi: reklama (F19, F42) ``mp_expenses`` dan to'g'ridan-to'g'ri
hisoblanadi (``upapi.reports.cells``). Qaytarishda ustun 0 bilan tiklanadi (reklama baribir ``mp_expenses`` da).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-12 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("daily_sku_metrics", "ads")


def downgrade() -> None:
    op.add_column(
        "daily_sku_metrics",
        sa.Column("ads", sa.Numeric(18, 2), server_default="0", nullable=False),
    )

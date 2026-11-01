"""Jarayondagi sotuvlar hisobga kiradi (ADR-036)

``daily_sku_metrics``: pul va dona ustunlari endi Yakunlangan + Jarayonda; Jarayondagi (yakuniy emas) qism —
``units_processing``, ``revenue_processing``. Mavjud qatorlar eski ma'noda (faqat Yakunlangan) — har tashkilot uchun
kunlik agregatni to'liq qayta qurish so'rovi (``recalc_queue``, ``metrics``) qo'yiladi; worker deploy'dan keyin quradi.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-02 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_sku_metrics",
        sa.Column("units_processing", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "daily_sku_metrics",
        sa.Column("revenue_processing", sa.Numeric(18, 2), server_default="0", nullable=False),
    )
    op.execute(
        "INSERT INTO recalc_queue (org_id, kind, ref_id, since) SELECT id, 'metrics', NULL, NULL FROM orgs "
        "ON CONFLICT (org_id, kind, ref_id) DO UPDATE SET since = NULL, updated_at = now()"
    )


def downgrade() -> None:
    op.drop_column("daily_sku_metrics", "revenue_processing")
    op.drop_column("daily_sku_metrics", "units_processing")

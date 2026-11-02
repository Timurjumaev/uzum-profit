"""Naqd va kutilayotgan sof foyda (ADR-037)

``daily_sku_metrics``: Jarayondagi qism endi hamma pul ustunlari bo'yicha (komissiya, logistika, tannarx, tannarxi
ma'lum tushum va to'lov, dona, qatorlar) — kutilayotgan sof foyda (F16) shu qismdan; Uzum logistikasini hali yozmagan
Jarayondagi qatorlar donasi (taxmin asosi, F5). Mavjud qatorlarda yangi ustunlar 0 — har tashkilot uchun kunlik
agregatni to'liq qayta qurish so'rovi (``recalc_queue``, ``metrics``) qo'yiladi; worker deploy'dan keyin quradi.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-02 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = (
    "commission_processing",
    "logistics_processing",
    "cogs_processing",
    "revenue_costed_processing",
    "payout_costed_processing",
)
COUNTS = (
    "units_costed_processing",
    "lines_processing",
    "lines_uncosted_processing",
    "units_logistics_due",
    "units_logistics_due_costed",
    "lines_logistics_due",
)


def upgrade() -> None:
    for name in MONEY:
        op.add_column(
            "daily_sku_metrics",
            sa.Column(name, sa.Numeric(18, 2), server_default="0", nullable=False),
        )
    for name in COUNTS:
        op.add_column(
            "daily_sku_metrics", sa.Column(name, sa.Integer(), server_default="0", nullable=False)
        )
    op.execute(
        "INSERT INTO recalc_queue (org_id, kind, ref_id, since) SELECT id, 'metrics', NULL, NULL FROM orgs "
        "ON CONFLICT (org_id, kind, ref_id) DO UPDATE SET since = NULL, updated_at = now()"
    )


def downgrade() -> None:
    for name in reversed(COUNTS):
        op.drop_column("daily_sku_metrics", name)
    for name in reversed(MONEY):
        op.drop_column("daily_sku_metrics", name)

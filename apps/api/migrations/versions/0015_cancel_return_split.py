"""Bekor va qaytarish alohida (ADR-043)

``daily_sku_metrics``: Bekor holatdagi qatorlar ikkiga bo'linadi — tovar xaridorga topshirilgan (``dateIssued`` bor:
mijoz olgan yoki punktda ko'rib rad etgan) — qaytarish (F18), topshirilmagan — bekor (F17); bekor va qaytarish summalari
(yalpi GMV, F44). Mavjud qatorlarda yangi ustunlar 0 — har tashkilot uchun kunlik agregatni to'liq qayta qurish so'rovi
(``recalc_queue``, ``metrics``) qo'yiladi; worker deploy'dan keyin quradi.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-04 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = ("canceled_revenue", "canceled_issued_revenue", "returns_revenue")
COUNTS = ("canceled_issued",)


def upgrade() -> None:
    for name in COUNTS:
        op.add_column(
            "daily_sku_metrics", sa.Column(name, sa.Integer(), server_default="0", nullable=False)
        )
    for name in MONEY:
        op.add_column(
            "daily_sku_metrics",
            sa.Column(name, sa.Numeric(18, 2), server_default="0", nullable=False),
        )
    op.execute(
        "INSERT INTO recalc_queue (org_id, kind, ref_id, since) SELECT id, 'metrics', NULL, NULL FROM orgs "
        "ON CONFLICT (org_id, kind, ref_id) DO UPDATE SET since = NULL, updated_at = now()"
    )


def downgrade() -> None:
    for name in reversed(MONEY):
        op.drop_column("daily_sku_metrics", name)
    for name in reversed(COUNTS):
        op.drop_column("daily_sku_metrics", name)

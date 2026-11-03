"""Sotuv logistikasi — Uzum aslida yechgani (ADR-042)

``daily_sku_metrics`` dagi logistika endi sotuv qatoriga bog'langan logistika chiqimlari yig'indisidan (bo'lmasa
qatordagi ``logisticDeliveryFee``) quriladi. Sxema o'zgarmaydi — har tashkilot uchun kunlik agregatni to'liq qayta
qurish so'rovi (``recalc_queue``, ``metrics``) qo'yiladi; worker deploy'dan keyin quradi.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-03 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO recalc_queue (org_id, kind, ref_id, since) SELECT id, 'metrics', NULL, NULL FROM orgs "
        "ON CONFLICT (org_id, kind, ref_id) DO UPDATE SET since = NULL, updated_at = now()"
    )


def downgrade() -> None:
    """Qayta qurish so'rovi — ma'lumot emas; qaytarishda hech narsa qilinmaydi."""

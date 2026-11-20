"""To'lov jadvali — butun akkaunt uchun (B5.7, Temur 2026-11-16)

Uzum to'lov jadvalini butun akkauntga bitta qilib belgilaydi (Temurning kabineti: jadval do'konga bog'liq emas, pul
yechish haqi ham ``shopId: 0`` bilan keladi — ADR-062). ``payout_schedules.shop_id`` o'rniga ``account_id`` (``mp_accounts``):
mavjud qatorlar do'konning akkauntiga ko'chadi; bir akkaunt va sanada bir nechta bo'lsa — eng yangisi qoladi.

Qaytarish: har qator akkauntning har bir do'koni uchun nusxalanadi.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-20 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payout_schedules", sa.Column("account_id", sa.UUID(), nullable=True))
    op.execute(
        "UPDATE payout_schedules p SET account_id = s.account_id FROM shops s "
        "WHERE s.org_id = p.org_id AND s.id = p.shop_id"
    )
    op.execute(  # bir akkaunt va sanada bittadan ortiq bo'lsa — eng yangisi qoladi
        "DELETE FROM payout_schedules a USING payout_schedules b "
        "WHERE a.org_id = b.org_id AND a.account_id = b.account_id AND a.valid_from = b.valid_from "
        "AND (a.created_at, a.id) < (b.created_at, b.id)"
    )
    op.alter_column("payout_schedules", "account_id", nullable=False)
    op.drop_constraint("fk_payout_schedules_shop_id", "payout_schedules", type_="foreignkey")
    op.drop_column("payout_schedules", "shop_id")
    op.create_foreign_key(
        "fk_payout_schedules_account_id",
        "payout_schedules",
        "mp_accounts",
        ["org_id", "account_id"],
        ["org_id", "id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_payout_schedules_org_id_account_id_valid_from"),
        "payout_schedules",
        ["org_id", "account_id", "valid_from"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_payout_schedules_org_id_account_id_valid_from", "payout_schedules", type_="unique"
    )
    op.drop_constraint("fk_payout_schedules_account_id", "payout_schedules", type_="foreignkey")
    op.add_column("payout_schedules", sa.Column("shop_id", sa.UUID(), nullable=True))
    op.execute(  # har qator akkauntning birinchi do'koniga qaytadi
        "UPDATE payout_schedules p SET shop_id = (SELECT s.id FROM shops s WHERE s.org_id = p.org_id "
        "AND s.account_id = p.account_id ORDER BY s.created_at, s.id LIMIT 1)"
    )
    op.execute("DELETE FROM payout_schedules WHERE shop_id IS NULL")
    op.alter_column("payout_schedules", "shop_id", nullable=False)
    op.create_foreign_key(
        "fk_payout_schedules_shop_id",
        "payout_schedules",
        "shops",
        ["org_id", "shop_id"],
        ["org_id", "id"],
        ondelete="CASCADE",
    )
    op.drop_column("payout_schedules", "account_id")

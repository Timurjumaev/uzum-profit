"""calc (B2.8)

Hisob ishlari (``upapi.calc``): lotlar (F20), sotuv tannarxi (F21) va kunlik agregat qayta qurilishi.

- ``recalc_queue`` — qayta hisob navbati (tashkilot jadvali, RLS): manba o'zgarganda (sinxron, xarid) shu
  tranzaksiyada yoziladi, hisob ishi o'qib bajaradi va o'chiradi. ``(org_id, kind, ref_id)`` unikal, NULL ham
  bitta qiymat (``NULLS NOT DISTINCT``) — takroriy so'rov bitta qatorga birlashadi.
- ``sale_costs`` ga "qayta hisoblandi" belgisi (``changed_at``, ``previous_cogs``, 03 §7).
- ``daily_sku_metrics`` ga tannarxi ma'lum qism (F15, F8) va taxminiy qism (F22) ustunlari.
- ``lots`` — bitta xarid qatoriga bitta lot; tovar bo'yicha indekslar (``lots``, ``mp_skus``, ``sale_items``).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25 10:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)
UZS = sa.Numeric(18, 2)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "recalc_queue",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.UUID(), nullable=True),
        sa.Column("since", sa.Date(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('purchase', 'item', 'shop', 'metrics')",
            name=op.f("ck_recalc_queue_kind_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["orgs.id"],
            name=op.f("fk_recalc_queue_org_id_orgs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recalc_queue")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_recalc_queue_org_id_id")),
        sa.UniqueConstraint(
            "org_id",
            "kind",
            "ref_id",
            name=op.f("uq_recalc_queue_org_id_kind_ref_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    for statement in rls.tenant("recalc_queue", app_role):
        op.execute(statement)

    op.add_column("sale_costs", sa.Column("changed_at", TS, nullable=True))
    op.add_column("sale_costs", sa.Column("previous_cogs", UZS, nullable=True))
    for column in ("revenue_costed", "payout_costed", "cogs_estimated"):
        op.add_column(
            "daily_sku_metrics", sa.Column(column, UZS, server_default="0", nullable=False)
        )
    op.create_unique_constraint(
        op.f("uq_lots_org_id_purchase_line_id"), "lots", ["org_id", "purchase_line_id"]
    )
    op.create_index(op.f("ix_lots_org_id_item_id"), "lots", ["org_id", "item_id"])
    op.create_index(op.f("ix_mp_skus_org_id_item_id"), "mp_skus", ["org_id", "item_id"])
    op.create_index(op.f("ix_sale_items_org_id_sku_id"), "sale_items", ["org_id", "sku_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sale_items_org_id_sku_id"), table_name="sale_items")
    op.drop_index(op.f("ix_mp_skus_org_id_item_id"), table_name="mp_skus")
    op.drop_index(op.f("ix_lots_org_id_item_id"), table_name="lots")
    op.drop_constraint(op.f("uq_lots_org_id_purchase_line_id"), "lots", type_="unique")
    for column in ("cogs_estimated", "payout_costed", "revenue_costed"):
        op.drop_column("daily_sku_metrics", column)
    op.drop_column("sale_costs", "previous_cogs")
    op.drop_column("sale_costs", "changed_at")
    op.drop_table("recalc_queue")

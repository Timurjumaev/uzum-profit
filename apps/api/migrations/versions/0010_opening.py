"""boshlang'ich holat (B4.12, ADR-033, F41)

``orgs.cost_start_on`` — boshlash sanasi (NULL — o'chirilgan); ``item_costs`` — tovar tarixiy tannarxi sana bo'yicha;
``opening_stock`` — boshlash sanasidagi qoldiq (Uzumda + o'z omborimda).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01 12:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def _common(name: str) -> list[object]:
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
    ]


def _tail(name: str) -> list[object]:
    return [
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "item_id"],
            ["items.org_id", "items.id"],
            name=f"fk_{name}_item_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f(f"fk_{name}_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
        sa.UniqueConstraint("org_id", "id", name=op.f(f"uq_{name}_org_id_id")),
    ]


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.add_column("orgs", sa.Column("cost_start_on", sa.Date(), nullable=True))
    op.create_table(
        "item_costs",
        *_common("item_costs"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        *_tail("item_costs"),
        sa.CheckConstraint("unit_cost >= 0", name=op.f("ck_item_costs_unit_cost")),
        sa.UniqueConstraint(
            "org_id",
            "item_id",
            "valid_from",
            name=op.f("uq_item_costs_org_id_item_id_valid_from"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "opening_stock",
        *_common("opening_stock"),
        sa.Column("uzum_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("own_qty", sa.Integer(), server_default="0", nullable=False),
        *_tail("opening_stock"),
        sa.CheckConstraint("uzum_qty >= 0 AND own_qty >= 0", name=op.f("ck_opening_stock_qty")),
        sa.UniqueConstraint("org_id", "item_id", name=op.f("uq_opening_stock_org_id_item_id")),
    )
    for table in ("item_costs", "opening_stock"):
        for statement in rls.tenant(table, app_role):
            op.execute(statement)


def downgrade() -> None:
    op.drop_table("opening_stock")
    op.drop_table("item_costs")
    op.drop_column("orgs", "cost_start_on")

"""Kargo (jo'natma): bitta kargo — ko'p xarid (B4.31, ADR-046)

``shipments`` — kargo (nomi, kargo kompaniyasi, Xitoy omborida / yo'lda / Toshkentga keldi sanalari, izoh);
``purchases.shipment_id`` — xarid faqat bitta kargoga tegishli (ixtiyoriy); ``cost_components`` xaridniki yoki kargoniki
(``purchase_id`` yoki ``shipment_id`` — aynan bittasi). Mavjud xarid va komponentlar o'zgarmaydi: kargosiz xarid avvalgidek
ishlaydi.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-04 23:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "shipments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("carrier_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("cn_warehouse_on", sa.Date(), nullable=True),
        sa.Column("shipped_on", sa.Date(), nullable=True),
        sa.Column("arrived_on", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "carrier_id"],
            ["carriers.org_id", "carriers.id"],
            name="fk_shipments_carrier_id",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_shipments_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipments")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_shipments_org_id_id")),
    )
    for statement in rls.tenant("shipments", app_role):
        op.execute(statement)

    op.add_column("purchases", sa.Column("shipment_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_purchases_shipment_id",
        "purchases",
        "shipments",
        ["org_id", "shipment_id"],
        ["org_id", "id"],
    )
    op.alter_column("cost_components", "purchase_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("cost_components", sa.Column("shipment_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_cost_components_shipment_id",
        "cost_components",
        "shipments",
        ["org_id", "shipment_id"],
        ["org_id", "id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_cost_components_owner_exactly_one"),
        "cost_components",
        "num_nonnulls(purchase_id, shipment_id) = 1",
    )
    op.create_index(op.f("ix_purchases_org_id_shipment_id"), "purchases", ["org_id", "shipment_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_purchases_org_id_shipment_id"), table_name="purchases")
    op.execute("DELETE FROM cost_components WHERE purchase_id IS NULL")
    op.drop_constraint(
        op.f("ck_cost_components_owner_exactly_one"), "cost_components", type_="check"
    )
    op.drop_constraint("fk_cost_components_shipment_id", "cost_components", type_="foreignkey")
    op.drop_column("cost_components", "shipment_id")
    op.alter_column("cost_components", "purchase_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("fk_purchases_shipment_id", "purchases", type_="foreignkey")
    op.drop_column("purchases", "shipment_id")
    op.drop_table("shipments")

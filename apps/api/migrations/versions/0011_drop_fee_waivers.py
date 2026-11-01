"""fee_waivers olib tashlanadi (ADR-035, ADR-031 almashtirildi)

Uzum bonuslari (bepul logistika va h.k.) endi alohida qayd etilmaydi: Uzum API nima bersa, shu olinadi — logistika 0
kelsa, 0. ``fee_waivers`` jadvali (qo'lda kiritilgan bonus davrlari va rad etilgan takliflar) hech qanday hisobga
ta'sir qilmagan, shuning uchun ma'lumot ko'chirilmaydi. ``downgrade`` bo'sh jadvalni qayta yaratadi (0008 dagidek).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-01 18:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.drop_index(op.f("ix_fee_waivers_org_id_start_on_end_on"), table_name="fee_waivers")
    op.drop_table("fee_waivers")


def downgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "fee_waivers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=True),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("end_on", sa.Date(), nullable=False),
        sa.Column("kinds", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("source", sa.Text(), server_default="manual", nullable=False),
        sa.Column("dismissed_at", TS, nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "source IN ('manual', 'detected')", name=op.f("ck_fee_waivers_source_allowed")
        ),
        sa.CheckConstraint("end_on >= start_on", name=op.f("ck_fee_waivers_period")),
        sa.CheckConstraint("cardinality(kinds) > 0", name=op.f("ck_fee_waivers_kinds")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_fee_waivers_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "shop_id"], ["shops.org_id", "shops.id"], name="fk_fee_waivers_shop_id"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_fee_waivers_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fee_waivers")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_fee_waivers_org_id_id")),
    )
    op.create_index(
        op.f("ix_fee_waivers_org_id_start_on_end_on"),
        "fee_waivers",
        ["org_id", "start_on", "end_on"],
    )
    for statement in rls.tenant("fee_waivers", app_role):
        op.execute(statement)

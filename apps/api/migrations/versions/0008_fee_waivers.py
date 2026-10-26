"""fee_waivers (B4.2a, ADR-031)

Uzum bonuslari — vaqtinchalik bepul xarajat davrlari (ma'lumot, qoida emas): do'kon yoki hammasi (``shop_id`` NULL),
sanalar, bepul turlar (``kinds``), sabab, manba (qo'lda / tizim taklifi), rad etilgan taklif (``dismissed_at``).
``free_logistics_periods`` o'rniga — u bo'sh edi (hech kim yozmagan), ma'lumot ko'chirilmaydi.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26 18:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def _times() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.drop_table("free_logistics_periods")
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
        *_times(),
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


def downgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.drop_index(op.f("ix_fee_waivers_org_id_start_on_end_on"), table_name="fee_waivers")
    op.drop_table("fee_waivers")
    op.create_table(
        "free_logistics_periods",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("end_on", sa.Date(), nullable=False),
        sa.Column("detected", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("confirmed_at", TS, nullable=True),
        *_times(),
        sa.ForeignKeyConstraint(
            ["org_id", "shop_id"],
            ["shops.org_id", "shops.id"],
            name="fk_free_logistics_periods_shop_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["orgs.id"],
            name=op.f("fk_free_logistics_periods_org_id_orgs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_free_logistics_periods")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_free_logistics_periods_org_id_id")),
    )
    for statement in rls.tenant("free_logistics_periods", app_role):
        op.execute(statement)

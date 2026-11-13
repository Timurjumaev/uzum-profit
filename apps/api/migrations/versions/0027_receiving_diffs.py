"""Uzum qabulidagi farq (TM7, ADR-061 §8)

``receiving_diffs`` — jo'natma × SKU bo'yicha sotuvchi qarori: ``lost`` (Uzum yo'qotdi — kamomad ro'yxati; holat
``open`` → ``found`` / ``compensated`` / ``written_off``, kompensatsiya summasi, yopilgan sana; F52), ``miscount``
(sanashda adashganman — xarid soni tuzatildi), ``found`` (ortiqcha qabul ochiq kamomadni yopdi), ``recount`` (ortiqcha —
xarid soni oshirildi). Mavjud yozuvlar o'zgarmaydi.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-13 08:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "receiving_diffs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("dispatch_id", sa.UUID(), nullable=False),
        sa.Column("sku_id", sa.UUID(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="closed", nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("compensation", sa.Numeric(18, 2), nullable=True),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "resolution IN ('lost', 'miscount', 'found', 'recount')",
            name=op.f("ck_receiving_diffs_resolution_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'found', 'compensated', 'written_off', 'closed')",
            name=op.f("ck_receiving_diffs_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "dispatch_id"],
            ["fbo_dispatches.org_id", "fbo_dispatches.id"],
            name="fk_receiving_diffs_dispatch_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "sku_id"],
            ["mp_skus.org_id", "mp_skus.id"],
            name="fk_receiving_diffs_sku_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_receiving_diffs_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receiving_diffs")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_receiving_diffs_org_id_id")),
        sa.UniqueConstraint(
            "org_id",
            "dispatch_id",
            "sku_id",
            name=op.f("uq_receiving_diffs_org_id_dispatch_id_sku_id"),
        ),
    )
    for statement in rls.tenant("receiving_diffs", app_role):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("receiving_diffs")

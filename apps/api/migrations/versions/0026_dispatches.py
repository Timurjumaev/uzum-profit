"""Uzumga jo'natma (TM6, ADR-061 §7, ADR-050)

``fbo_dispatches`` — do'kon bo'yicha jo'natma (Excel chiqarilgan vaqt, holat: ``sending`` jo'natilmoqda / ``linked``
postavka bilan bog'landi / ``canceled`` bekor, bog'langan ``fbo_invoices`` yozuvi); ``fbo_dispatch_items`` — SKU, dona,
Excel'dagi tannarx va shtrix-kod. Mavjud yozuvlar o'zgarmaydi.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-13 06:00:00
"""

import os
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def _base(name: str) -> list[Any]:
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
    ]


def _tail(name: str) -> list[Any]:
    return [
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f(f"fk_{name}_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
        sa.UniqueConstraint("org_id", "id", name=op.f(f"uq_{name}_org_id_id")),
    ]


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "fbo_dispatches",
        *_base("fbo_dispatches"),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), server_default="sending", nullable=False),
        sa.Column("exported_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("linked_at", TS, nullable=True),
        sa.Column("canceled_at", TS, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('sending', 'linked', 'canceled')",
            name=op.f("ck_fbo_dispatches_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "shop_id"],
            ["shops.org_id", "shops.id"],
            name="fk_fbo_dispatches_shop_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "invoice_id"],
            ["fbo_invoices.org_id", "fbo_invoices.id"],
            name="fk_fbo_dispatches_invoice_id",
        ),
        *_tail("fbo_dispatches"),
    )
    op.create_table(
        "fbo_dispatch_items",
        *_base("fbo_dispatch_items"),
        sa.Column("dispatch_id", sa.UUID(), nullable=False),
        sa.Column("sku_id", sa.UUID(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.CheckConstraint("qty > 0", name=op.f("ck_fbo_dispatch_items_qty")),
        sa.ForeignKeyConstraint(
            ["org_id", "dispatch_id"],
            ["fbo_dispatches.org_id", "fbo_dispatches.id"],
            name="fk_fbo_dispatch_items_dispatch_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "sku_id"],
            ["mp_skus.org_id", "mp_skus.id"],
            name="fk_fbo_dispatch_items_sku_id",
            ondelete="CASCADE",
        ),
        *_tail("fbo_dispatch_items"),
    )
    for table in ("fbo_dispatches", "fbo_dispatch_items"):
        for statement in rls.tenant(table, app_role):
            op.execute(statement)


def downgrade() -> None:
    op.drop_table("fbo_dispatch_items")
    op.drop_table("fbo_dispatches")

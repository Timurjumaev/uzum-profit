"""Kelmagan tovar zarari va qaytarilgan summa qatorga (TM9.6, ADR-068 (6); F55)

- ``purchase_lines.refund_amount`` — sotuvchi qaytargan summaning shu qatorga yozilgan qismi (xarid ``refund_currency``
  valyutasida). Bo'sh — eski usul (qaytarilgan summa hamma qatorga, hisobi o'zgarmaydi).
- ``missing_losses`` — hosila (lotlar bilan birga qayta quriladi): sanalgan, sog' donasi 0 qatorning zarari (F55) —
  sanash kuniga, foyda hisobida alohida qator.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-18 10:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.add_column("purchase_lines", sa.Column("refund_amount", sa.Numeric(18, 4), nullable=True))
    op.create_check_constraint(
        op.f("ck_purchase_lines_line_refund"),
        "purchase_lines",
        "refund_amount IS NULL OR refund_amount >= 0",
    )
    op.create_table(
        "missing_losses",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("purchase_line_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("sku_id", sa.UUID(), nullable=True),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "purchase_line_id"],
            ["purchase_lines.org_id", "purchase_lines.id"],
            name="fk_missing_losses_purchase_line_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "item_id"], ["items.org_id", "items.id"], name="fk_missing_losses_item_id"
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "sku_id"], ["mp_skus.org_id", "mp_skus.id"], name="fk_missing_losses_sku_id"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_missing_losses_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_missing_losses")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_missing_losses_org_id_id")),
        sa.UniqueConstraint(
            "org_id", "purchase_line_id", name=op.f("uq_missing_losses_org_id_purchase_line_id")
        ),
    )
    for statement in rls.tenant("missing_losses", app_role):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("missing_losses")
    op.drop_constraint(op.f("ck_purchase_lines_line_refund"), "purchase_lines", type_="check")
    op.drop_column("purchase_lines", "refund_amount")

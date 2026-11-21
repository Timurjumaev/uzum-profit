"""To'liq eksport (B7.5, ADR-065): ``data_exports`` — so'rov, holat va tayyor ZIP

Egasi so'raydi (kuniga bir marta) → fon ishi ZIP (CSV + JSON) yig'adi va shu qatorga yozadi → bir martalik token bilan 24 soat
ichida yuklanadi; muddati o'tgach ``content`` o'chadi. ``content`` — bazada (zaxira nusxaga ham kiradi, diskka yozilmaydi).

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-21 12:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "data_exports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=True),
        sa.Column("token_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("tables", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed', 'expired')",
            name=op.f("ck_data_exports_status"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_data_exports_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_data_exports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_exports")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_data_exports_org_id_id")),
    )
    for statement in rls.tenant("data_exports", app_role):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("data_exports")

"""Dinamik soliq profili: soliq qatorlari va so'm ma'lumotnomasi (B4.77, ADR-058)

``tax_lines`` — profil ostidagi soliq qatorlari: foizli (``percent``: baza × stavka) yoki qat'iy (``fixed``: so'm yoki
n × BHM; oy / chorak / yil). ``ref_amounts`` — so'mdagi ma'lumotnoma (BHM va boshqa chegaralar), ``valid_from`` dan;
boshlang'ich qiymatlar ``upcore.tax.SEED_AMOUNTS`` dan (``seed_reference``). Mavjud ``tax_profiles`` o'zgarmaydi: qatorlari
yo'q profil eski ustunlaridan o'qiladi (``upcore.tax.profile_lines``); qatorlarga ko'chirish — API bilan birga (B4.78).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-11 15:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "ref_amounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ref_amounts")),
        sa.UniqueConstraint("code", "valid_from", name=op.f("uq_ref_amounts_code_valid_from")),
    )
    for statement in rls.global_read("ref_amounts", app_role):
        op.execute(statement)

    op.create_table(
        "tax_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("rate_pct", sa.Numeric(precision=7, scale=4), server_default="0", nullable=False),
        sa.Column("base", sa.Text(), server_default="revenue", nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("bhm_count", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("period", sa.Text(), server_default="month", nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('percent', 'fixed')", name=op.f("ck_tax_lines_kind_allowed")),
        sa.CheckConstraint("base IN ('revenue', 'payout')", name=op.f("ck_tax_lines_base_allowed")),
        sa.CheckConstraint(
            "period IN ('month', 'quarter', 'year')", name=op.f("ck_tax_lines_period_allowed")
        ),
        sa.CheckConstraint(
            "(kind = 'percent' AND rate_pct > 0 AND rate_pct <= 100 AND amount IS NULL "
            "AND bhm_count IS NULL) OR (kind = 'fixed' AND rate_pct = 0 "
            "AND num_nonnulls(amount, bhm_count) = 1 AND coalesce(amount, bhm_count) > 0)",
            name=op.f("ck_tax_lines_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "profile_id"],
            ["tax_profiles.org_id", "tax_profiles.id"],
            name="fk_tax_lines_profile_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_tax_lines_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_lines")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_tax_lines_org_id_id")),
        sa.UniqueConstraint(
            "org_id", "profile_id", "name", name=op.f("uq_tax_lines_org_id_profile_id_name")
        ),
    )
    for statement in rls.tenant("tax_lines", app_role):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("tax_lines")
    op.drop_table("ref_amounts")

"""To'lov shartlari ma'lumotnomasi (B5.7; Temur 2026-11-20: qoidalar kodga qotirilmasin)

``ref_payout_terms`` — Uzum to'lov jadvali shartlari sanasi bilan: jadval turi, oy kunlari (``NULL`` — har ish kuni) va
pul yechish foizi, ``valid_from`` dan. Bazada yozuv bo'lmasa ``upcore.cash.SEED_SCHEDULES`` (boshlang'ich) amal qiladi, bir
sanada bazadagi yozuv ustun. Boshqa qoidalar (pul yechishga berilish kechikishi, shoshilinch yechish foizi, kechikish
ish kunlari) — ``ref_amounts`` ning ``payout_*`` kodlari. Uzum qoidani o'zgartirsa — kod emas, shu jadval yangilanadi.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-20 14:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "ref_payout_terms",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("days_of_month", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("fee_pct", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('daily', 'weekly', 'biweekly', 'monthly')",
            name=op.f("ck_ref_payout_terms_kind_allowed"),
        ),
        sa.CheckConstraint(
            "fee_pct >= 0 AND fee_pct <= 100", name=op.f("ck_ref_payout_terms_fee_pct_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ref_payout_terms")),
        sa.UniqueConstraint("kind", "valid_from", name=op.f("uq_ref_payout_terms_kind_valid_from")),
    )
    for statement in rls.global_read("ref_payout_terms", app_role):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("ref_payout_terms")

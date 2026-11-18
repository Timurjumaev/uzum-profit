"""Postavka ↔ jo'natma har qanday yo'lda (TM9.1, ADR-068 (1))

- ``fbo_invoice_marks`` — dasturdan tashqari (jo'natmasiz) postavka bo'yicha sotuvchi qarori: ``not_mine`` — "bu postavka
  Omborimdan emas" (masalan, boshlang'ich qoldiqdan yoki boshqa joydan; "Diqqat"da chiqmaydi, Omborimni band qilmaydi).
  "Omborimdan ketgan" qarori jo'natma sifatida yoziladi (``fbo_dispatches.origin = 'invoice'``).
- ``fbo_dispatches.origin`` — ``excel`` (dasturdagi Excel) yoki ``invoice`` (postavka tarkibidan yaratilgan);
  ``fbo_dispatches.adjustments`` — bog'langanda tarkib e'lon qilingan songa tenglashtirilgani (SKU, oldin, keyin, e'lon).

Faqat qo'shiladi; mavjud jo'natmalar ``excel``. Qaytariladigan.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-17 16:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "fbo_invoice_marks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "decision IN ('not_mine')", name=op.f("ck_fbo_invoice_marks_decision_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "invoice_id"],
            ["fbo_invoices.org_id", "fbo_invoices.id"],
            name="fk_fbo_invoice_marks_invoice_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["orgs.id"],
            name=op.f("fk_fbo_invoice_marks_org_id_orgs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fbo_invoice_marks")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_fbo_invoice_marks_org_id_id")),
        sa.UniqueConstraint(
            "org_id", "invoice_id", name=op.f("uq_fbo_invoice_marks_org_id_invoice_id")
        ),
    )
    for statement in rls.tenant("fbo_invoice_marks", app_role):
        op.execute(statement)
    op.add_column(
        "fbo_dispatches",
        sa.Column("origin", sa.Text(), server_default="excel", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_fbo_dispatches_origin_allowed"), "fbo_dispatches", "origin IN ('excel', 'invoice')"
    )
    op.add_column("fbo_dispatches", sa.Column("adjustments", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("fbo_dispatches", "adjustments")
    op.drop_constraint(op.f("ck_fbo_dispatches_origin_allowed"), "fbo_dispatches", type_="check")
    op.drop_column("fbo_dispatches", "origin")
    op.drop_table("fbo_invoice_marks")

"""Kalkulyator ssenariylari (B5.9-3)

``calculator_scenarios`` — sotuvchi saqlagan kalkulyator kiritishi (nomi bilan): keyin ochib, tez xarid qoralamasiga
aylantirish uchun. Hisob natijasi saqlanmaydi (kurs va tarif o'zgaradi) — faqat kiritish. Nom tashkilot ichida noyob.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-20 23:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "calculator_scenarios",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["orgs.id"],
            name=op.f("fk_calculator_scenarios_org_id_orgs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calculator_scenarios")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_calculator_scenarios_org_id_id")),
        sa.UniqueConstraint("org_id", "name", name=op.f("uq_calculator_scenarios_org_id_name")),
    )
    for statement in rls.tenant("calculator_scenarios", app_role):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("calculator_scenarios")

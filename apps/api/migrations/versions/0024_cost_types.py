"""Xarajat turlari lug'ati (TM3, ADR-061 §4)

``cost_types`` — tashkilotning o'z xarajat turlari (tayyor turlar — ``ComponentKind`` da: agent, o'tkazma komissiyasi,
bojxona, taksi, Uzum omboriga olib borish ...). ``cost_components.cost_type_id`` — sotuvchi turi tanlangan xarajat
(``kind = 'other'``). Mavjud yozuvlar o'zgarmaydi.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-13 02:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "cost_types",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_cost_types_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_types")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_cost_types_org_id_id")),
        sa.UniqueConstraint("org_id", "name", name=op.f("uq_cost_types_org_id_name")),
    )
    for statement in rls.tenant("cost_types", app_role):
        op.execute(statement)
    op.add_column("cost_components", sa.Column("cost_type_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_cost_components_cost_type_id",
        "cost_components",
        "cost_types",
        ["org_id", "cost_type_id"],
        ["org_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_cost_components_cost_type_id", "cost_components", type_="foreignkey")
    op.drop_column("cost_components", "cost_type_id")
    op.drop_table("cost_types")

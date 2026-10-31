"""orgs.settings (B4.8)

Tashkilot sozlamalari (JSONB): standart yetkazish muddatlari (F25, bosqich → kun) va ABC qamrov kunlari (F27).
Biznes doimiylari kodda emas, bazada (tamoyil 2); bo'sh ``{}`` — sozlanmagan (muddat tarixdan o'rganiladi).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orgs",
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("orgs", "settings")

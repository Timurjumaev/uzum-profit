"""``orgs.calc_version`` (B8.4a, 09 X4): hisob qoidalari versiyasi

Ishchi har ishga tushganda hamma tashkilotni qayta hisoblamaydi — faqat ``calc_version`` kodning ``CALC_VERSION`` idan
eskirgan tashkilotlarni (tannarx dvigateli yoki belgilar qoidasi o'zgargach). Tungi 03:40 to'liq qayta qurish saqlanadi.
NULL — hali hisoblanmagan (birinchi ishga tushishda bir marta qayta quriladi).

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-21 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("calc_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("orgs", "calc_version")

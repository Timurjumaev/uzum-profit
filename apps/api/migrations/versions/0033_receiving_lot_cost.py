"""F52 va lot daftari (TM9.4, ADR-068 (4))

``receiving_diffs.lot_cost`` — yopilgan "Uzum yo'qotdi" kamomadining partiyadan chiqqan qiymati (lot narxida, FIFO /
o'rtacha — tannarx dvigateli yozadi, ``stock_moves.cost`` kabi). F52 zarari shu qiymatdan (zarar ham, tannarx ham bir marta);
hali hisoblanmagan bo'lsa — jo'natmadagi tannarx bo'yicha. Faqat ustun qo'shiladi; qaytariladigan.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-18 08:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receiving_diffs", sa.Column("lot_cost", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("receiving_diffs", "lot_cost")

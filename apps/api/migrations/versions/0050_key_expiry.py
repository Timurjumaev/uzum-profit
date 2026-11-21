"""Uzum kaliti muddati (B8.16): ``mp_accounts.key_expires_on``

Uzum kalit muddatini API orqali bermaydi — sotuvchi ulashda kiritadi (ixtiyoriy; NULL — cheklanmagan yoki noma'lum).
Muddatidan 5 va 1 kun oldin hodisa ``key_expiring``; tugagach kalit Uzumda "Faolsiz" bo'ladi va mavjud "kalit yaroqsiz"
oqimi ishlaydi.

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-21 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mp_accounts", sa.Column("key_expires_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("mp_accounts", "key_expires_on")

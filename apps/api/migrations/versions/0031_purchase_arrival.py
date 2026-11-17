""" "Keldi" — sanashdan oldin (TM9.8, ADR-069)

``purchases.arrival_marked`` — uch holat: ``NULL`` — eski yozuv (TM9.8 gacha; holat va lot tayyor sanasi F21 avvalgidek:
sanash → kargo to'lovi → keyingi bosqich, eski "Toshkentga keldi" sanasi ta'sir qilmaydi — tannarx tiyinigacha
o'zgarmaydi, ADR-061 §11); ``false`` — yangi qoida, tovar hali kelmagan (kargo to'lov sanasi tayyor sana emas);
``true`` — "Keldi" belgilangan (kargo puli oynasida "Ha", ro'yxatda "Keldi" yoki sanash o'zi qo'ygan), sana —
``purchases.arrived_on``. Yangi xaridlar ``false`` bilan yaratiladi; mavjud qatorlar ``NULL`` qoladi. Faqat ustun
qo'shiladi; qaytariladigan.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-17 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("purchases", sa.Column("arrival_marked", sa.Boolean(), nullable=True))
    # Mavjud qatorlar NULL (eski qoida); standart faqat yangi qatorlar uchun.
    op.alter_column("purchases", "arrival_marked", server_default=sa.text("false"))


def downgrade() -> None:
    op.drop_column("purchases", "arrival_marked")

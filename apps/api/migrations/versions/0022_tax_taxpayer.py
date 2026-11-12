"""Soliq profilida soliq to'lovchi turi (B4.80, F50 — yillik tushum chegarasi)

``tax_profiles.taxpayer``: ``individual`` (YaTT), ``llc`` (MChJ), ``self_employed`` (o'zini o'zi band qilgan) yoki ``NULL``
(ko'rsatilmagan — chegara ogohlantirishi yo'q). Mavjud profillar ``NULL`` bilan qoladi: tur taxmin qilinmaydi (sotuvchi
Sozlamalarda tanlaydi). Chegaralar ``ref_amounts`` da (``upcore.tax.SEED_AMOUNTS`` boshlang'ich qiymatlari).

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-12 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tax_profiles", sa.Column("taxpayer", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_tax_profiles_taxpayer_allowed"),
        "tax_profiles",
        "taxpayer IN ('individual', 'llc', 'self_employed')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_tax_profiles_taxpayer_allowed"), "tax_profiles", type_="check")
    op.drop_column("tax_profiles", "taxpayer")

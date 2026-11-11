"""Mavjud aylanmadan foiz profillarini soliq qatoriga ko'chirish (B4.79, ADR-058)

Stavkasi 0 dan katta ``turnover`` profil bitta foizli qator (``Aylanmadan soliq``) oladi — hisob natijasi o'zgarmaydi
(``upcore.tax.profile_lines`` eski ustunlardan shuni o'zi ham qilardi). Boshqa rejimlar (agent, QQS + foyda, yo'q) va
qatori bor profillar o'zgarmaydi. Eski ustunlar (``rate_pct``, ``base``) saqlanadi — qatorlar bor profilda e'tiborsiz.

Tenant jadvallarida RLS majburiy (FORCE) — migratsiya roli (jadval egasi) uchun uni shu tranzaksiyada vaqtincha
o'chiramiz va qaytaramiz.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-11 17:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "Aylanmadan soliq"


def _force(table: str, on: bool) -> None:
    op.execute(f"ALTER TABLE {table} {'FORCE' if on else 'NO FORCE'} ROW LEVEL SECURITY")


def upgrade() -> None:
    _force("tax_profiles", False)
    _force("tax_lines", False)
    op.execute(
        "INSERT INTO tax_lines (org_id, profile_id, position, name, kind, rate_pct, base, period) "
        f"SELECT p.org_id, p.id, 0, '{NAME}', 'percent', p.rate_pct, p.base, 'month' "
        "FROM tax_profiles p WHERE p.regime = 'turnover' AND p.rate_pct > 0 "
        "AND NOT EXISTS (SELECT 1 FROM tax_lines l WHERE l.org_id = p.org_id AND l.profile_id = p.id)"
    )
    _force("tax_lines", True)
    _force("tax_profiles", True)


def downgrade() -> None:
    _force("tax_lines", False)
    op.execute(f"DELETE FROM tax_lines WHERE name = '{NAME}' AND kind = 'percent'")
    _force("tax_lines", True)

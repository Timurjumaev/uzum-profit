"""Akkaunt xarajati takrorini tozalash (Temur topdi, 2026-11-16)

Uzum akkaunt darajasidagi xarajatni (``shopId: 0`` — shoshilinch pul yechish C000011) akkauntning har bir do'koni
so'roviga qaytaradi; ``mp_expenses`` kaliti ``(org, shop, external_id)`` bo'lgani uchun bitta to'lov har do'konga
yozilgan (staging: 210635460 — 62 000 so'm ikki marta). Endi sinxron uni bir marta saqlaydi (akkauntning eng kichik
Uzum id'li do'koni qatorida, ``upapi.sync.engine._write_expenses``), foyda hisobida esa u tashkilot darajasida —
do'konlarga tushum ulushida (``upapi.reports.cells``). Bu migratsiya mavjud takrorlarni o'chiradi (o'sha qator qoladi). Sinxron ma'lumoti (sotuvchi kiritgani emas). Hosila jadvallar ishchi ishga tushganda to'liq qayta
quriladi (``rebuild_all``). Tenant jadvallarida RLS majburiy (FORCE) — migratsiya roli uchun shu tranzaksiyada vaqtincha
o'chiriladi (0019 kabi).

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-16 08:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = ("mp_expenses", "shops")


def _force(on: bool) -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} {'FORCE' if on else 'NO FORCE'} ROW LEVEL SECURITY")


def upgrade() -> None:
    _force(False)
    op.execute(
        """
        DELETE FROM mp_expenses e
        USING shops s
        WHERE s.id = e.shop_id
          AND e.raw ->> 'shopId' = '0'
          AND EXISTS (
            SELECT 1 FROM mp_expenses o JOIN shops os ON os.id = o.shop_id
            WHERE o.org_id = e.org_id AND o.external_id = e.external_id AND o.id <> e.id
              AND os.account_id = s.account_id AND os.external_id < s.external_id
          )
        """
    )
    _force(True)


def downgrade() -> None:
    # O'chirilgan takrorlar qayta yaratilmaydi (keyingi sinxron ham ularni yozmaydi).
    pass

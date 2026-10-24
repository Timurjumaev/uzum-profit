"""CBU kurslarini yozish (B2.7)

``fx_rates`` — global jadval, ilova roli (``up_app``) uni faqat o'qiydi. Kurslarni ishchi ``fx_upsert()`` orqali yozadi:
``SECURITY DEFINER``, egasi ``up_sync`` (0004), unga faqat shu jadvalga kerakli huquqlar; manba doim ``cbu``
(qo'lda kiritilgan kurslar bu yo'ldan yozilmaydi). Migratsiya roli superuser yoki ``up_sync`` a'zosi bo'lishi
kerak (0004 kabi).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24 23:00:00
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_ROLE = "up_sync"
SIGNATURE = "fx_upsert(date, text, numeric)"


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    for sql in [
        f"GRANT USAGE ON SCHEMA public TO {SYNC_ROLE}",
        f"GRANT CREATE ON SCHEMA public TO {SYNC_ROLE}",  # egasini o'zgartirish uchun vaqtincha
        f"GRANT SELECT, INSERT ON fx_rates TO {SYNC_ROLE}",
        f"GRANT UPDATE (rate, fetched_at) ON fx_rates TO {SYNC_ROLE}",
        """CREATE FUNCTION fx_upsert(p_day date, p_currency text, p_rate numeric) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  INSERT INTO fx_rates (day, currency, source, rate) VALUES (p_day, p_currency, 'cbu', p_rate)
  ON CONFLICT (day, currency, source) DO UPDATE SET rate = EXCLUDED.rate, fetched_at = now()
$$""",
        f"ALTER FUNCTION {SIGNATURE} OWNER TO {SYNC_ROLE}",
        f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {app_role}",
        f"REVOKE CREATE ON SCHEMA public FROM {SYNC_ROLE}",
    ]:
        op.execute(sql)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {SIGNATURE}")
    op.execute(f"REVOKE ALL ON fx_rates FROM {SYNC_ROLE}")

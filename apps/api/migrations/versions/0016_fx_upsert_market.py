"""Bozor kursini yozish (ADR-045): CBU serverdan ochilmaganda zaxira manba

``fx_upsert_market()`` — ``fx_upsert()`` (0005) bilan bir xil, lekin manba ``market``: rasmiy kurs emas, hisobda har
doim belgilanadi (``market_rate``). CBU kursi (``cbu``) bir kunda bo'lsa — u ustun (``upcore.fx.rate_on``). Egasi —
``up_sync``, ilova roli faqat bajarishi mumkin. Migratsiya roli superuser yoki ``up_sync`` a'zosi bo'lishi kerak.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-04 22:00:00
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_ROLE = "up_sync"
SIGNATURE = "fx_upsert_market(date, text, numeric)"


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    for sql in [
        f"GRANT CREATE ON SCHEMA public TO {SYNC_ROLE}",  # egasini o'zgartirish uchun vaqtincha
        """CREATE FUNCTION fx_upsert_market(p_day date, p_currency text, p_rate numeric) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  INSERT INTO fx_rates (day, currency, source, rate) VALUES (p_day, p_currency, 'market', p_rate)
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

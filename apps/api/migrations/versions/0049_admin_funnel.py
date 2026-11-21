"""admin voronka (B8.9): har tashkilot bo'yicha aktivatsiya hodisalarining birinchi vaqti — B9.4 jadvali uchun

``up_admin`` (0047) ga ``events`` jadvalidan faqat ``org_id, name, created_at`` o'qish huquqi (props va user_id yo'q) va
``admin_funnel()`` funksiyasi (``admin_overview()`` kabi ilova roliga berilmagan; migratsiya egasi chaqiradi).

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-21 20:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "up_admin"
SIGNATURE = "admin_funnel()"
FUNCTION = f"""
CREATE FUNCTION {SIGNATURE} RETURNS TABLE (org_id uuid, name text, first_at timestamptz, times bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT e.org_id, e.name, min(e.created_at), count(*) FROM events e
  JOIN orgs o ON o.id = e.org_id WHERE o.deleted_at IS NULL
  GROUP BY e.org_id, e.name ORDER BY e.org_id, min(e.created_at)
$$"""


def upgrade() -> None:
    op.execute(f"GRANT SELECT (org_id, name, created_at) ON events TO {ROLE}")
    op.execute(f"CREATE POLICY admin_definer ON events FOR SELECT TO {ROLE} USING (true)")
    op.execute(f"GRANT CREATE ON SCHEMA public TO {ROLE}")
    op.execute(FUNCTION)
    op.execute(f"ALTER FUNCTION {SIGNATURE} OWNER TO {ROLE}")
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO CURRENT_USER")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
    op.execute("DROP POLICY IF EXISTS admin_definer ON events")
    op.execute(f"REVOKE ALL ON events FROM {ROLE}")

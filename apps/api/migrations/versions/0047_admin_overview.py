"""admin ko'rinishi (B8.3a): faqat o'qish, alohida DB roli

``up_admin`` (NOLOGIN, BYPASSRLS yo'q) — ``up_sync`` kabi ustun darajasida SELECT va ``admin_define`` siyosatlari; faqat
``admin_overview()`` funksiyasining egasi. Funksiya ilova roliga (``up_app``) **berilmaydi** — API xavfsizligi buzilsa ham
barcha tashkilotlar ro'yxatini o'qib bo'lmaydi; uni faqat migratsiya egasi chaqiradi (``python -m upapi.admin``, serverda).
Sotuvchi biznes ma'lumoti (sotuv, narx, tannarx) ustunlari berilmaydi — faqat tashkilot nomi, soni va sinxron holati.

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-21 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "up_admin"
GRANTS = {
    "orgs": "id, name, created_at, deleted_at",
    "memberships": "org_id",
    "shops": "org_id, active",
    "mp_accounts": "org_id, status, auth_failures, sync_paused_until",
    "sync_state": "org_id, last_success_at, last_attempt_at, last_status, last_error, failures",
}
SIGNATURE = "admin_overview()"
FUNCTION = f"""
CREATE FUNCTION {SIGNATURE} RETURNS TABLE (
    org_id uuid, name text, created_at timestamptz, members bigint, shops bigint,
    account_status text, auth_failures integer, paused_until timestamptz,
    last_success_at timestamptz, sync_failures bigint, last_error text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT o.id, o.name, o.created_at,
    (SELECT count(*) FROM memberships m WHERE m.org_id = o.id),
    (SELECT count(*) FROM shops s WHERE s.org_id = o.id AND s.active),
    (SELECT a.status FROM mp_accounts a WHERE a.org_id = o.id ORDER BY a.status LIMIT 1),
    (SELECT max(a.auth_failures) FROM mp_accounts a WHERE a.org_id = o.id),
    (SELECT max(a.sync_paused_until) FROM mp_accounts a WHERE a.org_id = o.id),
    (SELECT max(t.last_success_at) FROM sync_state t WHERE t.org_id = o.id),
    (SELECT coalesce(sum(t.failures), 0) FROM sync_state t WHERE t.org_id = o.id),
    (SELECT left(t.last_error, 200) FROM sync_state t
       WHERE t.org_id = o.id AND t.last_error IS NOT NULL ORDER BY t.last_attempt_at DESC NULLS LAST LIMIT 1)
  FROM orgs o WHERE o.deleted_at IS NULL ORDER BY o.created_at
$$"""


def upgrade() -> None:
    op.execute(
        f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
          CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
        END $$"""
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT CREATE ON SCHEMA public TO {ROLE}")  # egasini o'zgartirish uchun vaqtincha
    for table, columns in GRANTS.items():
        op.execute(f"GRANT SELECT ({columns}) ON {table} TO {ROLE}")
        op.execute(f"CREATE POLICY admin_definer ON {table} FOR SELECT TO {ROLE} USING (true)")
    op.execute(FUNCTION)
    op.execute(f"ALTER FUNCTION {SIGNATURE} OWNER TO {ROLE}")
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO CURRENT_USER")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
    for table in GRANTS:
        op.execute(f"DROP POLICY IF EXISTS admin_definer ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")

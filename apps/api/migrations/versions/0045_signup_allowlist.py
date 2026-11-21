"""ro'yxatdan o'tishni cheklash (B8.11): ruxsat etilgan telefon raqamlari

``signup_allowlist`` — kirish jadvali (``dev_tokens`` kabi): RLS yoqilgan, ilova roliga huquq yo'q; faqat ``auth_signup_*``
funksiyalari (``SECURITY DEFINER``, egasi ``up_auth``) orqali. ``auth_signup_allowed`` — raqam allaqachon foydalanuvchi
yoki ro'yxatda bo'lsa ``true``. ``auth_signup_allow`` taklif yaratilganda (a'zo taklifi — ruxsat) va CLI orqali chaqiriladi.

Faqat qo'shiladi; qaytariladigan.

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-21 14:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)
AUTH_ROLE = "up_auth"
_HEAD = "LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$\n#variable_conflict use_column\n"

FUNCTIONS = {
    "auth_signup_allowed(text)": f"""
CREATE FUNCTION auth_signup_allowed(p_phone text) RETURNS boolean {_HEAD}
BEGIN
  RETURN EXISTS (SELECT 1 FROM users WHERE phone = p_phone)
      OR EXISTS (SELECT 1 FROM signup_allowlist WHERE phone = p_phone);
END $$""",
    "auth_signup_allow(text, text)": f"""
CREATE FUNCTION auth_signup_allow(p_phone text, p_source text) RETURNS void {_HEAD}
BEGIN
  INSERT INTO signup_allowlist (phone, source) VALUES (p_phone, p_source) ON CONFLICT (phone) DO NOTHING;
END $$""",
    "auth_signup_list()": f"""
CREATE FUNCTION auth_signup_list() RETURNS TABLE (phone text, source text, created_at timestamptz) {_HEAD}
BEGIN
  RETURN QUERY SELECT a.phone, a.source, a.created_at FROM signup_allowlist a ORDER BY a.created_at;
END $$""",
    "auth_signup_remove(text)": f"""
CREATE FUNCTION auth_signup_remove(p_phone text) RETURNS integer {_HEAD}
DECLARE v_count integer;
BEGIN
  DELETE FROM signup_allowlist WHERE phone = p_phone;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END $$""",
}


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "signup_allowlist",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signup_allowlist")),
        sa.UniqueConstraint("phone", name=op.f("uq_signup_allowlist_phone")),
    )
    for statement in rls.auth_only("signup_allowlist"):
        op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT, DELETE ON signup_allowlist TO {AUTH_ROLE}")
    op.execute(
        f"CREATE POLICY auth_definer ON signup_allowlist FOR ALL TO {AUTH_ROLE} USING (true) WITH CHECK (true)"
    )
    op.execute(f"GRANT CREATE ON SCHEMA public TO {AUTH_ROLE}")
    for signature, body in FUNCTIONS.items():
        op.execute(body)
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {AUTH_ROLE}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {app_role}")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {AUTH_ROLE}")


def downgrade() -> None:
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute("DROP POLICY IF EXISTS auth_definer ON signup_allowlist")
    op.execute(f"REVOKE ALL ON signup_allowlist FROM {AUTH_ROLE}")
    op.drop_table("signup_allowlist")

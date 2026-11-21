"""dev-tokenlar (ADR-072): faqat staging'da, faqat o'qish uchun vaqtinchalik ishlab chiqish vositasi

``dev_tokens`` — kirish jadvali (``sessions`` kabi): RLS yoqilgan, ilova roliga huquq yo'q; faqat ``auth_dev_*``
funksiyalari (``SECURITY DEFINER``, egasi ``up_auth``) orqali. Bazada faqat SHA-256 xesh. Alohida jadval (``sessions``
emas): dev-token cookie sifatida yuborilsa ham to'liq sessiya bo'lib qolmasin.

Faqat qo'shiladi; qaytariladigan. Production'da ``UP_DEV_TOKENS_ENABLED`` yoqilmaydi (jadval bo'sh qoladi).

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-21 12:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)
AUTH_ROLE = "up_auth"
_HEAD = "LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$\n#variable_conflict use_column\n"

FUNCTIONS = {
    # Token → foydalanuvchi. last_used_at daqiqada bir martadan ko'p yozilmaydi (har so'rovda yozuv bo'lmasin).
    "auth_dev_token(bytea)": f"""
CREATE FUNCTION auth_dev_token(p_token_hash bytea)
    RETURNS TABLE (token_id uuid, user_id uuid, phone text, name text, language text)
{_HEAD}BEGIN
  UPDATE dev_tokens SET last_used_at = now()
  WHERE token_hash = p_token_hash AND revoked_at IS NULL AND expires_at > now()
    AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute');
  RETURN QUERY SELECT t.id, u.id, u.phone, u.name, u.language
    FROM dev_tokens t JOIN users u ON u.id = t.user_id
    WHERE t.token_hash = p_token_hash AND t.revoked_at IS NULL AND t.expires_at > now();
END $$""",
    # /auth/me va /orgs uchun: dev-token egasining tashkilotlari (``auth_user_orgs`` ning dev-token varianti).
    "auth_dev_user_orgs(bytea)": """
CREATE FUNCTION auth_dev_user_orgs(p_token_hash bytea) RETURNS TABLE (org_id uuid, name text, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT o.id, o.name, m.role
  FROM memberships m JOIN orgs o ON o.id = m.org_id
  JOIN dev_tokens t ON t.user_id = m.user_id
  WHERE t.token_hash = p_token_hash AND t.revoked_at IS NULL AND t.expires_at > now()
    AND o.deleted_at IS NULL
  ORDER BY o.name, o.id
$$""",
    # CLI (serverda): token yaratish. Telefon bo'yicha foydalanuvchi bo'lmasa NULL (yangi foydalanuvchi yaratilmaydi).
    "auth_dev_token_create(text, bytea, text, integer)": f"""
CREATE FUNCTION auth_dev_token_create(p_phone text, p_token_hash bytea, p_label text, p_seconds integer)
    RETURNS uuid
{_HEAD}DECLARE
  v_user uuid;
  v_id uuid;
BEGIN
  SELECT u.id INTO v_user FROM users u WHERE u.phone = p_phone;
  IF v_user IS NULL THEN
    RETURN NULL;
  END IF;
  INSERT INTO dev_tokens (user_id, token_hash, label, expires_at)
    VALUES (v_user, p_token_hash, p_label, now() + make_interval(secs => p_seconds))
    RETURNING id INTO v_id;
  RETURN v_id;
END $$""",
    # Sirsiz ro'yxat (xesh chiqmaydi): qaysi token, kimniki, qachon tugaydi, oxirgi ishlatilishi.
    "auth_dev_token_list()": """
CREATE FUNCTION auth_dev_token_list() RETURNS TABLE (id uuid, phone text, label text, created_at timestamptz,
    expires_at timestamptz, last_used_at timestamptz, revoked_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT t.id, u.phone, t.label, t.created_at, t.expires_at, t.last_used_at, t.revoked_at
  FROM dev_tokens t JOIN users u ON u.id = t.user_id
  ORDER BY t.created_at DESC
$$""",
    # p_id — bitta token; NULL — hammasi. Qaytadi: bekor qilingan soni.
    "auth_dev_token_revoke(uuid)": f"""
CREATE FUNCTION auth_dev_token_revoke(p_id uuid) RETURNS integer
{_HEAD}DECLARE
  v_count integer;
BEGIN
  UPDATE dev_tokens SET revoked_at = now()
  WHERE revoked_at IS NULL AND (p_id IS NULL OR id = p_id);
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END $$""",
}


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "dev_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("last_used_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_dev_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dev_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_dev_tokens_token_hash")),
    )
    op.create_index(op.f("ix_dev_tokens_user_id"), "dev_tokens", ["user_id"])
    for statement in rls.auth_only("dev_tokens"):
        op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON dev_tokens TO {AUTH_ROLE}")
    op.execute(
        f"CREATE POLICY auth_definer ON dev_tokens FOR ALL TO {AUTH_ROLE} USING (true) WITH CHECK (true)"
    )
    # Funksiya egasini o'zgartirish uchun vaqtincha (0002 kabi, oxirida qaytarib olinadi).
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
    op.execute("DROP POLICY IF EXISTS auth_definer ON dev_tokens")
    op.execute(f"REVOKE ALL ON dev_tokens FROM {AUTH_ROLE}")
    op.drop_index(op.f("ix_dev_tokens_user_id"), table_name="dev_tokens")
    op.drop_table("dev_tokens")

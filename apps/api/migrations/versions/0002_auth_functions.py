"""auth functions (B2.3)

Kirish jadvallari (``sessions``, ``otp_codes``) ilova roliga ochilmaydi. Ilova faqat ``auth_*`` funksiyalarini
chaqiradi: ``SECURITY DEFINER``, egasi — ``up_auth`` (NOLOGIN, BYPASSRLS yo'q, faqat kerakli jadvallarga huquq).
Har funksiya sirni talab qiladi: OTP kodi xeshi (kirish) yoki sessiya tokeni xeshi (qolganlari) — ilova roli
token bilmasdan boshqa foydalanuvchi nomidan sessiya ocha olmaydi va sessiya/kod jadvallarini o'qiy olmaydi.

Migratsiya roli superuser yoki ``up_auth`` a'zosi bo'lishi kerak (``ALTER FUNCTION ... OWNER TO``).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 08:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTH_ROLE = "up_auth"
_HEAD = "LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$\n#variable_conflict use_column\n"

FUNCTIONS = {
    # Kod berish: blok (oxirgi N daqiqada xato urinishlar yig'indisi) va soatlik cheklov; eski kodlar bekor.
    "auth_otp_issue(text, bytea, integer, integer, integer, integer)": f"""
CREATE FUNCTION auth_otp_issue(p_phone text, p_code_hash bytea, p_ttl_seconds integer, p_per_hour integer,
    p_max_attempts integer, p_block_minutes integer) RETURNS text
{_HEAD}BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('otp:' || p_phone));
  IF (SELECT coalesce(sum(o.attempts), 0) FROM otp_codes o WHERE o.phone = p_phone
      AND o.updated_at > now() - make_interval(mins => p_block_minutes)) >= p_max_attempts THEN
    RETURN 'blocked';
  END IF;
  IF (SELECT count(*) FROM otp_codes o WHERE o.phone = p_phone
      AND o.created_at > now() - interval '1 hour') >= p_per_hour THEN
    RETURN 'rate_limited';
  END IF;
  UPDATE otp_codes SET consumed_at = now() WHERE phone = p_phone AND consumed_at IS NULL;
  INSERT INTO otp_codes (phone, code_hash, expires_at)
    VALUES (p_phone, p_code_hash, now() + make_interval(secs => p_ttl_seconds));
  RETURN 'ok';
END $$""",
    # Kirish: kod to'g'ri bo'lsa foydalanuvchi (yo'q bo'lsa yaratiladi) va sessiya bitta tranzaksiyada.
    "auth_login(text, bytea, bytea, text, integer, integer, integer)": f"""
CREATE FUNCTION auth_login(p_phone text, p_code_hash bytea, p_token_hash bytea, p_device text,
    p_session_seconds integer, p_max_attempts integer, p_block_minutes integer)
    RETURNS TABLE (status text, user_id uuid, session_id uuid, created boolean)
{_HEAD}DECLARE
  v_otp otp_codes%ROWTYPE;
  v_user uuid;
  v_created boolean;
  v_session uuid;
  v_failed bigint;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('otp:' || p_phone));
  SELECT coalesce(sum(o.attempts), 0) INTO v_failed FROM otp_codes o WHERE o.phone = p_phone
    AND o.updated_at > now() - make_interval(mins => p_block_minutes);
  IF v_failed >= p_max_attempts THEN
    RETURN QUERY SELECT 'blocked'::text, NULL::uuid, NULL::uuid, NULL::boolean;
    RETURN;
  END IF;
  SELECT * INTO v_otp FROM otp_codes o WHERE o.phone = p_phone AND o.consumed_at IS NULL AND o.expires_at > now()
    ORDER BY o.created_at DESC LIMIT 1 FOR UPDATE;
  IF NOT FOUND THEN
    RETURN QUERY SELECT 'expired'::text, NULL::uuid, NULL::uuid, NULL::boolean;
    RETURN;
  END IF;
  IF v_otp.code_hash <> p_code_hash THEN
    UPDATE otp_codes SET attempts = attempts + 1, updated_at = now() WHERE id = v_otp.id;
    RETURN QUERY SELECT CASE WHEN v_failed + 1 >= p_max_attempts THEN 'blocked' ELSE 'invalid' END,
      NULL::uuid, NULL::uuid, NULL::boolean;
    RETURN;
  END IF;
  UPDATE otp_codes SET consumed_at = now() WHERE id = v_otp.id;
  INSERT INTO users (phone, last_login_at) VALUES (p_phone, now())
    ON CONFLICT (phone) DO UPDATE SET last_login_at = EXCLUDED.last_login_at
    RETURNING id, (xmax = 0) INTO v_user, v_created;
  INSERT INTO sessions (user_id, token_hash, device, expires_at)
    VALUES (v_user, p_token_hash, p_device, now() + make_interval(secs => p_session_seconds))
    RETURNING id INTO v_session;
  RETURN QUERY SELECT 'ok'::text, v_user, v_session, v_created;
END $$""",
    # Sessiya: joriy token yoki yangilashdan keyingi qisqa muddatda eski token.
    "auth_session(bytea)": """
CREATE FUNCTION auth_session(p_token_hash bytea)
    RETURNS TABLE (session_id uuid, user_id uuid, phone text, name text, language text,
                   rotated_at timestamptz, is_current boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT s.id, u.id, u.phone, u.name, u.language, s.updated_at, s.token_hash = p_token_hash
  FROM sessions s JOIN users u ON u.id = s.user_id
  WHERE (s.token_hash = p_token_hash OR (s.prev_token_hash = p_token_hash AND s.prev_valid_until > now()))
    AND s.revoked_at IS NULL AND s.expires_at > now()
$$""",
    "auth_session_rotate(bytea, bytea, integer, integer)": f"""
CREATE FUNCTION auth_session_rotate(p_old bytea, p_new bytea, p_session_seconds integer, p_grace_seconds integer)
    RETURNS boolean
{_HEAD}BEGIN
  UPDATE sessions SET prev_token_hash = token_hash, prev_valid_until = now() + make_interval(secs => p_grace_seconds),
    token_hash = p_new, expires_at = now() + make_interval(secs => p_session_seconds), updated_at = now()
  WHERE token_hash = p_old AND revoked_at IS NULL AND expires_at > now();
  RETURN FOUND;
END $$""",
    "auth_sessions(bytea)": """
CREATE FUNCTION auth_sessions(p_token_hash bytea)
    RETURNS TABLE (id uuid, device text, created_at timestamptz, rotated_at timestamptz, expires_at timestamptz,
                   is_current boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT s.id, s.device, s.created_at, s.updated_at, s.expires_at, s.id = c.session_id
  FROM sessions s JOIN auth_session(p_token_hash) c ON c.user_id = s.user_id
  WHERE s.revoked_at IS NULL AND s.expires_at > now()
  ORDER BY s.updated_at DESC
$$""",
    # p_scope: 'current' (chiqish), 'one' (p_session_id), 'others' (boshqa hamma qurilmalar).
    "auth_session_revoke(bytea, text, uuid)": f"""
CREATE FUNCTION auth_session_revoke(p_token_hash bytea, p_scope text, p_session_id uuid) RETURNS integer
{_HEAD}DECLARE
  v_sid uuid;
  v_uid uuid;
  v_count integer;
BEGIN
  SELECT a.session_id, a.user_id INTO v_sid, v_uid FROM auth_session(p_token_hash) a;
  IF v_uid IS NULL THEN
    RETURN 0;
  END IF;
  UPDATE sessions SET revoked_at = now()
  WHERE user_id = v_uid AND revoked_at IS NULL AND CASE p_scope
    WHEN 'current' THEN id = v_sid WHEN 'one' THEN id = p_session_id WHEN 'others' THEN id <> v_sid ELSE false END;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END $$""",
    "auth_user_orgs(bytea)": """
CREATE FUNCTION auth_user_orgs(p_token_hash bytea) RETURNS TABLE (org_id uuid, name text, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT o.id, o.name, m.role
  FROM memberships m JOIN orgs o ON o.id = m.org_id JOIN auth_session(p_token_hash) a ON a.user_id = m.user_id
  WHERE o.deleted_at IS NULL
  ORDER BY o.name, o.id
$$""",
    # Taklif faqat o'sha telefon raqamli foydalanuvchiga; muddati o'tgan yoki ishlatilgan — rad.
    "auth_invite_accept(bytea, bytea)": f"""
CREATE FUNCTION auth_invite_accept(p_token_hash bytea, p_invite_hash bytea)
    RETURNS TABLE (status text, org_id uuid, role text)
{_HEAD}DECLARE
  v_uid uuid;
  v_phone text;
  v_inv invites%ROWTYPE;
BEGIN
  SELECT a.user_id, a.phone INTO v_uid, v_phone FROM auth_session(p_token_hash) a;
  IF v_uid IS NULL THEN
    RETURN QUERY SELECT 'unauthenticated'::text, NULL::uuid, NULL::text;
    RETURN;
  END IF;
  SELECT * INTO v_inv FROM invites i WHERE i.token_hash = p_invite_hash FOR UPDATE;
  IF NOT FOUND THEN
    RETURN QUERY SELECT 'not_found'::text, NULL::uuid, NULL::text;
    RETURN;
  ELSIF v_inv.accepted_at IS NOT NULL THEN
    RETURN QUERY SELECT 'used'::text, NULL::uuid, NULL::text;
    RETURN;
  ELSIF v_inv.expires_at <= now() THEN
    RETURN QUERY SELECT 'expired'::text, NULL::uuid, NULL::text;
    RETURN;
  ELSIF v_inv.phone <> v_phone THEN
    RETURN QUERY SELECT 'phone_mismatch'::text, NULL::uuid, NULL::text;
    RETURN;
  END IF;
  INSERT INTO memberships (org_id, user_id, role) VALUES (v_inv.org_id, v_uid, v_inv.role)
    ON CONFLICT (org_id, user_id) DO NOTHING;
  UPDATE invites SET accepted_at = now() WHERE id = v_inv.id;
  RETURN QUERY SELECT 'ok'::text, v_inv.org_id, v_inv.role;
END $$""",
}

# up_auth huquqlari: faqat funksiyalarga keraklisi. Siyosatlar faqat shu rolga (ilova roliga emas).
GRANTS = [
    ("sessions", "SELECT, INSERT, UPDATE", "ALL"),
    ("otp_codes", "SELECT, INSERT, UPDATE", "ALL"),
    ("users", "SELECT, INSERT, UPDATE (last_login_at)", "ALL"),
    ("memberships", "SELECT, INSERT", "ALL"),
    ("invites", "SELECT, UPDATE (accepted_at)", "ALL"),
    ("orgs", "SELECT", "SELECT"),
]


def _security(app_role: str) -> list[str]:
    sql = [
        f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{AUTH_ROLE}') THEN
          CREATE ROLE {AUTH_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
        END $$""",
        f"GRANT USAGE ON SCHEMA public TO {AUTH_ROLE}",
        # Funksiya egasini o'zgartirish uchun vaqtincha (oxirida qaytarib olinadi).
        f"GRANT CREATE ON SCHEMA public TO {AUTH_ROLE}",
    ]
    for table, privileges, command in GRANTS:
        sql += [
            f"GRANT {privileges} ON {table} TO {AUTH_ROLE}",
            f"CREATE POLICY auth_definer ON {table} FOR {command} TO {AUTH_ROLE} USING (true)"
            + (" WITH CHECK (true)" if command == "ALL" else ""),
        ]
    for signature, body in FUNCTIONS.items():
        sql += [
            body,
            f"ALTER FUNCTION {signature} OWNER TO {AUTH_ROLE}",
            f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC",
            f"GRANT EXECUTE ON FUNCTION {signature} TO {app_role}",
        ]
    sql += [
        f"REVOKE CREATE ON SCHEMA public FROM {AUTH_ROLE}",
        # Foydalanuvchi o'zining faqat ismi va tilini o'zgartiradi (telefon — kirish identifikatori).
        f"REVOKE UPDATE ON users FROM {app_role}",
        f"GRANT UPDATE (name, language) ON users TO {app_role}",
    ]
    return sql


def upgrade() -> None:
    op.add_column("sessions", sa.Column("prev_token_hash", sa.LargeBinary(), nullable=True))
    op.add_column(
        "sessions", sa.Column("prev_valid_until", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.create_index(op.f("ix_sessions_prev_token_hash"), "sessions", ["prev_token_hash"])
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_index(op.f("ix_otp_codes_phone_created_at"), "otp_codes", ["phone", "created_at"])
    for statement in _security(os.environ.get("UP_DB_APP_ROLE", "up_app")):
        op.execute(statement)


def downgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.execute(f"REVOKE UPDATE (name, language) ON users FROM {app_role}")
    op.execute(f"GRANT UPDATE ON users TO {app_role}")
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for table, _, _ in GRANTS:
        op.execute(f"DROP POLICY IF EXISTS auth_definer ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {AUTH_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {AUTH_ROLE}")
    op.drop_index(op.f("ix_otp_codes_phone_created_at"), table_name="otp_codes")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_prev_token_hash"), table_name="sessions")
    op.drop_column("sessions", "prev_valid_until")
    op.drop_column("sessions", "prev_token_hash")

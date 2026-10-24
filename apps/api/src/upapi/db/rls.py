"""RLS va huquqlar SQL'i (ADR-012; 03-arxitektura.md §10). Migratsiyalar shu funksiyalardan foydalanadi.

Ilova ``up_app`` roli bilan ulanadi: ``NOSUPERUSER NOBYPASSRLS``, jadval egasi emas. Har tranzaksiyada
``SET LOCAL app.org_id`` (``set_config(..., true)``) — tranzaksiyadan tashqariga chiqmaydi; o'rnatilmagan bo'lsa
``app_current_org()`` NULL → hech bir qator ko'rinmaydi va yozilmaydi.
"""

from __future__ import annotations

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION app_current_org() RETURNS uuid LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.org_id', true), '')::uuid $$""",
    """CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$""",
]
DROP_FUNCTIONS = [
    "DROP FUNCTION IF EXISTS app_current_org()",
    "DROP FUNCTION IF EXISTS app_current_user()",
]


def ensure_role(role: str) -> list[str]:
    """Rol yo'q bo'lsa NOLOGIN yaratiladi (parol va LOGIN — infra, B2.10). Bor bo'lsa o'zgarmaydi."""
    return [
        f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN CREATE ROLE {role} NOLOGIN; END IF;
        END $$""",
        f"GRANT USAGE ON SCHEMA public TO {role}",
        f"GRANT EXECUTE ON FUNCTION app_current_org(), app_current_user() TO {role}",
    ]


def tenant(table: str, role: str, append_only: bool = False, key: str = "org_id") -> list[str]:
    privileges = "SELECT, INSERT" if append_only else "SELECT, INSERT, UPDATE, DELETE"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {table} USING ({key} = app_current_org()) "
        f"WITH CHECK ({key} = app_current_org())",
        f"GRANT {privileges} ON {table} TO {role}",
    ]


def global_read(table: str, role: str) -> list[str]:
    return [f"GRANT SELECT ON {table} TO {role}"]


def auth_only(table: str) -> list[str]:
    """Kirish jadvallari: RLS yoqilgan, siyosat va ilova roliga huquq yo'q (B2.3 — alohida yo'l)."""
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
    ]


def users(role: str) -> list[str]:
    """Foydalanuvchi: o'zi yoki joriy tashkilot a'zosi ko'rinadi; faqat o'zini o'zgartiradi."""
    return [
        "ALTER TABLE users ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE users FORCE ROW LEVEL SECURITY",
        "CREATE POLICY users_visible ON users FOR SELECT USING (id = app_current_user() OR EXISTS "
        "(SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.org_id = app_current_org()))",
        "CREATE POLICY users_self_update ON users FOR UPDATE USING (id = app_current_user()) "
        "WITH CHECK (id = app_current_user())",
        f"GRANT SELECT, UPDATE ON users TO {role}",
    ]

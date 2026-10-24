"""sync (B2.6)

- **Procrastinate** navbati (03 §2, ADR-003): sxema o'rnatilgan kutubxona versiyasidan (``SchemaManager``). Kutubxona
  yangilansa uning ``sql/migrations/*.sql`` fayllari yangi Alembic reviziyasida qo'llanadi (Dependabot PR'ida).
  Jadvallar tashkilotsiz (ish argumentlarida faqat id'lar) — ilova roliga o'qish/yozish.
- ``sync_state``/``sync_runs`` ga navbat va "Ma'lumotlar holati" ustunlari, ``mp_accounts`` ga ketma-ket kalit
  xatolari va pauza, ``sale_items`` ga SKU nomi, mahsulot va topshirilgan vaqt; indekslar.
- ``provider_health`` — Uzum uzilishi holati (tizim jadvali).
- ``sync_accounts()`` — rejalashtiruvchi uchun ulangan akkauntlar ro'yxati (faqat id'lar). Ishchi ``up_app`` bilan
  ulanadi va RLS tufayli tashkilotlar bo'ylab ko'ra olmaydi; funksiya ``SECURITY DEFINER``, egasi ``up_sync``
  (NOLOGIN, BYPASSRLS yo'q, faqat kerakli ustunlarga huquq — kalit ustunlari yo'q). Migratsiya roli superuser yoki
  ``up_sync`` a'zosi bo'lishi kerak (``ALTER FUNCTION ... OWNER TO``), 0002 dagi ``up_auth`` kabi.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24 18:00:00
"""

import inspect
import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from procrastinate.schema import SchemaManager
from sqlalchemy.dialects import postgresql
from sqlalchemy.util import await_only
from upapi.db import rls

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_ROLE = "up_sync"
SYNC_ACCOUNTS = "sync_accounts()"
CHECKS = {
    "sync_state": {
        "kind": ("shops", "orders", "expenses", "products", "snapshot", "invoices", "returns")
    },
    "sync_runs": {
        "kind": ("shops", "orders", "expenses", "products", "snapshot", "invoices", "returns"),
        "status": ("running", "ok", "warning", "error", "skipped"),
        "trigger": ("schedule", "user", "connect"),
        "mode": ("full", "history", "incremental", "deep", "outage"),
    },
}
# up_sync huquqlari: faqat funksiyaga kerakli ustunlar (kalit, nom va boshqa ma'lumot yo'q).
SYNC_GRANTS = {
    "orgs": "id, deleted_at",
    "mp_accounts": "id, org_id, status",
    "shops": "org_id, account_id, active",
}


def _script(sql: str) -> None:
    """Ko'p buyruqli SQL (funksiyalar ``$$`` ichida, ``%`` belgilar) — drayverning o'zi orqali: psycopg ham, asyncpg
    ham parametrsiz so'rovda bir nechta buyruqni qabul qiladi (SQLAlchemy esa tayyorlangan so'rov qiladi)."""
    raw = op.get_bind().connection.driver_connection
    assert raw is not None
    result = raw.execute(sql)
    if inspect.isawaitable(result):
        await_only(result)


def _procrastinate(app_role: str) -> list[str]:
    return [
        f"""DO $$ DECLARE r record; BEGIN
        FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'procrastinate\\_%' LOOP
          EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO {app_role}', r.tablename);
        END LOOP;
        FOR r IN SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          WHERE n.nspname = 'public' AND c.relkind = 'S' AND relname LIKE 'procrastinate\\_%' LOOP
          EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO {app_role}', r.relname);
        END LOOP;
        END $$""",
    ]


def _sync_role(app_role: str) -> list[str]:
    sql = [
        f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{SYNC_ROLE}') THEN
          CREATE ROLE {SYNC_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
        END $$""",
        f"GRANT USAGE ON SCHEMA public TO {SYNC_ROLE}",
        f"GRANT CREATE ON SCHEMA public TO {SYNC_ROLE}",  # egasini o'zgartirish uchun vaqtincha
    ]
    for table, columns in SYNC_GRANTS.items():
        sql += [
            f"GRANT SELECT ({columns}) ON {table} TO {SYNC_ROLE}",
            f"CREATE POLICY sync_definer ON {table} FOR SELECT TO {SYNC_ROLE} USING (true)",
        ]
    sql += [
        f"""CREATE FUNCTION {SYNC_ACCOUNTS} RETURNS TABLE (org_id uuid, account_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT a.org_id, a.id FROM mp_accounts a JOIN orgs o ON o.id = a.org_id
  WHERE o.deleted_at IS NULL AND a.status <> 'disconnected'
    AND EXISTS (SELECT 1 FROM shops s WHERE s.org_id = a.org_id AND s.account_id = a.id AND s.active)
  ORDER BY a.org_id, a.id
$$""",
        f"ALTER FUNCTION {SYNC_ACCOUNTS} OWNER TO {SYNC_ROLE}",
        f"REVOKE ALL ON FUNCTION {SYNC_ACCOUNTS} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {SYNC_ACCOUNTS} TO {app_role}",
        f"REVOKE CREATE ON SCHEMA public FROM {SYNC_ROLE}",
    ]
    return sql


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "provider_health",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("outage_since", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paused_until", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "failures",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("recovered_from", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("recovered_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider", name=op.f("pk_provider_health")),
    )
    op.add_column(
        "mp_accounts", sa.Column("auth_failures", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "mp_accounts",
        sa.Column("sync_paused_until", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_mp_expenses_org_id_shop_id_created_on"),
        "mp_expenses",
        ["org_id", "shop_id", "created_on"],
    )
    op.create_index(
        op.f("ix_mp_skus_org_id_shop_id_sku_code"), "mp_skus", ["org_id", "shop_id", "sku_code"]
    )
    op.add_column("sale_items", sa.Column("sku_title", sa.Text(), nullable=True))
    op.add_column("sale_items", sa.Column("product_external_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "sale_items", sa.Column("issued_at", postgresql.TIMESTAMP(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_sale_items_org_id_shop_id_ordered_at"),
        "sale_items",
        ["org_id", "shop_id", "ordered_at"],
    )
    op.add_column("sync_runs", sa.Column("total", sa.Integer(), nullable=True))
    op.add_column(
        "sync_runs", sa.Column("requests", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "sync_runs", sa.Column("trigger", sa.Text(), server_default="schedule", nullable=False)
    )
    op.add_column("sync_runs", sa.Column("mode", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_sync_runs_org_id_shop_id_kind_started_at"),
        "sync_runs",
        ["org_id", "shop_id", "kind", "started_at"],
    )
    op.add_column(
        "sync_state",
        sa.Column("last_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column("sync_state", sa.Column("last_status", sa.Text(), nullable=True))
    op.add_column("sync_state", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "sync_state", sa.Column("failures", sa.Integer(), server_default="0", nullable=False)
    )
    for table, columns in CHECKS.items():
        for column, values in columns.items():
            op.create_check_constraint(
                op.f(f"ck_{table}_{column}_allowed"),
                table,
                f"{column} IN ({', '.join(repr(v) for v in values)})",
            )

    for statement in rls.system("provider_health", app_role):
        op.execute(statement)
    _script(SchemaManager.get_schema())
    for statement in _procrastinate(app_role) + _sync_role(app_role):
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SYNC_ACCOUNTS}")
    for table in SYNC_GRANTS:
        op.execute(f"DROP POLICY IF EXISTS sync_definer ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {SYNC_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {SYNC_ROLE}")
    # Procrastinate obyektlari: jadvallar (navbatdagi ishlar bilan), funksiyalar, turlar.
    op.execute(
        """DO $$ DECLARE r record; BEGIN
        FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'procrastinate\\_%' LOOP
          EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', r.tablename);
        END LOOP;
        FOR r IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname = 'public' AND p.proname LIKE 'procrastinate\\_%' LOOP
          EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
        END LOOP;
        FOR r IN SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
          WHERE n.nspname = 'public' AND t.typname LIKE 'procrastinate\\_%' AND t.typtype IN ('e', 'c') LOOP
          EXECUTE format('DROP TYPE IF EXISTS %I CASCADE', r.typname);
        END LOOP;
        END $$"""
    )
    for table, columns in reversed(CHECKS.items()):
        for column in columns:
            op.drop_constraint(op.f(f"ck_{table}_{column}_allowed"), table, type_="check")
    op.drop_column("sync_state", "failures")
    op.drop_column("sync_state", "last_error")
    op.drop_column("sync_state", "last_status")
    op.drop_column("sync_state", "last_attempt_at")
    op.drop_index(op.f("ix_sync_runs_org_id_shop_id_kind_started_at"), table_name="sync_runs")
    op.drop_column("sync_runs", "mode")
    op.drop_column("sync_runs", "trigger")
    op.drop_column("sync_runs", "requests")
    op.drop_column("sync_runs", "total")
    op.drop_index(op.f("ix_sale_items_org_id_shop_id_ordered_at"), table_name="sale_items")
    op.drop_column("sale_items", "issued_at")
    op.drop_column("sale_items", "product_external_id")
    op.drop_column("sale_items", "sku_title")
    op.drop_index(op.f("ix_mp_skus_org_id_shop_id_sku_code"), table_name="mp_skus")
    op.drop_index(op.f("ix_mp_expenses_org_id_shop_id_created_on"), table_name="mp_expenses")
    op.drop_column("mp_accounts", "sync_paused_until")
    op.drop_column("mp_accounts", "auth_failures")
    op.drop_table("provider_health")

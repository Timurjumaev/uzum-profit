"""Telegram bog'lash (B6.2, 02 M15)

- ``notification_links`` — ilovadagi "Telegram'ni ulash" bir martalik tokeni (xeshi, 15 daqiqa); bot ``/start`` da
  tashkilot tranzaksiyasi ichida tekshiradi va ``notification_channels`` ga chat yozadi.
- ``telegram_memberships(tg)`` — bot buyrug'i kelganda Telegram foydalanuvchisi (shaxsiy chatda chat id = foydalanuvchi id)
  qaysi tashkilotlarda va qaysi rolda ekanini faol ``notification_channels`` dan bilish uchun (``users.telegram_user_id``
  ga ilova yozmaydi — B2.3 huquqi o'zgarmaydi) (bot ``up_app`` bilan ulanadi, RLS tufayli tashkilotlar bo'ylab ko'rmaydi). ``SECURITY DEFINER``,
  egasi ``up_sync`` (0004): faqat kerakli ustunlarga o'qish huquqi, ``sync_accounts()`` kabi.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-15 20:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)
SYNC_ROLE = "up_sync"
FUNCTION = "telegram_memberships(bigint)"
GRANTS = {
    "users": "id, language",
    "memberships": "org_id, user_id, role",
    "notification_channels": "org_id, user_id, kind, target, active",
}


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.create_table(
        "notification_links",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("used_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["orgs.id"],
            name=op.f("fk_notification_links_org_id_orgs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_links")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_notification_links_org_id_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_notification_links_token_hash")),
    )
    for statement in rls.tenant("notification_links", app_role):
        op.execute(statement)

    op.execute(f"GRANT SELECT (id, name, deleted_at) ON orgs TO {SYNC_ROLE}")
    for table, columns in GRANTS.items():
        op.execute(f"GRANT SELECT ({columns}) ON {table} TO {SYNC_ROLE}")
        op.execute(
            f"CREATE POLICY telegram_definer ON {table} FOR SELECT TO {SYNC_ROLE} USING (true)"
        )
    op.execute(f"GRANT CREATE ON SCHEMA public TO {SYNC_ROLE}")
    op.execute(
        f"""CREATE FUNCTION {FUNCTION.replace("(bigint)", "(tg bigint)")}
RETURNS TABLE (org_id uuid, user_id uuid, role text, org_name text, language text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT m.org_id, u.id, m.role, o.name, u.language
  FROM notification_channels c
  JOIN memberships m ON m.org_id = c.org_id AND m.user_id = c.user_id
  JOIN users u ON u.id = c.user_id JOIN orgs o ON o.id = c.org_id
  WHERE c.kind = 'telegram' AND c.active AND c.target = tg::text AND o.deleted_at IS NULL
  ORDER BY o.name, m.org_id
$$"""
    )
    op.execute(f"ALTER FUNCTION {FUNCTION} OWNER TO {SYNC_ROLE}")
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {app_role}")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {SYNC_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}")
    for table, columns in GRANTS.items():
        op.execute(f"DROP POLICY IF EXISTS telegram_definer ON {table}")
        op.execute(f"REVOKE SELECT ({columns}) ON {table} FROM {SYNC_ROLE}")
    op.execute(f"REVOKE SELECT (name) ON orgs FROM {SYNC_ROLE}")
    op.drop_table("notification_links")

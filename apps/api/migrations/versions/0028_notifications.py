"""Bildirishnomalar: qoidalar foydalanuvchi bo'yicha, tinch soatlar, navbat (B6.1, 02 M15)

0001 dagi bo'sh jadvallar to'ldiriladi (ular hali ishlatilmagan — qatorlar yo'q):

- ``notification_rules`` — ``user_id`` (har foydalanuvchining o'z qoidasi), ``UNIQUE (org_id, user_id, event)``;
  tinch soatlar qoidadan ``notification_prefs`` ga ko'chdi (hodisa bo'yicha emas, foydalanuvchi bo'yicha).
- ``notification_prefs`` — tinch soatlar (qator yo'q — 22:00–08:00).
- ``notifications`` — ``user_id``, ``event``, ``critical``, ``due_at`` (tinch soat tugaganda), ``attempts``, ``error``;
  takror yo'q: ``UNIQUE (org_id, user_id, dedupe_key)``.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-15 08:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from upapi.db import rls

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = postgresql.TIMESTAMP(timezone=True)


def _user(table: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("user_id", sa.UUID(), nullable=False)


def _user_fk(table: str) -> None:
    op.create_foreign_key(
        op.f(f"fk_{table}_user_id_users"), table, "users", ["user_id"], ["id"], ondelete="CASCADE"
    )


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    # Jadvallar 0001 dan beri bo'sh; ehtiyot uchun tozalanadi (NOT NULL ustun qo'shiladi).
    op.execute("DELETE FROM notifications")
    op.execute("DELETE FROM notification_rules")

    op.add_column("notification_rules", _user("notification_rules"))
    _user_fk("notification_rules")
    op.drop_column("notification_rules", "quiet_from")
    op.drop_column("notification_rules", "quiet_to")
    op.create_unique_constraint(
        op.f("uq_notification_rules_org_id_user_id_event"),
        "notification_rules",
        ["org_id", "user_id", "event"],
    )

    op.create_table(
        "notification_prefs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("quiet_from", sa.Time(), nullable=True),
        sa.Column("quiet_to", sa.Time(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["orgs.id"],
            name=op.f("fk_notification_prefs_org_id_orgs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_prefs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_prefs")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_notification_prefs_org_id_id")),
        sa.UniqueConstraint("org_id", "user_id", name=op.f("uq_notification_prefs_org_id_user_id")),
    )
    for statement in rls.tenant("notification_prefs", app_role):
        op.execute(statement)

    op.add_column("notifications", _user("notifications"))
    _user_fk("notifications")
    op.add_column("notifications", sa.Column("event", sa.Text(), nullable=False))
    op.add_column(
        "notifications",
        sa.Column("critical", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("notifications", sa.Column("due_at", TS, nullable=False))
    op.add_column(
        "notifications", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("notifications", sa.Column("error", sa.Text(), nullable=True))
    op.drop_constraint(op.f("uq_notifications_org_id_dedupe_key"), "notifications", type_="unique")
    op.create_unique_constraint(
        op.f("uq_notifications_org_id_user_id_dedupe_key"),
        "notifications",
        ["org_id", "user_id", "dedupe_key"],
    )
    op.create_index(op.f("ix_notifications_status_due_at"), "notifications", ["status", "due_at"])
    op.create_check_constraint(
        op.f("ck_notifications_status_allowed"),
        "notifications",
        "status IN ('pending', 'sent', 'failed', 'skipped')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications")
    op.execute("DELETE FROM notification_rules")
    op.drop_constraint(op.f("ck_notifications_status_allowed"), "notifications", type_="check")
    op.drop_index(op.f("ix_notifications_status_due_at"), table_name="notifications")
    op.drop_constraint(
        op.f("uq_notifications_org_id_user_id_dedupe_key"), "notifications", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_notifications_org_id_dedupe_key"), "notifications", ["org_id", "dedupe_key"]
    )
    for col in ("error", "attempts", "due_at", "critical", "event", "user_id"):
        op.drop_column("notifications", col)
    op.drop_table("notification_prefs")
    op.drop_constraint(
        op.f("uq_notification_rules_org_id_user_id_event"), "notification_rules", type_="unique"
    )
    op.add_column("notification_rules", sa.Column("quiet_to", sa.Time(), nullable=True))
    op.add_column("notification_rules", sa.Column("quiet_from", sa.Time(), nullable=True))
    op.drop_column("notification_rules", "user_id")

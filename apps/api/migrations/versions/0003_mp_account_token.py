"""marketplace account token (B2.4)

Kalitni uzish: ``mp_accounts`` da shifrlangan kalit, versiya va oxirgi 4 belgi NULL bo'lishi mumkin — faqat
``disconnected`` holatida (``token_state`` cheklovi). Kalit urinishlari cheklovi uchun ``audit_log`` indeksi.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 22:00:00
"""

from collections.abc import Sequence

from alembic import op
from upapi.db.models import TOKEN_STATE

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = "ck_mp_accounts_status_allowed"
_TOKEN = "ck_mp_accounts_token_state"
_INDEX = "ix_audit_log_org_id_action_created_at"
_OLD = ("active", "invalid", "quota_exhausted", "waf_blocked")
_NEW = (*_OLD, "disconnected")


def _status_check(values: tuple[str, ...]) -> str:
    allowed = ", ".join(f"'{v}'" for v in values)
    return f"ALTER TABLE mp_accounts ADD CONSTRAINT {_STATUS} CHECK (status IN ({allowed}))"


def upgrade() -> None:
    for column in ("token_encrypted", "key_version", "token_last4"):
        op.alter_column("mp_accounts", column, nullable=True)
    op.execute(f"ALTER TABLE mp_accounts DROP CONSTRAINT {_STATUS}")
    op.execute(_status_check(_NEW))
    op.execute(f"ALTER TABLE mp_accounts ADD CONSTRAINT {_TOKEN} CHECK ({TOKEN_STATE})")
    op.create_index(_INDEX, "audit_log", ["org_id", "action", "created_at"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="audit_log")
    # Uzilgan akkauntda kalit yo'q — eski sxemaga sig'maydi; o'chirib yuborilmaydi (do'konlar va ma'lumotlari ketadi).
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT FROM mp_accounts WHERE token_encrypted IS NULL) THEN "
        "RAISE EXCEPTION 'uzilgan akkauntlar bor: 0003 dan pastga tushib bo''lmaydi'; END IF; END $$"
    )
    op.execute(f"ALTER TABLE mp_accounts DROP CONSTRAINT {_TOKEN}")
    op.execute(f"ALTER TABLE mp_accounts DROP CONSTRAINT {_STATUS}")
    op.execute(_status_check(_OLD))
    for column in ("token_encrypted", "key_version", "token_last4"):
        op.alter_column("mp_accounts", column, nullable=False)

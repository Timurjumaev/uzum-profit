"""tashkilotni o'chirish (B8.13): ``orgs.deletion_requested_at`` va muddati o'tganlarni topish funksiyasi

Egasi o'chirishni so'raydi — tashkilot 30 kun ishlashda davom etadi (bekor qilsa bo'ladi), keyin kunlik ish
(``org.purge``) uni butunlay o'chiradi (``DELETE FROM orgs`` — hamma tashkilot jadvallari ``ON DELETE CASCADE``).
``purge_due_orgs(cutoff)`` — ``up_sync`` egasidagi ``SECURITY DEFINER`` funksiya (``sync_accounts()`` kabi: faqat kerakli
ustunlar); ilova roli uni chaqiradi, lekin boshqa tashkilot ma'lumotini ko'rmaydi (faqat id'lar).

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-21 19:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_ROLE = "up_sync"
SIGNATURE = "purge_due_orgs(timestamptz)"
FUNCTION = """
CREATE FUNCTION purge_due_orgs(p_cutoff timestamptz) RETURNS TABLE (org_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT o.id FROM orgs o
  WHERE o.deletion_requested_at IS NOT NULL AND o.deletion_requested_at < p_cutoff
  ORDER BY o.deletion_requested_at
$$"""


def upgrade() -> None:
    app_role = os.environ.get("UP_DB_APP_ROLE", "up_app")
    op.add_column(
        "orgs",
        sa.Column("deletion_requested_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(f"GRANT SELECT (deletion_requested_at) ON orgs TO {SYNC_ROLE}")
    op.execute(
        f"GRANT CREATE ON SCHEMA public TO {SYNC_ROLE}"
    )  # egasini o'zgartirish uchun vaqtincha
    op.execute(FUNCTION)
    op.execute(f"ALTER FUNCTION {SIGNATURE} OWNER TO {SYNC_ROLE}")
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {app_role}")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {SYNC_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
    op.execute(f"REVOKE SELECT (deletion_requested_at) ON orgs FROM {SYNC_ROLE}")
    op.drop_column("orgs", "deletion_requested_at")

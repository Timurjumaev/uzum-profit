"""Ta'minot qayta loyihasi, 1-qadam: ustunlar (TM1, ADR-061)

Faqat qo'shiladi — mavjud xarid, qator, xarajat va kargo yozuvlari o'zgarmaydi (yangi ustunlar ``NULL`` / ``0`` /
``false``: eski hisob aynan avvalgidek, ADR-061 §11).

- ``purchases``: ``track_no`` (trek raqami, ixtiyoriy), ``on_hand`` ("Tovar qo'limda" — kargo kutilmaydi),
  ``refund_amount`` / ``refund_currency`` / ``refund_on`` (sotuvchi qaytargan summa — tovar summasidan ayriladi).
- ``purchase_lines``: ``sku_id`` (qator qaysi SKU uchun — sanash va Uzumga jo'natish SKU bo'yicha), ``line_sum`` (qator
  summasi, xarid valyutasida), ``defect_qty`` (sanashdagi brak), ``pack_unit_cost`` (qadoq qo'shimchasi, so'm/dona —
  sanashda tovardan nusxa).
- ``items.pack_unit_cost``: tovarning qadoq qo'shimchasi (so'm/dona, ixtiyoriy).
- ``cost_components``: ``weight_kg`` (kargo vazni, faqat ma'lumot); taqsimot asosi ``line_sum`` (qator summasi bo'yicha).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FX = sa.Numeric(18, 4)
UZS = sa.Numeric(18, 2)
OLD_BASES = "allocation IN ('units', 'weight', 'volume', 'value', 'manual')"
NEW_BASES = "allocation IN ('units', 'weight', 'volume', 'value', 'manual', 'line_sum')"


def upgrade() -> None:
    op.add_column("purchases", sa.Column("track_no", sa.Text(), nullable=True))
    op.add_column(
        "purchases",
        sa.Column("on_hand", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("purchases", sa.Column("refund_amount", FX, nullable=True))
    op.add_column("purchases", sa.Column("refund_currency", sa.Text(), nullable=True))
    op.add_column("purchases", sa.Column("refund_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f("ck_purchases_refund"),
        "purchases",
        "refund_amount IS NULL OR (refund_amount >= 0 AND refund_currency IS NOT NULL)",
    )

    op.add_column("purchase_lines", sa.Column("sku_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_purchase_lines_sku_id",
        "purchase_lines",
        "mp_skus",
        ["org_id", "sku_id"],
        ["org_id", "id"],
    )
    op.add_column("purchase_lines", sa.Column("line_sum", FX, nullable=True))
    op.add_column(
        "purchase_lines",
        sa.Column("defect_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("purchase_lines", sa.Column("pack_unit_cost", UZS, nullable=True))
    op.create_check_constraint(
        op.f("ck_purchase_lines_counting"),
        "purchase_lines",
        "defect_qty >= 0 AND defect_qty <= coalesce(received_qty, ordered_qty)"
        " AND (line_sum IS NULL OR line_sum >= 0)"
        " AND (pack_unit_cost IS NULL OR pack_unit_cost >= 0)",
    )

    op.add_column("items", sa.Column("pack_unit_cost", UZS, nullable=True))
    op.create_check_constraint(
        op.f("ck_items_pack_unit_cost"), "items", "pack_unit_cost IS NULL OR pack_unit_cost >= 0"
    )

    op.add_column("cost_components", sa.Column("weight_kg", sa.Numeric(12, 3), nullable=True))
    op.drop_constraint(
        op.f("ck_cost_components_allocation_allowed"), "cost_components", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_cost_components_allocation_allowed"), "cost_components", NEW_BASES
    )


def downgrade() -> None:
    # ``line_sum`` asosi eski sxemada yo'q: dona asosiga qaytadi (qator summalari ustuni ham o'chadi).
    op.execute("UPDATE cost_components SET allocation = 'units' WHERE allocation = 'line_sum'")
    op.drop_constraint(
        op.f("ck_cost_components_allocation_allowed"), "cost_components", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_cost_components_allocation_allowed"), "cost_components", OLD_BASES
    )
    op.drop_column("cost_components", "weight_kg")
    op.drop_constraint(op.f("ck_items_pack_unit_cost"), "items", type_="check")
    op.drop_column("items", "pack_unit_cost")
    op.drop_constraint(op.f("ck_purchase_lines_counting"), "purchase_lines", type_="check")
    op.drop_column("purchase_lines", "pack_unit_cost")
    op.drop_column("purchase_lines", "defect_qty")
    op.drop_column("purchase_lines", "line_sum")
    op.drop_constraint("fk_purchase_lines_sku_id", "purchase_lines", type_="foreignkey")
    op.drop_column("purchase_lines", "sku_id")
    op.drop_constraint(op.f("ck_purchases_refund"), "purchases", type_="check")
    for column in ("refund_on", "refund_currency", "refund_amount", "on_hand", "track_no"):
        op.drop_column("purchases", column)

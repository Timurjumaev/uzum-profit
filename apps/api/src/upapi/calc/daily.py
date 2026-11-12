"""Kunlik agregat ``daily_sku_metrics`` (03 §5, §11): do'kon × SKU × Toshkent kuni — bosh sahifa va P&L tezligi uchun.

Manba: ``sale_items`` (hamma holatlar) va ``sale_costs`` (F21). Yig'indilar ``upcore.metrics.sale_totals`` dan (F3–F8, F15, F17, F18, F22, F44 — ADR-043) —
SQL'da formula yo'q. Hamma ustunlar additiv: davr natijasi = kunlar yig'indisi. Sotuvlar — Yakunlangan + Jarayonda
(ADR-036), Jarayondagi qismi har pul ustuni bo'yicha alohida (``*_processing``, ADR-037) va Uzum logistikasini hali
yozmagan Jarayondagi qatorlar donasi (``*_logistics_due`` — F5 taxmini asosi; summa o'qishda F40 bilan).

- Kun — buyurtma sanasi (F1).
- Reklama bu jadvalda yo'q (audit K13: ``ads`` ustuni yozilardi, hech kim o'qimasdi) — u ``mp_expenses`` dan to'g'ridan-to'g'ri
  o'qiladi (``upapi.reports.cells``, F19, F42).
- SKU'ga bog'lanmagan sotuvlar ham ``sku_id`` NULL qatorga tushadi (tushum yo'qolmaydi).

Qayta qurish do'kon bo'yicha ``since`` kunidan (``None`` — butun tarix): eski qatorlar o'chib, yangidan yoziladi.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.costing import is_estimated
from upcore.expenses import ExpenseCategory
from upcore.metrics import SaleLine, business_date, sale_totals

from upapi.calc.costs import day_start
from upapi.db import models as m

type Key = tuple[UUID | None, date]


def charged_logistics() -> Any:
    """ADR-042: Uzum sotuv qatori uchun aslida yechgan logistika — ``finance/expenses`` dagi, sotuv qatoriga bog'langan
    logistika chiqimlari yig'indisi (status bekor qilinganlari hisobga olinmaydi). Uzum logistikani tovar olib
    ketilganda yechadi va bonusni olib ketilgan kunga qarab beradi (9–31-oktabr — 0, noyabrda — tarif), sotuv qatoridagi
    ``logisticDeliveryFee`` esa buyurtma sanasiga qarab yozilgan — o'tish davrida ular farq qiladi."""
    e = m.mp_expenses
    return (
        select(e.c.sale_item_id, func.sum(e.c.amount).label("charged"))
        .where(
            e.c.category == ExpenseCategory.LOGISTICS.value,
            e.c.type == "OUTCOME",
            e.c.sale_item_id.is_not(None),
            e.c.excluded.is_distinct_from("status"),
        )
        .group_by(e.c.sale_item_id)
        .subquery()
    )


def effective_logistics(s: Any, x: Any) -> Any:
    """F5 (ADR-042): sotuv logistikasi — Uzum yechgan bo'lsa yechgani, hali yechmagan bo'lsa sotuv qatoridagi summa
    (Uzum buyurtma paytida yozgan; 0 va topshirilmagan — F40 taxmini, ``upcore.metrics.logistics_due``)."""
    return func.coalesce(x.c.charged, s.c.logistics_fee).label("logistics_effective")


async def _sales(
    conn: AsyncConnection, shop_id: UUID, since: date | None
) -> dict[Key, list[SaleLine]]:
    s, c = m.sale_items, m.sale_costs
    x = charged_logistics()
    query = (
        select(
            s.c.sku_id,
            s.c.ordered_at,
            s.c.status,
            s.c.sell_price,
            s.c.amount,
            s.c.commission,
            effective_logistics(s, x),
            s.c.amount_returns,
            s.c.issued_at,
            c.c.cogs,
            c.c.flags,
        )
        .outerjoin(c, c.c.sale_item_id == s.c.id)
        .outerjoin(x, x.c.sale_item_id == s.c.id)
        .where(s.c.shop_id == shop_id)
    )
    if since is not None:
        query = query.where(s.c.ordered_at >= day_start(since))
    out: dict[Key, list[SaleLine]] = {}
    for r in await conn.execute(query):
        day = business_date(r.ordered_at)
        unit = None
        if r.cogs is not None:
            unit = r.cogs / r.amount if r.amount else Decimal(0)
        out.setdefault((r.sku_id, day), []).append(
            SaleLine(
                sku=str(r.sku_id),
                order_date=day,
                status=r.status,
                sell_price=r.sell_price,
                amount=r.amount,
                commission=r.commission,
                logistics=r.logistics_effective,
                amount_returns=r.amount_returns,
                unit_cost=unit,
                estimated=is_estimated(r.flags),  # B4.69: Markaziy bank kursi, tarixiy — aniq
                issued=r.issued_at is not None,
            )
        )
    return out


async def rebuild_shop(
    conn: AsyncConnection, org_id: UUID, shop_id: UUID, since: date | None
) -> int:
    """Do'kon kunlik agregatini ``since`` kunidan qayta quradi. Qaytadi: yozilgan qatorlar soni."""
    d = m.daily_sku_metrics
    stale = delete(d).where(d.c.shop_id == shop_id)
    if since is not None:
        stale = stale.where(d.c.day >= since)
    await conn.execute(stale)
    sales = await _sales(conn, shop_id, since)
    rows: list[dict[str, Any]] = []
    for sku_id, day in sorted(sales, key=lambda k: (k[1], str(k[0]))):
        t = sale_totals(sales[(sku_id, day)])
        rows.append(
            {
                "org_id": org_id,
                "shop_id": shop_id,
                "sku_id": sku_id,
                "day": day,
                "revenue": t.revenue.amount,
                "units": t.units,
                "commission": t.commission.amount,
                "logistics": t.logistics.amount,
                "cogs": t.cogs.amount,
                "returns": t.returns,
                "canceled": t.canceled,
                "revenue_costed": t.revenue_costed.amount,
                "payout_costed": t.payout_costed.amount,
                "cogs_estimated": t.cogs_estimated.amount,
                "lines": t.lines,
                "lines_uncosted": t.uncovered_lines,
                "units_costed": t.units_costed,
                "units_processing": t.units_processing,
                "revenue_processing": t.revenue_processing.amount,
                "commission_processing": t.commission_processing.amount,
                "logistics_processing": t.logistics_processing.amount,
                "cogs_processing": t.cogs_processing.amount,
                "revenue_costed_processing": t.revenue_costed_processing.amount,
                "payout_costed_processing": t.payout_costed_processing.amount,
                "units_costed_processing": t.units_costed_processing,
                "lines_processing": t.lines_processing,
                "lines_uncosted_processing": t.uncovered_lines_processing,
                "units_logistics_due": t.units_logistics_due,
                "units_logistics_due_costed": t.units_logistics_due_costed,
                "lines_logistics_due": t.lines_logistics_due,
                "canceled_issued": t.canceled_issued,
                "canceled_revenue": t.canceled_revenue.amount,
                "canceled_issued_revenue": t.canceled_issued_revenue.amount,
                "returns_revenue": t.returns_revenue.amount,
            }
        )
    for start in range(0, len(rows), 2_000):
        await conn.execute(insert(d), rows[start : start + 2_000])
    return len(rows)


async def rebuild(
    conn: AsyncConnection, org_id: UUID, shops: Iterable[tuple[UUID, date | None]]
) -> int:
    return sum([await rebuild_shop(conn, org_id, shop, since) for shop, since in shops])

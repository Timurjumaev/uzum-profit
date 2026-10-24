"""Kunlik agregat ``daily_sku_metrics`` (03 §5, §11): do'kon × SKU × Toshkent kuni — bosh sahifa va P&L tezligi uchun.

Manba: ``sale_items`` (hamma holatlar), ``sale_costs`` (F21) va reklama xarajatlari (``mp_expenses``, toifa
``advertising``, P&L'ga kiradiganlari). Yig'indilar ``upcore.metrics.sale_totals`` dan (F3–F8, F15, F17, F18, F22) —
SQL'da formula yo'q. Hamma ustunlar additiv: davr natijasi = kunlar yig'indisi.

- Kun — buyurtma sanasi (F1); reklama — xarajat sanasi.
- Reklama SKU'ga ``AD#<sotuv qatori id>`` orqali (F19); bog'lanmagani (yoki bir ma'noli bo'lmagani) — ``sku_id`` NULL
  qatorda (do'kon darajasi), taqsimot — o'qishda (``upcore.metrics.sku_acos``, B2.9). Summa ishora bilan (INCOME −).
- SKU'ga bog'lanmagan sotuvlar ham ``sku_id`` NULL qatorga tushadi (tushum yo'qolmaydi).

Qayta qurish do'kon bo'yicha ``since`` kunidan (``None`` — butun tarix): eski qatorlar o'chib, yangidan yoziladi.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import SaleLine, business_date, sale_totals
from upcore.money import Currency, Money

from upapi.calc.costs import day_start
from upapi.db import models as m

UZS = Currency.UZS
type Key = tuple[UUID | None, date]


async def _ads(conn: AsyncConnection, shop_id: UUID, since: date | None) -> dict[Key, Money]:
    e, s = m.mp_expenses, m.sale_items
    query = select(e.c.created_on, e.c.type, e.c.amount, e.c.item_external_id).where(
        e.c.shop_id == shop_id,
        e.c.category == ExpenseCategory.ADVERTISING.value,
        e.c.excluded.is_(None),
    )
    if since is not None:
        query = query.where(e.c.created_on >= day_start(since))
    rows: list[Any] = list(await conn.execute(query))
    wanted = {r.item_external_id for r in rows if r.item_external_id is not None}
    sku_of: dict[int, set[UUID | None]] = {}
    if wanted:
        for r in await conn.execute(
            select(s.c.external_id, s.c.sku_id).where(
                s.c.shop_id == shop_id, s.c.external_id.in_(wanted)
            )
        ):
            sku_of.setdefault(r.external_id, set()).add(r.sku_id)
    out: dict[Key, Money] = {}
    for r in rows:
        skus = sku_of.get(r.item_external_id, set())
        sku = next(iter(skus)) if len(skus) == 1 else None
        key = (sku, business_date(r.created_on))
        out[key] = out.get(key, Money.zero(UZS)) + signed_amount(Money(r.amount, UZS), r.type)
    return out


async def _sales(
    conn: AsyncConnection, shop_id: UUID, since: date | None
) -> dict[Key, list[SaleLine]]:
    s, c = m.sale_items, m.sale_costs
    query = (
        select(
            s.c.sku_id,
            s.c.ordered_at,
            s.c.status,
            s.c.sell_price,
            s.c.amount,
            s.c.commission,
            s.c.logistics_fee,
            s.c.amount_returns,
            c.c.cogs,
            c.c.flags,
        )
        .outerjoin(c, c.c.sale_item_id == s.c.id)
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
                logistics=r.logistics_fee,
                amount_returns=r.amount_returns,
                unit_cost=unit,
                estimated=bool(r.flags),
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
    ads = await _ads(conn, shop_id, since)
    rows: list[dict[str, Any]] = []
    for sku_id, day in sorted(set(sales) | set(ads), key=lambda k: (k[1], str(k[0]))):
        t = sale_totals(sales.get((sku_id, day), ()))
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
                "ads": ads.get((sku_id, day), Money.zero(UZS)).amount,
                "returns": t.returns,
                "canceled": t.canceled,
                "revenue_costed": t.revenue_costed.amount,
                "payout_costed": t.payout_costed.amount,
                "cogs_estimated": t.cogs_estimated.amount,
            }
        )
    for start in range(0, len(rows), 2_000):
        await conn.execute(insert(d), rows[start : start + 2_000])
    return len(rows)


async def rebuild(
    conn: AsyncConnection, org_id: UUID, shops: Iterable[tuple[UUID, date | None]]
) -> int:
    return sum([await rebuild_shop(conn, org_id, shop, since) for shop, since in shops])

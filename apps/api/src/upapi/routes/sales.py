"""``/sales``: sotuv qatorlari (M7; P&L drill-down). Ruxsat — ``view_finance``.

Qator: sana (F1), holat va guruh (F2), SKU, dona, narx, tushum, komissiya, logistika, Uzum to'lovi (F6), tannarx
(F21, belgilari bilan: taxminiy, lot yetmadi ...), yalpi foyda (F8), "qayta hisoblandi" (oxirgi 7 kun), Uzum bonusi
davri (``waiver_id``, ADR-031). Tartib —
eng yangisidan; sahifalash kursor bilan. ``summary`` — filtr (davr, do'kon, SKU) bo'yicha bekor va qaytish ulushi
(F17, F18, ``daily_sku_metrics`` dan; holat filtri unga ta'sir qilmaydi).

P&L qatori drill-down'i: ``group=completed`` qatorlari tushum/komissiya/logistika/tannarx yig'indisi = P&L qatori.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from upcore.metrics import StatusGroup, cancel_rate, return_share, status_group, statuses
from upcore.money import Currency, Money
from upcore.waivers import waiver_for

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports import cells as rc
from upapi.reports import waivers as rw
from upapi.reports.common import (
    Cursor,
    Filters,
    Limit,
    Meta,
    db_now,
    decode_cursor,
    encode_cursor,
    filters,
    meta,
)

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders"]
UZS = Currency.UZS


class SaleOut(BaseModel):
    id: UUID
    shop_id: UUID
    sku_id: UUID | None
    sku_title: str | None
    order_id: int
    external_id: int
    ordered_at: datetime
    day: date  # F1
    status: str
    group: StatusGroup  # F2
    amount: int
    amount_returns: int
    return_cause: str | None
    sell_price: Decimal
    revenue: Decimal
    commission: Decimal
    logistics: Decimal
    payout: Decimal  # F6
    cogs: Decimal | None  # F7 (F21)
    gross_profit: Decimal | None  # F8
    cost_flags: list[str]  # F22: taxminiy, lot yetmadi, lot yo'q, tovar yo'q ...
    recalculated_at: datetime | None  # 03 §7: oxirgi 7 kunda tannarx o'zgargan bo'lsa
    previous_cogs: Decimal | None
    waiver_id: (
        UUID | None
    )  # Uzum bonusi davri (ADR-031) — "Bonus davri" belgisi; hisobga ta'sir qilmaydi


class SalesSummaryOut(BaseModel):
    units: int
    canceled: int
    returns: int
    cancel_share: Decimal | None  # F17
    return_share: Decimal | None  # F18


class SalesOut(BaseModel):
    meta: Meta
    items: list[SaleOut]
    next_cursor: str | None
    summary: SalesSummaryOut


@router.get("/orgs/{org_id}/sales", response_model=SalesOut)
async def sales(
    ctx: Finance,
    f: Filter,
    group: StatusGroup | None = None,
    sku: Annotated[UUID | None, Query(description="SKU id")] = None,
    unlinked: Annotated[bool, Query(description="Faqat SKU'ga bog'lanmagan sotuvlar")] = False,
    limit: Limit = 100,
    cursor: Cursor = None,
) -> SalesOut:
    s, c = m.sale_items, m.sale_costs
    now = await db_now(ctx.conn)
    after = decode_cursor(cursor, 2)
    where = [
        s.c.ordered_at >= day_start(f.period.start),
        s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
    ]
    if f.shops:
        where.append(s.c.shop_id.in_(f.shops))
    if sku is not None:
        where.append(s.c.sku_id == sku)
    if unlinked:
        where.append(s.c.sku_id.is_(None))
    if group is StatusGroup.UNKNOWN:
        known = [x for g in StatusGroup for x in statuses(g)]
        where.append(func.upper(func.trim(s.c.status)).not_in(known))
    elif group is not None:
        where.append(func.upper(func.trim(s.c.status)).in_(statuses(group)))
    query = (
        select(s, c.c.cogs, c.c.flags, c.c.changed_at, c.c.previous_cogs)
        .outerjoin(c, c.c.sale_item_id == s.c.id)
        .where(*where)
        .order_by(s.c.ordered_at.desc(), s.c.id.desc())
        .limit(limit + 1)
    )
    if after is not None:
        at, last = datetime.fromisoformat(after[0]), UUID(after[1])
        query = query.where(or_(s.c.ordered_at < at, and_(s.c.ordered_at == at, s.c.id < last)))
    rows = list(await ctx.conn.execute(query))
    more = len(rows) > limit
    rows = rows[:limit]
    recent = now - timedelta(days=rc.RECALC_DAYS)
    waivers = await rw.active_waivers(ctx.conn) if rows else []
    items = []
    for r in rows:
        line = rc.sale_line(r)
        waiver = waiver_for(waivers, str(r.shop_id), line.order_date)
        profit = line.gross_profit
        changed = r.changed_at if r.changed_at is not None and r.changed_at >= recent else None
        items.append(
            SaleOut(
                id=r.id,
                shop_id=r.shop_id,
                sku_id=r.sku_id,
                sku_title=r.sku_title,
                order_id=r.order_id,
                external_id=r.external_id,
                ordered_at=r.ordered_at,
                day=line.order_date,
                status=r.status,
                group=status_group(r.status),
                amount=r.amount,
                amount_returns=r.amount_returns,
                return_cause=r.return_cause,
                sell_price=r.sell_price,
                revenue=line.revenue,
                commission=r.commission,
                logistics=r.logistics_fee,
                payout=line.payout,
                cogs=r.cogs,
                gross_profit=None if profit is None else Money(profit, UZS).amount,
                cost_flags=sorted(r.flags or []),
                recalculated_at=changed,
                previous_cogs=r.previous_cogs if changed else None,
                waiver_id=None if waiver is None else UUID(waiver.id),
            )
        )

    t = (await rc.sale_sums(ctx.conn, f, sku=sku, unlinked=unlinked)).get(None, rc.SaleSums())
    units, canceled, returns = t.units, t.canceled, t.returns
    tail = rows[-1] if rows else None
    return SalesOut(
        meta=await meta(ctx.conn, f, KINDS),
        items=items,
        next_cursor=encode_cursor([tail.ordered_at.isoformat(), str(tail.id)])
        if more and tail is not None
        else None,
        summary=SalesSummaryOut(
            units=units,
            canceled=canceled,
            returns=returns,
            cancel_share=cancel_rate(units, canceled),
            return_share=return_share(units, returns),
        ),
    )

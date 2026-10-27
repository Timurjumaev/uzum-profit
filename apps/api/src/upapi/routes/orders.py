"""``/orders/analysis``: bekor va qaytish tahlili (M7). Ruxsat — ``view_finance``; ro'yxat — ``/sales``.

Bekor (F17): kunlik yig'indilardan (``daily_sku_metrics``) ulush, SKU bo'yicha jadval va kunlik trend; topshirilgandan
keyin bekor — ``issued_at`` (``dateIssued``) bor Bekor qatorlar donasi. Qaytish (F18): Yakunlangan qatorlardagi
``amountReturns``; sabab (``returnCause``) — qator bo'yicha; qaytish xarajati — "Qaytim saqlash" (C000004) toifasi,
ishora bilan (kompensatsiya ayiriladi). Bekor qatorning ``returnCause`` i alohida ro'yxatda (bekor sababi).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Text, cast, func, select
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import StatusGroup, cancel_rate, late_cancel_share, return_share, statuses
from upcore.money import Currency, Money

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports import cells as rc
from upapi.reports.common import Filters, Meta, filters, meta

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders"]
UZS = Currency.UZS
TOP_SKUS = 50  # SKU jadvali: bekor + qaytish donasi eng ko'p birinchi 50 ta


class OrdersSummaryOut(BaseModel):
    units: int  # Yakunlangan dona
    canceled: int
    returns: int
    cancel_share: Decimal | None  # F17
    return_share: Decimal | None  # F18
    canceled_after_issue: int  # topshirilgandan keyin bekor (dona)
    after_issue_share: Decimal | None  # shu ulushning Bekor ichidagi qismi
    return_storage_cost: Decimal  # qaytim saqlash (C000004), kompensatsiya ayirilgan


class OrdersDayOut(BaseModel):
    day: date  # F1
    units: int
    canceled: int
    returns: int
    cancel_share: Decimal | None  # F17
    return_share: Decimal | None  # F18


class OrdersSkuOut(BaseModel):
    sku_id: UUID | None  # null — SKU'ga bog'lanmagan sotuvlar
    title: str | None
    units: int
    canceled: int
    returns: int
    cancel_share: Decimal | None  # F17
    return_share: Decimal | None  # F18


class OrdersCauseOut(BaseModel):
    cause: str | None  # Uzum ``returnCause``; null — sabab ko'rsatilmagan
    units: int


class OrdersAnalysisOut(BaseModel):
    meta: Meta
    summary: OrdersSummaryOut
    daily: list[OrdersDayOut]
    by_sku: list[OrdersSkuOut]
    return_causes: list[OrdersCauseOut]
    cancel_causes: list[OrdersCauseOut]


def _causes(rows: Any) -> list[OrdersCauseOut]:
    sums: dict[str | None, int] = defaultdict(int)
    for cause, units in rows:
        sums[cause] += int(units)
    ordered = sorted(sums.items(), key=lambda kv: (-kv[1], kv[0] or ""))
    return [OrdersCauseOut(cause=c, units=v) for c, v in ordered if v > 0]


@router.get("/orgs/{org_id}/orders/analysis", response_model=OrdersAnalysisOut)
async def analysis(ctx: Finance, f: Filter) -> OrdersAnalysisOut:
    conn = ctx.conn
    d, s, e, k = m.daily_sku_metrics, m.sale_items, m.mp_expenses, m.mp_skus

    day_query = (
        select(
            d.c.day,
            func.sum(d.c.units),
            func.sum(d.c.canceled),
            func.sum(d.c.returns),
        )
        .where(d.c.day >= f.period.start, d.c.day <= f.period.end)
        .group_by(d.c.day)
        .order_by(d.c.day)
    )
    if f.shops:
        day_query = day_query.where(d.c.shop_id.in_(f.shops))
    daily = [
        OrdersDayOut(
            day=day,
            units=int(u),
            canceled=int(c),
            returns=int(r),
            cancel_share=cancel_rate(int(u), int(c)),
            return_share=return_share(int(u), int(r)),
        )
        for day, u, c, r in await conn.execute(day_query)
    ]
    units = sum(x.units for x in daily)
    canceled = sum(x.canceled for x in daily)
    returns = sum(x.returns for x in daily)

    sums = {str(key): v for key, v in (await rc.sale_sums(conn, f, by_sku=True)).items()}
    titles: dict[str, str | None] = {}
    wanted = [UUID(key) for key in sums if key != rc.UNLINKED]
    if wanted:
        for sku_id, title in await conn.execute(
            select(cast(k.c.id, Text), k.c.sku_code).where(k.c.id.in_(wanted))
        ):
            titles[sku_id] = title
    ranked = sorted(sums.items(), key=lambda kv: (-(kv[1].canceled + kv[1].returns), kv[0]))
    by_sku = [
        OrdersSkuOut(
            sku_id=None if key == rc.UNLINKED else UUID(key),
            title=titles.get(key),
            units=v.units,
            canceled=v.canceled,
            returns=v.returns,
            cancel_share=cancel_rate(v.units, v.canceled),
            return_share=return_share(v.units, v.returns),
        )
        for key, v in ranked
        if v.canceled + v.returns > 0
    ][:TOP_SKUS]

    window = [
        s.c.ordered_at >= day_start(f.period.start),
        s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
    ]
    if f.shops:
        window.append(s.c.shop_id.in_(f.shops))
    status = func.upper(func.trim(s.c.status))
    returned = await conn.execute(
        select(s.c.return_cause, func.sum(s.c.amount_returns))
        .where(*window, s.c.amount_returns > 0, status.in_(statuses(StatusGroup.COMPLETED)))
        .group_by(s.c.return_cause)
    )
    # Bekor qator: bekor qilingan dona `amount + amountReturns` (F17, upcore.metrics._units).
    cancel_units = func.sum(s.c.amount + s.c.amount_returns)
    cancel_where = [*window, status.in_(statuses(StatusGroup.CANCELED))]
    canceled_by_cause = await conn.execute(
        select(s.c.return_cause, cancel_units).where(*cancel_where).group_by(s.c.return_cause)
    )
    after_issue = int(
        await conn.scalar(select(cancel_units).where(*cancel_where, s.c.issued_at.is_not(None)))
        or 0
    )

    cost_query = select(e.c.type, e.c.amount).where(
        e.c.created_on >= day_start(f.period.start),
        e.c.created_on < day_start(f.period.end + timedelta(days=1)),
        e.c.category == ExpenseCategory.RETURN_STORAGE.value,
        e.c.excluded.is_(None),
    )
    if f.shops:
        cost_query = cost_query.where(e.c.shop_id.in_(f.shops))
    cost = sum(
        (
            signed_amount(Money(amount, UZS), type_)
            for type_, amount in await conn.execute(cost_query)
        ),
        Money.zero(UZS),
    )

    return OrdersAnalysisOut(
        meta=await meta(conn, f, KINDS),
        summary=OrdersSummaryOut(
            units=units,
            canceled=canceled,
            returns=returns,
            cancel_share=cancel_rate(units, canceled),
            return_share=return_share(units, returns),
            canceled_after_issue=after_issue,
            after_issue_share=late_cancel_share(canceled, after_issue),
            return_storage_cost=cost.amount,
        ),
        daily=daily,
        by_sku=by_sku,
        return_causes=_causes(returned),
        cancel_causes=_causes(canceled_by_cause),
    )

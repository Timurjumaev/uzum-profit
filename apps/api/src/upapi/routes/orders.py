"""``/orders/analysis``: bekor va qaytish tahlili (M7). Ruxsat — ``view_finance``; ro'yxat — ``/sales``.

ADR-043: Uzum Bekor holatidagi qator ikkiga bo'linadi. **Bekor** (F17) — tovar xaridorga topshirilmagan (``dateIssued``
yo'q: olib ketilmagan, bekor qilingan yoki yetib kelmagan). **Qaytarish** (F18) — topshirilgan (``dateIssued`` bor: mijoz
olgan yoki punktda ko'rib rad etgan) va Yakunlangan qatordagi ``amountReturns``. Ulushlar, SKU bo'yicha jadval va kunlik
trend — kunlik yig'indilardan (``daily_sku_metrics``); sabab (``returnCause``) — qator bo'yicha, ikkala ro'yxat uchun
alohida; qaytarish xarajati — "Qaytim saqlash" (C000004) toifasi, ishora bilan (kompensatsiya ayiriladi).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Text, cast, select
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import OrderFlow
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
    units: int  # sotilgan dona (F3: Yakunlangan + Jarayonda)
    canceled: int  # F17 bekor dona
    returns: int  # F18 qaytarish dona
    cancel_share: Decimal | None  # F17
    return_share: Decimal | None  # F18
    cancel_revenue: Decimal  # F17 bekor summasi
    return_revenue: Decimal  # F18 qaytarish summasi
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


def _causes(rows: list[tuple[str | None, int]]) -> list[OrdersCauseOut]:
    return [OrdersCauseOut(cause=c, units=v) for c, v in rows]


@router.get("/orgs/{org_id}/orders/analysis", response_model=OrdersAnalysisOut)
async def analysis(ctx: Finance, f: Filter) -> OrdersAnalysisOut:
    conn = ctx.conn
    e, k = m.mp_expenses, m.mp_skus

    by_day = await rc.sale_sums(conn, f, by_day=True)
    daily = [
        OrdersDayOut(
            day=day,
            units=v.units,
            canceled=v.cancel_units,
            returns=v.return_units,
            cancel_share=v.cancel_share,
            return_share=v.return_share,
        )
        for day, v in sorted(by_day.items())
    ]
    flow = sum(by_day.values(), OrderFlow())

    sums = {str(key): v for key, v in (await rc.sale_sums(conn, f, by_sku=True)).items()}
    titles: dict[str, str | None] = {}
    wanted = [UUID(key) for key in sums if key != rc.UNLINKED]
    if wanted:
        for sku_id, title in await conn.execute(
            select(cast(k.c.id, Text), k.c.sku_code).where(k.c.id.in_(wanted))
        ):
            titles[sku_id] = title
    ranked = sorted(
        sums.items(), key=lambda kv: (-(kv[1].cancel_units + kv[1].return_units), kv[0])
    )
    by_sku = [
        OrdersSkuOut(
            sku_id=None if key == rc.UNLINKED else UUID(key),
            title=titles.get(key),
            units=v.units,
            canceled=v.cancel_units,
            returns=v.return_units,
            cancel_share=v.cancel_share,
            return_share=v.return_share,
        )
        for key, v in ranked
        if v.cancel_units + v.return_units > 0
    ][:TOP_SKUS]

    # Sabablar (ADR-043): qaytarish — qisman qaytarish + topshirilgan Bekor; bekor — topshirilmagan (SKU sahifasi bilan bitta hisob).
    causes = await rc.cause_sums(conn, f)

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
            units=flow.units,
            canceled=flow.cancel_units,
            returns=flow.return_units,
            cancel_share=flow.cancel_share,
            return_share=flow.return_share,
            cancel_revenue=flow.cancel_revenue.amount,
            return_revenue=flow.return_revenue.amount,
            return_storage_cost=cost.amount,
        ),
        daily=daily,
        by_sku=by_sku,
        return_causes=_causes(causes.returned),
        cancel_causes=_causes(causes.canceled),
    )

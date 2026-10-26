"""``/dashboard``: bosh sahifa (M4). Ruxsat — ``view_finance``.

Bloklar: hisob varag'i (P&L bilan bitta funksiya — ``upapi.reports.cells``, oldingi davr bilan), davr chizig'i
(bugun, kecha, shu oy, oy prognozi, o'tgan oy — tanlangan davrdan qat'i nazar, do'kon filtri bilan), kunlik grafik,
eng foydali 5 va zarar 5 SKU, qo'shimcha ko'rsatkichlar (F13–F19, F16, F29) va "Diqqat talab qiladi" sanoqlari.
Uzum bonuslari (ADR-031) — kunlik grafik soyasi uchun; to'lov kutilmoqda (F38) — B5 da.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from upcore.expenses import ExpenseCategory
from upcore.inventory import StockStatus
from upcore.metrics import (
    Period,
    ProfitLabel,
    cancel_rate,
    drr,
    profit_label,
    return_share,
    run_rate,
)
from upcore.money import Currency, Money, total
from upcore.pnl import CellKey, Cells, Statement, compare

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.reports import cells as rc
from upapi.reports import waivers as rw
from upapi.reports.common import (
    Filters,
    Heavy,
    Meta,
    PeriodOut,
    db_now,
    filters,
    meta,
    sku_catalog,
)
from upapi.reports.schemas import PendingOut, RowOut, StatementOut
from upapi.reports.stock import load_stock

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders", "expenses", "products", "snapshot"]
TOP = 5
UZS = Currency.UZS


class PeriodTotalOut(BaseModel):
    key: str  # today / yesterday / this_month / last_month
    period: PeriodOut
    revenue: Decimal
    net_profit: Decimal
    units: int


class ForecastOut(BaseModel):
    """M4 "Oy prognozi" (run-rate) shu oy bo'yicha."""

    revenue: Decimal | None
    net_profit: Decimal | None
    units: Decimal | None


class DayOut(BaseModel):
    day: date
    revenue: Decimal
    net_profit: Decimal
    units: int


class SkuBriefOut(BaseModel):
    sku_id: UUID
    shop_id: UUID | None
    title: str | None
    product_title: str | None
    units: int
    revenue: Decimal
    net_profit: Decimal
    margin: Decimal | None


class KpiOut(BaseModel):
    margin: Decimal | None  # F13
    uncovered_share: Decimal  # 1 − F15 (marja yonida)
    roi: Decimal | None  # F14
    cancel_share: Decimal | None  # F17
    return_share: Decimal | None  # F18
    drr: Decimal | None  # F19
    expected_profit: PendingOut  # F16
    frozen_money: Decimal  # F29 (Uzum FBO + FBS + brak, lot narxida)
    in_transit_value: Decimal  # F29 "yo'lda"
    average_days_to_sell: Decimal | None  # F29


class AttentionOut(BaseModel):
    """M4 "Diqqat talab qiladi" — sanoqlar; ro'yxatlar tegishli sahifalarda."""

    uncosted_lines: int
    uncosted_revenue: Decimal
    loss_skus: int
    stock_critical: int
    stock_high: int
    recalculated: int


class DashboardOut(BaseModel):
    meta: Meta
    statement: StatementOut
    rows: list[RowOut]
    periods: list[PeriodTotalOut]
    forecast: ForecastOut
    daily: list[DayOut]
    top: list[SkuBriefOut]
    bottom: list[SkuBriefOut]
    kpis: KpiOut
    attention: AttentionOut
    waivers: list[rw.WaiverOut]  # Uzum bonuslari (ADR-031) — kunlik grafikda soya


def _days(period: Period) -> Callable[[CellKey], bool]:
    first, last = period.start, period.end
    return lambda k: first <= k.day <= last


def _total(key: str, period: Period, s: Statement) -> PeriodTotalOut:
    return PeriodTotalOut(
        key=key,
        period=PeriodOut.of(period),
        revenue=s.revenue.amount,
        net_profit=s.net_profit.amount,
        units=s.units,
    )


@router.get("/orgs/{org_id}/dashboard", response_model=DashboardOut)
async def dashboard(ctx: Finance, f: Filter, _: Heavy) -> DashboardOut:
    conn, today = ctx.conn, f.today
    previous = f.period.previous()
    this_month = Period(today.replace(day=1), today)
    last_end = this_month.start - timedelta(days=1)
    last_month = Period(last_end.replace(day=1), last_end)
    book = await rc.load_book(conn, rc.span(previous, f.period, last_month, this_month))
    cur = book.scoped(f, f.period)

    periods = [
        ("today", Period(today, today)),
        ("yesterday", Period(today - timedelta(days=1), today - timedelta(days=1))),
        ("this_month", this_month),
        ("last_month", last_month),
    ]
    # Bir o'tishda: oldingi davr va davr chizig'i (har biri ``book.scoped(f, davr).statement()`` bilan bir xil).
    totals = book.scoped(f).statements(
        {key: _days(period) for key, period in [("previous", previous), *periods]}
    )
    by_day, s = cur.by_and_total(lambda k: k.day)
    p = totals["previous"]
    month = totals["this_month"]
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    empty = Cells(f.period, {}).statement()
    daily = []
    for i in range(f.period.days):  # sotuvsiz kun ham grafikda (0)
        day = f.period.start + timedelta(days=i)
        ds = by_day.get(day, empty)
        daily.append(
            DayOut(
                day=day, revenue=ds.revenue.amount, net_profit=ds.net_profit.amount, units=ds.units
            )
        )

    skus = {k: v for k, v in cur.by_sku().items() if k is not None and k != rc.UNLINKED}
    ranked = sorted(skus.items(), key=lambda kv: (-kv[1].net_profit.amount, kv[0]))
    top = [kv for kv in ranked[:TOP] if kv[1].net_profit.amount > 0]
    bottom = sorted(
        (kv for kv in ranked if kv[1].net_profit.amount < 0), key=lambda kv: kv[1].net_profit.amount
    )[:TOP]
    catalog = await sku_catalog(
        conn, ids=[UUID(k) for k, _ in (*top, *bottom)] if (top or bottom) else []
    )

    def brief(key: str, st: Statement) -> SkuBriefOut:
        info = catalog.get(UUID(key))
        return SkuBriefOut(
            sku_id=UUID(key),
            shop_id=info.shop_id if info else None,
            title=info.title if info else None,
            product_title=info.product_title if info else None,
            units=st.units,
            revenue=st.revenue.amount,
            net_profit=st.net_profit.amount,
            margin=st.margin,
        )

    sums = (await rc.sale_sums(conn, f)).get(None, rc.SaleSums())
    ads = s.uzum_expenses.get(ExpenseCategory.ADVERTISING, Money.zero(UZS))
    pend = await rc.pending(conn, f)
    stock = await load_stock(conn, sorted(f.shops, key=str) if f.shops else None, today)
    statuses = [x.status for x in stock.skus.values()]
    now = await db_now(conn)
    in_transit = stock.frozen["in_transit"]
    on_hand = total([v for k, v in stock.frozen.items() if k != "in_transit"], UZS)

    def forecast(value: Decimal | int) -> Decimal | None:
        return run_rate(value, today.day, days_in_month)

    return DashboardOut(
        meta=await meta(conn, f, KINDS, previous),
        statement=StatementOut.of(s),
        rows=[RowOut.of(r) for r in compare(s, p)],
        periods=[_total(key, period, totals[key]) for key, period in periods],
        forecast=ForecastOut(
            revenue=forecast(month.revenue.amount),
            net_profit=forecast(month.net_profit.amount),
            units=forecast(month.units),
        ),
        daily=daily,
        top=[brief(k, v) for k, v in top],
        bottom=[brief(k, v) for k, v in bottom],
        kpis=KpiOut(
            margin=s.margin,
            uncovered_share=s.uncovered_share,
            roi=s.roi,
            cancel_share=cancel_rate(sums.units, sums.canceled),
            return_share=return_share(sums.units, sums.returns),
            drr=drr(ads, s.revenue),
            expected_profit=PendingOut.of(pend.total),
            frozen_money=on_hand.amount,
            in_transit_value=in_transit.amount,
            average_days_to_sell=stock.average_days,
        ),
        attention=AttentionOut(
            uncosted_lines=s.uncovered_lines,
            uncosted_revenue=s.uncovered_revenue.amount,
            loss_skus=sum(
                1
                for st in skus.values()
                if profit_label(st.net_profit, st.margin) is ProfitLabel.LOSS
            ),
            stock_critical=statuses.count(StockStatus.CRITICAL),
            stock_high=statuses.count(StockStatus.HIGH),
            recalculated=await rc.recalculated(conn, f, now),
        ),
        waivers=rw.in_report(await rw.rows(conn), f),
    )

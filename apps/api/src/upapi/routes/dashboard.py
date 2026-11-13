"""``/dashboard``: bosh sahifa (M4). Ruxsat — ``view_finance``.

Bloklar: hisob varag'i (P&L bilan bitta funksiya — ``upapi.reports.cells``, oldingi davr bilan), davr chizig'i
(bugun, kecha, shu oy, oy prognozi, o'tgan oy — tanlangan davrdan qat'i nazar, do'kon filtri bilan), kunlik grafik,
eng foydali 5 va zarar 5 SKU, KPI sarhisob (ADR-043: 4 guruh, har kartochkada joriy va oldingi davr, o'zgarish va trend
nuqtalari), ombor ko'rsatkichlari (F29) va "Diqqat talab qiladi" sanoqlari.
Sotuvlar Yakunlangan + Jarayonda (ADR-036); sof foyda har kesimda ikki qismda — yakunlangan va kutilayotgan (ADR-037, F16):
hisobot, davr chizig'i, kunlar; ``expected`` — kutilayotgan qism tafsiloti va R (fakt). To'lov kutilmoqda (F38) — B5 da.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from upcore.expenses import ExpenseCategory
from upcore.inventory import StockStatus
from upcore.metrics import (
    OrderFlow,
    Period,
    drr,
    relative_change,
    run_rate,
    share_change,
)
from upcore.money import Currency, Money, total
from upcore.pnl import CellKey, Cells, Statement, compare, expected_value, order_to_profit

from upapi import orgsettings
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.reports import cells as rc
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
from upapi.reports.receiving import attention as receiving_attention
from upapi.reports.schemas import ExpectedOut, RevenueLimitOut, RowOut, StatementOut
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
    net_profit_done: Decimal  # ADR-037: yakunlangan + kutilayotgan (Jarayonda) = ``net_profit``
    net_profit_processing: Decimal
    units: int
    units_processing: int  # ADR-036: shundan Jarayonda (yakuniy emas)
    revenue_processing: Decimal


class ForecastOut(BaseModel):
    """M4 "Oy prognozi" (run-rate) shu oy bo'yicha: oy boshidan kechagacha (to'liq o'tgan kunlar) qiymat × oydagi kunlar /
    o'tgan to'liq kunlar. Oyning 1-kuni — ``null`` (hali to'liq kun yo'q)."""

    revenue: Decimal | None
    net_profit: Decimal | None
    units: Decimal | None
    # ADR-057 Q4: asosdagi Jarayondagi qism × yakunlanish ulushi (F16 R); ulush noma'lum bo'lsa — to'liq (false).
    estimated: bool = False


class DayOut(BaseModel):
    day: date
    revenue: Decimal
    net_profit: Decimal
    units: int
    revenue_done: Decimal  # ADR-036: tushumning Yakunlangan qismi (grafikda qatlam)
    revenue_processing: Decimal  # tushumning Jarayondagi qismi (grafikda ustidagi qatlam)
    net_profit_done: (
        Decimal  # ADR-037: sof foydaning yakunlangan va kutilayotgan qismlari (grafikda qatlamlar)
    )
    net_profit_processing: Decimal


class SkuBriefOut(BaseModel):
    sku_id: UUID
    shop_id: UUID | None
    title: str | None
    product_title: str | None
    units: int
    revenue: Decimal
    net_profit: Decimal
    margin: Decimal | None


Unit = Literal["money", "count", "ratio", "number"]


class KpiCardOut(BaseModel):
    """KPI sarhisob kartochkasi (ADR-043). ``change`` — pul va sonlarda nisbiy o'zgarish, ulushlarda (``ratio``) — farq
    punktda; oldingi davr 0 yoki yo'q — ``null``. ``good`` — qaysi yo'nalish yaxshi (rang), ``warn`` — sozlamadagi
    chegaradan oshgan. ``series`` — ``KpiSummaryOut.points`` bo'laklaridagi qiymatlar (trend chizig'i)."""

    key: str
    formula: str  # F-raqam (02-funksiyalar.md)
    unit: Unit
    value: Decimal | None
    previous: Decimal | None
    change: Decimal | None
    good: Literal["up", "down"] | None
    warn: bool = False
    series: list[Decimal | None]


class KpiGroupOut(BaseModel):
    key: str  # orders / uzum / returns / average
    cards: list[KpiCardOut]


class FlowStepOut(BaseModel):
    """F49 "Buyurtmadan sof foydagacha" qatori (ADR-053): summa va yalpi buyurtmalar summasidagi ulushi."""

    key: str
    formula: str  # F-raqam (02-funksiyalar.md)
    value: Decimal
    share: Decimal | None  # F44 = 0 — null


class KpiSummaryOut(BaseModel):
    bucket: Literal["day", "week", "month"]  # trend nuqtasi kattaligi (davr uzunligiga qarab)
    points: list[date]  # bo'laklar boshi
    groups: list[KpiGroupOut]
    flow: list[FlowStepOut]  # F49: bo'laklar yig'indisi = birinchi qator (F44)


class KpiOut(BaseModel):
    uncovered_share: Decimal  # 1 − F15 (marja kartochkasi yonida)
    frozen_money: Decimal  # F29 (Uzum FBO + FBS + brak + o'z omborim, lot narxida)
    in_transit_value: Decimal  # F29 "yo'lda" (Xitoyda buyurtma qilingan + yo'lda)
    average_days_to_sell: Decimal | None  # F29


class AttentionOut(BaseModel):
    """M4 "Diqqat talab qiladi" — sanoqlar; ro'yxatlar tegishli sahifalarda."""

    uncosted_lines: int
    uncosted_revenue: Decimal
    loss_skus: int
    stock_critical: (
        int  # F26 "Buyurtma berish": Kritik (hamma joydagi tovar to'liq muddatga yetmaydi)
    )
    stock_high: int
    stock_ship: int  # F26 "Uzumga yuborish" signali bor SKU'lar (ADR-057 Q2)
    recalculated: int
    receiving: int = 0  # TM7: Uzum qabulidagi qarorsiz farqlar + ochiq kamomadlar


class DashboardOut(BaseModel):
    meta: Meta
    statement: StatementOut
    expected: ExpectedOut  # F16 (ADR-037): kutilayotgan sof foyda tafsiloti va R
    rows: list[RowOut]
    periods: list[PeriodTotalOut]
    forecast: ForecastOut
    daily: list[DayOut]
    top: list[SkuBriefOut]
    bottom: list[SkuBriefOut]
    summary: KpiSummaryOut
    kpis: KpiOut
    attention: AttentionOut
    # F50 (B4.80): yillik tushum chegarasi (butun tashkilot, do'kon filtrisiz); profilda soliq to'lovchi turi yo'q — null.
    revenue_limit: RevenueLimitOut | None


def _days(period: Period) -> Callable[[CellKey], bool]:
    first, last = period.start, period.end
    return lambda k: first <= k.day <= last


def _total(key: str, period: Period, s: Statement) -> PeriodTotalOut:
    return PeriodTotalOut(
        key=key,
        period=PeriodOut.of(period),
        revenue=s.revenue.amount,
        net_profit=s.net_profit.amount,
        net_profit_done=s.net_profit_done.amount,
        net_profit_processing=s.net_profit_processing.amount,
        units=s.units,
        units_processing=s.units_processing,
        revenue_processing=s.revenue_processing.amount,
    )


def forecast_basis(today: date) -> Period | None:
    """M4 "Oy prognozi" asosi — oyning **to'liq o'tgan** kunlari (oy boshidan kechagacha). Bugungi kun hali tugamagan:
    uni to'liq kun deb sanash prognozni pasaytiradi (soat 10:00 da 1-sanada −60%, 10-sanada −6%). Oyning 1-kuni to'liq kun
    yo'q — ``None`` (prognoz ko'rsatilmaydi, raqam o'ylab topilmaydi)."""
    if today.day == 1:
        return None
    return Period(today.replace(day=1), today - timedelta(days=1))


type Bucket = Literal["day", "week", "month"]
DAY_POINTS = 62  # shundan uzun davr — haftalik, 366 kundan uzun — oylik nuqtalar


def _buckets(period: Period) -> tuple[Bucket, Callable[[date], date]]:
    """Trend nuqtalari: davr ≤ 62 kun — kunlik, ≤ 366 — 7 kunlik bo'laklar (davr boshidan), undan uzun — oylik."""
    if period.days <= DAY_POINTS:
        return "day", lambda d: d
    if period.days <= 366:
        return "week", lambda d: period.start + timedelta(days=(d - period.start).days // 7 * 7)
    return "month", lambda d: d.replace(day=1)


@dataclass(frozen=True, slots=True)
class _Slice:
    """Bitta kesim (davr yoki trend bo'lagi) uchun kartochka manbalari."""

    s: Statement
    flow: OrderFlow

    @property
    def ads(self) -> Money:
        return self.s.uzum_expenses.get(ExpenseCategory.ADVERTISING, Money.zero(UZS))


def _money(m: Money | None) -> Decimal | None:
    return None if m is None else m.amount


# Kartochkalar (ADR-043): guruh → (kalit, F-raqam, birlik, yaxshi yo'nalish, qiymat, ogohlantirish kaliti).
type Getter = Callable[[_Slice], Decimal | int | None]
CARDS: list[
    tuple[
        str,
        list[tuple[str, str, Unit, Literal["up", "down"] | None, Getter, orgsettings.Alert | None]],
    ]
] = [
    (
        "orders",
        [
            ("gross_revenue", "F44", "money", "up", lambda x: x.flow.gross_revenue.amount, None),
            ("revenue", "F3", "money", "up", lambda x: x.s.revenue.amount, None),
            ("units", "F3", "count", "up", lambda x: x.s.units, None),
            ("orders", "F45", "count", "up", lambda x: x.flow.orders, None),
            ("orders_net", "F45", "count", "up", lambda x: x.flow.orders_net, None),
            ("net_order_share", "F45", "ratio", "up", lambda x: x.flow.net_order_share, None),
        ],
    ),
    (
        "uzum",
        [
            ("uzum_costs", "F46", "money", "down", lambda x: x.s.uzum_costs.amount, None),
            ("uzum_costs_share", "F46", "ratio", "down", lambda x: x.s.uzum_costs_share, None),
            ("after_uzum", "F47", "money", "up", lambda x: x.s.after_uzum.amount, None),
            ("drr", "F19", "ratio", "down", lambda x: drr(x.ads, x.s.revenue), None),
            ("net_profit", "F12", "money", "up", lambda x: x.s.net_profit.amount, None),
            ("margin", "F13", "ratio", "up", lambda x: x.s.margin, None),
            ("roi", "F14", "ratio", "up", lambda x: x.s.roi, None),
        ],
    ),
    (
        "returns",
        [
            ("return_units", "F18", "count", "down", lambda x: x.flow.return_units, None),
            (
                "return_revenue",
                "F18",
                "money",
                "down",
                lambda x: x.flow.return_revenue.amount,
                None,
            ),
            ("return_share", "F18", "ratio", "down", lambda x: x.flow.return_share, "return_share"),
            (
                "return_revenue_share",
                "F18",
                "ratio",
                "down",
                lambda x: x.flow.return_revenue_share,
                None,
            ),
            ("cancel_units", "F17", "count", "down", lambda x: x.flow.cancel_units, None),
            (
                "cancel_revenue",
                "F17",
                "money",
                "down",
                lambda x: x.flow.cancel_revenue.amount,
                None,
            ),
            ("cancel_share", "F17", "ratio", "down", lambda x: x.flow.cancel_share, "cancel_share"),
            (
                "cancel_revenue_share",
                "F17",
                "ratio",
                "down",
                lambda x: x.flow.cancel_revenue_share,
                None,
            ),
        ],
    ),
    (
        "average",
        [
            ("average_check", "F48", "money", "up", lambda x: _money(x.flow.average_check), None),
            ("average_price", "F48", "money", None, lambda x: _money(x.flow.average_price), None),
            ("units_per_order", "F48", "number", "up", lambda x: x.flow.units_per_order, None),
        ],
    ),
]


def _dec(value: Decimal | int | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _summary(
    cur: _Slice,
    prev: _Slice,
    comparable: bool,
    bucket: Bucket,
    points: list[date],
    slices: dict[date, _Slice],
    cfg: orgsettings.OrgSettings,
) -> KpiSummaryOut:
    groups = []
    for group, cards in CARDS:
        out = []
        for key, code, unit, good, get, alert in cards:
            value, before = _dec(get(cur)), _dec(get(prev)) if comparable else None
            if unit == "ratio":
                change = share_change(value, before)
            else:
                change = None if value is None or before is None else relative_change(value, before)
            out.append(
                KpiCardOut(
                    key=key,
                    formula=code,
                    unit=unit,
                    value=value,
                    previous=before,
                    change=change,
                    good=good,
                    warn=alert is not None and cfg.over(alert, value),
                    series=[_dec(get(slices[point])) for point in points],
                )
            )
        groups.append(KpiGroupOut(key=group, cards=out))
    flow = [
        FlowStepOut(key=x.key, formula=x.formula, value=x.amount.amount, share=x.share)
        for x in order_to_profit(cur.s, cur.flow)
    ]
    return KpiSummaryOut(bucket=bucket, points=points, groups=groups, flow=flow)


@router.get("/orgs/{org_id}/dashboard", response_model=DashboardOut)
async def dashboard(ctx: Finance, f: Filter, _: Heavy) -> DashboardOut:
    conn, today = ctx.conn, f.today
    previous = f.period.previous()
    this_month = Period(today.replace(day=1), today)
    last_end = this_month.start - timedelta(days=1)
    last_month = Period(last_end.replace(day=1), last_end)
    book = await rc.load_book(conn, rc.span(previous, f.period, last_month, this_month), today)
    cur = book.scoped(f, f.period)

    periods = [
        ("today", Period(today, today)),
        ("yesterday", Period(today - timedelta(days=1), today - timedelta(days=1))),
        ("this_month", this_month),
        ("last_month", last_month),
    ]
    # Bir o'tishda: oldingi davr va davr chizig'i (har biri ``book.scoped(f, davr).statement()`` bilan bir xil).
    basis = forecast_basis(today)
    extra = [("forecast_basis", basis)] if basis is not None else []
    totals = book.scoped(f).statements(
        {key: _days(period) for key, period in [("previous", previous), *periods, *extra]}
    )
    by_day, s = cur.by_and_total(lambda k: k.day)
    p = totals["previous"]
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    empty = Cells(f.period, {}).statement()
    # Oy prognozi asosi: oy boshidan kechagacha (to'liq kunlar); oyning 1-kuni — to'liq kun 0, prognoz yo'q (``run_rate``).
    done_days = totals.get("forecast_basis", empty)
    elapsed = basis.days if basis is not None else 0
    daily = []
    for i in range(f.period.days):  # sotuvsiz kun ham grafikda (0)
        day = f.period.start + timedelta(days=i)
        ds = by_day.get(day, empty)
        daily.append(
            DayOut(
                day=day,
                revenue=ds.revenue.amount,
                net_profit=ds.net_profit.amount,
                units=ds.units,
                revenue_done=ds.revenue_done.amount,
                revenue_processing=ds.revenue_processing.amount,
                net_profit_done=ds.net_profit_done.amount,
                net_profit_processing=ds.net_profit_processing.amount,
            )
        )

    skus = {k: v for k, v in cur.by_sku().items() if k is not None and k != rc.UNLINKED}
    ranked = sorted(skus.items(), key=lambda kv: (-kv[1].net_profit.amount, kv[0]))
    top = [kv for kv in ranked[:TOP] if kv[1].net_profit.amount > 0]
    # "Zarar bilan sotilayotgan": davrda sotuvi bor (tannarxi ma'lum) va F12 < 0 — sotuvsiz SKU saqlash/reklamasi emas.
    bottom = sorted(
        (kv for kv in ranked if kv[1].sold_at_loss), key=lambda kv: kv[1].net_profit.amount
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

    # KPI sarhisob (ADR-043): joriy va oldingi davr bitta so'rovda (kunlar bo'yicha), trend — bo'laklar bo'yicha.
    both = rc.span(previous, f.period)
    flows = await rc.sale_sums(conn, f, by_day=True, period=both)
    counts = await rc.order_counts(conn, f, both)

    flow_days = {
        day: flows.get(day, OrderFlow())
        + OrderFlow(orders=counts.get(day, (0, 0))[0], orders_net=counts.get(day, (0, 0))[1])
        for day in set(flows) | set(counts)
    }

    def flow_of(days: Callable[[date], bool]) -> OrderFlow:
        return sum((v for day, v in flow_days.items() if days(day)), OrderFlow())

    bucket, bucket_of = _buckets(f.period)
    points = sorted({bucket_of(f.period.start + timedelta(days=i)) for i in range(f.period.days)})
    statements = cur.by(lambda k: bucket_of(k.day))
    bucket_flows: dict[date, OrderFlow] = {}
    for day, v in flow_days.items():
        if day in f.period:
            key = bucket_of(day)
            bucket_flows[key] = bucket_flows.get(key, OrderFlow()) + v
    prev_flow = flow_of(lambda d: d in previous)
    summary = _summary(
        _Slice(s, flow_of(lambda d: d in f.period)),
        _Slice(p, prev_flow),
        # Oldingi davrda faoliyat bo'lmasa (do'kon hali ulanmagan) foiz ma'nosiz — CompareRow kabi.
        comparable=not (p.revenue.is_zero() and prev_flow.gross_units == 0),
        bucket=bucket,
        points=points,
        slices={
            point: _Slice(statements.get(point, empty), bucket_flows.get(point, OrderFlow()))
            for point in points
        },
        cfg=await orgsettings.load(conn),
    )
    rates = await rc.realization(conn, f)
    stock = await load_stock(conn, sorted(f.shops, key=str) if f.shops else None, today)
    statuses = [x.status for x in stock.skus.values()]
    now = await db_now(conn)
    in_transit = total([stock.frozen["china"], stock.frozen["road"]], UZS)
    on_hand = total([v for k, v in stock.frozen.items() if k not in ("china", "road")], UZS)

    def forecast(value: Decimal | int) -> Decimal | None:
        return run_rate(value, elapsed, days_in_month)

    # ADR-057 Q4: prognoz asosida Jarayondagi qism yakunlanish ulushiga ko'paytiriladi (bir qismi bekor bo'ladi).
    part = done_days.processing
    r = rates.total
    basis_revenue = expected_value(
        done_days.revenue, part.revenue if part else Money.zero(UZS), r
    ).amount
    basis_profit = expected_value(
        done_days.net_profit, part.net_profit if part else Money.zero(UZS), r
    ).amount
    pending_units = done_days.units_processing
    basis_units = (
        Decimal(done_days.units)
        if r is None
        else Decimal(done_days.units - pending_units) + Decimal(pending_units) * r
    )

    limit = await rc.revenue_limit(conn, today)
    return DashboardOut(
        meta=await meta(conn, f, KINDS, previous),
        statement=StatementOut.of(s),
        expected=ExpectedOut.of(s, rates.total),
        rows=[RowOut.of(row) for row in compare(s, p, rates.total)],
        periods=[_total(key, period, totals[key]) for key, period in periods],
        forecast=ForecastOut(
            revenue=forecast(basis_revenue),
            net_profit=forecast(basis_profit),
            units=forecast(basis_units),
            estimated=r is not None and part is not None,
        ),
        daily=daily,
        top=[brief(k, v) for k, v in top],
        bottom=[brief(k, v) for k, v in bottom],
        summary=summary,
        kpis=KpiOut(
            uncovered_share=s.uncovered_share,
            frozen_money=on_hand.amount,
            in_transit_value=in_transit.amount,
            average_days_to_sell=stock.average_days,
        ),
        attention=AttentionOut(
            uncosted_lines=s.uncovered_lines,
            uncosted_revenue=s.uncovered_revenue.amount,
            loss_skus=sum(1 for st in skus.values() if st.sold_at_loss),
            stock_critical=statuses.count(StockStatus.CRITICAL),
            stock_high=statuses.count(StockStatus.HIGH),
            stock_ship=sum(1 for x in stock.skus.values() if x.ship is not None),
            recalculated=await rc.recalculated(conn, f, now),
            receiving=await receiving_attention(conn),
        ),
        revenue_limit=None if limit is None else RevenueLimitOut.of(limit),
    )

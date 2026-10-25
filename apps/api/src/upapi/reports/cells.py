"""P&L kataklari bazadan (ADR-026, 03 §5 "Hosila jadvallar"): ``daily_sku_metrics`` + xarajatlar + soliq profili →
``upcore.pnl.build_cells``. Bosh sahifa, P&L va SKU jadvali shu bitta funksiyadan (M5 qabul mezoni: P&L sof foydasi
= bosh sahifa = SKU jadvali yig'indisi).

- Sotuvlar — ``daily_sku_metrics`` (B2.8 kunlik yig'indilar, ``sale_totals`` natijasi); katak — (kun, do'kon, SKU).
  SKU'ga bog'lanmagan sotuvlar — ``UNLINKED`` katagi (taqsimlanmagan xarajatlar ``None`` katagidan alohida).
- Uzum xarajatlari (F9) — ``mp_expenses``, P&L'ga kiradiganlari (``excluded`` bo'sh, toifa ``in_pnl``), ishora bilan;
  sotuv qatoriga bog'langani (``sale_item_id``) — o'sha sotuv SKU'siga, qolgani — do'kon darajasida.
- O'z xarajatlari (F10) — ``manual_expenses``: tovarga bog'langan va tovarning bitta SKU'si bo'lsa — o'sha SKU'ga,
  aks holda do'kon (yoki tashkilot) darajasida. Takrorlanish va tovar bo'yicha taqsimot sozlamasi — B4 (M8).
- Soliq (F11) — ``tax_profiles`` sana bo'yicha (``upcore.tax.daily_rule``).

Kataklar butun tashkilot uchun quriladi, do'kon filtri keyin qo'llanadi: tashkilot xarajati tanlangan do'konlarga
emas, hamma do'konlarga tushum ulushida taqsimlanadi (filtr bo'yicha natija = do'konlar kesimidagi qatorlar).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import (
    ExpectedProfit,
    ManualExpense,
    Period,
    SaleLine,
    StatusGroup,
    business_date,
    expected_profit,
    realization_rate_units,
    statuses,
)
from upcore.money import Currency, Money
from upcore.pnl import CellKey, Cells, CellSales, ExpenseItem, OwnExpense, TaxBase, build_cells
from upcore.tax import TaxProfile, TaxRegime, daily_rule

from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.common import Filters

UZS = Currency.UZS
UNLINKED = "unlinked"  # SKU'ga bog'lanmagan sotuvlar katagi (``sku_id`` NULL)
REALIZATION_DAYS = 90  # F16: R — do'konning oxirgi 90 kuni
RECALC_DAYS = 7  # 03 §7: "qayta hisoblandi" belgisi oxirgi 7 kun ko'rinadi


def sku_key(sku_id: UUID | None) -> str:
    return UNLINKED if sku_id is None else str(sku_id)


@dataclass(frozen=True, slots=True)
class Book:
    """Davr kataklari (butun tashkilot)."""

    cells: Cells

    def scoped(self, f: Filters, period: Period | None = None) -> Cells:
        """Tanlangan do'konlar (va ichki davr) kataklari."""
        if f.shops is None and (period is None or period == self.cells.period):
            return self.cells
        where = None if f.shops is None else (lambda k: f.shop_ok(k.shop))
        return self.cells.within(period or self.cells.period, where)


@dataclass(slots=True)
class SaleSums:
    """Yakunlangan, bekor va qaytgan dona (F17, F18) — ``daily_sku_metrics`` yig'indisi."""

    units: int = 0
    canceled: int = 0
    returns: int = 0


async def sale_sums(
    conn: AsyncConnection,
    f: Filters,
    *,
    by_sku: bool = False,
    sku: UUID | None = None,
    unlinked: bool = False,
) -> dict[str | None, SaleSums]:
    """Filtr bo'yicha dona yig'indilari; ``by_sku`` — SKU kaliti bo'yicha (``UNLINKED`` — bog'lanmagan), aks holda
    bitta ``None`` kaliti."""
    d = m.daily_sku_metrics
    sums = [func.coalesce(func.sum(c), 0) for c in (d.c.units, d.c.canceled, d.c.returns)]
    query = select(cast(d.c.sku_id, Text) if by_sku else literal(None), *sums).where(
        d.c.day >= f.period.start, d.c.day <= f.period.end
    )
    if f.shops:
        query = query.where(d.c.shop_id.in_(f.shops))
    if sku is not None:
        query = query.where(d.c.sku_id == sku)
    if unlinked:
        query = query.where(d.c.sku_id.is_(None))
    if by_sku:
        query = query.group_by(d.c.sku_id)
    out = {}
    for key, units, canceled, returns in await conn.execute(query):
        name = (UNLINKED if key is None else key) if by_sku else None
        out[name] = SaleSums(int(units), int(canceled), int(returns))
    return out


def _uzs(value: Any) -> Money:
    return Money(value, UZS)


async def _totals(conn: AsyncConnection, period: Period) -> list[tuple[CellKey, CellSales]]:
    d = m.daily_sku_metrics
    rows = await conn.execute(
        select(
            d.c.day,
            cast(d.c.shop_id, Text),  # matn — katak kaliti (Python'da UUID → str sekin)
            cast(d.c.sku_id, Text),
            d.c.revenue,
            d.c.commission,
            d.c.logistics,
            d.c.cogs,
            d.c.revenue_costed,
            d.c.payout_costed,
            d.c.units,
            d.c.units_costed,
            d.c.lines,
            d.c.lines_uncosted,
        ).where(d.c.day >= period.start, d.c.day <= period.end)
    )
    return [
        (CellKey(r[0], r[1], UNLINKED if r[2] is None else r[2]), CellSales(*r[3:])) for r in rows
    ]


def in_pnl(category: str) -> bool:
    try:
        return ExpenseCategory(category).in_pnl
    except ValueError:
        return False


async def _expenses(conn: AsyncConnection, period: Period) -> list[ExpenseItem]:
    e, s = m.mp_expenses, m.sale_items
    rows = await conn.execute(
        select(
            e.c.created_on,
            e.c.shop_id,
            e.c.category,
            e.c.type,
            e.c.amount,
            e.c.sale_item_id,
            s.c.sku_id,
        )
        .outerjoin(s, s.c.id == e.c.sale_item_id)
        .where(
            e.c.created_on >= day_start(period.start),
            e.c.created_on < day_start(period.end + timedelta(days=1)),
            e.c.excluded.is_(None),
        )
    )
    return [
        ExpenseItem(
            day=business_date(r.created_on),
            shop=str(r.shop_id),
            category=ExpenseCategory(r.category),
            amount=signed_amount(_uzs(r.amount), r.type),
            sku=None if r.sale_item_id is None else sku_key(r.sku_id),
        )
        for r in rows
        if in_pnl(r.category)
    ]


async def _own(conn: AsyncConnection, period: Period) -> list[OwnExpense]:
    x, c, k = m.manual_expenses, m.expense_categories, m.mp_skus
    rows = list(
        await conn.execute(
            select(x, c.c.name.label("category"))
            .join(c, c.c.id == x.c.category_id)
            .where(x.c.start_on <= period.end, x.c.end_on >= period.start)
        )
    )
    items = {r.item_id for r in rows if r.item_id is not None}
    skus: dict[UUID, list[tuple[UUID, UUID]]] = {}
    if items:
        for r in await conn.execute(
            select(k.c.item_id, k.c.shop_id, k.c.id).where(k.c.item_id.in_(items))
        ):
            skus.setdefault(r.item_id, []).append((r.shop_id, r.id))
    out = []
    for r in rows:
        shop = None if r.shop_id is None else str(r.shop_id)
        sku = None
        linked = skus.get(r.item_id, []) if r.item_id is not None else []
        if len(linked) == 1:
            shop, sku = str(linked[0][0]), str(linked[0][1])
        out.append(
            OwnExpense(ManualExpense(_uzs(r.amount), r.start_on, r.end_on), r.category, shop, sku)
        )
    return out


async def tax_profiles(conn: AsyncConnection) -> list[TaxProfile]:
    t = m.tax_profiles
    return [
        TaxProfile(
            valid_from=r.valid_from,
            regime=TaxRegime(r.regime),
            rate_pct=r.rate_pct,
            base=TaxBase(r.base),
            vat_pct=r.vat_pct,
            profit_pct=r.profit_pct,
        )
        for r in await conn.execute(select(t).order_by(t.c.valid_from))
    ]


async def load_book(conn: AsyncConnection, period: Period) -> Book:
    """Davr (masalan, joriy + oldingi davr birga) kataklari butun tashkilot bo'yicha."""
    totals = await _totals(conn, period)
    cells = build_cells(
        period,
        [],
        await _expenses(conn, period),
        await _own(conn, period),
        tax=daily_rule(await tax_profiles(conn)),
        totals=totals,
    )
    return Book(cells)


def span(*periods: Period) -> Period:
    return Period(min(p.start for p in periods), max(p.end for p in periods))


# --- F16 va "qayta hisoblandi" ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pending:
    total: ExpectedProfit
    shops: dict[UUID, ExpectedProfit]


async def pending(conn: AsyncConnection, f: Filters) -> Pending:
    """F16: davrdagi Jarayondagi qatorlar × R; R har do'kon uchun alohida (oxirgi 90 kun, ``daily_sku_metrics``)."""
    s, c, d = m.sale_items, m.sale_costs, m.daily_sku_metrics
    query = (
        select(
            s.c.shop_id,
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
        .where(
            s.c.ordered_at >= day_start(f.period.start),
            s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
            func.upper(func.trim(s.c.status)).in_(statuses(StatusGroup.PROCESSING)),
        )
    )
    if f.shops:
        query = query.where(s.c.shop_id.in_(f.shops))
    lines: dict[UUID, list[SaleLine]] = {}
    for r in await conn.execute(query):
        lines.setdefault(r.shop_id, []).append(sale_line(r))
    since = f.today - timedelta(days=REALIZATION_DAYS - 1)
    window = {
        r.shop_id: realization_rate_units(int(r.done), int(r.canceled))
        for r in await conn.execute(
            select(
                d.c.shop_id,
                func.sum(d.c.units).label("done"),
                func.sum(d.c.canceled).label("canceled"),
            )
            .where(d.c.shop_id.in_(lines), d.c.day >= since, d.c.day <= f.today)
            .group_by(d.c.shop_id)
        )
    }
    shops = {shop: expected_profit(items, window.get(shop)) for shop, items in lines.items()}
    return Pending(_combine(list(shops.values())), shops)


def _combine(items: list[ExpectedProfit]) -> ExpectedProfit:
    """Do'konlar F16 natijalari yig'indisi; biror do'konda R noma'lum bo'lsa umumiy summa ham noma'lum."""
    zero = Money.zero(UZS)
    raw = sum((e.raw for e in items), zero)
    known = all(e.amount is not None for e in items)
    rates = {e.rate for e in items}
    return ExpectedProfit(
        amount=sum((e.amount or zero for e in items), zero) if known else None,
        rate=next(iter(rates)) if len(rates) == 1 else None,
        raw=raw,
        uncovered_lines=sum(e.uncovered_lines for e in items),
    )


def sale_line(r: Any) -> SaleLine:
    """``sale_items`` (+ ``sale_costs.cogs``) qatori → ``SaleLine`` (``upapi.calc.daily`` dagi kabi)."""
    unit = None
    if r.cogs is not None:
        unit = r.cogs / r.amount if r.amount else Decimal(0)
    return SaleLine(
        sku=sku_key(r.sku_id),
        order_date=business_date(r.ordered_at),
        status=r.status,
        sell_price=r.sell_price,
        amount=r.amount,
        commission=r.commission,
        logistics=r.logistics_fee,
        amount_returns=r.amount_returns,
        unit_cost=unit,
        shop=str(r.shop_id),
        estimated=bool(r.flags),
    )


async def recalculated(conn: AsyncConnection, f: Filters, now: datetime) -> int:
    """03 §7: davrdagi sotuvlardan oxirgi 7 kunda tannarxi qayta hisoblanganlari soni."""
    s, c = m.sale_items, m.sale_costs
    query = (
        select(func.count())
        .select_from(c.join(s, s.c.id == c.c.sale_item_id))
        .where(
            c.c.changed_at >= now - timedelta(days=RECALC_DAYS),
            s.c.ordered_at >= day_start(f.period.start),
            s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
        )
    )
    if f.shops:
        query = query.where(s.c.shop_id.in_(f.shops))
    return int(await conn.scalar(query) or 0)


def month_start(day: date) -> date:
    return day.replace(day=1)

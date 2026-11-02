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
- Kutilayotgan logistika (F5, ADR-037) — Uzum hali yozmagan Jarayondagi donalar × F40 tarifi (``reports.products``),
  hisobot kunidagi tarif bilan; naqd va kutilayotgan sof foyda (F16) — ``upcore.pnl`` kataklarida.

Kataklar butun tashkilot uchun quriladi, do'kon filtri keyin qo'llanadi: tashkilot xarajati tanlangan do'konlarga
emas, hamma do'konlarga tushum ulushida taqsimlanadi (filtr bo'yicha natija = do'konlar kesimidagi qatorlar).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import (
    ManualExpense,
    Period,
    SaleLine,
    business_date,
    realization_rate_units,
)
from upcore.money import Currency, Money
from upcore.pnl import CellKey, Cells, CellSales, ExpenseItem, OwnExpense, TaxBase, build_cells
from upcore.tax import TaxProfile, TaxRegime, daily_rule

from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.common import Filters
from upapi.reports.products import load_fees

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
    """Yakunlangan, bekor va qaytgan dona (F17, F18) — ``daily_sku_metrics`` yig'indisi (Yakunlangan =
    ``units − units_processing``, ADR-036)."""

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
    done = d.c.units - d.c.units_processing
    sums = [func.coalesce(func.sum(c), 0) for c in (done, d.c.canceled, d.c.returns)]
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


# ``daily_sku_metrics`` ustuni → ``CellSales`` maydoni (tartib — ``CellSales`` dagi kabi).
_SALES = (
    ("revenue", "revenue"),
    ("commission", "commission"),
    ("logistics", "logistics"),
    ("cogs", "cogs"),
    ("revenue_costed", "revenue_costed"),
    ("payout_costed", "payout_costed"),
    ("units", "units"),
    ("units_costed", "units_costed"),
    ("lines", "lines"),
    ("uncovered_lines", "lines_uncosted"),
    ("units_processing", "units_processing"),
    ("revenue_processing", "revenue_processing"),
    ("commission_processing", "commission_processing"),
    ("logistics_processing", "logistics_processing"),
    ("cogs_processing", "cogs_processing"),
    ("revenue_costed_processing", "revenue_costed_processing"),
    ("payout_costed_processing", "payout_costed_processing"),
    ("units_costed_processing", "units_costed_processing"),
    ("lines_processing", "lines_processing"),
    ("uncovered_lines_processing", "lines_uncosted_processing"),
    ("units_logistics_due", "units_logistics_due"),
    ("units_logistics_due_costed", "units_logistics_due_costed"),
    ("lines_logistics_due", "lines_logistics_due"),
)


async def _totals(conn: AsyncConnection, period: Period) -> list[tuple[CellKey, CellSales]]:
    d = m.daily_sku_metrics
    rows = await conn.execute(
        select(
            d.c.day,
            cast(d.c.shop_id, Text),  # matn — katak kaliti (Python'da UUID → str sekin)
            cast(d.c.sku_id, Text),
            *(d.c[column] for _, column in _SALES),
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


async def expected_fees(
    conn: AsyncConnection, today: date, keys: list[tuple[str, str]]
) -> Callable[[str, str], Money | None]:
    """F40 tariflari (``today`` kungi) Uzum logistikasini hali yozmagan Jarayondagi donalar kataklari (do'kon, SKU
    kaliti) uchun — kutilayotgan logistika taxmini (F5, ADR-037)."""
    skus = {UUID(sku): UUID(shop) for shop, sku in keys if sku != UNLINKED}
    shops = {UUID(shop) for shop, sku in keys if sku == UNLINKED}
    if not skus and not shops:
        return lambda _shop, _sku: None
    return (await load_fees(conn, today, skus, shops)).unit


async def load_book(conn: AsyncConnection, period: Period, today: date) -> Book:
    """Davr (masalan, joriy + oldingi davr birga) kataklari butun tashkilot bo'yicha. ``today`` — kutilayotgan
    logistika taxmini tarifi kuni (F40, ADR-037)."""
    totals = await _totals(conn, period)
    due = sorted({(k.shop, k.sku or UNLINKED) for k, t in totals if t.lines_logistics_due})
    cells = build_cells(
        period,
        [],
        await _expenses(conn, period),
        await _own(conn, period),
        tax=daily_rule(await tax_profiles(conn)),
        totals=totals,
        logistics_fee=await expected_fees(conn, today, due),
    )
    return Book(cells)


def span(*periods: Period) -> Period:
    return Period(min(p.start for p in periods), max(p.end for p in periods))


# --- F16 (R) va "qayta hisoblandi" ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Realization:
    """F16 R — fakt (ADR-036, ADR-037): oxirgi 90 kunda yakuniy holatga yetgan donalar ichida Yakunlangan ulushi;
    ``total`` — tanlangan do'konlar birga, ``shops`` — har do'kon. Kutilayotgan sof foydaga ko'paytirilmaydi."""

    total: Decimal | None
    shops: dict[UUID, Decimal | None]


async def realization(conn: AsyncConnection, f: Filters) -> Realization:
    """F16 R: tanlangan do'konlar (filtr bo'lmasa — hammasi) bo'yicha oxirgi 90 kun (``daily_sku_metrics``)."""
    d = m.daily_sku_metrics
    since = f.today - timedelta(days=REALIZATION_DAYS - 1)
    query = (
        select(
            d.c.shop_id,
            func.sum(d.c.units - d.c.units_processing).label("done"),
            func.sum(d.c.canceled).label("canceled"),
        )
        .where(d.c.day >= since, d.c.day <= f.today)
        .group_by(d.c.shop_id)
    )
    if f.shops:
        query = query.where(d.c.shop_id.in_(f.shops))
    rows = [(r.shop_id, int(r.done), int(r.canceled)) for r in await conn.execute(query)]
    return Realization(
        total=realization_rate_units(sum(r[1] for r in rows), sum(r[2] for r in rows)),
        shops={shop: realization_rate_units(done, canceled) for shop, done, canceled in rows},
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
        issued=r.issued_at is not None,
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

"""P&L kataklari bazadan (ADR-026, 03 §5 "Hosila jadvallar"): ``daily_sku_metrics`` + xarajatlar + soliq profili →
``upcore.pnl.build_cells``. Bosh sahifa, P&L va SKU jadvali shu bitta funksiyadan (M5 qabul mezoni: P&L sof foydasi
= bosh sahifa = SKU jadvali yig'indisi).

- Sotuvlar — ``daily_sku_metrics`` (B2.8 kunlik yig'indilar, ``sale_totals`` natijasi); katak — (kun, do'kon, SKU).
  SKU'ga bog'lanmagan sotuvlar — ``UNLINKED`` katagi (taqsimlanmagan xarajatlar ``None`` katagidan alohida).
- Uzum xarajatlari (F9) — ``mp_expenses``, P&L'ga kiradiganlari (``excluded`` bo'sh, toifa ``in_pnl``), ishora bilan
  (ADR-039, :func:`expense_day`): sotuv qatoriga bog'langani (buyurtmaga bog'liq reklama) — o'sha sotuvning buyurtma
  kuni, SKU'si va qismiga (Jarayonda — kutilayotgan, aks holda yakunlangan); saqlash — shu kuni SKU'larga Uzum
  omboridagi qoldiq × saqlash narxi og'irligida (F43, ``sku_daily``; snapshot yo'q kun — tushum ulushida); qolgani —
  yechilgan kuni do'kon darajasida (tushum ulushida).
- Kutilayotgan reklama (F42) — hali topshirilmagan Jarayondagi sotuvlar tushumi × SKU'ning (bo'lmasa do'konning)
  oxirgi 30 kundagi buyurtmaga bog'liq reklama ulushi, "≈" (taxminiy).
- O'z xarajatlari (F10) — ``manual_expenses``: tovarga bog'langan — tovarning SKU'lariga (bitta bo'lsa o'shanga, bir
  nechta bo'lsa ular orasida tushum ulushida, ADR-039), aks holda do'kon (yoki tashkilot) darajasida.
- Soliq (F11) — ``tax_profiles`` sana bo'yicha (``upcore.tax.daily_rule``).
- Kutilayotgan logistika (F5, ADR-037) — Uzum hali yozmagan Jarayondagi donalar × F40 tarifi (``reports.products``),
  hisobot kunidagi tarif bilan; yakunlangan va kutilayotgan sof foyda (F16) — ``upcore.pnl`` kataklarida.

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

from sqlalchemy import Text, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import (
    ManualExpense,
    Period,
    SaleLine,
    StatusGroup,
    ad_rate,
    business_date,
    expected_ads,
    realization_rate_units,
    status_group,
    storage_weights,
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
AD_RATE_DAYS = 30  # F42: buyurtmaga bog'liq reklama ulushi — oxirgi 30 kunda topshirilgan sotuvlar
SNAPSHOT_LOOKBACK = (
    7  # F43: saqlash kuni uchun qoldiq snapshoti — shu kun yoki oldingi 7 kun ichidagi oxirgisi
)
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


def by_sale(e: Any) -> Any:
    """ADR-039: xarajat P&L'da sotuv sanasi bo'yicha (sotuv qatoriga bog'langan va P&L'ga kiradigan — buyurtmaga bog'liq
    reklama); logistika qatorlari (P&L'dan tashqari) yechilgan kunida qoladi."""
    return and_(e.c.sale_item_id.is_not(None), e.c.excluded.is_(None))


def expense_day(e: Any, s: Any) -> Any:
    """P&L kuni (vaqt): sotuvga bog'langan xarajat — sotuvning buyurtma vaqti, qolgani — Uzum yechgan vaqt
    (``/expenses`` ham shu qoida bilan — drill-down yig'indisi P&L qatoriga teng)."""
    return case((by_sale(e), s.c.ordered_at), else_=e.c.created_on)


async def _expenses(conn: AsyncConnection, period: Period) -> list[ExpenseItem]:
    e, s = m.mp_expenses, m.sale_items
    when = expense_day(e, s)
    rows = list(
        await conn.execute(
            select(
                e.c.created_on,
                e.c.shop_id,
                e.c.category,
                e.c.type,
                e.c.amount,
                e.c.sale_item_id,
                s.c.sku_id,
                s.c.ordered_at,
                s.c.status,
            )
            .outerjoin(s, s.c.id == e.c.sale_item_id)
            .where(
                when >= day_start(period.start),
                when < day_start(period.end + timedelta(days=1)),
                e.c.excluded.is_(None),
            )
        )
    )
    weights = await _storage_weights(
        conn,
        {
            (r.shop_id, business_date(r.created_on))
            for r in rows
            if r.sale_item_id is None and r.category == ExpenseCategory.STORAGE.value
        },
    )
    out = []
    for r in rows:
        if not in_pnl(r.category):
            continue
        amount = signed_amount(_uzs(r.amount), r.type)
        category = ExpenseCategory(r.category)
        if r.sale_item_id is not None:
            out.append(
                ExpenseItem(
                    day=business_date(r.ordered_at),
                    shop=str(r.shop_id),
                    category=category,
                    amount=amount,
                    sku=sku_key(r.sku_id),
                    processing=status_group(r.status) is StatusGroup.PROCESSING,
                )
            )
            continue
        day = business_date(r.created_on)
        out.append(
            ExpenseItem(
                day=day,
                shop=str(r.shop_id),
                category=category,
                amount=amount,
                weights=weights.get((r.shop_id, day))
                if category is ExpenseCategory.STORAGE
                else None,
            )
        )
    return out


async def _storage_weights(
    conn: AsyncConnection, wanted: set[tuple[UUID, date]]
) -> dict[tuple[UUID, date], dict[str, Decimal]]:
    """F43 og'irliklari (do'kon, kun) uchun: shu kun yoki oldingi ``SNAPSHOT_LOOKBACK`` kun ichidagi oxirgi qoldiq
    snapshoti (``sku_daily.qty_active`` — Uzum omboridagi sotuvdagi dona) × SKU saqlash narxi. Snapshot yo'q — kiritilmaydi
    (xarajat tushum ulushida bo'linadi)."""
    if not wanted:
        return {}
    shops = {shop for shop, _ in wanted}
    first = min(day for _, day in wanted) - timedelta(days=SNAPSHOT_LOOKBACK)
    last = max(day for _, day in wanted)
    k, sd = m.mp_skus, m.sku_daily
    prices = {
        r.id: r.storage_price
        for r in await conn.execute(select(k.c.id, k.c.storage_price).where(k.c.shop_id.in_(shops)))
    }
    snaps: dict[UUID, dict[date, dict[str, int]]] = {}
    for r in await conn.execute(
        select(k.c.shop_id, sd.c.sku_id, sd.c.day, sd.c.qty_active)
        .join(k, k.c.id == sd.c.sku_id)
        .where(k.c.shop_id.in_(shops), sd.c.day >= first, sd.c.day <= last)
    ):
        snaps.setdefault(r.shop_id, {}).setdefault(r.day, {})[str(r.sku_id)] = int(
            r.qty_active or 0
        )
    out = {}
    for shop, day in wanted:
        days = snaps.get(shop, {})
        found = next(
            (
                days[d]
                for i in range(SNAPSHOT_LOOKBACK + 1)
                if (d := day - timedelta(days=i)) in days
            ),
            None,
        )
        if found:
            w = storage_weights(found, {sku: prices.get(UUID(sku)) for sku in found})
            if w:
                out[shop, day] = w
    return out


async def _expected_ads(conn: AsyncConnection, period: Period, today: date) -> list[ExpenseItem]:
    """F42 (ADR-039): hali topshirilmagan Jarayondagi sotuvlarga kutilayotgan reklama — SKU ulushi (oxirgi
    ``AD_RATE_DAYS`` kunda topshirilgan sotuvlar), SKU'da topshirilgan sotuv bo'lmasa do'kon ulushi; ulush 0 — taxmin yo'q."""
    s, e = m.sale_items, m.mp_expenses
    pending: dict[tuple[date, UUID, str], Decimal] = {}
    for r in await conn.execute(
        select(s.c.shop_id, s.c.sku_id, s.c.ordered_at, s.c.sell_price, s.c.amount).where(
            func.upper(func.trim(s.c.status)) == "PROCESSING",
            s.c.issued_at.is_(None),
            s.c.amount > 0,
            s.c.ordered_at >= day_start(period.start),
            s.c.ordered_at < day_start(period.end + timedelta(days=1)),
        )
    ):
        key = (business_date(r.ordered_at), r.shop_id, sku_key(r.sku_id))
        pending[key] = pending.get(key, Decimal(0)) + r.sell_price * r.amount
    if not pending:
        return []
    ads = (
        select(
            e.c.sale_item_id,
            func.sum(case((e.c.type == "OUTCOME", e.c.amount), else_=-e.c.amount)).label("ads"),
        )
        .where(
            e.c.category == ExpenseCategory.ADVERTISING.value,
            e.c.excluded.is_(None),
            e.c.sale_item_id.is_not(None),
        )
        .group_by(e.c.sale_item_id)
        .subquery()
    )
    sku_sums: dict[tuple[UUID, str], tuple[Decimal, Decimal]] = {}
    shop_sums: dict[UUID, tuple[Decimal, Decimal]] = {}
    for row in await conn.execute(
        select(
            s.c.shop_id,
            s.c.sku_id,
            func.coalesce(func.sum(ads.c.ads), 0),
            func.coalesce(func.sum(s.c.sell_price * s.c.amount), 0),
        )
        .outerjoin(ads, ads.c.sale_item_id == s.c.id)
        .where(
            s.c.issued_at >= day_start(today - timedelta(days=AD_RATE_DAYS - 1)),
            s.c.issued_at < day_start(today + timedelta(days=1)),
            s.c.shop_id.in_({shop for _, shop, _ in pending}),
        )
        .group_by(s.c.shop_id, s.c.sku_id)
    ):
        spent, revenue = Decimal(row[2]), Decimal(row[3])
        sku_sums[row.shop_id, sku_key(row.sku_id)] = (spent, revenue)
        a, b = shop_sums.get(row.shop_id, (Decimal(0), Decimal(0)))
        shop_sums[row.shop_id] = (a + spent, b + revenue)
    out = []
    for (day, shop, sku), revenue in sorted(
        pending.items(), key=lambda x: (x[0][0], str(x[0][1]), x[0][2])
    ):
        spent, base = sku_sums.get((shop, sku), (Decimal(0), Decimal(0)))
        if base <= 0:
            spent, base = shop_sums.get(shop, (Decimal(0), Decimal(0)))
        rate = ad_rate(spent, base)
        if not rate:
            continue
        estimate = expected_ads(rate, revenue)
        if estimate.amount > 0:
            out.append(
                ExpenseItem(
                    day=day,
                    shop=str(shop),
                    category=ExpenseCategory.ADVERTISING,
                    amount=estimate,
                    sku=sku,
                    processing=True,
                    estimated=True,
                )
            )
    return out


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
            OwnExpense(
                ManualExpense(_uzs(r.amount), r.start_on, r.end_on),
                r.category,
                shop,
                sku,
                skus=tuple((str(a), str(b)) for a, b in linked) if len(linked) > 1 else (),
            )
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
        [*await _expenses(conn, period), *await _expected_ads(conn, period, today)],
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

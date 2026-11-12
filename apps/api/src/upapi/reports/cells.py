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
- Soliq (F11) — ``tax_profiles`` sana bo'yicha (``upcore.tax.daily_rules``; qat'iy qatorlar — ``fixed_expenses``, ADR-058).
- Kutilayotgan logistika (F5, ADR-037) — Uzum hali yozmagan Jarayondagi donalar × F40 tarifi (``reports.products``),
  hisobot kunidagi tarif bilan; yakunlangan va kutilayotgan sof foyda (F16) — ``upcore.pnl`` kataklarida.

Kataklar butun tashkilot uchun quriladi, do'kon filtri keyin qo'llanadi: tashkilot xarajati tanlangan do'konlarga
emas, hamma do'konlarga tushum ulushida taqsimlanadi (filtr bo'yicha natija = do'konlar kesimidagi qatorlar).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Text, and_, case, cast, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import (
    ManualExpense,
    OrderFlow,
    Period,
    SaleLine,
    StatusGroup,
    ad_rate,
    business_date,
    expected_ads,
    realization_rate_units,
    status_group,
    statuses,
    storage_weights,
)
from upcore.money import Currency, Money
from upcore.pnl import CellKey, Cells, CellSales, ExpenseItem, OwnExpense, TaxBase, build_cells
from upcore.tariffs import SEED_STORAGE_RULES, paid_storage, storage_rule
from upcore.tax import (
    BHM,
    SEED_AMOUNTS,
    AmountValue,
    FixedPeriod,
    LineKind,
    TaxLine,
    TaxProfile,
    TaxRegime,
    amount_on,
    daily_rules,
    fixed_expenses,
)

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
    """Davr kataklari (butun tashkilot). ``tax_missing_bhm`` — BHM ma'lumotnomada yo'q kunlar bor: BHM'ga bog'liq
    qat'iy soliq o'sha kunlarga hisoblanmadi (ADR-058)."""

    cells: Cells
    tax_missing_bhm: bool = False

    def scoped(self, f: Filters, period: Period | None = None) -> Cells:
        """Tanlangan do'konlar (va ichki davr) kataklari."""
        if f.shops is None and (period is None or period == self.cells.period):
            return self.cells
        where = None if f.shops is None else (lambda k: f.shop_ok(k.shop))
        return self.cells.within(period or self.cells.period, where)


SaleSums = (
    OrderFlow  # F17, F18, F44 yig'indilari (ADR-043); buyurtma sanoqlari (F45) — ``order_counts``
)

# ``daily_sku_metrics`` ustunlari = ``OrderFlow`` maydonlari (F3 dona va summa, bekor/qaytarish bo'linishi).
_FLOW = (
    "units",
    "revenue",
    "canceled",
    "canceled_revenue",
    "canceled_issued",
    "canceled_issued_revenue",
    "returns",
    "returns_revenue",
)


def flow_of(v: Sequence[Any]) -> OrderFlow:
    """``_FLOW`` tartibidagi SQL yig'indilari → ``OrderFlow``."""
    return OrderFlow(
        units=int(v[0]),
        revenue=Money(v[1], UZS),
        canceled=int(v[2]),
        canceled_revenue=Money(v[3], UZS),
        canceled_issued=int(v[4]),
        canceled_issued_revenue=Money(v[5], UZS),
        returns=int(v[6]),
        returns_revenue=Money(v[7], UZS),
    )


async def sale_sums(
    conn: AsyncConnection,
    f: Filters,
    *,
    by_sku: bool = False,
    by_day: bool = False,
    sku: UUID | None = None,
    unlinked: bool = False,
    period: Period | None = None,
) -> dict[Any, OrderFlow]:
    """Filtr bo'yicha sotuv, bekor va qaytarish yig'indilari (``daily_sku_metrics``); ``by_sku`` — SKU kaliti bo'yicha
    (``UNLINKED`` — bog'lanmagan), ``by_day`` — kun bo'yicha, aks holda bitta ``None`` kaliti. Buyurtma sanoqlari bu
    yerda yo'q (0) — ``order_counts``."""
    d = m.daily_sku_metrics
    window = period or f.period
    sums = [func.coalesce(func.sum(d.c[column]), 0) for column in _FLOW]
    key: Any = cast(d.c.sku_id, Text) if by_sku else d.c.day if by_day else literal(None)
    query = select(key, *sums).where(d.c.day >= window.start, d.c.day <= window.end)
    if f.shops:
        query = query.where(d.c.shop_id.in_(f.shops))
    if sku is not None:
        query = query.where(d.c.sku_id == sku)
    if unlinked:
        query = query.where(d.c.sku_id.is_(None))
    if by_sku:
        query = query.group_by(d.c.sku_id)
    elif by_day:
        query = query.group_by(d.c.day)
    out: dict[Any, OrderFlow] = {}
    for row in await conn.execute(query):
        name = (UNLINKED if row[0] is None else row[0]) if by_sku else row[0]
        out[name] = flow_of(row[1:])
    return out


@dataclass(frozen=True, slots=True)
class Causes:
    """Sabablar bo'yicha dona (ADR-043, F17/F18 bilan bir xil bo'linish): ``returned`` — qaytarish (Yakunlangan qatordagi
    ``amountReturns`` + Bekor holatdagi, mijozga topshirilgan qator), ``canceled`` — bekor (topshirilmagan Bekor qator).
    Kalit — Uzum ``returnCause`` (``None`` — sabab ko'rsatilmagan); kamayish tartibida, 0 lar yo'q."""

    returned: list[tuple[str | None, int]]
    canceled: list[tuple[str | None, int]]


def _ranked(rows: Any) -> list[tuple[str | None, int]]:
    sums: dict[str | None, int] = {}
    for cause, units in rows:
        sums[cause] = sums.get(cause, 0) + int(units or 0)
    return sorted(((c, v) for c, v in sums.items() if v > 0), key=lambda kv: (-kv[1], kv[0] or ""))


async def cause_sums(conn: AsyncConnection, f: Filters, *, sku: UUID | None = None) -> Causes:
    """Davrdagi qaytarish va bekor sabablari (Buyurtmalar tahlili va SKU sahifasi — bitta hisob, B4.46). Bekor qator
    donasi = ``amount + amountReturns`` (``upcore.metrics``)."""
    s = m.sale_items
    where = [
        s.c.ordered_at >= day_start(f.period.start),
        s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
    ]
    if f.shops:
        where.append(s.c.shop_id.in_(f.shops))
    if sku is not None:
        where.append(s.c.sku_id == sku)
    status = func.upper(func.trim(s.c.status))
    cancel_units = func.sum(s.c.amount + s.c.amount_returns)
    canceled_ = [*where, status.in_(statuses(StatusGroup.CANCELED))]
    partial = await conn.execute(
        select(s.c.return_cause, func.sum(s.c.amount_returns))
        .where(*where, s.c.amount_returns > 0, status.in_(statuses(StatusGroup.COMPLETED)))
        .group_by(s.c.return_cause)
    )
    issued = await conn.execute(
        select(s.c.return_cause, cancel_units)
        .where(*canceled_, s.c.issued_at.is_not(None))
        .group_by(s.c.return_cause)
    )
    returned = _ranked([*partial, *issued])
    canceled = _ranked(
        await conn.execute(
            select(s.c.return_cause, cancel_units)
            .where(*canceled_, s.c.issued_at.is_(None))
            .group_by(s.c.return_cause)
        )
    )
    return Causes(returned, canceled)


async def order_counts(
    conn: AsyncConnection, f: Filters, period: Period | None = None
) -> dict[date, tuple[int, int]]:
    """F45 kun bo'yicha: (yalpi buyurtmalar, sof buyurtmalar) — ``sale_items`` dagi ``orderId`` soni. Buyurtma bitta
    kunga (F1, buyurtma sanasi) va bitta do'konga tegishli, shuning uchun kunlar yig'indisi davr soniga teng. Sof —
    kamida bitta hisobga olinadigan (Yakunlangan + Jarayonda, ADR-036) donasi bor buyurtma; noma'lum holat — hech qaysi."""
    s = m.sale_items
    window = period or f.period
    status = func.upper(func.trim(s.c.status))
    known = (
        statuses(StatusGroup.COMPLETED)
        | statuses(StatusGroup.PROCESSING)
        | statuses(StatusGroup.CANCELED)
    )
    counted_ = statuses(StatusGroup.COMPLETED) | statuses(StatusGroup.PROCESSING)
    day = func.date(func.timezone("Asia/Tashkent", s.c.ordered_at)).label("day")
    order = func.concat(cast(s.c.shop_id, Text), ":", s.c.order_id)
    query = (
        select(
            day,
            func.count(func.distinct(order)),
            func.count(func.distinct(order)).filter(status.in_(counted_) & (s.c.amount > 0)),
        )
        .where(
            s.c.ordered_at >= day_start(window.start),
            s.c.ordered_at < day_start(window.end + timedelta(days=1)),
            status.in_(known),
        )
        .group_by(day)
    )
    if f.shops:
        query = query.where(s.c.shop_id.in_(f.shops))
    return {r[0]: (int(r[1]), int(r[2])) for r in await conn.execute(query)}


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


_RETURN_NO = re.compile(r"^\s*(\d+)\s*-")


def return_number(name: str | None) -> int | None:
    """Qaytim saqlash matnidagi qaytarish (yukxat) raqami: "1234567890 - sonli yukxat ..." (B4.22 realcheck)."""
    match = _RETURN_NO.match(name or "")
    return int(match.group(1)) if match else None


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
                e.c.name,
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
    weights = await storage_split(
        conn,
        {
            (r.shop_id, business_date(r.created_on))
            for r in rows
            if r.sale_item_id is None and r.category == ExpenseCategory.STORAGE.value
        },
    )
    returns = await _return_weights(
        conn,
        {
            (r.shop_id, n)
            for r in rows
            if r.sale_item_id is None
            and r.category == ExpenseCategory.RETURN_STORAGE.value
            and (n := return_number(r.name)) is not None
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
                else returns.get((r.shop_id, return_number(r.name) or 0))
                if category is ExpenseCategory.RETURN_STORAGE
                else None,
            )
        )
    return out


async def storage_split(
    conn: AsyncConnection, wanted: set[tuple[UUID, date]]
) -> dict[tuple[UUID, date], dict[str, Decimal]]:
    """F43 og'irliklari (do'kon, kun) uchun (ADR-040): Uzum qoidasi bo'yicha pullik saqlashdagi SKU'lar
    (``upcore.tariffs.paid_storage``: oxirgi 15 kun o'rtacha qoldig'i / o'rtacha kunlik sotuv > 60 kun, yangi SKU
    emas) — shu kungi qoldiq × saqlash narxi; qoida hech kimni topmasa — hamma qoldiq bo'yicha. Qoldiq — shu kun yoki
    oldingi ``SNAPSHOT_LOOKBACK`` kun ichidagi oxirgi snapshot (``sku_daily.qty_active``); snapshot yo'q — kiritilmaydi
    (xarajat tushum ulushida bo'linadi)."""
    if not wanted:
        return {}
    shops = {shop for shop, _ in wanted}
    window = max(r.window_days for r in SEED_STORAGE_RULES)
    first = min(day for _, day in wanted) - timedelta(days=max(SNAPSHOT_LOOKBACK, window))
    last = max(day for _, day in wanted)
    k, sd, d, s = m.mp_skus, m.sku_daily, m.daily_sku_metrics, m.sale_items
    prices = {
        str(r.id): r.storage_price
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
    sold: dict[tuple[str, date], int] = {}
    for sale in await conn.execute(
        select(d.c.sku_id, d.c.day, d.c.units).where(
            d.c.shop_id.in_(shops), d.c.sku_id.is_not(None), d.c.day >= first, d.c.day <= last
        )
    ):
        key = (str(sale.sku_id), sale.day)
        sold[key] = sold.get(key, 0) + int(sale.units)
    started: dict[str, date] = {}
    v, vi = m.fbo_invoices, m.fbo_invoice_items
    for sku, at in [
        *await conn.execute(
            select(s.c.sku_id, func.min(s.c.ordered_at))
            .where(s.c.shop_id.in_(shops), s.c.sku_id.is_not(None))
            .group_by(s.c.sku_id)
        ),
        *await conn.execute(
            select(vi.c.sku_id, func.min(v.c.created_on))
            .join(v, v.c.id == vi.c.invoice_id)
            .where(v.c.shop_id.in_(shops), vi.c.sku_id.is_not(None), v.c.created_on.is_not(None))
            .group_by(vi.c.sku_id)
        ),
    ]:
        day = business_date(at)
        if str(sku) not in started or day < started[str(sku)]:
            started[str(sku)] = day
    out = {}
    for shop, day in wanted:
        days = snaps.get(shop, {})
        found = next(
            (
                days[x]
                for i in range(SNAPSHOT_LOOKBACK + 1)
                if (x := day - timedelta(days=i)) in days
            ),
            None,
        )
        if not found:
            continue
        rule = storage_rule(day)
        paid = None
        if rule is not None:
            span = [day - timedelta(days=i) for i in range(rule.window_days)]
            paid = set()
            for sku in found:
                stock = [days[x][sku] for x in span if x in days and sku in days[x]]
                avg = Decimal(sum(stock)) / len(stock) if stock else Decimal(0)
                units = sum(sold.get((sku, x), 0) for x in span)
                if paid_storage(avg, units, started.get(sku), day, rule):
                    paid.add(sku)
        w = storage_weights(found, {sku: prices.get(sku) for sku in found}, paid)
        if w:
            out[shop, day] = w
    return out


async def _return_weights(
    conn: AsyncConnection, wanted: set[tuple[UUID, int]]
) -> dict[tuple[UUID, int], dict[str, Decimal]]:
    """ADR-040: qaytim saqlash ("N - sonli yukxat ...", N = Uzum qaytarish id'si — B4.22 realcheck 36/36) — shu
    qaytarishdagi SKU'larga dona bo'yicha."""
    if not wanted:
        return {}
    r, ri = m.mp_returns, m.mp_return_items
    out: dict[tuple[UUID, int], dict[str, Decimal]] = {}
    for row in await conn.execute(
        select(r.c.shop_id, r.c.external_id, ri.c.sku_id, ri.c.quantity)
        .join(ri, ri.c.return_id == r.c.id)
        .where(
            r.c.shop_id.in_({shop for shop, _ in wanted}),
            r.c.external_id.in_({n for _, n in wanted}),
            ri.c.sku_id.is_not(None),
        )
    ):
        key = (row.shop_id, int(row.external_id))
        if key in wanted and row.quantity > 0:
            bucket = out.setdefault(key, {})
            bucket[str(row.sku_id)] = bucket.get(str(row.sku_id), Decimal(0)) + row.quantity
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
            # B4.24: reklamasi allaqachon yechilgan (bog'langan) sotuvga taxmin qo'shilmaydi — ikki marta bo'lmasin.
            ~exists().where(
                e.c.sale_item_id == s.c.id,
                e.c.category == ExpenseCategory.ADVERTISING.value,
                e.c.excluded.is_(None),
            ),
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
    """Soliq profillari qatorlari bilan (ADR-058); qatorsiz profil eski ustunlaridan o'qiladi (``upcore.tax``)."""
    t, tl = m.tax_profiles, m.tax_lines
    lines: dict[UUID, list[TaxLine]] = {}
    for r in await conn.execute(select(tl).order_by(tl.c.profile_id, tl.c.position, tl.c.name)):
        lines.setdefault(r.profile_id, []).append(
            TaxLine(
                name=r.name,
                kind=LineKind(r.kind),
                rate_pct=r.rate_pct,
                base=TaxBase(r.base),
                amount=r.amount,
                bhm_count=r.bhm_count,
                period=FixedPeriod(r.period),
            )
        )
    return [
        TaxProfile(
            valid_from=r.valid_from,
            regime=TaxRegime(r.regime),
            rate_pct=r.rate_pct,
            base=TaxBase(r.base),
            vat_pct=r.vat_pct,
            profit_pct=r.profit_pct,
            lines=tuple(lines.get(r.id, ())),
        )
        for r in await conn.execute(select(t).order_by(t.c.valid_from))
    ]


async def bhm_values(conn: AsyncConnection) -> list[AmountValue]:
    """BHM ma'lumotnomasi: bazadagi ``ref_amounts`` (admin tahrirlaydi) + ``upcore`` boshlang'ich qiymatlari — deploy
    ma'lumotnomani to'ldirmaydi (``seed`` faqat dev), shuning uchun baza bo'sh bo'lsa ham BHM ma'lum. Bir sanada bazadagi
    yozuv ustun (``amount_on`` birinchisini oladi)."""
    t = m.ref_amounts
    stored = [
        AmountValue(r.code, r.valid_from, r.amount)
        for r in await conn.execute(select(t).where(t.c.code == BHM))
    ]
    return [*stored, *(v for v in SEED_AMOUNTS if v.code == BHM)]


async def expected_fees(
    conn: AsyncConnection, today: date, keys: list[tuple[str, str]]
) -> Callable[[str, str], Money | None]:
    """F40 tariflari (``today`` kungi) Uzum hali yechmagan va qatorda 0 bo'lgan, topshirilmagan Jarayondagi donalar
    kataklari (do'kon, SKU kaliti) uchun — kutilayotgan logistika taxmini (F5, ADR-037, ADR-042)."""
    skus = {UUID(sku): UUID(shop) for shop, sku in keys if sku != UNLINKED}
    shops = {UUID(shop) for shop, sku in keys if sku == UNLINKED}
    if not skus and not shops:
        return lambda _shop, _sku: None
    return (await load_fees(conn, today, skus, shops)).unit


async def load_book(conn: AsyncConnection, period: Period, today: date) -> Book:
    """Davr (masalan, joriy + oldingi davr birga) kataklari butun tashkilot bo'yicha. ``today`` — F40 tarifi va F42
    ulushi kuni. Logistika (ADR-042) — Uzum aslida yechgani, hali yechilmagan bo'lsa sotuv qatoridagi summa; qatorda 0
    va hali olib ketilmagan sotuvga — F40 × dona taxmini (Uzum olib ketilganda yechadi)."""
    totals = await _totals(conn, period)
    due = sorted({(k.shop, k.sku or UNLINKED) for k, t in totals if t.lines_logistics_due})
    profiles = await tax_profiles(conn)
    values = await bhm_values(conn)
    # F11 (ADR-058): qat'iy soliq qatorlari — kunlik o'z xarajatlari kabi kataklarga taqsimlanadi, "Soliq" ostida ko'rinadi.
    fixed, missing = fixed_expenses(
        profiles, lambda day: amount_on(values, BHM, day), period.start, period.end
    )
    cells = build_cells(
        period,
        [],
        [*await _expenses(conn, period), *await _expected_ads(conn, period, today)],
        [*await _own(conn, period), *fixed],
        tax=daily_rules(profiles),
        totals=totals,
        logistics_fee=await expected_fees(conn, today, due),
    )
    return Book(cells, missing)


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
        logistics=r.logistics_effective,  # ADR-042: Uzum yechgan, bo'lmasa qatordagi
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

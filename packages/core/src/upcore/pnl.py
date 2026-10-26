"""Foyda va zarar (P&L) — F12–F16 hisobot qatorlari va kesimlari (02-funksiyalar.md M5; ADR-026).

Hisob eng mayda **katak**da yuritiladi: (kun, do'kon, SKU). Har katakda F3–F8, unga tushgan F9 / F10 / F11
xarajatlari va F15 qamrovi bo'yicha ayrilgan qismi. Har qanday kesim (davr, oy, do'kon, SKU, tashkilot)
— kataklar **yig'indisi**, qayta hisob emas. Shuning uchun M5 qabul mezoni o'z-o'zidan bajariladi:
oylar yig'indisi = butun davr, do'konlar / SKU'lar yig'indisi = tashkilot, P&L = bosh sahifa = SKU jadvali.

Xarajatlarni kataklarga bo'lish (F19 dagi reklama qoidasi bilan bir xil):
- SKU'ga bog'langan xarajat — o'sha kun va SKU katagiga;
- do'kon xarajati — o'sha kuni do'kon SKU'lariga yakunlangan tushum ulushida; tushum bo'lmagan kunda
  do'konning "taqsimlanmagan" katagiga (``sku=None``);
- tashkilot xarajati (o'z xarajatlari, F10) — o'sha kuni hamma do'kon SKU'lariga tushum ulushida.
O'z xarajatlari kunlarga amortizatsiya qilinadi (F10), kunlar yig'indisi xarajatga aniq teng.

Katakda F15: ayriladigan xarajat = katak xarajati × katak qamrovi (tannarxi ma'lum tushum / tushum;
tushum 0 bo'lsa 1). Qolgani — "tannarxsiz qism".

Sotuvlar ikki ko'rinishda beriladi: qatorlar (``SaleLine``) yoki katak yig'indilari (``CellSales`` —
``daily_sku_metrics`` qatori, ``upcore.metrics.sale_totals`` natijasining xom ko'rinishi). Ikkalasi bir xil
kataklar beradi.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple, cast

from upcore.expenses import ExpenseCategory, ExpenseRecord
from upcore.metrics import (
    ExpectedProfit,
    ManualExpense,
    Period,
    SaleLine,
    SaleTotals,
    StatusGroup,
    completed,
    expected_profit,
    own_expense_in_period,
    ratio,
    realization_rate,
)
from upcore.money import Currency, Money, quantize, split, to_decimal, total

UZS = Currency.UZS
ZERO = Money.zero(UZS)
_D0 = Decimal(0)


# --- Kirish ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExpenseItem:
    """Uzum xarajati (F9) P&L uchun: ishorali summa (OUTCOME +, INCOME −), do'kon, ixtiyoriy SKU."""

    day: date
    shop: str
    category: ExpenseCategory
    amount: Money
    sku: str | None = None


def expense_items(
    records: Iterable[ExpenseRecord],
    shop: str,
    sku_of: Callable[[ExpenseRecord], str | None] | None = None,
) -> list[ExpenseItem]:
    """B1.3 natijasi → P&L xarajatlari (faqat P&L'ga kiradiganlari). ``sku_of`` — bog'lanish
    (masalan, ``item_id`` / buyurtma → SKU); berilmasa do'kon darajasida."""
    return [
        ExpenseItem(r.day, shop, r.category, r.signed, sku_of(r) if sku_of else None)
        for r in records
        if r.counted
    ]


@dataclass(frozen=True, slots=True)
class OwnExpense:
    """O'z xarajati (F10): toifa va taqsimot doirasi — tashkilot (``shop=None``), do'kon yoki SKU."""

    expense: ManualExpense
    category: str
    shop: str | None = None
    sku: str | None = None


class TaxBase(StrEnum):
    REVENUE = "revenue"  # F3 (standart)
    PAYOUT = "payout"  # F6


@dataclass(frozen=True, slots=True)
class TaxRule:
    """F11 (a): aylanmadan foiz. Profillar va sana bo'yicha tanlash — ``upcore.tax``."""

    rate_pct: Decimal
    base: TaxBase = TaxBase.REVENUE

    def on(self, revenue: Money, payout: Money) -> Money:
        return Money(self.amount_on(revenue.amount, payout.amount), UZS)

    def amount_on(self, revenue: Decimal, payout: Decimal) -> Decimal:
        """``on`` ning xom ko'rinishi (so'm, tiyinga yaxlitlangan) — P&L kataklari uchun."""
        base = revenue if self.base is TaxBase.REVENUE else payout
        return quantize(base * (to_decimal(self.rate_pct) / 100), UZS.places)


# --- Katak ----------------------------------------------------------------------------------


class CellKey(NamedTuple):
    """Katak kaliti (kortej — xeshlash tez: davrda o'n minglab katak)."""

    day: date
    shop: str
    sku: str | None  # None — do'kon (yoki tashkilot) xarajatlarining taqsimlanmagan qismi

    def order(self) -> tuple[date, str, bool, str]:
        """Barqaror tartib: kun, do'kon, SKU (taqsimlanmagan katak oxirida)."""
        return (self.day, self.shop, self.sku is None, self.sku or "")


@dataclass(slots=True)
class Cell:
    """Katak: xom ``Decimal`` (so'm, tiyinga yaxlitlangan qismlar) — tezlik uchun ``Money`` emas. Kesim natijasi
    (``Statement``) kataklar yig'indisidan bir marta yaratiladi. ``tax`` va ``deducted`` — katakda yaxlitlangan
    (kesimlar yig'indisi jamiga tiyinigacha teng bo'lishi uchun)."""

    revenue: Decimal = _D0
    commission: Decimal = _D0
    logistics: Decimal = _D0
    cogs: Decimal = _D0
    covered_revenue: Decimal = _D0
    covered_payout: Decimal = _D0
    units: int = 0
    covered_units: int = 0
    lines: int = 0
    uncovered_lines: int = 0
    # Xarajatlar (F9 turlari, F10 toifalari) va shundan taqsimlangani; ``None`` — yo'q (lug'at kerak bo'lganda).
    uzum: dict[ExpenseCategory, Decimal] | None = None
    own: dict[str, Decimal] | None = None
    uzum_alloc: dict[ExpenseCategory, Decimal] | None = None
    own_alloc: dict[str, Decimal] | None = None
    tax: Decimal = _D0
    deducted: Decimal = _D0


def _uzs(amount: Decimal) -> Money:
    return Money.rounded(amount, UZS)


def _cents(amount: Decimal) -> Decimal:
    return quantize(amount, UZS.places)


def _money_map[K: Hashable](bucket: Mapping[K, Decimal]) -> dict[K, Money]:
    return {k: Money.rounded(v, UZS) for k, v in bucket.items()}


@dataclass(frozen=True, slots=True)
class CellSales:
    """Katak sotuvlari yig'indisi, xom so'm (``daily_sku_metrics`` qatori) — ``SaleTotals`` ning P&L uchun
    keragi. Ko'p katakli davrda ``Money`` yaratmaslik uchun (M4: 1 yil, 50 000 qator)."""

    revenue: Decimal  # F3
    commission: Decimal  # F4
    logistics: Decimal  # F5
    cogs: Decimal  # F7
    revenue_costed: Decimal
    payout_costed: Decimal
    units: int
    units_costed: int
    lines: int
    uncovered_lines: int

    @classmethod
    def of(cls, t: SaleTotals) -> CellSales:
        return cls(
            revenue=t.revenue.amount,
            commission=t.commission.amount,
            logistics=t.logistics.amount,
            cogs=t.cogs.amount,
            revenue_costed=t.revenue_costed.amount,
            payout_costed=t.payout_costed.amount,
            units=t.units,
            units_costed=t.units_costed,
            lines=t.lines,
            uncovered_lines=t.uncovered_lines,
        )


@dataclass(frozen=True, slots=True)
class Statement:
    """P&L hisoboti (bitta kesim). Hamma summalar kataklar yig'indisi."""

    revenue: Money  # F3
    commission: Money  # F4
    logistics: Money  # F5
    cogs: Money  # F7 (tannarxi ma'lum qatorlar)
    covered_revenue: Money
    covered_payout: Money
    uzum_expenses: Mapping[ExpenseCategory, Money]  # F9 turlari (kompensatsiya manfiy)
    own_expenses: Mapping[str, Money]  # F10 toifalari
    tax: Money  # F11
    expenses_deducted: Money  # F15: qamrov bo'yicha ayrilgan qism
    units: int
    lines: int
    uncovered_lines: int
    # ADR-026: shundan tushum ulushida taqsimlangan qism (do'kon / tashkilot xarajatidan SKU'larga).
    uzum_allocated: Mapping[ExpenseCategory, Money] = field(default_factory=dict)
    own_allocated: Mapping[str, Money] = field(default_factory=dict)
    covered_units: int = 0  # tannarxi ma'lum Yakunlangan dona

    @property
    def payout(self) -> Money:
        """F6 = F3 − F4 − F5."""
        return self.revenue - self.commission - self.logistics

    @property
    def gross_profit(self) -> Money:
        """F8 = F6 − F7 (tannarxi ma'lum qism)."""
        return self.covered_payout - self.cogs

    @property
    def uzum_total(self) -> Money:
        return total(list(self.uzum_expenses.values()), UZS)

    @property
    def own_total(self) -> Money:
        return total(list(self.own_expenses.values()), UZS)

    @property
    def allocated_total(self) -> Money:
        """Taqsimlangan xarajatlar (F9 + F10): do'kon / tashkilot xarajatining tushum ulushidagi qismi."""
        return total([*self.uzum_allocated.values(), *self.own_allocated.values()], UZS)

    @property
    def direct_total(self) -> Money:
        """To'g'ridan-to'g'ri xarajatlar (F9 + F10): shu SKU'ga bog'langan yoki o'z darajasidagi."""
        return self.uzum_total + self.own_total - self.allocated_total

    @property
    def overhead(self) -> Money:
        """F9 + F10 + F11."""
        return self.uzum_total + self.own_total + self.tax

    @property
    def net_profit(self) -> Money:
        """F12 (F15 bilan): ma'lum qism yalpi foydasi − qamrov bo'yicha ayrilgan xarajatlar."""
        return self.gross_profit - self.expenses_deducted

    @property
    def uncovered_revenue(self) -> Money:
        return self.revenue - self.covered_revenue

    @property
    def uncovered_payout(self) -> Money:
        return self.payout - self.covered_payout

    @property
    def uncovered_expenses(self) -> Money:
        return self.overhead - self.expenses_deducted

    @property
    def coverage(self) -> Decimal:
        """F15 tushum bo'yicha (tushum 0 bo'lsa 1)."""
        share = ratio(self.covered_revenue.amount, self.revenue.amount)
        return Decimal(1) if share is None else share

    @property
    def uncovered_share(self) -> Decimal:
        return 1 - self.coverage

    @property
    def margin(self) -> Decimal | None:
        """F13 (ADR-024): F12 / tannarxi ma'lum tushum."""
        return ratio(self.net_profit.amount, self.covered_revenue.amount)

    @property
    def roi(self) -> Decimal | None:
        """F14 = F12 / F7."""
        return ratio(self.net_profit.amount, self.cogs.amount)

    def rows(self) -> list[tuple[str, Money]]:
        """M5 hisob varag'i qatorlari tartibida: kod → summa (UI matni i18n'dan)."""
        out: list[tuple[str, Money]] = [
            ("revenue", self.revenue),
            ("commission", -self.commission),
            ("logistics", -self.logistics),
            ("payout", self.payout),
            ("cogs", -self.cogs),
            ("gross_profit", self.gross_profit),
        ]
        out += [(f"uzum:{c.value}", -a) for c, a in sorted(self.uzum_expenses.items())]
        out += [(f"own:{c}", -a) for c, a in sorted(self.own_expenses.items())]
        out += [("tax", -self.tax)]
        if not self.uncovered_expenses.is_zero() or not self.uncovered_revenue.is_zero():
            out += [
                ("uncovered_payout", self.uncovered_payout),
                ("uncovered_expenses", self.uncovered_expenses),
            ]
        out += [("net_profit", self.net_profit)]
        return out


@dataclass(frozen=True, slots=True)
class Cells:
    """Davr kataklari; kesimlar shu yerdan olinadi (har kesim — kataklar yig'indisi)."""

    period: Period
    cells: Mapping[CellKey, Cell]

    @property
    def items(self) -> dict[CellKey, Statement]:
        """Har katak hisoboti (kam kataklar uchun: tekshiruv, izoh)."""
        return {k: _total([c]) for k, c in self.cells.items()}

    def within(self, period: Period, where: Callable[[CellKey], bool] | None = None) -> Cells:
        """Ichki davr (va tanlangan) kataklari — masalan, joriy va oldingi davr bitta hisobdan."""
        first, last = period.start, period.end
        return Cells(
            period,
            {
                k: c
                for k, c in self.cells.items()
                if first <= k[0] <= last and (where is None or where(k))
            },
        )

    def statement(self, where: Callable[[CellKey], bool] | None = None) -> Statement:
        """Tanlangan kataklar yig'indisi (``where`` yo'q — butun davr, tashkilot)."""
        return _total(c for k, c in self.cells.items() if where is None or where(k))

    def statements[K: Hashable](
        self, groups: Mapping[K, Callable[[CellKey], bool]]
    ) -> dict[K, Statement]:
        """Bir necha (kesishishi mumkin bo'lgan) kesim bir o'tishda: masalan, joriy va oldingi davr, bugun,
        shu oy — har biri ``statement(where)`` bilan bir xil."""
        chosen: dict[K, list[Cell]] = {g: [] for g in groups}
        tests = list(groups.items())
        for k, c in self.cells.items():
            for g, where in tests:
                if where(k):
                    chosen[g].append(c)
        return {g: _total(cells) for g, cells in chosen.items()}

    def by[K: Hashable](self, key: Callable[[CellKey], K]) -> dict[K, Statement]:
        return self.by_and_total(key)[0]

    def by_and_total[K: Hashable](
        self, key: Callable[[CellKey], K]
    ) -> tuple[dict[K, Statement], Statement]:
        """``by`` va ``statement()`` bir o'tishda: jami — guruhlar (xom) yig'indisi, kataklar yig'indisi bilan
        bir xil (summalar aniq qo'shiladi)."""
        groups: dict[K, list[Cell]] = defaultdict(list)
        for k, c in self.cells.items():
            groups[key(k)].append(c)
        rolled = {g: _roll(groups[g]) for g in sorted(groups, key=lambda g: (g is None, str(g)))}
        return {g: _statement(c) for g, c in rolled.items()}, _total(rolled.values())

    def by_month(self) -> dict[date, Statement]:
        return self.by(lambda k: k.day.replace(day=1))

    def by_day(self) -> dict[date, Statement]:
        return self.by(lambda k: k.day)

    def by_shop(self) -> dict[str, Statement]:
        return self.by(lambda k: k.shop)

    def by_sku(self) -> dict[str | None, Statement]:
        return self.by(lambda k: k.sku)


def _roll(cells: Iterable[Cell]) -> Cell:
    """Kataklar yig'indisi (xom): kesim natijasi va kesimlar jami uchun."""
    revenue = commission = logistics = cogs = covered_revenue = covered_payout = _D0
    tax = deducted = _D0
    units = lines = uncovered = covered_units = 0
    uzum: dict[ExpenseCategory, Decimal] = {}
    own: dict[str, Decimal] = {}
    uzum_alloc: dict[ExpenseCategory, Decimal] = {}
    own_alloc: dict[str, Decimal] = {}
    for c in cells:
        revenue += c.revenue
        commission += c.commission
        logistics += c.logistics
        cogs += c.cogs
        covered_revenue += c.covered_revenue
        covered_payout += c.covered_payout
        tax += c.tax
        deducted += c.deducted
        units += c.units
        lines += c.lines
        uncovered += c.uncovered_lines
        covered_units += c.covered_units
        if c.uzum:
            for cat, a in c.uzum.items():
                uzum[cat] = uzum.get(cat, _D0) + a
        if c.own:
            for oc, a in c.own.items():
                own[oc] = own.get(oc, _D0) + a
        if c.uzum_alloc:
            for cat, a in c.uzum_alloc.items():
                uzum_alloc[cat] = uzum_alloc.get(cat, _D0) + a
        if c.own_alloc:
            for oc, a in c.own_alloc.items():
                own_alloc[oc] = own_alloc.get(oc, _D0) + a
    return Cell(
        revenue=revenue,
        commission=commission,
        logistics=logistics,
        cogs=cogs,
        covered_revenue=covered_revenue,
        covered_payout=covered_payout,
        units=units,
        covered_units=covered_units,
        lines=lines,
        uncovered_lines=uncovered,
        uzum=uzum,
        own=own,
        uzum_alloc=uzum_alloc,
        own_alloc=own_alloc,
        tax=tax,
        deducted=deducted,
    )


def _statement(c: Cell) -> Statement:
    return Statement(
        revenue=_uzs(c.revenue),
        commission=_uzs(c.commission),
        logistics=_uzs(c.logistics),
        cogs=_uzs(c.cogs),
        covered_revenue=_uzs(c.covered_revenue),
        covered_payout=_uzs(c.covered_payout),
        uzum_expenses=_money_map(c.uzum or {}),
        own_expenses=_money_map(c.own or {}),
        tax=_uzs(c.tax),
        expenses_deducted=_uzs(c.deducted),
        units=c.units,
        lines=c.lines,
        uncovered_lines=c.uncovered_lines,
        uzum_allocated=_money_map(c.uzum_alloc or {}),
        own_allocated=_money_map(c.own_alloc or {}),
        covered_units=c.covered_units,
    )


def _total(cells: Iterable[Cell]) -> Statement:
    return _statement(_roll(cells))


def _put(a: Cell, own: bool, category: str, amount: Decimal) -> None:
    """Katakka to'g'ridan-to'g'ri (taqsimlanmagan) xarajat: ``own`` — o'z xarajati toifasi (F10), aks holda Uzum
    turi (F9). Tushum ulushidagi taqsimot — ``build_cells`` ichidagi ``spread``."""
    if own:
        if a.own is None:
            a.own = {}
        a.own[category] = a.own.get(category, _D0) + amount
    else:
        c = cast(ExpenseCategory, category)
        if a.uzum is None:
            a.uzum = {}
        a.uzum[c] = a.uzum.get(c, _D0) + amount


def _days(period: Period) -> list[date]:
    return [period.start + timedelta(days=i) for i in range(period.days)]


def build_cells(
    period: Period,
    lines: Iterable[SaleLine],
    expenses: Iterable[ExpenseItem] = (),
    own_expenses: Iterable[OwnExpense] = (),
    tax: TaxRule | Callable[[date], TaxRule | None] | None = None,
    totals: Iterable[tuple[CellKey, CellSales]] = (),
) -> Cells:
    """F12–F15 kataklari. Davrdan tashqari sotuv va xarajatlar e'tiborga olinmaydi.

    ``totals`` — tayyor katak yig'indilari (``CellSales``, masalan ``daily_sku_metrics``); ``lines`` bilan bir
    xil natija beradi (Yakunlangan qatori yo'q yig'indi katak yaratmaydi)."""
    acc: dict[CellKey, Cell] = defaultdict(Cell)
    first, last = period.start, period.end

    for key, t in totals:
        if not first <= key[0] <= last or t.lines == 0:
            continue
        a = acc[key]
        a.revenue += t.revenue
        a.commission += t.commission
        a.logistics += t.logistics
        a.cogs += t.cogs
        a.covered_revenue += t.revenue_costed
        a.covered_payout += t.payout_costed
        a.units += t.units
        a.covered_units += t.units_costed
        a.lines += t.lines
        a.uncovered_lines += t.uncovered_lines

    for line in completed(x for x in lines if x.order_date in period):
        a = acc[CellKey(line.order_date, line.shop, line.sku)]
        rev = _cents(line.revenue)
        fee = _cents(to_decimal(line.commission))
        logistic = _cents(to_decimal(line.logistics))
        a.revenue += rev
        a.commission += fee
        a.logistics += logistic
        a.units += line.amount
        a.lines += 1
        cost = line.cogs
        if cost is None:
            a.uncovered_lines += 1
        else:
            a.cogs += _cents(cost)
            a.covered_units += line.amount
            a.covered_revenue += rev
            a.covered_payout += rev - fee - logistic

    # Kun × do'kon bo'yicha SKU tushumlari — taqsimot og'irliklari (kataklar yaratilishidan oldin olinadi).
    sales_by_day: dict[date, list[CellKey]] = defaultdict(list)
    sales_by_shop: dict[tuple[date, str], list[CellKey]] = defaultdict(list)
    for key in sorted(acc, key=CellKey.order):
        sales_by_day[key.day].append(key)
        sales_by_shop[key.day, key.shop].append(key)
    weights_of: dict[tuple[date, str | None], tuple[list[CellKey], list[Decimal]] | None] = {}

    def targets(day: date, shop: str | None) -> tuple[list[CellKey], list[Decimal]] | None:
        """Taqsimot kataklari va og'irliklari (tushumlar) — keshda: kataklar tushumi keyin o'zgarmaydi."""
        if (day, shop) not in weights_of:
            keys = sales_by_day.get(day, []) if shop is None else sales_by_shop.get((day, shop), [])
            weights = [acc[k].revenue for k in keys]
            ok = keys and any(w > 0 for w in weights)
            weights_of[day, shop] = (keys, weights) if ok else None
        return weights_of[day, shop]

    def spread(day: date, shop: str | None, own: bool, category: str, amount: Money) -> None:
        """Summani kun bo'yicha SKU kataklariga tushum ulushida ("taqsimlangan"); tushum yo'q —
        do'kon / tashkilot darajasidagi taqsimlanmagan katakka (o'z darajasida, taqsimlanmagan).
        ``own`` — o'z xarajati (F10), aks holda Uzum xarajati (F9; ``category`` — ``ExpenseCategory``)."""
        found = targets(day, shop)
        if found is None:
            _put(acc[CellKey(day, shop or "", None)], own, category, amount.amount)
            return
        keys, weights = found
        for k, part in zip(keys, split(amount.amount, weights, UZS.places), strict=True):
            a = acc[k]  # taqsimlangan qism: ichma-ich (ko'p chaqiriladi)
            if own:
                if a.own is None:
                    a.own, a.own_alloc = {}, {}
                elif a.own_alloc is None:
                    a.own_alloc = {}
                a.own[category] = a.own.get(category, _D0) + part
                a.own_alloc[category] = a.own_alloc.get(category, _D0) + part
            else:
                c = cast(ExpenseCategory, category)
                if a.uzum is None:
                    a.uzum, a.uzum_alloc = {}, {}
                elif a.uzum_alloc is None:
                    a.uzum_alloc = {}
                a.uzum[c] = a.uzum.get(c, _D0) + part
                a.uzum_alloc[c] = a.uzum_alloc.get(c, _D0) + part

    for e in expenses:
        if e.day not in period:
            continue
        if e.sku is not None:
            _put(acc[CellKey(e.day, e.shop, e.sku)], False, e.category, e.amount.amount)
        else:
            spread(e.day, e.shop, False, e.category, e.amount)

    for oe in own_expenses:
        for day in _days(period):
            part = own_expense_in_period(oe.expense, Period(day, day))
            if part.is_zero():
                continue
            if oe.sku is not None:
                _put(acc[CellKey(day, oe.shop or "", oe.sku)], True, oe.category, part.amount)
            else:
                spread(day, oe.shop, True, oe.category, part)

    rules: dict[date, TaxRule | None] = {}
    for key, a in acc.items():
        day = key[0]
        if callable(tax):  # F11 profili sana bo'yicha (upcore.tax), kun bo'yicha keshda
            rule = rules[day] if day in rules else rules.setdefault(day, tax(day))
        else:
            rule = tax
        if rule is not None:
            a.tax = rule.amount_on(a.revenue, a.revenue - a.commission - a.logistics)
        overhead = a.tax
        if a.uzum:
            overhead += sum(a.uzum.values(), _D0)
        if a.own:
            overhead += sum(a.own.values(), _D0)
        if a.revenue == 0:
            a.deducted = _cents(overhead)
        elif overhead:
            a.deducted = _cents(overhead * a.covered_revenue / a.revenue)
    return Cells(period, dict(acc))


# --- Unit-iqtisod (M6) ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnitEconomics:
    """M6 jadvali ustunlari bitta kesim (SKU) uchun; maxraj nol bo'lsa ``None``.

    Tannarx/dona va foyda/dona — tannarxi ma'lum dona bo'yicha (F15: sof foyda faqat shu qism uchun)."""

    avg_price: Money | None  # F3 / dona
    commission_share: Decimal | None  # F4 / F3
    logistics_per_unit: Money | None  # F5 / dona
    cogs_per_unit: Money | None  # F7 / tannarxi ma'lum dona
    ads_per_unit: Money | None  # F19 reklamasi (bog'langan + taqsimlangan) / dona
    acos: Decimal | None  # F19 = reklama / F3
    profit_per_unit: Money | None  # F12 / tannarxi ma'lum dona


def _per(amount: Money, n: int) -> Money | None:
    return None if n == 0 else Money(amount.amount / n, amount.currency)


def unit_economics(s: Statement) -> UnitEconomics:
    """M6 unit-iqtisod kesim hisobotidan (``Cells.by_sku``): reklama — F9 ning reklama turi (F19 qoidasi bilan
    SKU'ga bog'langan va tushum ulushida taqsimlangan)."""
    ads = s.uzum_expenses.get(ExpenseCategory.ADVERTISING, ZERO)
    return UnitEconomics(
        avg_price=_per(s.revenue, s.units),
        commission_share=ratio(s.commission.amount, s.revenue.amount),
        logistics_per_unit=_per(s.logistics, s.units),
        cogs_per_unit=_per(s.cogs, s.covered_units),
        ads_per_unit=_per(ads, s.units),
        acos=ratio(ads.amount, s.revenue.amount),
        profit_per_unit=_per(s.net_profit, s.covered_units),
    )


# --- Kutilayotgan foyda va solishtirish -----------------------------------------------------


def pending_profit(
    period: Period, lines: Iterable[SaleLine], window: Iterable[SaleLine], min_units: int = 50
) -> ExpectedProfit:
    """F16 bloki: davrdagi Jarayondagi qatorlar × R (R — ``window``: do'konning oxirgi 90 kuni)."""
    pending = [x for x in lines if x.order_date in period and x.group is StatusGroup.PROCESSING]
    return expected_profit(pending, realization_rate(window, min_units))


@dataclass(frozen=True, slots=True)
class CompareRow:
    """M5 ustunlari: joriy, tushumga nisbatan %, oldingi davr, farq va o'zgarish ulushi.

    ``change`` = farq / |oldingi davr| (ishorali qiymat bo'yicha: yuqori — yaxshi); oldingi davr nol bo'lsa ``None``.
    """

    code: str
    current: Money
    share_of_revenue: Decimal | None
    previous: Money
    diff: Money
    change: Decimal | None


def compare(current: Statement, previous: Statement) -> list[CompareRow]:
    """Ikki davr hisobot qatorlari: joriy davrda yo'q qator oldingisida bo'lsa ham ko'rsatiladi."""
    cur, prev = dict(current.rows()), dict(previous.rows())
    codes = [c for c, _ in current.rows()] + [c for c, _ in previous.rows() if c not in cur]
    rows = []
    for code in codes:
        now, before = cur.get(code, ZERO), prev.get(code, ZERO)
        diff = now - before
        rows.append(
            CompareRow(
                code,
                now,
                ratio(now.amount, current.revenue.amount),
                before,
                diff,
                ratio(diff.amount, abs(before.amount)),
            )
        )
    return rows

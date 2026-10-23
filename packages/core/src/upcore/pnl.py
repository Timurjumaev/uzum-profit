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
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from upcore.expenses import ExpenseCategory, ExpenseRecord
from upcore.metrics import (
    ExpectedProfit,
    ManualExpense,
    Period,
    SaleLine,
    StatusGroup,
    completed,
    expected_profit,
    own_expense_in_period,
    ratio,
    realization_rate,
)
from upcore.money import Currency, Money, allocate, to_decimal, total

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
    """F11 (a): aylanmadan foiz. Boshqa profillar (agent, QQS + foyda solig'i) — B1.8."""

    rate_pct: Decimal
    base: TaxBase = TaxBase.REVENUE

    def on(self, revenue: Money, payout: Money) -> Money:
        base = revenue if self.base is TaxBase.REVENUE else payout
        return base * (to_decimal(self.rate_pct) / 100)


# --- Katak ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CellKey:
    day: date
    shop: str
    sku: str | None  # None — do'kon (yoki tashkilot) xarajatlarining taqsimlanmagan qismi

    def order(self) -> tuple[date, str, bool, str]:
        """Barqaror tartib: kun, do'kon, SKU (taqsimlanmagan katak oxirida)."""
        return (self.day, self.shop, self.sku is None, self.sku or "")


@dataclass(slots=True)
class _Acc:
    """Katak yig'uvchisi: tezlik uchun xom ``Decimal`` (so'm), ``Money`` — faqat natijada."""

    revenue: Decimal = _D0
    commission: Decimal = _D0
    logistics: Decimal = _D0
    cogs: Decimal = _D0
    covered_revenue: Decimal = _D0
    covered_payout: Decimal = _D0
    units: int = 0
    lines: int = 0
    uncovered_lines: int = 0
    uzum: dict[ExpenseCategory, Decimal] = field(default_factory=dict)
    own: dict[str, Decimal] = field(default_factory=dict)


def _add[K: Hashable](bucket: dict[K, Decimal], key: K, amount: Decimal) -> None:
    bucket[key] = bucket.get(key, _D0) + amount


def _money_map[K: Hashable](bucket: Mapping[K, Decimal]) -> dict[K, Money]:
    return {k: Money(v, UZS) for k, v in bucket.items()}


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
    """Davr kataklari; kesimlar shu yerdan olinadi."""

    period: Period
    items: Mapping[CellKey, Statement]

    def statement(self, where: Callable[[CellKey], bool] | None = None) -> Statement:
        """Tanlangan kataklar yig'indisi (``where`` yo'q — butun davr, tashkilot)."""
        return _sum(s for k, s in self.items.items() if where is None or where(k))

    def by[K: Hashable](self, key: Callable[[CellKey], K]) -> dict[K, Statement]:
        groups: dict[K, list[Statement]] = defaultdict(list)
        for k, s in self.items.items():
            groups[key(k)].append(s)
        return {g: _sum(groups[g]) for g in sorted(groups, key=lambda g: (g is None, str(g)))}

    def by_month(self) -> dict[date, Statement]:
        return self.by(lambda k: k.day.replace(day=1))

    def by_day(self) -> dict[date, Statement]:
        return self.by(lambda k: k.day)

    def by_shop(self) -> dict[str, Statement]:
        return self.by(lambda k: k.shop)

    def by_sku(self) -> dict[str | None, Statement]:
        return self.by(lambda k: k.sku)


def _sum(statements: Iterable[Statement]) -> Statement:
    items = list(statements)
    uzum: dict[ExpenseCategory, Decimal] = {}
    own: dict[str, Decimal] = {}
    for s in items:
        for c, a in s.uzum_expenses.items():
            _add(uzum, c, a.amount)
        for oc, a in s.own_expenses.items():
            _add(own, oc, a.amount)

    def add(get: Callable[[Statement], Money]) -> Money:
        return Money(sum((get(s).amount for s in items), _D0), UZS)

    return Statement(
        revenue=add(lambda s: s.revenue),
        commission=add(lambda s: s.commission),
        logistics=add(lambda s: s.logistics),
        cogs=add(lambda s: s.cogs),
        covered_revenue=add(lambda s: s.covered_revenue),
        covered_payout=add(lambda s: s.covered_payout),
        uzum_expenses=_money_map(uzum),
        own_expenses=_money_map(own),
        tax=add(lambda s: s.tax),
        expenses_deducted=add(lambda s: s.expenses_deducted),
        units=sum(s.units for s in items),
        lines=sum(s.lines for s in items),
        uncovered_lines=sum(s.uncovered_lines for s in items),
    )


def _days(period: Period) -> list[date]:
    return [period.start + timedelta(days=i) for i in range(period.days)]


def build_cells(
    period: Period,
    lines: Iterable[SaleLine],
    expenses: Iterable[ExpenseItem] = (),
    own_expenses: Iterable[OwnExpense] = (),
    tax: TaxRule | None = None,
) -> Cells:
    """F12–F15 kataklari. Davrdan tashqari sotuv va xarajatlar e'tiborga olinmaydi."""
    acc: dict[CellKey, _Acc] = defaultdict(_Acc)

    for line in completed(x for x in lines if x.order_date in period):
        a = acc[CellKey(line.order_date, line.shop, line.sku)]
        rev = line.revenue
        a.revenue += rev
        a.commission += line.commission
        a.logistics += line.logistics
        a.units += line.amount
        a.lines += 1
        cost = line.cogs
        if cost is None:
            a.uncovered_lines += 1
        else:
            a.cogs += cost
            a.covered_revenue += rev
            a.covered_payout += rev - line.commission - line.logistics

    # Kun × do'kon bo'yicha SKU tushumlari — taqsimot og'irliklari (kataklar yaratilishidan oldin olinadi).
    sales_by_day: dict[date, list[CellKey]] = defaultdict(list)
    for key in sorted(acc, key=CellKey.order):
        sales_by_day[key.day].append(key)

    def spread(
        day: date, shops: Sequence[str] | None, put: Callable[[_Acc, Money], None], amount: Money
    ) -> None:
        """Summani kun bo'yicha SKU kataklariga tushum ulushida; tushum yo'q — taqsimlanmagan katak."""
        keys = [k for k in sales_by_day.get(day, ()) if shops is None or k.shop in shops]
        weights = [acc[k].revenue for k in keys]
        if keys and any(w > 0 for w in weights):
            for k, part in zip(keys, allocate(amount, weights), strict=True):
                put(acc[k], part)
        else:
            put(acc[CellKey(day, shops[0] if shops and len(shops) == 1 else "", None)], amount)

    for e in expenses:
        if e.day not in period:
            continue

        def put_uzum(a: _Acc, m: Money, c: ExpenseCategory = e.category) -> None:
            _add(a.uzum, c, m.amount)

        if e.sku is not None:
            put_uzum(acc[CellKey(e.day, e.shop, e.sku)], e.amount)
        else:
            spread(e.day, [e.shop], put_uzum, e.amount)

    for oe in own_expenses:

        def put_own(a: _Acc, m: Money, c: str = oe.category) -> None:
            _add(a.own, c, m.amount)

        for day in _days(period):
            part = own_expense_in_period(oe.expense, Period(day, day))
            if part.is_zero():
                continue
            if oe.sku is not None:
                put_own(acc[CellKey(day, oe.shop or "", oe.sku)], part)
            else:
                spread(day, None if oe.shop is None else [oe.shop], put_own, part)

    items: dict[CellKey, Statement] = {}
    for key in sorted(acc, key=CellKey.order):
        a = acc[key]
        revenue = Money(a.revenue, UZS)
        payout = Money(a.revenue - a.commission - a.logistics, UZS)
        tax_amount = tax.on(revenue, payout) if tax else ZERO
        uzum, own = _money_map(a.uzum), _money_map(a.own)
        overhead = sum((m.amount for m in (*uzum.values(), *own.values())), tax_amount.amount)
        if a.revenue == 0:
            deducted = Money(overhead, UZS)
        else:
            deducted = Money(overhead * a.covered_revenue / a.revenue, UZS)
        items[key] = Statement(
            revenue=revenue,
            commission=Money(a.commission, UZS),
            logistics=Money(a.logistics, UZS),
            cogs=Money(a.cogs, UZS),
            covered_revenue=Money(a.covered_revenue, UZS),
            covered_payout=Money(a.covered_payout, UZS),
            uzum_expenses=uzum,
            own_expenses=own,
            tax=tax_amount,
            expenses_deducted=deducted,
            units=a.units,
            lines=a.lines,
            uncovered_lines=a.uncovered_lines,
        )
    return Cells(period, items)


# --- Kutilayotgan foyda va solishtirish -----------------------------------------------------


def pending_profit(
    period: Period, lines: Iterable[SaleLine], window: Iterable[SaleLine], min_units: int = 50
) -> ExpectedProfit:
    """F16 bloki: davrdagi Jarayondagi qatorlar × R (R — ``window``: do'konning oxirgi 90 kuni)."""
    pending = [x for x in lines if x.order_date in period and x.group is StatusGroup.PROCESSING]
    return expected_profit(pending, realization_rate(window, min_units))


@dataclass(frozen=True, slots=True)
class CompareRow:
    """M5 ustunlari: joriy, tushumga nisbatan %, oldingi davr, farq."""

    code: str
    current: Money
    share_of_revenue: Decimal | None
    previous: Money
    diff: Money


def compare(current: Statement, previous: Statement) -> list[CompareRow]:
    """Ikki davr hisobot qatorlari: joriy davrda yo'q qator oldingisida bo'lsa ham ko'rsatiladi."""
    cur, prev = dict(current.rows()), dict(previous.rows())
    codes = [c for c, _ in current.rows()] + [c for c, _ in previous.rows() if c not in cur]
    return [
        CompareRow(
            code,
            cur.get(code, ZERO),
            ratio(cur.get(code, ZERO).amount, current.revenue.amount),
            prev.get(code, ZERO),
            cur.get(code, ZERO) - prev.get(code, ZERO),
        )
        for code in codes
    ]

"""Uzum to'lov prognozi — F38, kassa prognozi — F39 (02-funksiyalar.md M11; 08-tadqiqot.md §5).

To'lov jadvallari va foizlari biznes ma'lumoti (ADR-015): ``payout_schedules`` (do'kon, jadval, amal qilish
sanasi) va ``SEED_SCHEDULES`` dagi shartlar. Dam olish kunlari: shanba, yakshanba + berilgan bayramlar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from upcore.money import Currency, DecimalLike, Money, to_decimal, total

UZS = Currency.UZS


class ScheduleKind(StrEnum):
    DAILY = "daily"  # har ish kuni
    WEEKLY = "weekly"  # 7, 14, 21, 28
    BIWEEKLY = "biweekly"  # 7, 21
    MONTHLY = "monthly"  # 7


@dataclass(frozen=True, slots=True)
class ScheduleTerms:
    """Jadval shartlari: oy kunlari (``None`` — har ish kuni) va pul yechish foizi."""

    kind: ScheduleKind
    days_of_month: tuple[int, ...] | None
    fee_pct: Decimal
    valid_from: date = date(2026, 1, 1)


SEED_SCHEDULES: Mapping[ScheduleKind, ScheduleTerms] = {
    ScheduleKind.DAILY: ScheduleTerms(ScheduleKind.DAILY, None, Decimal("1.5")),
    ScheduleKind.WEEKLY: ScheduleTerms(ScheduleKind.WEEKLY, (7, 14, 21, 28), Decimal(1)),
    ScheduleKind.BIWEEKLY: ScheduleTerms(ScheduleKind.BIWEEKLY, (7, 21), Decimal(0)),
    ScheduleKind.MONTHLY: ScheduleTerms(ScheduleKind.MONTHLY, (7,), Decimal(0)),
}
URGENT_FEE_PCT = Decimal("2.5")  # shoshilinch yechish (seed)
DELAY_WORKDAYS = 4  # Uzum kechiktirishi mumkin bo'lgan ish kunlari (seed)


def is_workday(day: date, holidays: frozenset[date] = frozenset()) -> bool:
    return day.weekday() < 5 and day not in holidays


def next_workday(day: date, holidays: frozenset[date] = frozenset()) -> date:
    """``day`` ish kuni bo'lsa o'zi, aks holda keyingi ish kuni."""
    while not is_workday(day, holidays):
        day += timedelta(days=1)
    return day


def add_workdays(day: date, n: int, holidays: frozenset[date] = frozenset()) -> date:
    for _ in range(n):
        day = next_workday(day + timedelta(days=1), holidays)
    return day


def _scheduled_dates(terms: ScheduleTerms, start: date, end: date) -> list[date]:
    """[start; end] dagi jadval sanalari (dam olish kunlari keyingi ish kuniga surilmagan holda)."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if terms.days_of_month is None:
        return days
    return [d for d in days if d.day in terms.days_of_month]


def next_payout(
    after: date, terms: ScheduleTerms, holidays: frozenset[date] = frozenset()
) -> tuple[date, date]:
    """F38. ``after`` kunidan keyingi to'lov: (kutilgan sana, eng kech sana).

    Kutilgan = jadvaldagi navbatdagi sana (dam olish kuni → keyingi ish kuni); eng kech = + 4 ish kuni."""
    # Jadval sanasi har oyda bor; dam olish kunlariga surilganda ham 62 kun yetarli.
    for d in _scheduled_dates(terms, after + timedelta(days=1), after + timedelta(days=62)):
        expected = next_workday(d, holidays)
        if expected > after:
            return expected, add_workdays(expected, DELAY_WORKDAYS, holidays)
    raise ValueError(f"{terms.kind}: jadval sanasi topilmadi")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class PayoutEvent:
    """F38: kutilgan to'lov."""

    expected: date
    latest: date
    gross: Money  # Yakunlangan F6 − ushlanmalar
    fee: Money

    @property
    def net(self) -> Money:
        return self.gross - self.fee


def forecast_payouts(
    daily_net: Mapping[date, Money],
    terms: ScheduleTerms,
    holidays: frozenset[date] = frozenset(),
) -> list[PayoutEvent]:
    """F38. Kunlik summalar (o'sha kuni Yakunlangan bo'lgan F6 − ushlanmalar) navbatdagi to'lovga yig'iladi.

    Pul yechish foizi jadval shartidan; manfiy yig'indi (ushlanma ko'p) keyingi to'lovga o'tadi."""
    by_date: dict[date, Money] = {}
    latest: dict[date, date] = {}
    for day in sorted(daily_net):
        expected, late = next_payout(day, terms, holidays)
        by_date[expected] = by_date.get(expected, Money.zero(UZS)) + daily_net[day]
        latest[expected] = late
    events = []
    carry = Money.zero(UZS)
    for expected in sorted(by_date):
        gross = by_date[expected] + carry
        if gross.amount <= 0:
            carry = gross
            continue
        carry = Money.zero(UZS)
        events.append(PayoutEvent(expected, latest[expected], gross, gross * (terms.fee_pct / 100)))
    return events


def urgent_withdrawal_fee(amount: Money, fee_pct: DecimalLike = URGENT_FEE_PCT) -> Money:
    """F38: shoshilinch yechish foizi."""
    return amount * (to_decimal(fee_pct) / 100)


# --- F39 ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CashForecast:
    """F39 natijasi: kunlik qoldiq va birinchi kassa uzilishi kuni."""

    balances: Sequence[tuple[date, Money]]
    gap_day: date | None

    @property
    def minimum(self) -> Money:
        return min((b for _, b in self.balances), key=lambda m: m.amount)


def cash_forecast(
    opening: Money,
    start: date,
    inflows: Iterable[tuple[date, Money]],
    outflows: Iterable[tuple[date, Money]],
    days: int = 90,
) -> CashForecast:
    """F39. Kassa prognozi = boshlang'ich qoldiq + kutilgan kirimlar (F38) − rejalashtirilgan chiqimlar
    (xarid to'lovlari, takroriy xarajatlar), ``days`` kun. Istalgan kunda < 0 → kassa uzilishi."""
    delta: dict[date, list[Money]] = {}
    for d, m in inflows:
        delta.setdefault(d, []).append(m)
    for d, m in outflows:
        delta.setdefault(d, []).append(-m)
    balance, gap = opening, None
    balances = []
    for i in range(days):
        day = start + timedelta(days=i)
        balance += total(delta.get(day, []), UZS)
        balances.append((day, balance))
        if gap is None and balance.amount < 0:
            gap = day
    return CashForecast(tuple(balances), gap)

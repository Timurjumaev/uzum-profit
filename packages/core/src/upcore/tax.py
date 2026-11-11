"""Soliq profillari — F11 (02-funksiyalar.md; 08-tadqiqot.md §6).

Profil tashkilot sozlamasi, sana bo'yicha (``tax_profiles``); stavkalar ma'lumotnomasi ``ref_tax_rates``
(ADR-015). ``SEED_RATES`` — boshlang'ich yozuvlar (2026); standartlar buxgalter bilan tasdiqlanadi.

Rejimlar:
(a) aylanmadan foiz — stavka × baza (F3 standart yoki F6), P&L kataklarida (``upcore.pnl.TaxRule``);
(b) Uzum soliq agenti sifatida ushlaydi — summa Uzum xarajatlarida keladi, qayta hisoblanmaydi;
(c) QQS + foyda solig'i — oylik taxmin;
(d) yo'q.

ADR-058: profil endi **soliq qatorlari** (``TaxLine``) ro'yxati — foizli (``percent``) va qat'iy (``fixed``: so'm yoki
n × BHM; oy / chorak / yil). Eski profillar (``lines`` bo'sh) ``profile_lines`` orqali qatorlarga o'giriladi.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from upcore.metrics import ratio
from upcore.money import Currency, DecimalLike, Money, quantize, to_decimal
from upcore.pnl import TaxBase, TaxRule

UZS = Currency.UZS


class TaxRegime(StrEnum):
    TURNOVER = "turnover"  # (a)
    AGENT = "agent"  # (b)
    VAT_PROFIT = "vat_profit"  # (c)
    NONE = "none"  # (d)


@dataclass(frozen=True, slots=True)
class TaxRate:
    """Ma'lumotnoma yozuvi: soliq turi va stavkasi, ``valid_from`` dan."""

    code: str
    valid_from: date
    rate_pct: Decimal
    note: str = ""


SEED_RATES: tuple[TaxRate, ...] = (
    TaxRate(
        "turnover_individual", date(2026, 1, 1), Decimal(1), "YaTT, yillik daromad 1 mlrd so'mgacha"
    ),
    TaxRate("turnover_ecommerce", date(2026, 1, 1), Decimal(4), "e-tijorat yuridik shaxs, bazaviy"),
    TaxRate("profit", date(2026, 1, 1), Decimal(15), "foyda solig'i, bazaviy"),
    TaxRate(
        "vat", date(2026, 1, 1), Decimal(12), "QQS, Soliq kodeksi 36-bob (2026-10-24 tekshirildi)"
    ),
)


@dataclass(frozen=True, slots=True)
class AmountValue:
    """Ma'lumotnoma yozuvi: so'mdagi qiymat (BHM, chegaralar), ``valid_from`` dan (``ref_amounts``)."""

    code: str
    valid_from: date
    amount: Decimal
    note: str = ""


BHM = "bhm"

SEED_AMOUNTS: tuple[AmountValue, ...] = (
    AmountValue(BHM, date(2025, 8, 1), Decimal(412_000), "bazaviy hisoblash miqdori"),
    AmountValue(
        BHM,
        date(2026, 9, 1),
        Decimal(440_000),
        "PF-115 (2026-06-23); aksar manbalarda 1 sentabrdan, bittasida 1 iyuldan — matn bilan tekshiriladi",
    ),
)


class LineKind(StrEnum):
    PERCENT = "percent"  # baza × stavka (har kun, katak darajasida)
    FIXED = "fixed"  # qat'iy summa yoki n × BHM, davr kunlariga teng taqsimlanadi


class FixedPeriod(StrEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


@dataclass(frozen=True, slots=True)
class TaxLine:
    """Soliq qatori (ADR-058). ``percent``: ``rate_pct`` (0 < stavka ≤ 100) va ``base``; ``fixed``: aynan bittasi —
    ``amount`` (so'm) yoki ``bhm_count`` (n × BHM) — va ``period``."""

    name: str
    kind: LineKind
    rate_pct: Decimal = Decimal(0)
    base: TaxBase = TaxBase.REVENUE
    amount: Decimal | None = None
    bhm_count: Decimal | None = None
    period: FixedPeriod = FixedPeriod.MONTH

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("soliq qatori nomi bo'sh")
        if self.kind is LineKind.PERCENT:
            if not Decimal(0) < self.rate_pct <= Decimal(100):
                raise ValueError("foizli qator: stavka 0 dan katta va 100 dan oshmasligi kerak")
            if self.amount is not None or self.bhm_count is not None:
                raise ValueError("foizli qatorda summa yoki BHM soni bo'lmaydi")
            return
        if self.rate_pct != 0:
            raise ValueError("qat'iy qatorda stavka bo'lmaydi")
        if (self.amount is None) == (self.bhm_count is None):
            raise ValueError("qat'iy qator: summa yoki BHM sonidan aynan bittasi kerak")
        value = self.amount if self.amount is not None else self.bhm_count
        if value is None or value <= 0:
            raise ValueError("qat'iy qator: qiymat 0 dan katta bo'lishi kerak")


@dataclass(frozen=True, slots=True)
class TaxProfile:
    """Tashkilot soliq profili ``valid_from`` sanasidan."""

    valid_from: date
    regime: TaxRegime
    rate_pct: Decimal = Decimal(0)  # (a)
    base: TaxBase = TaxBase.REVENUE  # (a)
    vat_pct: Decimal = Decimal(0)  # (c)
    profit_pct: Decimal = Decimal(0)  # (c)
    lines: tuple[TaxLine, ...] = ()  # ADR-058; bo'sh bo'lsa — eski ustunlardan (``profile_lines``)

    def __post_init__(self) -> None:
        names = [line.name.strip().casefold() for line in self.lines]
        if len(set(names)) != len(names):
            raise ValueError("profilda soliq qatori nomlari takrorlanmasligi kerak")


def rate_on(rates: Iterable[TaxRate], code: str, day: date) -> Decimal | None:
    """Ma'lumotnomadan sanada amaldagi stavka."""
    best = None
    for r in rates:
        if (
            r.code == code
            and r.valid_from <= day
            and (best is None or r.valid_from > best.valid_from)
        ):
            best = r
    return None if best is None else best.rate_pct


def profile_on(profiles: Iterable[TaxProfile], day: date) -> TaxProfile | None:
    """Sanada amaldagi profil (``valid_from <= day`` bo'lgan eng oxirgisi)."""
    best = None
    for p in profiles:
        if p.valid_from <= day and (best is None or p.valid_from > best.valid_from):
            best = p
    return best


def amount_on(values: Iterable[AmountValue], code: str, day: date) -> Decimal | None:
    """Ma'lumotnomadan sanada amaldagi so'm qiymati (``None`` — o'sha sanada qiymat yo'q)."""
    best = None
    for v in values:
        if (
            v.code == code
            and v.valid_from <= day
            and (best is None or v.valid_from > best.valid_from)
        ):
            best = v
    return None if best is None else best.amount


def profile_lines(profile: TaxProfile) -> tuple[TaxLine, ...]:
    """Profilning soliq qatorlari. ``lines`` bo'sh bo'lsa — eski ustunlardan: aylanmadan foiz rejimi bitta foizli qator;
    agent, QQS + foyda (hisoblanmaydi) va "yo'q" — qatorsiz."""
    if profile.lines:
        return profile.lines
    if profile.regime is TaxRegime.TURNOVER and profile.rate_pct > 0:
        return (TaxLine("Soliq", LineKind.PERCENT, profile.rate_pct, profile.base),)
    return ()


def percent_rules(profiles: Iterable[TaxProfile], day: date) -> tuple[tuple[str, TaxRule], ...]:
    """Kunning foizli qatorlari: (qator nomi, ``TaxRule``) — P&L kataklarida qo'llanadi."""
    p = profile_on(profiles, day)
    if p is None:
        return ()
    return tuple(
        (line.name, TaxRule(line.rate_pct, line.base))
        for line in profile_lines(p)
        if line.kind is LineKind.PERCENT
    )


def _period_bounds(day: date, period: FixedPeriod) -> tuple[date, date]:
    if period is FixedPeriod.MONTH:
        first = day.replace(day=1)
        return first, first.replace(day=calendar.monthrange(day.year, day.month)[1])
    if period is FixedPeriod.QUARTER:
        month = (day.month - 1) // 3 * 3 + 1
        first = date(day.year, month, 1)
        return first, date(day.year, month + 2, calendar.monthrange(day.year, month + 2)[1])
    return date(day.year, 1, 1), date(day.year, 12, 31)


def fixed_on_day(line: TaxLine, day: date, bhm: Callable[[date], Decimal | None]) -> Decimal | None:
    """Qat'iy qatorning ``day`` kuniga to'g'ri keladigan summasi (so'm, tiyin). Davr summasi (``amount`` yoki n × BHM,
    **davr boshidagi** BHM) davr kunlariga kumulyativ yaxlitlash bilan taqsimlanadi — har qanday ketma-ket kunlar
    yig'indisi aniq (butun davr — davr summasiga teng). ``None`` — BHM o'sha sanada ma'lumotnomada yo'q (0 emas:
    hisoblanmagan soliq yashirilmaydi, tamoyil 9)."""
    start, end = _period_bounds(day, line.period)
    if line.amount is not None:
        total = line.amount
    else:
        value = bhm(start)
        if value is None or line.bhm_count is None:
            return None
        total = value * line.bhm_count
    n = (end - start).days + 1
    k = (day - start).days + 1
    places = UZS.places
    return quantize(total * k / n, places) - quantize(total * (k - 1) / n, places)


def fixed_daily(
    profiles: Iterable[TaxProfile], day: date, bhm: Callable[[date], Decimal | None]
) -> dict[str, Decimal | None]:
    """Kunning qat'iy soliqlari: qator nomi → summa (``None`` — BHM noma'lum). Amaldagi profil sanasidan boshlab;
    profil almashsa — yangi profilning qatorlari (har kun mustaqil)."""
    p = profile_on(profiles, day)
    if p is None:
        return {}
    return {
        line.name: fixed_on_day(line, day, bhm)
        for line in profile_lines(p)
        if line.kind is LineKind.FIXED
    }


def daily_rule(profiles: Iterable[TaxProfile]) -> Callable[[date], TaxRule | None]:
    """F11 (a) uchun P&L'ga beriladigan kunlik qoida: ``build_cells(..., tax=daily_rule(profiles))``.

    (b), (c), (d) rejimlarida katakka soliq yozilmaydi: (b) xarajatlarda, (c) oylik taxmin alohida."""
    items = list(profiles)

    def rule(day: date) -> TaxRule | None:
        p = profile_on(items, day)
        if p is None or p.regime is not TaxRegime.TURNOVER:
            return None
        return TaxRule(p.rate_pct, p.base)

    return rule


_NOT_CALCULATED = frozenset({TaxRegime.VAT_PROFIT, TaxRegime.AGENT})


def uncalculated_regimes(
    profiles: Iterable[TaxProfile], start: date, end: date
) -> frozenset[TaxRegime]:
    """F11: ``start``…``end`` kunlarida amalda bo'lgan rejimlar ichida soliq **hisoblanmaydiganlari** — QQS + foyda
    (c, oylik taxmin hali yo'q) va Uzum agenti (b, summa faqat Uzum xarajatlarida kelsa hisobga olinadi). Sof foyda bu
    kunlarda soliqsiz — UI shuni ochiq aytadi (tamoyil 9, 09-audit K7). Profilsiz davr va "yo'q" rejimi foydalanuvchi
    tanlovi — bu yerga kirmaydi."""
    items = list(profiles)
    active = []
    first = profile_on(items, start)
    if first is not None:
        active.append(first)
    active += [p for p in items if start < p.valid_from <= end]
    return frozenset(p.regime for p in active) & _NOT_CALCULATED


@dataclass(frozen=True, slots=True)
class VatProfitEstimate:
    """F11 (c) oylik taxmini."""

    vat: Money
    profit_tax: Money

    @property
    def total(self) -> Money:
        return self.vat + self.profit_tax


def vat_profit_estimate(
    revenue: Money,
    profit_before_tax: Money,
    vat_pct: DecimalLike,
    profit_pct: DecimalLike,
    input_vat: Money | None = None,
) -> VatProfitEstimate:
    """F11 (c). QQS = narx ichidagi QQS (tushum × v / (100 + v)) − kirim QQS (bo'lsa, ≥ 0);
    foyda solig'i = max(0, soliqdan oldingi foyda − QQS) × p / 100. Taxmin — UI'da belgilanadi."""
    v, p = to_decimal(vat_pct), to_decimal(profit_pct)
    output_vat = revenue * (v / (100 + v))
    vat = output_vat - input_vat if input_vat is not None else output_vat
    if vat.amount < 0:
        vat = Money.zero(revenue.currency)
    base = profit_before_tax - vat
    profit_tax = base * (p / 100) if base.amount > 0 else Money.zero(revenue.currency)
    return VatProfitEstimate(vat, profit_tax)


def effective_rate(tax: Money, revenue: Money) -> Decimal | None:
    """Soliqning tushumga nisbati (taqqoslash uchun)."""
    return ratio(tax.amount, revenue.amount)

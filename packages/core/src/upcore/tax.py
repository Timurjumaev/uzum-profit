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

F50 (B4.80): yillik tushum chegarasi — soliq to'lovchi turi (``Taxpayer``) bo'yicha chegara ma'lumotnomadan, yil boshidan
tushum uning 80% iga yetsa ogohlantirish (rejim o'zi almashmaydi).
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from upcore.metrics import ManualExpense, ratio
from upcore.money import Currency, DecimalLike, Money, quantize, to_decimal
from upcore.pnl import TAX_PREFIX, OwnExpense, TaxBase, TaxRule, TaxRules

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
# F50 chegaralari (ADR-058; 08 §6): so'mda, MChJ — BHM sonida (so'm = son × sanadagi BHM).
LIMIT_INDIVIDUAL = "revenue_limit_individual"
LIMIT_SELF_EMPLOYED = "revenue_limit_self_employed"
LIMIT_LLC_BHM = "revenue_limit_llc_bhm"

SEED_AMOUNTS: tuple[AmountValue, ...] = (
    AmountValue(BHM, date(2025, 8, 1), Decimal(412_000), "bazaviy hisoblash miqdori"),
    AmountValue(
        BHM,
        date(2026, 9, 1),
        Decimal(440_000),
        "PF-115 (2026-06-23); aksar manbalarda 1 sentabrdan, bittasida 1 iyuldan — matn bilan tekshiriladi",
    ),
    AmountValue(
        LIMIT_INDIVIDUAL,
        date(2026, 1, 1),
        Decimal(1_000_000_000),
        "YaTT aylanma solig'i: yillik daromad 1 mlrd so'mgacha (08 §6)",
    ),
    AmountValue(
        LIMIT_SELF_EMPLOYED,
        date(2026, 1, 1),
        Decimal(100_000_000),
        "o'zini o'zi band qilgan: yillik daromad 100 mln so'mgacha ozod (08 §6)",
    ),
    AmountValue(
        LIMIT_LLC_BHM,
        date(2026, 1, 1),
        Decimal(12_000),
        "MChJ aylanma solig'i: yillik aylanma 12 000 BHM gacha — BHM soni, so'm emas (08 §6)",
    ),
)


class Taxpayer(StrEnum):
    """Soliq to'lovchi turi (F50 chegarasi uchun; profilda ixtiyoriy)."""

    INDIVIDUAL = "individual"  # YaTT
    LLC = "llc"  # MChJ
    SELF_EMPLOYED = "self_employed"  # o'zini o'zi band qilgan


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
    taxpayer: Taxpayer | None = None  # F50; ``None`` — ko'rsatilmagan (chegara ogohlantirishi yo'q)

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


def daily_rules(profiles: Iterable[TaxProfile]) -> Callable[[date], TaxRules]:
    """F11 foizli qatorlari uchun P&L'ga beriladigan kunlik qoidalar: ``build_cells(..., tax=daily_rules(profiles))``.
    Qat'iy qatorlar — ``fixed_expenses`` (o'z xarajati mexanizmi bilan). Agent, QQS + foyda (hisoblanmaydi) va "yo'q"
    rejimlarida foizli qator yo'q."""
    items = list(profiles)
    return lambda day: percent_rules(items, day)


def fixed_expenses(
    profiles: Iterable[TaxProfile],
    bhm: Callable[[date], Decimal | None],
    start: date,
    end: date,
) -> tuple[list[OwnExpense], bool]:
    """``start``…``end`` kunlarining qat'iy soliqlari — kunlik o'z xarajatlari (``tax:<qator nomi>`` toifasida, tashkilot
    darajasida): ``build_cells`` ularni F10 kabi kataklarga taqsimlaydi, hisobotda esa "Soliq" ostida ko'rinadi. Ikkinchi
    qiymat: BHM ma'lumotnomada yo'q kun bo'lsa ``True`` (o'sha kunlar hisobga kirmadi — UI aytadi)."""
    items = list(profiles)
    out: list[OwnExpense] = []
    missing = False
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        for name, amount in fixed_daily(items, day, bhm).items():
            if amount is None:
                missing = True
            elif amount:
                out.append(
                    OwnExpense(
                        ManualExpense(Money.rounded(amount, UZS), day, day), TAX_PREFIX + name
                    )
                )
    return out, missing


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


# --- F50. Yillik tushum chegarasi (B4.80) -----------------------------------------------------------------------------

WARN_SHARE = Decimal("0.8")  # ADR-058: chegaraning 80% i — "rejimni o'zgartirish vaqti"


class LimitLevel(StrEnum):
    OK = "ok"  # < 80%
    NEAR = "near"  # ≥ 80%
    OVER = "over"  # ≥ 100%


def revenue_limit(taxpayer: Taxpayer, day: date, values: Iterable[AmountValue]) -> Money | None:
    """F50 chegarasi sanada: YaTT va o'zini o'zi band qilgan — so'mda; MChJ — BHM soni × sanadagi BHM. Ma'lumotnomada
    qiymat bo'lmasa ``None``."""
    items = list(values)
    if taxpayer is Taxpayer.LLC:
        count, bhm = amount_on(items, LIMIT_LLC_BHM, day), amount_on(items, BHM, day)
        return None if count is None or bhm is None else Money(count * bhm, UZS)
    code = LIMIT_INDIVIDUAL if taxpayer is Taxpayer.INDIVIDUAL else LIMIT_SELF_EMPLOYED
    value = amount_on(items, code, day)
    return None if value is None else Money(value, UZS)


@dataclass(frozen=True, slots=True)
class RevenueLimit:
    """F50 holati: ``revenue`` — yil boshidan ``day`` gacha tushum (F3, butun tashkilot), ``limit`` — chegara."""

    taxpayer: Taxpayer
    year: int
    revenue: Money
    limit: Money

    def __post_init__(self) -> None:
        if self.limit.amount <= 0:
            raise ValueError("tushum chegarasi 0 dan katta bo'lishi kerak")

    @property
    def share(self) -> Decimal:
        """Tushum / chegara (6 xona)."""
        return ratio(self.revenue.amount, self.limit.amount) or Decimal(0)

    @property
    def level(self) -> LimitLevel:
        """≥ 100% — oshdi; ≥ 80% — yaqin (ogohlantirish); qolgani — joyida."""
        if self.revenue.amount >= self.limit.amount:
            return LimitLevel.OVER
        if self.revenue.amount >= self.limit.amount * WARN_SHARE:
            return LimitLevel.NEAR
        return LimitLevel.OK


def revenue_limit_status(
    profiles: Iterable[TaxProfile], day: date, revenue_ytd: Money, values: Iterable[AmountValue]
) -> RevenueLimit | None:
    """F50. Yillik tushum chegarasi: sanadagi profilning soliq to'lovchi turi bo'yicha chegara va yil boshidan tushum
    (F3). Profil, tur yoki chegara bo'lmasa (yoki chegara ≤ 0) — ``None``. Rejim o'zi almashmaydi, faqat ogohlantirish."""
    profile = profile_on(profiles, day)
    if profile is None or profile.taxpayer is None:
        return None
    limit = revenue_limit(profile.taxpayer, day, values)
    if limit is None or limit.amount <= 0:
        return None
    return RevenueLimit(profile.taxpayer, day.year, revenue_ytd, limit)

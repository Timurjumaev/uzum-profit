"""Soliq profillari — F11 (02-funksiyalar.md; 08-tadqiqot.md §6).

Profil tashkilot sozlamasi, sana bo'yicha (``tax_profiles``); stavkalar ma'lumotnomasi ``ref_tax_rates``
(ADR-015). ``SEED_RATES`` — boshlang'ich yozuvlar (2026); standartlar buxgalter bilan tasdiqlanadi.

Rejimlar:
(a) aylanmadan foiz — stavka × baza (F3 standart yoki F6), P&L kataklarida (``upcore.pnl.TaxRule``);
(b) Uzum soliq agenti sifatida ushlaydi — summa Uzum xarajatlarida keladi, qayta hisoblanmaydi;
(c) QQS + foyda solig'i — oylik taxmin;
(d) yo'q.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from upcore.metrics import ratio
from upcore.money import DecimalLike, Money, to_decimal
from upcore.pnl import TaxBase, TaxRule


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
    TaxRate("vat", date(2026, 1, 1), Decimal(12), "QQS"),
)


@dataclass(frozen=True, slots=True)
class TaxProfile:
    """Tashkilot soliq profili ``valid_from`` sanasidan."""

    valid_from: date
    regime: TaxRegime
    rate_pct: Decimal = Decimal(0)  # (a)
    base: TaxBase = TaxBase.REVENUE  # (a)
    vat_pct: Decimal = Decimal(0)  # (c)
    profit_pct: Decimal = Decimal(0)  # (c)


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

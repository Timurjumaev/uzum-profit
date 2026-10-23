"""Valyuta kurslari: CBU kursini o'qish, sana bo'yicha tanlash, so'mga o'tkazish (F20).

Kurs — 1 birlik valyuta necha so'm (CBU ``Rate / Nominal``), 6 xona.
Bu modul sof: kurslar ro'yxati tashqaridan beriladi (bazadagi ``fx_rates``); tarmoqqa chiqmaydi.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from upcore.money import (
    Currency,
    DecimalLike,
    Money,
    MoneyError,
    round_rate,
    to_decimal,
)


class RateSource(StrEnum):
    """Kurs rejimlari (02-funksiyalar.md M9): CBU, qo'lda, kartadan yechilgan summadan."""

    CBU = "cbu"
    MANUAL = "manual"
    EFFECTIVE = "effective"


class FxError(ValueError):
    """Kurs topilmadi yoki noto'g'ri."""


@dataclass(frozen=True, slots=True)
class FxRate:
    """``day`` sanasidan amal qiladigan kurs: 1 ``currency`` = ``rate`` so'm."""

    day: date
    currency: Currency
    rate: Decimal
    source: RateSource = RateSource.CBU

    def __post_init__(self) -> None:
        currency = Currency(self.currency)
        if currency is Currency.UZS:
            raise FxError("so'm uchun kurs kerak emas")
        rate = round_rate(self.rate)
        if rate <= 0:
            raise FxError(f"kurs musbat bo'lishi kerak: {self.rate}")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "rate", rate)
        object.__setattr__(self, "source", RateSource(self.source))


@dataclass(frozen=True, slots=True)
class RateLookup:
    """Sana bo'yicha topilgan kurs. ``rate.day < requested`` — dam olish yoki bayram kuni."""

    requested: date
    rate: FxRate

    @property
    def is_fallback(self) -> bool:
        return self.rate.day != self.requested

    @property
    def gap_days(self) -> int:
        return (self.requested - self.rate.day).days


def parse_cbu_row(row: Mapping[str, Any]) -> FxRate:
    """CBU JSON qatori → ``FxRate``.

    Namuna: ``{"Ccy": "CNY", "Nominal": "1", "Rate": "1792.29", "Date": "22.10.2026"}``.
    Nominal 1 dan katta bo'lishi mumkin (masalan, 10 JPY), shuning uchun kurs = Rate / Nominal.
    """
    try:
        currency = Currency(str(row["Ccy"]).strip().upper())
        nominal = to_decimal(str(row.get("Nominal") or "1"))
        rate = to_decimal(str(row["Rate"]))
        day = datetime.strptime(str(row["Date"]).strip(), "%d.%m.%Y").date()
    except (KeyError, ValueError, MoneyError) as exc:
        raise FxError(f"CBU qatori tushunarsiz: {dict(row)!r}") from exc
    if nominal <= 0:
        raise FxError(f"CBU nominali noto'g'ri: {nominal}")
    return FxRate(day=day, currency=currency, rate=rate / nominal, source=RateSource.CBU)


def parse_cbu_rows(rows: Iterable[Mapping[str, Any]]) -> list[FxRate]:
    """CBU javobidagi qatorlardan bizga ma'lum valyutalarnikini oladi, qolganini tashlaydi."""
    known = {c.value for c in Currency}
    return [parse_cbu_row(r) for r in rows if str(r.get("Ccy", "")).strip().upper() in known]


def rate_on(rates: Iterable[FxRate], currency: Currency | str, day: date) -> RateLookup:
    """``day`` uchun amaldagi kurs: shu sanadagi yoki undan oldingi eng oxirgi kurs (F20).

    CBU dam olish va bayram kunlari kurs e'lon qilmaydi — oxirgi ish kunining kursi amal qiladi.
    Kelajakdagi kurs hech qachon olinmaydi. Mos kurs bo'lmasa — ``FxError`` (raqam o'ylab topilmaydi).
    """
    ccy = Currency(currency)
    best: FxRate | None = None
    for r in rates:
        if r.currency is ccy and r.day <= day and (best is None or r.day > best.day):
            best = r
    if best is None:
        raise FxError(f"{ccy} uchun {day.isoformat()} sanasigacha kurs yo'q")
    return RateLookup(requested=day, rate=best)


def to_uzs(money: Money, rate: FxRate | None = None) -> Money:
    """Summani so'mga o'tkazadi: summa × kurs, 2 xonaga yaxlitlanadi (F20).

    So'm summasi kurssiz o'zgarishsiz qaytadi.
    """
    if money.currency is Currency.UZS:
        return money
    if rate is None:
        raise FxError(f"{money.currency} uchun kurs berilmagan")
    if rate.currency is not money.currency:
        raise FxError(f"kurs valyutasi {rate.currency}, summa valyutasi {money.currency}")
    return Money(money.amount * rate.rate, Currency.UZS)


def effective_rate(paid: Money, charged: Money) -> Decimal:
    """Kartadan yechilgan summadan effektiv kurs: 1 birlik ``paid`` = natija × ``charged`` (F20).

    Masalan, 1 000 CNY uchun kartadan 142,50 USD yechildi → 0,1425 (USD / CNY).
    ``charged`` so'mda bo'lsa natija to'g'ridan-to'g'ri so'mdagi kurs.
    """
    if paid.amount <= 0 or charged.amount <= 0:
        raise FxError("effektiv kurs uchun summalar musbat bo'lishi kerak")
    if paid.currency is charged.currency:
        raise FxError("effektiv kurs uchun valyutalar har xil bo'lishi kerak")
    return round_rate(charged.amount / paid.amount)


def effective_fx_rate(
    day: date, paid: Money, charged: Money, charged_rate: FxRate | None = None
) -> FxRate:
    """Kartadan yechilgan summadan so'mdagi kurs (kurs rejimi 3, F20).

    Karta so'mda bo'lsa: kurs = yechilgan so'm / to'langan summa. Karta boshqa valyutada bo'lsa
    (masalan USD), uning kursi ``charged_rate`` (odatda CBU, to'lov sanasi) bilan so'mga o'tkaziladi:
    1 000 CNY → 142,50 USD, USD = 12 650 so'm → CNY = 142,50 × 12 650 / 1 000 = 1 802,625 so'm.
    """
    if paid.currency is Currency.UZS:
        raise FxError("so'mda to'langan summa uchun kurs kerak emas")
    if charged.currency is Currency.UZS:
        uzs_per_charged = Decimal(1)
    elif charged_rate is None or charged_rate.currency is not charged.currency:
        raise FxError(f"yechilgan summa valyutasi {charged.currency} uchun kurs kerak")
    else:
        uzs_per_charged = charged_rate.rate
    effective_rate(paid, charged)  # musbatlik va valyutalar tekshiruvi
    # Oraliq yaxlitlashsiz: bitta bo'lish, oxirida 6 xona.
    rate = charged.amount * uzs_per_charged / paid.amount
    return FxRate(day=day, currency=paid.currency, rate=rate, source=RateSource.EFFECTIVE)


def manual_rate(day: date, currency: Currency | str, rate: DecimalLike) -> FxRate:
    """Sotuvchi qo'lda kiritgan kurs (``RateSource.MANUAL``)."""
    return FxRate(
        day=day, currency=Currency(currency), rate=to_decimal(rate), source=RateSource.MANUAL
    )

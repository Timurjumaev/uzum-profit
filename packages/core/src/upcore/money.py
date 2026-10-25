"""Pul: Decimal, valyutalar, yaxlitlash (02-funksiyalar.md, "Umumiy qoidalar"; ADR-007).

- Pul faqat ``Decimal``; ``float`` qabul qilinmaydi (xato beradi).
- So'm 2 xona, chet el valyutasi 4 xona, kurs 6 xona.
- Yaxlitlash: ``ROUND_HALF_UP`` (0,5 yuqoriga) — buxgalteriyadagi odatiy usul.
- Turli valyutadagi summalar to'g'ridan-to'g'ri qo'shilmaydi: avval kurs bilan so'mga (``upcore.fx``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum


class Currency(StrEnum):
    """ISO 4217 kodlari. Yangi valyuta qo'shish uchun shu ro'yxatga yoziladi."""

    UZS = "UZS"
    USD = "USD"
    CNY = "CNY"
    RUB = "RUB"
    EUR = "EUR"

    @property
    def places(self) -> int:
        """Saqlashdagi kasr xonalari: so'm 2, qolganlari 4."""
        return 2 if self is Currency.UZS else 4


RATE_PLACES = 6

type DecimalLike = Decimal | int | str


class MoneyError(ValueError):
    """Pul bilan noto'g'ri amal (float, turli valyuta, noto'g'ri son)."""


def to_decimal(value: DecimalLike) -> Decimal:
    """``Decimal`` ga aylantiradi. ``float`` va ``bool`` rad etiladi, NaN va cheksizlik ham."""
    if type(value) is Decimal and value.is_finite():
        return value
    if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
        raise MoneyError(f"pul uchun Decimal, int yoki str kerak, {type(value).__name__} berildi")
    try:
        result = Decimal(value.strip()) if isinstance(value, str) else Decimal(value)
    except InvalidOperation as exc:
        raise MoneyError(f"son emas: {value!r}") from exc
    if not result.is_finite():
        raise MoneyError(f"son chekli bo'lishi kerak: {value!r}")
    return result


_EXPONENTS = {p: Decimal(1).scaleb(-p) for p in range(13)}


def quantize(value: Decimal, places: int) -> Decimal:
    """``places`` xonaga ROUND_HALF_UP bilan yaxlitlaydi."""
    exp = _EXPONENTS.get(places) or Decimal(1).scaleb(-places)
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def round_rate(value: DecimalLike) -> Decimal:
    """Kursni 6 xonaga yaxlitlaydi."""
    return quantize(to_decimal(value), RATE_PLACES)


@dataclass(frozen=True, slots=True)
class Money:
    """Summa va valyuta. Summa doim valyutaning xonalariga yaxlitlangan holda saqlanadi."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        currency = self.currency if type(self.currency) is Currency else Currency(self.currency)
        amount = self.amount
        if type(amount) is not Decimal or not amount.is_finite():
            amount = to_decimal(amount)  # tekshiruv va xato matni shu yerda
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "amount", quantize(amount, currency.places))

    @classmethod
    def _exact(cls, amount: Decimal, currency: Currency) -> Money:
        """Yaxlitlangan summalar yig'indisi/ayirmasi — qayta yaxlitlash shart emas (tez yo'l)."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "amount", amount)
        object.__setattr__(obj, "currency", currency)
        return obj

    @classmethod
    def rounded(cls, amount: Decimal, currency: Currency) -> Money:
        """Tez yo'l: tayyor ``Decimal`` (chekli) va ``Currency`` — faqat yaxlitlanadi (ko'p sonli natijalar uchun,
        masalan P&L kataklari)."""
        return cls._exact(quantize(amount, currency.places), currency)

    @classmethod
    def of(cls, amount: DecimalLike, currency: Currency | str) -> Money:
        return cls(to_decimal(amount), Currency(currency))

    @classmethod
    def zero(cls, currency: Currency | str) -> Money:
        return cls(Decimal(0), Currency(currency))

    def _same(self, other: Money) -> None:
        if self.currency is not other.currency:
            raise MoneyError(f"turli valyuta: {self.currency} va {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money._exact(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money._exact(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money._exact(-self.amount, self.currency)

    def __mul__(self, factor: DecimalLike) -> Money:
        return Money(self.amount * to_decimal(factor), self.currency)

    __rmul__ = __mul__

    def __lt__(self, other: Money) -> bool:
        self._same(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._same(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._same(other)
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        return self.amount == 0

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


def total(items: Sequence[Money], currency: Currency | str) -> Money:
    """Bir valyutadagi summalar yig'indisi (bo'sh ro'yxat → 0)."""
    result = Money.zero(currency)
    for item in items:
        result += item
    return result


def allocate(amount: Money, weights: Sequence[DecimalLike]) -> list[Money]:
    """Summani og'irliklarga mutanosib bo'ladi; qismlar yig'indisi summaga aniq teng.

    Yaxlitlash qoldig'i eng katta og'irlikli qatorga qo'shiladi (teng bo'lsa — birinchisiga).
    F20 dagi taqsimotlar (dona, vazn, hajm, qiymat, qo'lda) shu funksiya ustida quriladi.
    """
    ws = [to_decimal(w) for w in weights]
    if not ws:
        raise MoneyError("taqsimot uchun kamida bitta qator kerak")
    if any(w < 0 for w in ws):
        raise MoneyError("og'irlik manfiy bo'lmasligi kerak")
    if sum(ws, Decimal(0)) == 0:
        raise MoneyError("og'irliklar yig'indisi nol")
    cur = amount.currency
    return [Money._exact(p, cur) for p in split(amount.amount, ws, cur.places)]


def split(amount: Decimal, weights: Sequence[Decimal], places: int) -> list[Decimal]:
    """``allocate`` ning xom ``Decimal`` ko'rinishi (tez yo'l, natija bir xil): ``amount`` — ``places`` xonaga
    yaxlitlangan, og'irliklar manfiy emas va yig'indisi musbat (chaqiruvchi tekshiradi)."""
    weight_sum = sum(weights, Decimal(0))
    exp = _EXPONENTS.get(places) or Decimal(1).scaleb(-places)
    parts = [(amount * w / weight_sum).quantize(exp, rounding=ROUND_HALF_UP) for w in weights]
    remainder = amount - sum(parts, Decimal(0))
    largest = max(range(len(weights)), key=lambda i: (weights[i], -i))
    parts[largest] += remainder
    return parts

"""Uzum xarajatlari klassifikatori — F9 manbasi (02-funksiyalar.md F9, M8; 08-tadqiqot.md §4).

``finance/expenses`` qatorlari → ``ExpenseRecord``: normallashtirilgan kod, toifa, yo'nalish, aniq summa,
bog'langan buyurtma/tovar va P&L'ga kirish-kirmasligi (sababi bilan).

Kod lug'ati biznes ma'lumoti (ADR-015): ishlash vaqtida bazadagi ``expense_codes`` dan ``CodeBook``
sifatida beriladi. ``SEED_CODEBOOK`` — shu jadvalning boshlang'ich yozuvlari (08 §4), testlar ham undan
foydalanadi. Kirill/lotin variantlari va ``BALANCE_CORRECTION`` semantikasi B2.11 da real ma'lumotda tasdiqlanadi.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from upcore.metrics import date_from_epoch_ms
from upcore.money import Currency, Money, to_decimal

# --- Kod normallashtirish -------------------------------------------------------------------

# Uzum kodlarida kirill harflar lotin ko'rinishida keladi (C000003 kirill C bilan). Kirill → lotin.
_HOMOGLYPHS = str.maketrans(
    {
        "\u0410": "A",
        "\u0412": "B",
        "\u0421": "C",
        "\u0415": "E",
        "\u041d": "H",
        "\u041a": "K",
        "\u041c": "M",
        "\u041e": "O",
        "\u0420": "P",
        "\u0422": "T",
        "\u0425": "X",
        "\u0423": "Y",
    }
)
# "U000120" (legacy) va "Y000120" (qo'llanma) — bitta kod: harf + raqamlar ko'rinishida U → Y.
_U_CODE = re.compile(r"^U(?=\d+$)")


def normalize_code(code: str | None) -> str:
    """Xarajat kodini yagona ko'rinishga keltiradi (F9).

    Bo'shliqlar olib tashlanadi, katta harf; kirill o'xshash harflar → lotin (U+0421 → C, U+0423 → Y);
    ``U000120`` → ``Y000120``. Kodsiz qator → bo'sh satr.
    """
    text = (code or "").strip().upper().translate(_HOMOGLYPHS)
    return _U_CODE.sub("Y", text)


# --- Toifalar va lug'at ---------------------------------------------------------------------


class ExpenseCategory(StrEnum):
    """Uzum xarajat toifalari (M8). P&L'ga kirishi ``in_pnl`` da."""

    ADVERTISING = "advertising"
    STORAGE = "storage"
    RETURN_STORAGE = "return_storage"
    FINE = "fine"
    PHOTO_STUDIO = "photo_studio"
    WITHDRAWAL_FEE = "withdrawal_fee"
    PAID_SHIPPING = "paid_shipping"
    COMPENSATION = "compensation"
    LOGISTICS = "logistics"
    LOGISTICS_REFUND = "logistics_refund"
    BALANCE_CORRECTION = "balance_correction"
    OTHER = "other"

    @property
    def in_pnl(self) -> bool:
        """F9 ga kiradimi. Logistika F5 da sotuv qatoridan olinadi (qayta ayrilmaydi);
        ``BALANCE_CORRECTION`` xarajat emas."""
        return self not in _NOT_IN_PNL


_NOT_IN_PNL = frozenset(
    {
        ExpenseCategory.LOGISTICS,
        ExpenseCategory.LOGISTICS_REFUND,
        ExpenseCategory.BALANCE_CORRECTION,
    }
)


@dataclass(frozen=True, slots=True)
class CodeBook:
    """Xarajat kodlari lug'ati (bazadagi ``expense_codes``). Ustuvorlik: aniq kod → prefiks →
    nomdagi kalit so'z → ``source`` → ``OTHER``. Kodlar ``normalize_code`` ko'rinishida yoziladi."""

    codes: Mapping[str, ExpenseCategory]
    prefixes: Sequence[tuple[str, ExpenseCategory]] = ()
    keywords: Sequence[tuple[str, ExpenseCategory]] = ()
    sources: Mapping[str, ExpenseCategory] = field(default_factory=dict)

    def classify(self, code: str, name: str = "", source: str = "") -> ExpenseCategory:
        """Normallashtirilgan kod, nom va manba bo'yicha toifa (F9)."""
        if code in self.codes:
            return self.codes[code]
        for prefix, category in self.prefixes:
            if code.startswith(prefix):
                return category
        low = name.lower()
        for word, category in self.keywords:
            if word in low:
                return category
        return self.sources.get(source.strip(), ExpenseCategory.OTHER)


_C = ExpenseCategory
SEED_CODEBOOK = CodeBook(
    codes={
        "BALANCE_CORRECTION": _C.BALANCE_CORRECTION,
        "C000003": _C.STORAGE,
        "C000004": _C.RETURN_STORAGE,
        "C000005": _C.PAID_SHIPPING,
        "C000007": _C.FINE,
        "00001": _C.FINE,
        "Y000050": _C.ADVERTISING,
        "Y000119": _C.ADVERTISING,
        "Y000120": _C.ADVERTISING,
        "Y000002": _C.PHOTO_STUDIO,
        "Y000003": _C.PHOTO_STUDIO,
        "C000010": _C.WITHDRAWAL_FEE,
        "C000011": _C.WITHDRAWAL_FEE,
        "DBS003": _C.FINE,
        "LOGISTICS-VOLUME": _C.LOGISTICS,
        "RETURN-LOGISTICS-VOLUME": _C.LOGISTICS_REFUND,
    },
    prefixes=(("FBS00", _C.FINE), ("RETURN-C", _C.COMPENSATION)),
    keywords=(("kompensatsiya", _C.COMPENSATION), ("jarima", _C.FINE)),
    sources={"Marketing": _C.ADVERTISING, "Ombor": _C.STORAGE, "Logistika": _C.LOGISTICS},
)

# --- Qatorlarni o'qish ----------------------------------------------------------------------


class Direction(StrEnum):
    """``type``: OUTCOME — sotuvchidan yechildi, INCOME — sotuvchiga qaytdi (kompensatsiya, qaytarim)."""

    OUTCOME = "OUTCOME"
    INCOME = "INCOME"


class Exclusion(StrEnum):
    """Qator nega P&L'ga kirmadi."""

    STATUS = "status"  # CANCELED / REFUNDED
    NOT_EXPENSE = "not_expense"  # toifa P&L'dan tashqarida (logistika F5 da, BALANCE_CORRECTION)


EXCLUDED_STATUSES = frozenset({"CANCELED", "CANCELLED", "REFUNDED"})
_BALANCE = "BALANCE_CORRECTION"

# Reklama: paymentPrice butun songa qirqilgan, aniq summa matnda ("... olganida 12345.67 so'm ...").
_AD_AMOUNT = re.compile(r"olganida\s+([\d\s]+(?:[.,]\d+)?)\s*so")
_ORDER_NO = re.compile(r"№\s*(\d+)")
_AD_ITEM = re.compile(r"^AD#(\d+)-")


class ExpenseParseError(ValueError):
    """``finance/expenses`` qatori tushunarsiz."""


@dataclass(frozen=True, slots=True)
class ExpenseRecord:
    """Toifalangan xarajat qatori. ``amount`` doim musbat; ishora ``signed`` da."""

    id: str
    day: date
    raw_code: str
    code: str
    category: ExpenseCategory
    direction: Direction
    status: str
    amount: Money
    name: str
    order_id: int | None = None
    item_id: int | None = None
    excluded: Exclusion | None = None

    @property
    def signed(self) -> Money:
        """P&L ta'siri: OUTCOME +, INCOME − (xarajatni kamaytiradi)."""
        return signed_amount(self.amount, self.direction)

    @property
    def counted(self) -> bool:
        return self.excluded is None


def signed_amount(amount: Money, direction: Direction | str) -> Money:
    """F9: xarajatning P&L ta'siri — OUTCOME +, INCOME − (``amount`` musbat, bazadagi ``mp_expenses`` ham)."""
    return amount if Direction(direction) is Direction.OUTCOME else -amount


def ad_amount_from_text(name: str, payment: Decimal) -> Decimal:
    """Reklama matnidagi aniq summa (F9). Matndagi summa ``paymentPrice`` dan 1 so'mdan ko'p farq
    qilsa — matn boshqa narsani bildiradi, ``paymentPrice`` olinadi."""
    match = _AD_AMOUNT.search(name)
    if not match:
        return payment
    digits = re.sub(r"\s", "", match.group(1)).replace(",", ".")
    exact = to_decimal(digits)  # regex faqat raqamlar va bitta kasr qismini oladi
    return exact if abs(exact - payment) < 1 else payment


def parse_expense(row: Mapping[str, Any], codebook: CodeBook) -> ExpenseRecord:
    """``finance/expenses`` qatori → ``ExpenseRecord`` (F9).

    Summa ``abs(paymentPrice)``, yo'nalish ``type`` dan; status CANCELED/REFUNDED va P&L'dan tashqari
    toifalar ``excluded`` bilan belgilanadi (o'chirilmaydi — drill-down va tekshiruv uchun).
    """
    raw_type = str(row.get("type") or "").strip().upper()
    try:
        expense_id = str(row["id"])
        day = date_from_epoch_ms(int(row["dateCreated"]))
        payment = abs(to_decimal(str(row.get("paymentPrice") or 0)))
        # BALANCE_CORRECTION ``type`` sifatida kelsa ham xarajat emas; yo'nalishi ahamiyatsiz.
        direction = Direction.OUTCOME if raw_type == _BALANCE else Direction(raw_type)
    except (KeyError, TypeError, ValueError) as exc:
        raise ExpenseParseError(f"xarajat qatori tushunarsiz: {dict(row)!r}") from exc
    raw_code = str(row.get("code") or "")
    code = normalize_code(raw_code)
    name = str(row.get("name") or "")
    if raw_type == _BALANCE:
        category = ExpenseCategory.BALANCE_CORRECTION
    else:
        category = codebook.classify(code, name, str(row.get("source") or ""))
    status = str(row.get("status") or "").strip().upper()
    if category is ExpenseCategory.ADVERTISING:
        payment = ad_amount_from_text(name, payment)

    excluded = None
    if status in EXCLUDED_STATUSES:
        excluded = Exclusion.STATUS
    elif not category.in_pnl:
        excluded = Exclusion.NOT_EXPENSE

    external = str(row.get("externalId") or "")
    order = _ORDER_NO.search(name)
    ad_item = _AD_ITEM.match(external)
    item_id = None
    if ad_item:
        item_id = int(ad_item.group(1))
    elif category in (ExpenseCategory.LOGISTICS, ExpenseCategory.LOGISTICS_REFUND) and (
        external.isdigit()
    ):
        item_id = int(external)

    return ExpenseRecord(
        id=expense_id,
        day=day,
        raw_code=raw_code,
        code=code,
        category=category,
        direction=direction,
        status=status,
        amount=Money(payment, Currency.UZS),
        name=name,
        order_id=int(order.group(1)) if order else None,
        item_id=item_id,
        excluded=excluded,
    )


def classify_expenses(
    rows: Iterable[Mapping[str, Any]], codebook: CodeBook = SEED_CODEBOOK
) -> list[ExpenseRecord]:
    """Qatorlarni o'qiydi; bir xil ``id`` takrorlansa oxirgi qiymati qoladi, tartib — birinchi uchragan
    joyi bo'yicha (dublikatlar, F9)."""
    by_id: dict[str, ExpenseRecord] = {}
    for row in rows:
        record = parse_expense(row, codebook)
        by_id[record.id] = record
    return list(by_id.values())


def totals_by_category(records: Iterable[ExpenseRecord]) -> dict[ExpenseCategory, Money]:
    """P&L'ga kiradigan qatorlar bo'yicha toifa summalari (ishora bilan; M5 F9 qatorlari)."""
    result: dict[ExpenseCategory, Money] = {}
    for r in records:
        if r.counted:
            result[r.category] = result.get(r.category, Money.zero(Currency.UZS)) + r.signed
    return result


def uzum_expense_total(records: Iterable[ExpenseRecord]) -> Money:
    """F9. Uzum xarajatlari = P&L'ga kiradigan xarajatlar − kompensatsiya va qaytarimlar."""
    result = Money.zero(Currency.UZS)
    for amount in totals_by_category(records).values():
        result += amount
    return result

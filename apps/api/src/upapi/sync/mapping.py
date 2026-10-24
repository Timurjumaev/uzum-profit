"""Uzum qatori → baza qatori (B2.6): sof funksiyalar, IO yo'q. Formulalar bu yerda emas (``upcore``) — faqat maydonlarni
o'qish, turlarni tekshirish va xom JSON'ni saqlash.

Qoidalar (02 M3, 03 §6):

- Pul — ``Decimal`` (``str`` orqali, float yo'q), vaqt — UTC ``datetime`` (Uzum: Unix millisekund).
- Uzum bermagan (``null`` yoki yo'q) maydon ``None`` bo'ladi — yozishda mavjud qiymat ustidan yozilmaydi
  (:mod:`upapi.sync.store`). Istisno: hisobda nol ma'nosidagi ustunlar (komissiya, logistika, qaytgan dona) — legacy
  kabi 0.
- Majburiy maydon (id, sana, narx ...) yo'q yoki noto'g'ri bo'lsa :class:`MappingError` — qator yozilmaydi, ish
  "ogohlantirish" bilan tugaydi (qolgan qatorlar yoziladi).
- ``raw`` — Uzum qatori o'zgarishsiz (yangi maydon chiqsa qayta so'ramasdan qayta ishlanadi).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from upcore.expenses import (
    SEED_CODEBOOK,
    CodeBook,
    ExpenseCategory,
    ExpenseParseError,
    normalize_code,
    parse_expense,
)

Row = dict[str, Any]
TASHKENT = timezone(timedelta(hours=5))  # O'zbekistonda yozgi vaqt yo'q
# Uzum xarajat va qaytarish turlari (03 §5 cheklovi bilan bir xil).
RETURN_TYPES = frozenset({"RETURN", "DEFECTED", "FBS"})


class MappingError(ValueError):
    """Qatorni o'qib bo'lmadi (majburiy maydon yo'q yoki turi noto'g'ri)."""


# --- Turlar ------------------------------------------------------------------------------------


def as_int(value: Any) -> int | None:
    """Butun son (``"123"`` ham); ``bool``, kasr va bo'sh — ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def as_decimal(value: Any) -> Decimal | None:
    """Pul/foiz: ``Decimal`` (float ham ``str`` orqali — ikkilik xatosiz). Bo'sh yoki son emas — ``None``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def as_text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def from_ms(value: Any) -> datetime | None:
    """Unix millisekund → UTC vaqt."""
    ms = as_int(value)
    if ms is None or ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, UTC)


_DOTTED = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def parse_time(value: Any) -> datetime | None:
    """Uzum vaqtining hamma ko'rinishlari: millisekund (son yoki matn), ISO 8601, ``dd.MM.yyyy[ HH:mm[:ss]]``
    (faktura ``dateCreated`` matn — 08 §8; mintaqasiz matn Toshkent vaqti). Tushunarsiz — ``None``."""
    if (stamp := from_ms(value)) is not None:
        return stamp
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if match := _DOTTED.match(text):
        day, month, year, hour, minute, second = match.groups()
        try:
            local = datetime(
                int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0)
            )
        except ValueError:
            return None
        return local.replace(tzinfo=TASHKENT).astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=TASHKENT)).astimezone(UTC)


def _required(value: Any, name: str) -> Any:
    if value is None:
        raise MappingError(f"{name} yo'q yoki noto'g'ri")
    return value


def _status(value: Any) -> str | None:
    """Holat ``"X"`` yoki ``{"value": "X", ...}`` ko'rinishida."""
    if isinstance(value, dict):
        value = value.get("value")
    return as_text(value)


# --- Sotuvlar (``finance/orders``) ---------------------------------------------------------------


def sale(row: Mapping[str, Any]) -> Row:
    """``finance/orders`` qatori (``group=false`` — SKU qatori) → ``sale_items``. ``sku_title`` = SKU ``skuFullTitle``
    (bog'lanish keyin, :func:`upapi.sync.store.link_sales`)."""
    return {
        "external_id": _required(as_int(row.get("id")), "id"),
        "order_id": _required(as_int(row.get("orderId")), "orderId"),
        "status": _required(as_text(row.get("status")), "status"),
        "ordered_at": _required(from_ms(row.get("date")), "date"),
        "issued_at": from_ms(row.get("dateIssued")),
        "sell_price": _required(as_decimal(row.get("sellPrice")), "sellPrice"),
        "amount": _required(as_int(row.get("amount")), "amount"),
        "commission": as_decimal(row.get("commission")) or Decimal(0),
        "logistics_fee": as_decimal(row.get("logisticDeliveryFee")) or Decimal(0),
        "seller_profit": as_decimal(row.get("sellerProfit")),
        "amount_returns": as_int(row.get("amountReturns")) or 0,
        "return_cause": as_text(row.get("returnCause")),
        "purchase_price": as_decimal(row.get("purchasePrice")),
        "sku_title": as_text(row.get("skuTitle")),
        "product_external_id": as_int(row.get("productId")),
        "raw": dict(row),
    }


# --- Xarajatlar (``finance/expenses``) -----------------------------------------------------------


def codebook(rows: Iterable[Mapping[str, Any]], base: CodeBook = SEED_CODEBOOK) -> CodeBook:
    """Bazadagi ``expense_codes`` (admin tahrirlaydi) + ``upcore`` boshlang'ich lug'ati: bazadagi yozuv ustun.
    Noma'lum toifa nomi e'tiborsiz qoldiriladi (lug'at buzilsa sinxron to'xtamaydi — "boshqa" bo'ladi)."""
    codes = dict(base.codes)
    prefixes: list[tuple[str, ExpenseCategory]] = []
    keywords: list[tuple[str, ExpenseCategory]] = []
    sources = dict(base.sources)
    for row in rows:
        try:
            category = ExpenseCategory(str(row["category"]))
        except (KeyError, ValueError):
            continue
        code, match = str(row.get("code") or ""), str(row.get("match") or "exact")
        if not code:
            continue
        if match == "prefix":
            prefixes.append((normalize_code(code), category))
        elif match == "keyword":
            keywords.append((code.lower(), category))
        elif match == "source":
            sources[code] = category
        else:
            codes[normalize_code(code)] = category
    return CodeBook(
        codes=codes,
        prefixes=[*prefixes, *(p for p in base.prefixes if p[0] not in dict(prefixes))],
        keywords=[*keywords, *(k for k in base.keywords if k[0] not in dict(keywords))],
        sources=sources,
    )


def expense(row: Mapping[str, Any], book: CodeBook) -> Row:
    """``finance/expenses`` qatori → ``mp_expenses``. Toifa, summa (reklama — matndagi aniq summa), yo'nalish,
    P&L'dan chiqarish sababi va bog'lanishlar — ``upcore.expenses.parse_expense`` (F9)."""
    try:
        record = parse_expense(row, book)
    except ExpenseParseError as exc:
        raise MappingError("xarajat qatori tushunarsiz") from exc
    return {
        "external_id": _required(as_int(row.get("id")), "id"),
        "raw_code": record.raw_code or None,
        "code": record.code or None,
        "category": record.category.value,
        "status": record.status or None,
        "type": record.direction.value,
        "amount": record.amount.amount,
        "name": record.name or None,
        "order_external_id": record.order_id,
        "item_external_id": record.item_id,
        "excluded": record.excluded.value if record.excluded else None,
        "created_on": _required(from_ms(row.get("dateCreated")), "dateCreated"),
        "raw": dict(row),
    }


# Xarajat qatoridagi hosila ustunlar: har safar qayta hisoblanadi (``NULL`` ham to'g'ri qiymat — masalan, status
# CANCELED dan qaytsa ``excluded`` bo'shaydi).
EXPENSE_DERIVED = frozenset(
    {"code", "category", "type", "amount", "order_external_id", "item_external_id", "excluded"}
)


# --- Mahsulotlar va SKU (``product/shop/{id}``) --------------------------------------------------


def product(row: Mapping[str, Any]) -> tuple[Row, list[Row]]:
    """Mahsulot → (``mp_products``, ``mp_skus`` qatorlari). Mahsulot ``raw`` ida ``skuList`` yo'q (har SKU o'z
    ``raw`` ida). SKU'siz qator (``skuId`` yo'q) — :class:`MappingError` (butun mahsulot emas, faqat o'sha SKU)."""
    product_row = {
        "external_id": _required(as_int(row.get("productId")), "productId"),
        "title": as_text(row.get("title")),
        "category": as_text(row.get("category")),
        "raw": {k: v for k, v in row.items() if k != "skuList"},
    }
    skus = []
    for sku in row.get("skuList") or []:
        if not isinstance(sku, dict) or as_int(sku.get("skuId")) is None:
            continue
        skus.append(sku_row(sku))
    return product_row, skus


def sku_row(sku: Mapping[str, Any]) -> Row:
    rank = sku.get("rankInfo")
    return {
        "external_id": _required(as_int(sku.get("skuId")), "skuId"),
        "sku_code": as_text(sku.get("skuFullTitle")),
        "barcode": as_text(sku.get("barcode")),
        "article": as_text(sku.get("article")) or as_text(sku.get("sellerItemCode")),
        "ikpu": as_text(sku.get("ikpu")),
        "price": as_decimal(sku.get("price")),
        "commission_pct": as_decimal(sku.get("commission")),
        "qty_active": as_int(sku.get("quantityActive")),
        "qty_fbs": as_int(sku.get("quantityFbs")),
        "qty_defected": as_int(sku.get("quantityDefected")),
        "qty_pending": as_int(sku.get("quantityPending")),
        "qty_sold": as_int(sku.get("quantitySold")),
        "qty_returned": as_int(sku.get("quantityReturned")),
        "avg_daily_sales": as_decimal(sku.get("avgdsales")),
        "rank": as_text(rank.get("rank")) if isinstance(rank, dict) else None,
        "storage_price": as_decimal(sku.get("paidStoragePriceItem")),
        "status": _status(sku.get("status")),
        "raw": dict(sku),
    }


# --- Postavkalar (``shop/{id}/invoice``) ---------------------------------------------------------


def invoice(row: Mapping[str, Any]) -> Row:
    return {
        "external_id": _required(as_int(row.get("id")), "id"),
        "number": as_int(row.get("invoiceNumber")),
        "status": _status(row.get("invoiceStatus")) or _status(row.get("status")),
        "created_on": parse_time(row.get("dateCreated")),
        "full_price": as_decimal(row.get("fullPrice")),
        "accepted": as_int(row.get("totalAccepted")),
        "to_stock": as_int(row.get("totalToStock")),
        "raw": dict(row),
    }


def invoice_items(rows: Iterable[Mapping[str, Any]]) -> list[Row]:
    """Postavka tarkibi: mahsulot qatorlari, ichida ``skuForInvoiceDtoList`` (08 §8) — har SKU alohida qator.
    Ro'yxat yo'q bo'lsa mahsulot qatorining o'zi (eski shakl)."""
    out = []
    for product_row in rows:
        skus = product_row.get("skuForInvoiceDtoList")
        for sku in skus if isinstance(skus, list) and skus else [product_row]:
            if not isinstance(sku, dict) or (ext := as_int(sku.get("id"))) is None:
                continue
            out.append(
                {
                    "sku_external_id": ext,
                    "quantity_to_stock": as_int(sku.get("quantityToStock")) or 0,
                    "quantity_accepted": as_int(sku.get("quantityAccepted")) or 0,
                }
            )
    return out


# --- Qaytarishlar (``/v1/return``) ---------------------------------------------------------------


def return_row(row: Mapping[str, Any]) -> Row:
    kind = as_text(row.get("type"))
    if kind is None or kind.upper() not in RETURN_TYPES:
        raise MappingError("qaytarish turi noma'lum")
    return {
        "external_id": _required(as_int(row.get("id")), "id"),
        "type": kind.upper(),
        "status": _status(row.get("status")),
        "created_on": parse_time(row.get("dateCreated")),
        "raw": dict(row),
    }


def return_items(row: Mapping[str, Any]) -> list[Row]:
    out = []
    for item in row.get("returnItems") or []:
        if not isinstance(item, dict) or (ext := as_int(item.get("skuId"))) is None:
            continue
        out.append({"sku_external_id": ext, "quantity": as_int(item.get("amount")) or 0})
    return out

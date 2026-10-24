"""B2.6 xaritalash (sof): haqiqiy kasseta qatorlari (08 §8) → baza qatorlari, turlar, vaqt, lug'at."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from cassette import FIXTURES, load
from upapi.sync import mapping as mp
from upcore.expenses import SEED_CODEBOOK, ExpenseCategory

RECORDED = load(FIXTURES / "recorded.json")


def body(name: str) -> Any:
    interaction = RECORDED.get(name)
    assert interaction is not None
    return interaction.body


def test_recorded_sale() -> None:
    raw = body("orders")["orderItems"][0]
    row = mp.sale(raw)
    assert row["external_id"] == raw["id"] and row["order_id"] == raw["orderId"]
    assert row["ordered_at"] == datetime.fromtimestamp(raw["date"] / 1000, UTC)
    assert row["sell_price"] == Decimal(raw["sellPrice"]) and isinstance(row["sell_price"], Decimal)
    assert row["commission"] == Decimal(raw["commission"])
    assert row["logistics_fee"] == Decimal(0) and row["issued_at"] is None
    assert row["sku_title"] == raw["skuTitle"] and row["product_external_id"] == raw["productId"]
    assert row["raw"] == raw and row["raw"] is not raw


def test_recorded_expense_and_lowercase_code() -> None:
    raw = body("expenses")["payload"]["payments"][0]
    row = mp.expense(raw, SEED_CODEBOOK)
    assert row["raw_code"] == "У000120" and row["code"] == "Y000120"
    assert row["category"] == "advertising" and row["type"] == "OUTCOME"
    assert row["amount"] == Decimal("1880.00") and row["excluded"] is None
    lower = mp.expense({**raw, "code": "logistics-volume", "source": "Logistika"}, SEED_CODEBOOK)
    assert (lower["code"], lower["category"], lower["excluded"]) == (
        "LOGISTICS-VOLUME",
        "logistics",
        "not_expense",
    )


def test_recorded_products() -> None:
    products = body("products")["productList"]
    archived, skus = mp.product(products[0])
    assert skus == [] and "skuList" not in archived["raw"]
    rows = [mp.product(p) for p in RECORDED.interactions[14].body["productList"]]
    sku = rows[0][1][0]
    assert sku["sku_code"] == "<skuFullTitle 174>" and sku["barcode"] == "900075"
    assert sku["commission_pct"] == Decimal("20.5") and sku["price"] == Decimal(24990)
    assert sku["status"] == "RUN_OUT" and sku["ikpu"] == "ID000076"
    assert sku["avg_daily_sales"] is None and sku["rank"] == "<rank 56>"


def test_recorded_invoice_and_items() -> None:
    raw = body("invoices")[0]
    row = mp.invoice(raw)
    assert row["status"] == "ACCEPTED" and row["full_price"] == Decimal(89000)
    assert row["created_on"] is None  # yozuvda anonimlashtirilgan matn
    items = mp.invoice_items(body("invoice_products"))
    assert items == [{"sku_external_id": 900046, "quantity_to_stock": 1, "quantity_accepted": 1}]
    # Eski shakl (ro'yxatsiz) — mahsulot qatorining o'zi.
    assert mp.invoice_items([{"id": 5, "quantityToStock": 2}]) == [
        {"sku_external_id": 5, "quantity_to_stock": 2, "quantity_accepted": 0}
    ]


def test_recorded_returns() -> None:
    raw = body("returns_all")[0]
    row = mp.return_row(raw)
    assert row["type"] == "DEFECTED" and row["status"] == "ASSEMBLED"
    assert mp.return_items(raw) == [{"sku_external_id": 900053, "quantity": 1}]
    with pytest.raises(mp.MappingError):
        mp.return_row({**raw, "type": "NEW"})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1792861682288, "2026-10-24T17:08:02.288000+00:00"),
        ("1792861682288", "2026-10-24T17:08:02.288000+00:00"),
        ("2026-10-24T10:30:00Z", "2026-10-24T10:30:00+00:00"),
        ("2026-10-24T10:30:00", "2026-10-24T05:30:00+00:00"),  # mintaqasiz — Toshkent
        ("24.10.2026 10:30", "2026-10-24T05:30:00+00:00"),
        ("24.10.2026", "2026-10-23T19:00:00+00:00"),
        ("1.2.2026 7:05:09", "2026-02-01T02:05:09+00:00"),
        ("31.02.2026", None),
        ("ertaga", None),
        ("", None),
        (None, None),
        (0, None),
        (True, None),
    ],
)
def test_parse_time(value: Any, expected: str | None) -> None:
    parsed = mp.parse_time(value)
    assert (parsed.isoformat() if parsed else None) == expected


def test_scalars() -> None:
    assert mp.as_decimal(20.5) == Decimal("20.5")  # float — str orqali
    assert mp.as_decimal("abc") is None and mp.as_decimal(True) is None
    assert mp.as_decimal("NaN") is None and mp.as_decimal(None) is None
    assert mp.as_int("12") == 12 and mp.as_int(3.0) == 3 and mp.as_int(3.5) is None
    assert mp.as_int(False) is None and mp.as_int("") is None
    assert mp.as_text("  x ") == "x" and mp.as_text({}) is None and mp.as_text(" ") is None


@pytest.mark.parametrize("missing", ["id", "orderId", "date", "sellPrice", "amount", "status"])
def test_sale_required_fields(missing: str) -> None:
    raw = dict(body("orders")["orderItems"][0])
    del raw[missing]
    with pytest.raises(mp.MappingError, match=missing):
        mp.sale(raw)


def test_expense_unreadable() -> None:
    with pytest.raises(mp.MappingError):
        mp.expense({"id": 1, "type": "SOMETHING", "dateCreated": 1}, SEED_CODEBOOK)


def test_codebook_from_database() -> None:
    book = mp.codebook(
        [
            {"code": "C000003", "category": "fine", "match": "exact"},  # bazadagi yozuv ustun
            {"code": "x-", "category": "photo_studio", "match": "prefix"},
            {"code": "Sovg'a", "category": "compensation", "match": "keyword"},
            {"code": "Studiya", "category": "photo_studio", "match": "source"},
            {"code": "Z1", "category": "yangi_toifa"},  # noma'lum toifa — e'tiborsiz
            {"code": "", "category": "fine"},
        ]
    )
    assert book.classify("C000003") is ExpenseCategory.FINE
    assert book.classify("X-1") is ExpenseCategory.PHOTO_STUDIO
    assert book.classify("Q", "Sovg'a uchun") is ExpenseCategory.COMPENSATION
    assert book.classify("Q", source="Studiya") is ExpenseCategory.PHOTO_STUDIO
    assert book.classify("Z1") is ExpenseCategory.OTHER
    assert book.classify("RETURN-C1") is ExpenseCategory.COMPENSATION  # boshlang'ich prefiks qoldi
    assert book.classify("Y000120") is ExpenseCategory.ADVERTISING

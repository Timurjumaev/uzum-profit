from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.expenses import (
    SEED_CODEBOOK,
    CodeBook,
    Direction,
    Exclusion,
    ExpenseCategory,
    ExpenseParseError,
    ad_amount_from_text,
    classify_expenses,
    normalize_code,
    parse_expense,
    signed_amount,
    totals_by_category,
    uzum_expense_total,
)
from upcore.metrics import uzum_expenses
from upcore.money import Money

C = ExpenseCategory
MS = int(datetime(2026, 10, 9, 20, 0, tzinfo=UTC).timestamp() * 1000)  # Toshkentda 10-oktabr 01:00


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def row(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 1,
        "dateCreated": MS,
        "name": "",
        "source": "",
        "paymentPrice": 1000,
        "externalId": "",
        "code": "C000003",
        "type": "OUTCOME",
    }
    base.update(kw)
    return base


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("С000003", "C000003"),  # kirill С
        ("C000003", "C000003"),
        (" c000004 ", "C000004"),
        ("У000120", "Y000120"),  # kirill У (legacy ma'lumoti)
        ("U000120", "Y000120"),  # legacy normallashtirgan ko'rinish
        ("Y000120", "Y000120"),  # qo'llanma
        ("FBS001", "FBS001"),
        ("logistics-volume", "LOGISTICS-VOLUME"),
        ("return-С000003", "RETURN-C000003"),
        ("UNKNOWN", "UNKNOWN"),  # harf + raqam emas — U o'zgarmaydi
        (None, ""),
    ],
)
def test_normalize_code(raw: str | None, norm: str) -> None:
    assert normalize_code(raw) == norm


@given(st.text(max_size=20))
def test_normalize_code_idempotent(code: str) -> None:
    once = normalize_code(code)
    assert normalize_code(once) == once


@pytest.mark.parametrize(
    ("code", "name", "source", "category"),
    [
        ("C000003", "", "", C.STORAGE),
        ("C000004", "", "", C.RETURN_STORAGE),
        ("C000005", "", "", C.PAID_SHIPPING),
        ("C000007", "", "", C.FINE),
        ("00001", "", "", C.FINE),
        ("Y000119", "", "", C.ADVERTISING),
        ("Y000050", "", "", C.ADVERTISING),
        ("Y000002", "", "", C.PHOTO_STUDIO),
        ("C000011", "", "", C.WITHDRAWAL_FEE),
        ("FBS003", "", "", C.FINE),
        ("DBS003", "", "", C.FINE),
        ("RETURN-C000003", "", "", C.COMPENSATION),
        ("LOGISTICS-VOLUME", "", "", C.LOGISTICS),
        ("RETURN-LOGISTICS-VOLUME", "", "", C.LOGISTICS_REFUND),
        ("BALANCE_CORRECTION", "", "", C.BALANCE_CORRECTION),
        ("Z1", "Yo'qolgan tovar uchun kompensatsiya", "", C.COMPENSATION),
        ("Z1", "Muddati o'tgani uchun JARIMA", "", C.FINE),
        ("Z1", "", "Marketing", C.ADVERTISING),
        ("Z1", "", "Ombor", C.STORAGE),
        ("Z1", "", "Logistika", C.LOGISTICS),
        ("Z1", "", "Boshqa", C.OTHER),
    ],
)
def test_seed_codebook(code: str, name: str, source: str, category: ExpenseCategory) -> None:
    assert SEED_CODEBOOK.classify(code, name, source) is category


def test_codebook_is_data_not_code() -> None:
    # Lug'at bazadan keladi: yangi kod qo'shilsa kod o'zgarmaydi.
    book = CodeBook(codes={"C000099": C.FINE})
    assert book.classify("C000099") is C.FINE
    assert book.classify("C000003") is C.OTHER


def test_in_pnl() -> None:
    assert C.ADVERTISING.in_pnl and C.COMPENSATION.in_pnl and C.OTHER.in_pnl
    assert not C.LOGISTICS.in_pnl and not C.LOGISTICS_REFUND.in_pnl
    assert not C.BALANCE_CORRECTION.in_pnl


def test_parse_legacy_ad_row_uses_exact_text_amount() -> None:
    r = parse_expense(
        row(
            id=101,
            name="Buyurtmalarni ko'paytirish. Sotuvdan foiz — 10%. Xaridor tovarni "
            "olganida 2000.5 so'm yechib oldik",
            source="Marketing",
            paymentPrice=2000,
            externalId="AD#11-1-2026-10-05",
            code="У000120",
        ),
        SEED_CODEBOOK,
    )
    assert r.id == "101" and r.day == date(2026, 10, 10)
    assert r.raw_code == "У000120" and r.code == "Y000120"
    assert r.category is C.ADVERTISING and r.direction is Direction.OUTCOME
    assert r.amount == uzs("2000.50") and r.signed == uzs("2000.50")
    assert r.item_id == 11 and r.counted


@pytest.mark.parametrize(
    ("text", "payment", "expected"),
    [
        ("olganida 2000.5 so'm", "2000", "2000.5"),
        ("olganida 12 345,67 so'm", "12345", "12345.67"),
        ("olganida 12 345.6 soʻm", "12345", "12345.6"),
        ("olganida 9000 so'm", "2000", "2000"),  # 1 so'mdan ko'p farq — matnga ishonilmaydi
        ("olganida 1.2.3 so'm", "1", "1"),  # son emas — mos kelmaydi
        ("matnda summa yo'q", "500", "500"),
    ],
)
def test_ad_amount_from_text(text: str, payment: str, expected: str) -> None:
    assert ad_amount_from_text(text, Decimal(payment)) == Decimal(expected)


def test_parse_links_and_directions() -> None:
    fine = parse_expense(row(code="C000007", name="Buyurtma № 777 bo'yicha jarima"), SEED_CODEBOOK)
    assert fine.order_id == 777 and fine.category is C.FINE
    comp = parse_expense(
        row(code="return-С000003", type="income", paymentPrice=-500), SEED_CODEBOOK
    )
    assert comp.direction is Direction.INCOME and comp.amount == uzs(500)
    assert comp.signed == uzs(-500)
    log = parse_expense(row(code="logistics-volume", externalId="555"), SEED_CODEBOOK)
    assert log.item_id == 555 and log.excluded is Exclusion.NOT_EXPENSE and not log.counted
    other = parse_expense(row(code="C000003", externalId="555"), SEED_CODEBOOK)
    assert other.item_id is None


@pytest.mark.parametrize("status", ["CANCELED", "canceled", "REFUNDED", "CANCELLED"])
def test_excluded_statuses(status: str) -> None:
    r = parse_expense(row(status=status), SEED_CODEBOOK)
    assert r.excluded is Exclusion.STATUS and not r.counted


def test_balance_correction_as_code_or_type() -> None:
    by_code = parse_expense(row(code="BALANCE_CORRECTION"), SEED_CODEBOOK)
    by_type = parse_expense(row(code="", type="BALANCE_CORRECTION"), SEED_CODEBOOK)
    for r in (by_code, by_type):
        assert r.category is C.BALANCE_CORRECTION and r.excluded is Exclusion.NOT_EXPENSE


@pytest.mark.parametrize(
    "bad",
    [
        {"id": 1, "paymentPrice": 1, "type": "OUTCOME"},  # sana yo'q
        row(dateCreated="kecha"),
        row(paymentPrice="abc"),
        row(type=""),  # yo'nalish taxmin qilinmaydi
        row(type="SOMETHING"),
    ],
)
def test_parse_errors(bad: dict[str, Any]) -> None:
    with pytest.raises(ExpenseParseError):
        parse_expense(bad, SEED_CODEBOOK)


def test_classify_dedup_and_f9_total() -> None:
    rows = [
        row(id=1, code="С000003", paymentPrice=3000),  # saqlash
        row(id=2, code="C000007", paymentPrice=2500),  # jarima
        row(id=2, code="C000007", paymentPrice=2600),  # dublikat — oxirgisi qoladi
        row(id=3, code="Y000120", paymentPrice=1000),  # reklama
        row(id=4, code="return-C000003", type="INCOME", paymentPrice=400),  # kompensatsiya
        row(id=5, code="logistics-volume", paymentPrice=9000),  # F5 da, F9 ga kirmaydi
        row(id=6, code="C000003", paymentPrice=7000, status="CANCELED"),
        row(id=7, code="BALANCE_CORRECTION", paymentPrice=100000),
        row(id=8, code="C000007", type="INCOME", paymentPrice=600),  # jarima qaytarildi
    ]
    records = classify_expenses(rows)
    assert [r.id for r in records] == ["1", "2", "3", "4", "5", "6", "7", "8"]
    assert totals_by_category(records) == {
        C.STORAGE: uzs(3000),
        C.FINE: uzs(2000),
        C.ADVERTISING: uzs(1000),
        C.COMPENSATION: uzs(-400),
    }
    assert uzum_expense_total(records) == uzs(5600)
    # metrics.uzum_expenses bilan bir xil natija
    charges = [r.amount for r in records if r.counted and r.direction is Direction.OUTCOME]
    refunds = [r.amount for r in records if r.counted and r.direction is Direction.INCOME]
    assert uzum_expenses(charges, refunds) == uzs(5600)
    assert uzum_expense_total([]) == uzs(0)


def test_signed_amount() -> None:
    assert signed_amount(uzs(500), "OUTCOME") == uzs(500)
    assert signed_amount(uzs(500), Direction.INCOME) == uzs(-500)
    with pytest.raises(ValueError):
        signed_amount(uzs(1), "SIDEWAYS")

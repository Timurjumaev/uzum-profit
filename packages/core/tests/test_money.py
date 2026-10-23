from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.money import (
    Currency,
    Money,
    MoneyError,
    allocate,
    quantize,
    round_rate,
    to_decimal,
    total,
)


def test_rounding_places_and_half_up() -> None:
    assert Money.of("100.005", "UZS").amount == Decimal("100.01")
    assert Money.of("100.004", "UZS").amount == Decimal("100.00")
    assert Money.of("1.23455", "CNY").amount == Decimal("1.2346")
    assert Money.of("-0.005", "UZS").amount == Decimal("-0.01")
    assert round_rate("1792.2912345") == Decimal("1792.291235")
    assert quantize(Decimal("2.5"), 0) == Decimal("3")


@pytest.mark.parametrize("bad", [1.5, True, None, "abc", "NaN", "Infinity"])
def test_rejects_float_and_garbage(bad: object) -> None:
    with pytest.raises(MoneyError):
        to_decimal(bad)  # type: ignore[arg-type]


def test_to_decimal_accepts_str_int_decimal() -> None:
    assert to_decimal(" 12.50 ") == Decimal("12.50")
    assert to_decimal(7) == Decimal(7)
    assert to_decimal(Decimal("1")) == Decimal(1)


def test_unknown_currency() -> None:
    with pytest.raises(ValueError):
        Money.of(1, "XYZ")


def test_arithmetic() -> None:
    a, b = Money.of("10.10", "UZS"), Money.of("0.95", "UZS")
    assert a + b == Money.of("11.05", "UZS")
    assert a - b == Money.of("9.15", "UZS")
    assert -a == Money.of("-10.10", "UZS")
    assert a * 3 == Money.of("30.30", "UZS")
    assert 3 * a == a * 3
    assert a * "0.5" == Money.of("5.05", "UZS")
    assert b < a and b <= a and a > b and a >= b
    assert Money.zero("USD").is_zero()
    assert str(a) == "10.10 UZS"
    assert Currency.UZS.places == 2 and Currency.USD.places == 4


def test_mixed_currency_is_error() -> None:
    uzs, usd = Money.of(1, "UZS"), Money.of(1, "USD")
    for op in (
        lambda: uzs + usd,
        lambda: uzs - usd,
        lambda: uzs < usd,
        lambda: uzs <= usd,
        lambda: uzs > usd,
        lambda: uzs >= usd,
    ):
        with pytest.raises(MoneyError):
            op()


def test_total() -> None:
    assert total([], "UZS") == Money.zero("UZS")
    assert total([Money.of(1, "CNY"), Money.of("2.5", "CNY")], "CNY") == Money.of("3.5", "CNY")


def test_allocate_remainder_goes_to_largest() -> None:
    # 100 so'm uchta teng qatorga: 33,33 + 33,33 + 33,34 emas — qoldiq birinchi eng katta qatorga.
    parts = allocate(Money.of(100, "UZS"), [1, 1, 1])
    assert [p.amount for p in parts] == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    # Kargo vazn bo'yicha: 1 000 000 so'm, 3 kg / 7 kg / 0 kg.
    parts = allocate(Money.of(1_000_000, "UZS"), ["3", "7", "0"])
    assert [p.amount for p in parts] == [
        Decimal("300000.00"),
        Decimal("700000.00"),
        Decimal("0.00"),
    ]
    parts = allocate(Money.of(10, "UZS"), [1, 2, 2])
    assert parts[1].amount == Decimal("4.00") and parts[2].amount == Decimal("4.00")


@pytest.mark.parametrize("weights", [[], [-1, 2], [0, 0]])
def test_allocate_invalid(weights: list[int]) -> None:
    with pytest.raises(MoneyError):
        allocate(Money.of(1, "UZS"), weights)


amounts = st.decimals(min_value=-(10**12), max_value=10**12, places=2, allow_nan=False)
weights = st.lists(st.integers(min_value=0, max_value=10**6), min_size=1, max_size=30).filter(any)


@given(amounts, weights)
def test_allocate_sum_is_exact(amount: Decimal, ws: list[int]) -> None:
    money = Money.of(amount, "UZS")
    parts = allocate(money, ws)
    assert total(parts, "UZS") == money
    assert len(parts) == len(ws)
    for part, w in zip(parts, ws, strict=True):
        if w == 0:
            assert part.is_zero()


@given(amounts, amounts)
def test_addition_is_exact(a: Decimal, b: Decimal) -> None:
    assert (Money.of(a, "UZS") + Money.of(b, "UZS")).amount == a + b

"""M6 unit kalkulyator: foyda/dona narxda, F35 zararsizlik va F36 maqsadli marja narxi bir tenglamadan."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.money import Currency, Money
from upcore.unit import CargoBasis, landed_unit_cost, unit_calc

D = Decimal


def uzs(value: int | str) -> Money:
    return Money.of(value, Currency.UZS)


def test_unit_calc_at_price() -> None:
    # Tannarx 40 000 + logistika 5 250 + qadoq 4 750 = 50 000; komissiya 20%, soliq 4%, reklama 6% → ulush 30%.
    c = unit_calc(uzs(100_000), uzs(40_000), uzs(5_250), uzs(4_750), 20, 4, 6, 15)
    assert c.fixed == uzs(50_000) and c.share_pct == D(30)
    assert (c.commission, c.tax, c.ads) == (uzs(20_000), uzs(4_000), uzs(6_000))
    assert c.profit == uzs(20_000)  # 100 000 − 50 000 − 30 000
    assert c.margin == D("0.200000") and c.roi == D("0.500000")
    assert c.breakeven == uzs("71428.57")  # F35: 50 000 / 0,70
    assert c.target_price == uzs("90909.09")  # F36: 50 000 / (1 − 0,45)


def test_breakeven_price_gives_zero_profit_and_target_gives_margin() -> None:
    first = unit_calc(uzs(100_000), uzs(40_000), uzs(10_000), uzs(0), 25, 4, 5, 10)
    assert first.breakeven is not None and first.target_price is not None
    at_breakeven = unit_calc(first.breakeven, uzs(40_000), uzs(10_000), uzs(0), 25, 4, 5)
    assert abs(at_breakeven.profit.amount) < 1  # yaxlitlash xatosi
    at_target = unit_calc(first.target_price, uzs(40_000), uzs(10_000), uzs(0), 25, 4, 5)
    assert at_target.margin is not None and abs(at_target.margin - D("0.1")) < D("0.0001")


def test_without_target_margin_there_is_no_target_price() -> None:
    assert unit_calc(uzs(10_000), uzs(1000), uzs(0), uzs(0), 10).target_price is None


def test_share_at_or_over_100_has_no_price_that_profits() -> None:
    c = unit_calc(uzs(100_000), uzs(10_000), uzs(0), uzs(0), 60, 25, 15, 5)
    assert c.breakeven is None and c.target_price is None
    assert c.profit == uzs(-10_000) and c.margin == D("-0.100000")


def test_zero_price_and_zero_cost_have_no_ratios() -> None:
    c = unit_calc(uzs(0), uzs(0), uzs(0), uzs(0), 10)
    assert c.margin is None and c.roi is None and c.profit == uzs(0)


@given(
    st.integers(min_value=1_000, max_value=5_000_000),
    st.decimals(min_value=0, max_value=60, places=1),
    st.decimals(min_value=0, max_value=30, places=1),
)
def test_breakeven_profit_is_never_negative_by_more_than_rounding(
    fixed: int, commission: Decimal, tax: Decimal
) -> None:
    first = unit_calc(uzs(1), uzs(fixed), uzs(0), uzs(0), commission, tax, 0)
    assert first.breakeven is not None
    again = unit_calc(first.breakeven, uzs(fixed), uzs(0), uzs(0), commission, tax, 0)
    assert again.profit.amount >= -1


@pytest.mark.parametrize("bad", ["x", 1.5])
def test_float_or_text_percent_is_rejected(bad: object) -> None:
    with pytest.raises(ValueError):
        unit_calc(uzs(1), uzs(1), uzs(0), uzs(0), bad)  # type: ignore[arg-type]


def test_landed_cost_goods_china_cargo_extra() -> None:
    """M13: 10 CNY × 1 800 + Xitoy ichki 50 CNY / 50 dona + kargo ($/kg × 0,3 kg × 12 500) + qo'shimcha 1 000."""
    c = landed_unit_cost(
        price_cny=10,
        qty=50,
        cny_rate=1800,
        china_cny_total=50,
        weight_kg=D("0.3"),
        cargo_usd_per_kg=D(4),
        usd_rate=12_500,
        extra_uzs=1_000,
    )
    assert c.goods.amount == D(18_000) and c.china.amount == D(1_800)  # 50 / 50 × 1 800
    assert c.cargo.amount == D(15_000) and c.cargo_basis is CargoBasis.WEIGHT  # 4 × 0,3 × 12 500
    assert c.extra.amount == D(1_000)
    assert c.unit_cost.amount == D(35_800)


def test_landed_cargo_takes_the_larger_of_weight_and_volume_and_never_guesses() -> None:
    base = dict(price_cny=10, qty=10, cny_rate=1800, usd_rate=12_500)
    both = landed_unit_cost(
        **base,
        weight_kg=D("0.2"),
        cargo_usd_per_kg=D(4),
        volume_m3=D("0.004"),
        cargo_usd_per_m3=D(300),
    )
    assert both.cargo_basis is CargoBasis.VOLUME and both.cargo.amount == D(
        15_000
    )  # 300 × 0,004 × 12 500 > 4 × 0,2 × 12 500
    # Narx bor, lekin o'lcham yo'q — o'sha usul hisobga olinmaydi (taxmin yo'q): faqat hajm.
    only_volume = landed_unit_cost(
        **base, cargo_usd_per_kg=D(4), volume_m3=D("0.004"), cargo_usd_per_m3=D(300)
    )
    assert only_volume.cargo_basis is CargoBasis.VOLUME
    none = landed_unit_cost(**base, weight_kg=D(1))  # kargo narxi yo'q
    assert none.cargo.amount == D(0) and none.cargo_basis is None
    no_rate = landed_unit_cost(
        price_cny=10, qty=10, cny_rate=1800, weight_kg=D(1), cargo_usd_per_kg=D(4)
    )  # $ kursi yo'q
    assert no_rate.cargo.amount == D(0) and no_rate.cargo_basis is None


def test_landed_requires_positive_qty() -> None:
    with pytest.raises(ValueError):
        landed_unit_cost(price_cny=10, qty=0, cny_rate=1800)


@given(
    st.decimals(0, 10_000, places=2),
    st.integers(1, 10_000),
    st.decimals(1, 3_000, places=2),
    st.decimals(0, 100_000, places=2),
)
def test_landed_unit_cost_is_the_sum_of_its_parts(
    price: Decimal, qty: int, rate: Decimal, china: Decimal
) -> None:
    c = landed_unit_cost(price_cny=price, qty=qty, cny_rate=rate, china_cny_total=china)
    assert c.unit_cost == c.goods + c.china + c.cargo + c.extra and c.unit_cost.amount >= 0

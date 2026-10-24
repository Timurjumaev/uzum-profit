from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.inventory import (
    DEFAULT,
    AbcClass,
    DayStat,
    Holding,
    InventorySettings,
    Liquidity,
    StockStatus,
    SupplyLine,
    XyzClass,
    abc_classes,
    acceptance_shortage,
    average_days_to_sell,
    compensation_estimate,
    days_of_stock,
    frozen_money,
    lead_time,
    liquidity,
    lost_goods,
    product_status,
    reorder,
    stock_status,
    stockout_days,
    stockout_lost_profit,
    trend_factor,
    velocity,
    weekly_sales,
    xyz_class,
)
from upcore.money import Money

D = Decimal
AS_OF = date(2026, 10, 31)


def day(n: int) -> date:
    """n kun oldin (0 — AS_OF)."""
    return AS_OF - timedelta(days=n)


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def series(
    sold: list[int], returned: list[int] | None = None, out: set[int] = frozenset()
) -> list[DayStat]:
    """sold[0] — AS_OF kuni, sold[1] — bir kun oldin ..."""
    returned = returned or [0] * len(sold)
    return [
        DayStat(day(i), s, r, i not in out)
        for i, (s, r) in enumerate(zip(sold, returned, strict=True))
    ]


# F23 ------------------------------------------------------------------------------------------


def test_velocity_weighted_and_steady_trend() -> None:
    v = velocity(series([2] * 30), AS_OF)
    assert v.base == D(2) and v.days_counted == 14
    assert v.trend_ratio == D(1) and v.trend_factor == D(1) and v.return_rate == 0
    assert v.value == D("2.0000")


def test_velocity_recent_week_weighs_double() -> None:
    sold = [4] * 7 + [1] * 7 + [1] * 16
    v = velocity(series(sold), AS_OF)
    assert v.base == D(2 * 28 + 7) / D(21)  # (2 × 28 + 7) / (2 × 7 + 7) = 3
    # v7 = 4, v30 = (28 + 23) / 30 = 1,7 → r ≈ 2,35 → 1,20
    assert v.trend_factor == D("1.20") and v.value == D("3.6000")


def test_velocity_excludes_stockout_days_and_new_item() -> None:
    sold = [3, 0, 0, 3, 3, 3, 3] + [3] * 23
    v = velocity(series(sold, out={1, 2}), AS_OF)
    assert v.days_counted == 12 and v.base == D(3)
    new = velocity(series([5, 5, 5, 0, 0]), AS_OF, first_day=day(2))
    assert new.days_counted == 3 and new.base == D(15) / 7  # kamida 7 kunga bo'linadi


def test_velocity_return_rate_capped() -> None:
    v = velocity(series([2] * 30, [1] * 30), AS_OF)
    assert v.return_rate == ratio_of(14, 42)
    heavy = velocity(series([1] * 30, [5] * 30), AS_OF)
    assert heavy.return_rate == D("0.5")
    assert velocity([], AS_OF).base == 0 and velocity([], AS_OF).trend_ratio is None


def ratio_of(a: int, b: int) -> Decimal:
    from upcore.metrics import ratio

    r = ratio(a, b)
    assert r is not None
    return r


@pytest.mark.parametrize(
    ("r", "factor"),
    [
        (None, "1"),
        ("1.3", "1.20"),
        ("1.29", "1.10"),
        ("1.1", "1.10"),
        ("1.0", "1"),
        ("0.9", "0.93"),
        ("0.71", "0.93"),
        ("0.7", "0.85"),
        ("0.1", "0.85"),
    ],
)
def test_trend_factor(r: str | None, factor: str) -> None:
    assert trend_factor(None if r is None else D(r)) == D(factor)


# F24–F27 --------------------------------------------------------------------------------------


def test_days_of_stock() -> None:
    assert days_of_stock(100, 20, D(4)) == D("30.0")
    assert days_of_stock(5, 0, 0) is None


def test_lead_time_learns_median_of_last_five() -> None:
    lt = lead_time(
        {"kargo": [30, 9, 18, 20, 22, 25], "tayyorlash": []},
        {"tayyorlash": 5, "kargo": 21, "qabul": 2},
    )
    assert lt.stages == {"tayyorlash": D(5), "kargo": D(20), "qabul": D(2)}
    assert lt.learned == {"kargo"} and lt.total == D(27)
    assert lead_time({"xitoy": [3, 4]}, {}).stages == {"xitoy": D("3.5")}


@pytest.mark.parametrize(
    ("stock", "speed", "status"),
    [
        (30, 1, StockStatus.CRITICAL),
        (37, 1, StockStatus.HIGH),
        (51, 1, StockStatus.MEDIUM),
        (52, 1, StockStatus.GOOD),
        (5, 0, StockStatus.DEAD),
        (0, 0, None),
        (0, 2, StockStatus.CRITICAL),
    ],
)
def test_stock_status(stock: int, speed: int, status: StockStatus | None) -> None:
    assert stock_status(stock, speed, 30) is status


def test_product_status() -> None:
    assert (
        product_status([(StockStatus.GOOD, 70), (StockStatus.CRITICAL, 30)]) is StockStatus.CRITICAL
    )
    assert product_status([(StockStatus.GOOD, 90), (StockStatus.CRITICAL, 10)]) is StockStatus.GOOD
    assert product_status([(StockStatus.DEAD, 0), (StockStatus.MEDIUM, 0)]) is StockStatus.MEDIUM
    assert product_status([(None, 5)]) is None


def test_reorder() -> None:
    r = reorder(
        D(2),
        D(35),
        AbcClass.B,
        stock=40,
        in_transit=20,
        ordered=10,
        batch=50,
        last_unit_prices=[Money.of("12.5", "CNY"), uzs(22_400)],
    )
    # 2 × (35 + 30) − 70 = 60 → 50 lik partiya → 100
    assert r.raw == D(60) and r.qty == 100
    assert r.budget == (Money.of(1250, "CNY"), uzs(2_240_000))
    assert reorder(D(1), D(10), AbcClass.C, stock=100).qty == 0
    assert reorder(D("0.3"), D(10), AbcClass.A, stock=0).qty == 21  # 0,3 × 70 = 21


# F28 ------------------------------------------------------------------------------------------


def test_abc() -> None:
    values = {
        "a": uzs(500),
        "b": uzs(300),
        "c": uzs(120),
        "d": uzs(50),
        "e": uzs(30),
        "z": uzs(0),
        "neg": uzs(-10),
    }
    assert abc_classes(values) == {
        "a": AbcClass.A,
        "b": AbcClass.A,
        "c": AbcClass.B,
        "d": AbcClass.B,
        "e": AbcClass.C,
        "z": AbcClass.C,
        "neg": AbcClass.C,
    }
    assert abc_classes({"only": uzs(1)}) == {"only": AbcClass.A}
    assert abc_classes({}) == {}


def test_xyz() -> None:
    assert xyz_class([10] * 8) is XyzClass.X
    assert xyz_class([10, 14, 6, 10, 14, 6, 10, 10]) is XyzClass.Y
    assert xyz_class([0, 0, 0, 40, 0, 0, 0, 0]) is XyzClass.Z
    assert xyz_class([0] * 8) is None and xyz_class([]) is None


def test_weekly_sales() -> None:
    days = [DayStat(day(i), 1) for i in range(60)]
    assert weekly_sales(days, AS_OF) == [7] * 8
    assert weekly_sales([DayStat(day(0), 3), DayStat(day(7), 2)], AS_OF)[-2:] == [2, 3]


# F29–F30 --------------------------------------------------------------------------------------


def test_frozen_money_and_avg_days() -> None:
    holdings = [
        Holding("fbo", 10, uzs(20_000)),
        Holding("fbo", 5, uzs(30_000)),
        Holding("yo'lda", 100, uzs(15_000)),
    ]
    assert frozen_money(holdings) == {"fbo": uzs(350_000), "yo'lda": uzs(1_500_000)}
    assert average_days_to_sell(
        [(D(10), uzs(300)), (D(40), uzs(100)), (None, uzs(999)), (D(5), uzs(0))]
    ) == D("17.5")
    assert average_days_to_sell([]) is None


@pytest.mark.parametrize(
    ("stock", "speed", "last", "expected"),
    [
        (5, 0, None, Liquidity.ILLIQUID),
        (5, 0, 181, Liquidity.ILLIQUID),
        (5, 0, 180, Liquidity.SLOW),
        (5, 0, 90, Liquidity.SLOW),
        (5, 0, 89, None),
        (5, 1, 300, None),
        (0, 0, None, None),
    ],
)
def test_liquidity(stock: int, speed: int, last: int | None, expected: Liquidity | None) -> None:
    assert liquidity(stock, speed, None if last is None else day(last), AS_OF) is expected


# F31–F34 --------------------------------------------------------------------------------------


def test_lost_goods() -> None:
    supplies = [
        SupplyLine(day(30), 100, 98),
        SupplyLine(day(2), 50, 50),
    ]  # oxirgisi 3 kun ichida — chiqariladi
    lg = lost_goods(
        supplies,
        fbs_shipped=10,
        sold=80,
        returned=5,
        fbs_returned=1,
        defected=2,
        on_hand=12,
        in_return_transit=3,
        as_of=AS_OF,
        history_reliable=True,
    )
    assert lg is not None
    # kutilgan = 98 + 10 − 80 − (5 + 1 + 2) = 20; farq 8; yo'qolgan = 8 − 3 = 5
    assert (lg.expected, lg.gap, lg.lost) == (20, 8, 5)
    big_transit = lost_goods(supplies, 10, 80, 5, 1, 2, 12, 50, AS_OF, True)
    assert big_transit is not None and big_transit.lost == 0
    surplus = lost_goods(supplies, 10, 80, 5, 1, 2, 60, 0, AS_OF, True)
    assert surplus is not None and surplus.gap == 0
    assert lost_goods(supplies, 0, 0, 0, 0, 0, 0, 0, AS_OF, history_reliable=False) is None


def test_compensation_estimate() -> None:
    prices = [uzs(100_000)] * 10 + [uzs(130_000)] * 30
    assert compensation_estimate(5, prices, 20) == uzs(520_000)  # oxirgi 30 ta: 130 000 × 5 × 0,8
    assert compensation_estimate(0, prices, 20) is None
    assert compensation_estimate(1, [], 20) is None


def test_acceptance_shortage() -> None:
    assert (
        acceptance_shortage(
            [SupplyLine(day(1), 100, 97), SupplyLine(day(1), 10, 12), SupplyLine(day(2), 5, 5)]
        )
        == 3
    )


def test_stockout_lost_profit() -> None:
    days = [DayStat(day(i), 0, 0, i % 3 != 0) for i in range(9)] + [DayStat(day(20))]
    assert stockout_days(days) == 3
    assert stockout_lost_profit(3, D("2.5"), uzs(18_000)) == uzs(135_000)
    assert stockout_lost_profit(3, D(2), uzs(-500)) == uzs(0)


def test_settings_are_configurable() -> None:
    s = InventorySettings(
        cover_days={AbcClass.A: 90, AbcClass.B: 45, AbcClass.C: 7}, illiquid_days=365, slow_days=120
    )
    assert reorder(D(1), D(10), AbcClass.A, stock=0, s=s).qty == 100
    assert liquidity(1, 0, day(200), AS_OF, s) is Liquidity.SLOW
    assert DEFAULT.cover_days[AbcClass.A] == 60


@given(
    st.lists(st.integers(0, 50), min_size=1, max_size=60), st.lists(st.integers(0, 60), max_size=10)
)
def test_velocity_non_negative_and_bounded(sold: list[int], out: list[int]) -> None:
    v = velocity(series(sold, out=set(out)), AS_OF)
    assert v.value >= 0
    assert v.value <= D(max(sold)) * D("1.2") * 2  # vazn va trend bilan ham chegaralangan

from datetime import date, timedelta
from decimal import Decimal

import pytest
from upcore.cash import (
    SEED_SCHEDULES,
    ScheduleKind,
    add_workdays,
    cash_forecast,
    forecast_payouts,
    next_payout,
    next_workday,
    urgent_withdrawal_fee,
)
from upcore.metrics import Period, SaleLine
from upcore.money import Money
from upcore.pnl import TaxBase, TaxRule, build_cells
from upcore.tariffs import (
    SEED_LOGISTICS,
    LogisticsTariff,
    TariffError,
    detect_free_days,
    is_free_day,
    last_paid_logistics,
    liters,
    logistics_fee,
    paid_unit_fee,
    standard_fee_of,
    tariff_on,
    to_periods,
    typical_fee,
    with_standard_logistics,
)
from upcore.tax import (
    SEED_RATES,
    TaxProfile,
    TaxRegime,
    daily_rule,
    effective_rate,
    profile_on,
    rate_on,
    vat_profit_estimate,
)

D = Decimal


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def sale(
    day: date, sku: str = "A", log: int = 5_000, qty: int = 1, status: str = "TO_WITHDRAW"
) -> SaleLine:
    return SaleLine(
        sku, day, status, D(100_000), qty, D(20_000), D(log), unit_cost=D(40_000), shop="S"
    )


# F37 ------------------------------------------------------------------------------------------

T = tariff_on(SEED_LOGISTICS, date(2026, 10, 1))


@pytest.mark.parametrize(
    ("dims", "sim", "fee"),
    [
        ((100, 100, 100), False, 5250),  # 1 l
        ((100, 100, 40), False, 5250),  # 0,4 l → 0 → asosiy
        ((200, 100, 100), False, 5500),  # 2 l
        ((300, 200, 100), False, 6500),  # 6 l
        ((1000, 1000, 1000), False, 50_000),  # 1000 l → maksimal
        (None, False, 50_000),
        ((0, 10, 10), False, 50_000),
        ((100, 100, 100), True, 20_000),
    ],
)
def test_logistics_fee(dims: tuple[int, int, int] | None, sim: bool, fee: int) -> None:
    assert logistics_fee(T, dims, sim) == uzs(fee)


def test_liters_rounding_and_tariff_dates() -> None:
    assert liters(150, 100, 100) == 2  # 1,5 → 2
    assert liters(140, 100, 100) == 1
    newer = LogisticsTariff(
        date(2027, 1, 1), uzs(6000), uzs(300), uzs(60_000), uzs(60_000), uzs(25_000)
    )
    table = (*SEED_LOGISTICS, newer)
    assert tariff_on(table, date(2026, 12, 31)) is SEED_LOGISTICS[0]
    assert tariff_on(table, date(2027, 1, 1)) is newer
    with pytest.raises(TariffError):
        tariff_on(table, date(2026, 5, 31))


# F40 ------------------------------------------------------------------------------------------


def test_standard_tariff_profit_and_free_days() -> None:
    d = [date(2026, 10, 8) + timedelta(days=i) for i in range(4)]
    lines = [
        sale(d[0], "A", log=6_000, qty=2),
        sale(d[1], "A", log=0, qty=3),
        sale(d[1], "B", log=0),
        sale(d[2], "B", log=0),
        sale(d[2], "A", log=0),
        sale(d[3], "A", log=5_000),
        sale(d[2], "C", log=0, status="PROCESSING"),
    ]
    assert last_paid_logistics(lines) == {"A": uzs(5_000)}
    free = detect_free_days(lines)
    assert free == [d[1], d[2]]
    assert to_periods(free) == [Period(d[1], d[2])]
    assert to_periods([d[0], d[2], d[3]]) == [Period(d[0], d[0]), Period(d[2], d[3])]
    paid = last_paid_logistics(lines)
    std = with_standard_logistics(lines, lambda x: paid.get(x.sku) or logistics_fee(T, None), free)
    assert [x.logistics for x in std] == [
        D(6_000),
        D(15_000),
        D(50_000),
        D(50_000),
        D(5_000),
        D(5_000),
        D(0),
    ]
    period = Period(d[0], d[3])
    actual = build_cells(period, lines).statement()
    standard = build_cells(period, std).statement()
    assert actual.net_profit - standard.net_profit == uzs(120_000)
    unchanged = with_standard_logistics(lines, lambda x: None)
    assert unchanged == lines


def test_free_day_and_fallback_fees() -> None:
    assert is_free_day(10, 9) and not is_free_day(10, 8) and not is_free_day(0, 0)
    assert paid_unit_fee(D(10_001), 3) == uzs("3333.67")
    assert typical_fee({}) is None
    assert typical_fee({D(5_250): 3, D(6_000): 1}) == uzs(5_250)
    assert typical_fee({D(5_250): 2, D(6_000): 2}) == uzs(6_000)  # teng — kattasi
    fee = standard_fee_of({"A": uzs(7_000)}, {"S": uzs(5_250)})
    assert fee("S", "A") == uzs(7_000)
    assert fee("S", "B") == uzs(5_250)
    assert fee("Q", "B") is None


# F11 ------------------------------------------------------------------------------------------


def test_tax_rates_and_profiles() -> None:
    assert rate_on(SEED_RATES, "turnover_individual", date(2026, 3, 1)) == D(1)
    assert rate_on(SEED_RATES, "profit", date(2025, 12, 31)) is None
    profiles = [
        TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, D(1)),
        TaxProfile(date(2026, 10, 15), TaxRegime.TURNOVER, D(4), TaxBase.PAYOUT),
        TaxProfile(date(2026, 11, 1), TaxRegime.AGENT),
    ]
    assert profile_on(profiles, date(2026, 10, 14)) is profiles[0]
    assert profile_on(profiles, date(2025, 1, 1)) is None
    rule = daily_rule(profiles)
    assert rule(date(2026, 10, 1)) == TaxRule(D(1))
    assert rule(date(2026, 10, 20)) == TaxRule(D(4), TaxBase.PAYOUT)
    assert rule(date(2026, 11, 2)) is None and rule(date(2025, 1, 1)) is None
    lines = [sale(date(2026, 10, 1)), sale(date(2026, 10, 20)), sale(date(2026, 11, 2))]
    s = build_cells(Period(date(2026, 10, 1), date(2026, 11, 30)), lines, tax=rule).statement()
    # 1% × 100 000 + 4% × (100 000 − 20 000 − 5 000) + 0
    assert s.tax == uzs(1_000 + 3_000)


def test_vat_profit_estimate() -> None:
    e = vat_profit_estimate(uzs(11_200_000), uzs(3_000_000), 12, 15)
    assert e.vat == uzs(1_200_000) and e.profit_tax == uzs(270_000) and e.total == uzs(1_470_000)
    e2 = vat_profit_estimate(uzs(11_200_000), uzs(1_000_000), 12, 15, input_vat=uzs(1_500_000))
    assert e2.vat == uzs(0) and e2.profit_tax == uzs(150_000)
    loss = vat_profit_estimate(uzs(1_120_000), uzs(-50_000), 12, 15)
    assert loss.profit_tax == uzs(0)
    assert (
        effective_rate(uzs(10), uzs(1000)) == D("0.01") and effective_rate(uzs(1), uzs(0)) is None
    )


# F38 ------------------------------------------------------------------------------------------

HOLIDAYS = frozenset({date(2026, 12, 8)})  # seshanba, bayram


def test_workdays() -> None:
    assert next_workday(date(2026, 10, 24)) == date(2026, 10, 26)  # shanba → dushanba
    assert next_workday(date(2026, 12, 8), HOLIDAYS) == date(2026, 12, 9)
    assert add_workdays(date(2026, 10, 23), 4) == date(2026, 10, 29)


def test_next_payout() -> None:
    weekly = SEED_SCHEDULES[ScheduleKind.WEEKLY]
    assert next_payout(date(2026, 10, 15), weekly) == (date(2026, 10, 21), date(2026, 10, 27))
    monthly = SEED_SCHEDULES[ScheduleKind.MONTHLY]
    # 7-noyabr shanba → 9-noyabr dushanba
    assert next_payout(date(2026, 10, 8), monthly)[0] == date(2026, 11, 9)
    daily = SEED_SCHEDULES[ScheduleKind.DAILY]
    assert next_payout(date(2026, 12, 7), daily, HOLIDAYS)[0] == date(2026, 12, 9)
    biweekly = SEED_SCHEDULES[ScheduleKind.BIWEEKLY]
    assert next_payout(date(2026, 12, 6), biweekly, HOLIDAYS)[0] == date(2026, 12, 7)


def test_forecast_payouts_and_carry() -> None:
    weekly = SEED_SCHEDULES[ScheduleKind.WEEKLY]
    daily_net = {
        date(2026, 10, 15): uzs(1_000_000),
        date(2026, 10, 16): uzs(500_000),
        date(2026, 10, 22): uzs(-300_000),  # ushlanma ko'p — keyingisiga o'tadi
        date(2026, 10, 29): uzs(400_000),
    }
    events = forecast_payouts(daily_net, weekly)
    assert [e.expected for e in events] == [date(2026, 10, 21), date(2026, 11, 9)]
    assert (
        events[0].gross == uzs(1_500_000)
        and events[0].fee == uzs(15_000)
        and events[0].net == uzs(1_485_000)
    )
    assert events[1].gross == uzs(100_000)  # −300 000 + 400 000; 7-noyabr shanba → 9-noyabr
    assert urgent_withdrawal_fee(uzs(1_000_000)) == uzs(25_000)


# F39 ------------------------------------------------------------------------------------------


def test_cash_forecast_gap() -> None:
    start = date(2026, 11, 1)
    f = cash_forecast(
        uzs(2_000_000),
        start,
        inflows=[(date(2026, 11, 10), uzs(1_500_000)), (date(2026, 10, 1), uzs(9_999_999))],
        outflows=[(date(2026, 11, 5), uzs(3_000_000)), (date(2026, 11, 20), uzs(100_000))],
        days=30,
    )
    assert len(f.balances) == 30 and f.balances[0] == (start, uzs(2_000_000))
    assert f.gap_day == date(2026, 11, 5) and f.minimum == uzs(-1_000_000)
    assert f.balances[-1][1] == uzs(400_000)
    ok = cash_forecast(uzs(1), start, [], [], days=3)
    assert ok.gap_day is None

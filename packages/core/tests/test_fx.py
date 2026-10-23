from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.fx import (
    FxError,
    FxRate,
    RateSource,
    effective_fx_rate,
    effective_rate,
    manual_rate,
    parse_cbu_row,
    parse_cbu_rows,
    rate_on,
    to_uzs,
)
from upcore.money import Currency, Money

CNY_ROW = {"Ccy": "CNY", "Nominal": "1", "Rate": "1792.29", "Date": "22.10.2026"}


def test_parse_cbu_row() -> None:
    r = parse_cbu_row(CNY_ROW)
    assert r == FxRate(date(2026, 10, 22), Currency.CNY, Decimal("1792.29"), RateSource.CBU)
    assert r.rate == Decimal("1792.290000")


def test_parse_cbu_row_nominal() -> None:
    r = parse_cbu_row({"Ccy": "rub", "Nominal": "10", "Rate": "1543.21", "Date": "01.10.2026"})
    assert r.currency is Currency.RUB and r.rate == Decimal("154.321000")


@pytest.mark.parametrize(
    "row",
    [
        {"Ccy": "CNY", "Rate": "x", "Date": "22.10.2026"},
        {"Ccy": "CNY", "Rate": "1", "Date": "2026-10-22"},
        {"Ccy": "CNY", "Date": "22.10.2026"},
        {"Ccy": "CNY", "Nominal": "0", "Rate": "1", "Date": "22.10.2026"},
        {"Ccy": "CNY", "Nominal": "-1", "Rate": "1", "Date": "22.10.2026"},
        {"Ccy": "CNY", "Rate": "0", "Date": "22.10.2026"},
        {"Ccy": "UZS", "Rate": "1", "Date": "22.10.2026"},
    ],
)
def test_parse_cbu_row_invalid(row: dict[str, str]) -> None:
    with pytest.raises(FxError):
        parse_cbu_row(row)


def test_parse_cbu_rows_skips_unknown() -> None:
    rows = [CNY_ROW, {"Ccy": "JPY", "Nominal": "10", "Rate": "800", "Date": "22.10.2026"}]
    assert [r.currency for r in parse_cbu_rows(rows)] == [Currency.CNY]


RATES = [
    FxRate(date(2026, 10, 23), Currency.USD, Decimal("12650")),  # juma
    FxRate(date(2026, 10, 26), Currency.USD, Decimal("12700")),  # dushanba
    FxRate(date(2026, 10, 24), Currency.CNY, Decimal("1790")),
]


def test_rate_on_exact_day() -> None:
    found = rate_on(RATES, "USD", date(2026, 10, 23))
    assert found.rate.rate == Decimal("12650") and not found.is_fallback and found.gap_days == 0


def test_rate_on_weekend_uses_last_working_day() -> None:
    found = rate_on(RATES, Currency.USD, date(2026, 10, 25))  # yakshanba
    assert found.rate.day == date(2026, 10, 23)
    assert found.is_fallback and found.gap_days == 2


def test_rate_on_never_uses_future_rate() -> None:
    with pytest.raises(FxError):
        rate_on(RATES, "USD", date(2026, 10, 22))
    with pytest.raises(FxError):
        rate_on(RATES, "EUR", date(2026, 10, 30))


def test_to_uzs() -> None:
    usd = FxRate(date(2026, 10, 23), Currency.USD, Decimal("12650.123456"))
    assert to_uzs(Money.of("142.50", "USD"), usd) == Money.of("1802642.59", "UZS")
    som = Money.of(5, "UZS")
    assert to_uzs(som) is som
    with pytest.raises(FxError):
        to_uzs(Money.of(1, "USD"))
    with pytest.raises(FxError):
        to_uzs(Money.of(1, "CNY"), usd)


def test_effective_rate() -> None:
    assert effective_rate(Money.of(1000, "CNY"), Money.of("142.50", "USD")) == Decimal("0.142500")
    with pytest.raises(FxError):
        effective_rate(Money.of(0, "CNY"), Money.of(1, "USD"))
    with pytest.raises(FxError):
        effective_rate(Money.of(1, "USD"), Money.of(1, "USD"))


def test_effective_fx_rate_via_usd_card() -> None:
    usd = FxRate(date(2026, 10, 23), Currency.USD, Decimal("12650"))
    r = effective_fx_rate(date(2026, 10, 23), Money.of(1000, "CNY"), Money.of("142.50", "USD"), usd)
    assert r == FxRate(date(2026, 10, 23), Currency.CNY, Decimal("1802.625"), RateSource.EFFECTIVE)


def test_effective_fx_rate_via_uzs_card() -> None:
    r = effective_fx_rate(date(2026, 10, 23), Money.of(3, "CNY"), Money.of(5400, "UZS"))
    assert r.rate == Decimal("1800.000000") and r.source is RateSource.EFFECTIVE


def test_effective_fx_rate_errors() -> None:
    day = date(2026, 10, 23)
    with pytest.raises(FxError):
        effective_fx_rate(day, Money.of(1, "UZS"), Money.of(1, "USD"))
    with pytest.raises(FxError):
        effective_fx_rate(day, Money.of(1, "CNY"), Money.of(1, "USD"))
    cny = FxRate(day, Currency.CNY, Decimal(1))
    with pytest.raises(FxError):
        effective_fx_rate(day, Money.of(1, "CNY"), Money.of(1, "USD"), cny)


def test_manual_rate() -> None:
    r = manual_rate(date(2026, 10, 1), "CNY", "1785.5")
    assert r.source is RateSource.MANUAL and r.rate == Decimal("1785.500000")


@given(
    st.lists(st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 1, 1)), min_size=1),
    st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 1, 1)),
)
def test_rate_on_picks_latest_not_after(days: list[date], ask: date) -> None:
    rates = [FxRate(d, Currency.USD, Decimal(i + 1)) for i, d in enumerate(days)]
    eligible = [d for d in days if d <= ask]
    if not eligible:
        with pytest.raises(FxError):
            rate_on(rates, "USD", ask)
        return
    found = rate_on(rates, "USD", ask)
    assert found.rate.day == max(eligible)
    assert found.gap_days >= 0

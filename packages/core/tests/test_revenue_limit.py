"""F50 (B4.80, ADR-058): yillik tushum chegarasi — soliq to'lovchi turi bo'yicha chegara va 80% / 100% ogohlantirish."""

from datetime import date
from decimal import Decimal

import pytest
from upcore.money import Money
from upcore.tax import (
    SEED_AMOUNTS,
    AmountValue,
    LimitLevel,
    RevenueLimit,
    Taxpayer,
    TaxProfile,
    TaxRegime,
    revenue_limit,
    revenue_limit_status,
)

D = Decimal
DAY = date(2026, 11, 12)


def uzs(value: int | str) -> Money:
    return Money(D(value), "UZS")


def test_limits_from_reference() -> None:
    assert revenue_limit(Taxpayer.INDIVIDUAL, DAY, SEED_AMOUNTS) == uzs(1_000_000_000)
    assert revenue_limit(Taxpayer.SELF_EMPLOYED, DAY, SEED_AMOUNTS) == uzs(100_000_000)
    # MChJ: 12 000 × BHM sanada — 440 000 (2026-09-01 dan), avval 412 000.
    assert revenue_limit(Taxpayer.LLC, DAY, SEED_AMOUNTS) == uzs(5_280_000_000)
    assert revenue_limit(Taxpayer.LLC, date(2026, 8, 31), SEED_AMOUNTS) == uzs(4_944_000_000)
    # Ma'lumotnomada yo'q (2026 dan oldin) — chegara noma'lum.
    assert revenue_limit(Taxpayer.INDIVIDUAL, date(2025, 12, 31), SEED_AMOUNTS) is None
    assert revenue_limit(Taxpayer.LLC, date(2025, 12, 31), SEED_AMOUNTS) is None


def test_reference_row_wins_and_changes_by_date() -> None:
    values = [
        AmountValue("revenue_limit_individual", date(2027, 1, 1), D(1_500_000_000)),
        *SEED_AMOUNTS,
    ]
    assert revenue_limit(Taxpayer.INDIVIDUAL, DAY, values) == uzs(1_000_000_000)
    assert revenue_limit(Taxpayer.INDIVIDUAL, date(2027, 3, 1), values) == uzs(1_500_000_000)


def profile(taxpayer: Taxpayer | None, start: date = date(2026, 1, 1)) -> TaxProfile:
    return TaxProfile(start, TaxRegime.NONE, taxpayer=taxpayer)


@pytest.mark.parametrize(
    ("revenue", "share", "level"),
    [
        (
            799_999_999,
            "0.800000",
            LimitLevel.OK,
        ),  # yaxlitlangan ulush 80%, lekin chegaraga yetmagan
        (800_000_000, "0.8", LimitLevel.NEAR),
        (999_999_999, "1.000000", LimitLevel.NEAR),
        (1_000_000_000, "1", LimitLevel.OVER),
        (1_250_000_000, "1.25", LimitLevel.OVER),
        (0, "0", LimitLevel.OK),
    ],
)
def test_levels(revenue: int, share: str, level: LimitLevel) -> None:
    s = revenue_limit_status([profile(Taxpayer.INDIVIDUAL)], DAY, uzs(revenue), SEED_AMOUNTS)
    assert s is not None
    assert (s.taxpayer, s.year, s.limit) == (Taxpayer.INDIVIDUAL, 2026, uzs(1_000_000_000))
    assert s.share == D(share)
    assert s.level is level


def test_profile_on_day_decides() -> None:
    profiles = [profile(Taxpayer.SELF_EMPLOYED), profile(Taxpayer.INDIVIDUAL, date(2026, 12, 1))]
    s = revenue_limit_status(profiles, DAY, uzs(90_000_000), SEED_AMOUNTS)
    assert s is not None and s.taxpayer is Taxpayer.SELF_EMPLOYED and s.level is LimitLevel.NEAR
    later = revenue_limit_status(profiles, date(2026, 12, 2), uzs(90_000_000), SEED_AMOUNTS)
    assert (
        later is not None and later.taxpayer is Taxpayer.INDIVIDUAL and later.level is LimitLevel.OK
    )


def test_no_status_without_profile_type_or_limit() -> None:
    assert revenue_limit_status([], DAY, uzs(1), SEED_AMOUNTS) is None
    assert revenue_limit_status([profile(None)], DAY, uzs(1), SEED_AMOUNTS) is None
    assert revenue_limit_status([profile(Taxpayer.LLC)], DAY, uzs(1), []) is None
    zero = [AmountValue("revenue_limit_self_employed", date(2026, 1, 1), D(0))]
    assert revenue_limit_status([profile(Taxpayer.SELF_EMPLOYED)], DAY, uzs(1), zero) is None


def test_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        RevenueLimit(Taxpayer.INDIVIDUAL, 2026, uzs(1), uzs(0))

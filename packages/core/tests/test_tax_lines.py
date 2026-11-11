"""F11 (ADR-058): dinamik soliq profili — soliq qatorlari, BHM ma'lumotnomasi, qat'iy soliqning kunlik hisobi."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from upcore.pnl import TaxBase, TaxRule
from upcore.tax import (
    SEED_AMOUNTS,
    AmountValue,
    FixedPeriod,
    LineKind,
    TaxLine,
    TaxProfile,
    TaxRegime,
    amount_on,
    fixed_daily,
    percent_rules,
    profile_lines,
)

D = Decimal

PERCENT = TaxLine("Aylanmadan soliq", LineKind.PERCENT, rate_pct=D(1))
SOCIAL = TaxLine("Ijtimoiy soliq", LineKind.FIXED, bhm_count=D(1))
YATT = TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(PERCENT, SOCIAL))


def bhm(day: date) -> D | None:
    return amount_on(SEED_AMOUNTS, "bhm", day)


def accrued(profiles: list[TaxProfile], start: date, end: date, name: str) -> D:
    total = D(0)
    for i in range((end - start).days + 1):
        value = fixed_daily(profiles, start + timedelta(days=i), bhm)[name]
        assert value is not None
        total += value
    return total


# Ma'lumotnoma --------------------------------------------------------------------------------


def test_bhm_reference_is_dated() -> None:
    assert bhm(date(2025, 7, 31)) is None  # birinchi qiymatdan oldin — noma'lum, 0 emas
    assert bhm(date(2025, 8, 1)) == D(412_000)
    assert bhm(date(2026, 8, 31)) == D(412_000)
    assert bhm(date(2026, 9, 1)) == D(440_000)
    assert amount_on(SEED_AMOUNTS, "no_such_code", date(2026, 9, 1)) is None
    more = (*SEED_AMOUNTS, AmountValue("bhm", date(2027, 1, 1), D(500_000)))
    assert amount_on(more, "bhm", date(2027, 1, 1)) == D(500_000)


# Qator tekshiruvi -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": " ", "kind": LineKind.PERCENT, "rate_pct": D(1)},
        {"name": "x", "kind": LineKind.PERCENT, "rate_pct": D(0)},
        {"name": "x", "kind": LineKind.PERCENT, "rate_pct": D(101)},
        {"name": "x", "kind": LineKind.PERCENT, "rate_pct": D(1), "amount": D(5)},
        {"name": "x", "kind": LineKind.FIXED},
        {"name": "x", "kind": LineKind.FIXED, "amount": D(5), "bhm_count": D(1)},
        {"name": "x", "kind": LineKind.FIXED, "amount": D(0)},
        {"name": "x", "kind": LineKind.FIXED, "bhm_count": D(-1)},
        {"name": "x", "kind": LineKind.FIXED, "amount": D(5), "rate_pct": D(1)},
    ],
)
def test_tax_line_validation(kwargs: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError):
        TaxLine(**kwargs)


def test_profile_rejects_duplicate_line_names() -> None:
    with pytest.raises(ValueError):
        TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(PERCENT, PERCENT))
    with pytest.raises(ValueError):
        TaxProfile(
            date(2026, 1, 1),
            TaxRegime.TURNOVER,
            lines=(PERCENT, TaxLine("aylanmadan SOLIQ", LineKind.PERCENT, rate_pct=D(2))),
        )


# Eski profillar ---------------------------------------------------------------------------------


def test_legacy_profiles_map_to_lines() -> None:
    legacy = TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, D(4), TaxBase.PAYOUT)
    [line] = profile_lines(legacy)
    assert line.kind is LineKind.PERCENT and line.rate_pct == D(4) and line.base is TaxBase.PAYOUT
    assert profile_lines(TaxProfile(date(2026, 1, 1), TaxRegime.AGENT)) == ()
    assert profile_lines(TaxProfile(date(2026, 1, 1), TaxRegime.NONE)) == ()
    assert profile_lines(TaxProfile(date(2026, 1, 1), TaxRegime.VAT_PROFIT, vat_pct=D(12))) == ()
    assert profile_lines(TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, D(0))) == ()
    assert profile_lines(YATT) == (PERCENT, SOCIAL)  # qatorlar bor bo'lsa — o'zlari


def test_percent_rules_per_day() -> None:
    payout = TaxLine("Qo'shimcha", LineKind.PERCENT, rate_pct=D(2), base=TaxBase.PAYOUT)
    profiles = [
        YATT,
        TaxProfile(date(2026, 11, 1), TaxRegime.TURNOVER, lines=(PERCENT, payout)),
        TaxProfile(date(2026, 12, 1), TaxRegime.NONE),
    ]
    assert percent_rules(profiles, date(2025, 12, 31)) == ()  # profil yo'q
    assert percent_rules(profiles, date(2026, 10, 31)) == (("Aylanmadan soliq", TaxRule(D(1))),)
    assert percent_rules(profiles, date(2026, 11, 15)) == (
        ("Aylanmadan soliq", TaxRule(D(1))),
        ("Qo'shimcha", TaxRule(D(2), TaxBase.PAYOUT)),
    )
    assert percent_rules(profiles, date(2026, 12, 1)) == ()


# Qat'iy soliq: kunlarga teng taqsimot ----------------------------------------------------------


def test_fixed_month_sums_exactly() -> None:
    # Noyabr 2026 — 30 kun, 1 BHM = 440 000: har qanday ketma-ket kunlar yig'indisi aniq.
    assert accrued([YATT], date(2026, 11, 1), date(2026, 11, 30), "Ijtimoiy soliq") == D(440_000)
    assert accrued([YATT], date(2026, 11, 1), date(2026, 11, 10), "Ijtimoiy soliq") == D(
        "146666.67"
    )
    assert accrued([YATT], date(2026, 11, 11), date(2026, 11, 30), "Ijtimoiy soliq") == D(
        "293333.33"
    )
    first = fixed_daily([YATT], date(2026, 11, 1), bhm)["Ijtimoiy soliq"]
    assert first == D("14666.67")


def test_fixed_follows_bhm_by_month() -> None:
    # Avgust — 412 000 (31 kun), sentabr — 440 000 (BHM 1 sentabrdan).
    assert accrued([YATT], date(2026, 8, 1), date(2026, 8, 31), "Ijtimoiy soliq") == D(412_000)
    assert accrued([YATT], date(2026, 9, 1), date(2026, 9, 30), "Ijtimoiy soliq") == D(440_000)
    # Oy chegarasida har oy o'z BHM'i bilan: 7 kun × 412 000 / 31 + 5 kun × 440 000 / 30.
    seven = accrued([YATT], date(2026, 8, 25), date(2026, 8, 31), "Ijtimoiy soliq")
    five = accrued([YATT], date(2026, 9, 1), date(2026, 9, 5), "Ijtimoiy soliq")
    assert seven == D("93032.26") and five == D("73333.33")
    assert accrued([YATT], date(2026, 8, 25), date(2026, 9, 5), "Ijtimoiy soliq") == seven + five


def test_fixed_quarter_year_and_amount() -> None:
    q = TaxLine("Choraklik", LineKind.FIXED, bhm_count=D(3), period=FixedPeriod.QUARTER)
    y = TaxLine("Yillik", LineKind.FIXED, amount=D(1_200_000), period=FixedPeriod.YEAR)
    p = TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(q, y))
    # IV chorak: 92 kun, davr boshidagi BHM (1 oktabr) = 440 000 → 3 × 440 000.
    assert accrued([p], date(2026, 10, 1), date(2026, 12, 31), "Choraklik") == D(1_320_000)
    # 2026 — 365 kun.
    assert accrued([p], date(2026, 1, 1), date(2026, 12, 31), "Yillik") == D(1_200_000)
    # III chorak: davr boshidagi BHM (1 iyul) = 412 000.
    assert accrued([p], date(2026, 7, 1), date(2026, 9, 30), "Choraklik") == D(1_236_000)


def test_fixed_starts_at_profile_date_and_stops_with_profile() -> None:
    a = TaxProfile(date(2026, 10, 1), TaxRegime.TURNOVER, lines=(SOCIAL,))
    b = TaxProfile(date(2026, 10, 16), TaxRegime.NONE)
    assert fixed_daily([a, b], date(2026, 9, 30), bhm) == {}  # profil boshlanmagan
    assert fixed_daily([a, b], date(2026, 10, 16), bhm) == {}  # profil almashdi — qator yo'q
    assert accrued([a, b], date(2026, 10, 1), date(2026, 10, 15), "Ijtimoiy soliq") == D(
        "212903.23"
    )
    # Avvalgi profil: oktabrning boshidan emas, profil sanasidan; 15 kun × 440 000 / 31.


def test_fixed_without_bhm_is_unknown_not_zero() -> None:
    p = TaxProfile(date(2025, 1, 1), TaxRegime.TURNOVER, lines=(SOCIAL,))
    assert fixed_daily([p], date(2025, 7, 15), bhm) == {"Ijtimoiy soliq": None}
    # Qat'iy summa — BHM'siz ham ma'lum.
    fixed = TaxLine("Qat'iy", LineKind.FIXED, amount=D(310_000))
    p2 = TaxProfile(date(2025, 1, 1), TaxRegime.TURNOVER, lines=(fixed,))
    assert fixed_daily([p2], date(2025, 7, 15), bhm)["Qat'iy"] == D("10000.00")  # 31 kun

from datetime import date, timedelta

import pytest
from upcore.metrics import Period
from upcore.waivers import (
    SALE_LOGISTICS,
    FeeWaiver,
    Suggestion,
    WaiverError,
    active,
    check,
    suggestions,
    waiver_for,
    waiver_kinds,
)


def d(day: int, month: int = 10) -> date:
    return date(2026, month, day)


def days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def test_kinds_are_dynamic_and_exclude_income() -> None:
    kinds = waiver_kinds()
    assert kinds[0] == SALE_LOGISTICS
    assert "storage" in kinds and "return_storage" in kinds and "advertising" in kinds
    # Kompensatsiya — kirim; logistika xarajati va balans tuzatishi P&L'ga kirmaydi.
    assert not {"compensation", "logistics", "logistics_refund", "balance_correction"} & set(kinds)


def test_check() -> None:
    assert check(d(1), d(31), ["storage", SALE_LOGISTICS, "storage"]) == [SALE_LOGISTICS, "storage"]
    with pytest.raises(WaiverError) as e:
        check(d(2), d(1), [SALE_LOGISTICS])
    assert e.value.code == "bad_period"
    with pytest.raises(WaiverError) as e:
        check(d(1, 1), date(2027, 1, 2), [SALE_LOGISTICS])
    assert e.value.code == "bad_period"
    with pytest.raises(WaiverError) as e:
        check(d(1), d(2), [])
    assert e.value.code == "bad_kinds"
    with pytest.raises(WaiverError) as e:
        check(d(1), d(2), ["compensation"])
    assert e.value.code == "bad_kinds" and "compensation" in str(e.value)


def test_covers_overlaps_and_waiver_for() -> None:
    oct_all = FeeWaiver(
        "w1", None, d(10), d(31), frozenset({SALE_LOGISTICS, "storage"}), "Nosozlik"
    )
    shop_a = FeeWaiver("w2", "A", d(5), d(12), frozenset({"storage"}))
    rejected = FeeWaiver("w0", "B", d(1), d(9), frozenset({SALE_LOGISTICS}), dismissed=True)
    waivers = [oct_all, shop_a, rejected]

    assert oct_all.covers("B", d(10)) and not oct_all.covers("B", d(9))
    assert shop_a.covers("A", d(5)) and not shop_a.covers("B", d(5))
    assert oct_all.overlaps(Period(d(1), d(10)), frozenset({"B"}))
    assert not shop_a.overlaps(Period(d(1), d(31)), frozenset({"B"}))
    assert not shop_a.overlaps(Period(d(13), d(31)))
    assert active(waivers) == [oct_all, shop_a]

    assert waiver_for(waivers, "A", d(11)) is shop_a  # eng erta boshlangani
    assert waiver_for(waivers, "B", d(11)) is oct_all
    assert waiver_for(waivers, "B", d(5)) is None  # rad etilgan taklif belgilamaydi
    assert waiver_for(waivers, "A", d(1, 11)) is None


def test_suggestions_skip_known_days() -> None:
    free = {"B": days(d(1), d(20)), "A": [d(3), d(4), d(8)], "C": []}
    known = [
        FeeWaiver(
            "w0", "B", d(1), d(9), frozenset({SALE_LOGISTICS}), dismissed=True
        ),  # rad etilgan
        FeeWaiver(
            "w1", None, d(15), d(31), frozenset({"storage"})
        ),  # boshqa tur — baribir qoplaydi
    ]
    assert suggestions(free, known) == [
        Suggestion("A", Period(d(3), d(4))),
        Suggestion("A", Period(d(8), d(8))),
        Suggestion("B", Period(d(10), d(14))),
    ]
    assert suggestions({}, known) == []

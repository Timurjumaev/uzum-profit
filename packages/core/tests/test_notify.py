"""upcore.notify (02 M15, B6.1): katalog, tinch soatlar, xulosa vaqti, F53."""

from datetime import date, datetime, time
from decimal import Decimal as D

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.notify import (
    CATALOG,
    Audience,
    Event,
    audience_of,
    due_at,
    in_quiet,
    line_profit,
    loss_streak,
    merged_params,
    parse_hhmm,
    returns_spike,
    summary_due,
    week_start,
)


def test_catalog_covers_every_event_and_marks_later_stages() -> None:
    assert set(CATALOG) == set(Event)
    assert CATALOG[Event.SYNC_STOPPED].critical
    assert CATALOG[Event.DAILY_SUMMARY].stage is None
    assert CATALOG[Event.PAYOUT_LATE].stage == "B5.7"


def test_audience_by_role() -> None:
    assert Audience.STOCK not in audience_of("accountant")
    assert Audience.FINANCE not in audience_of("warehouse")
    assert audience_of("owner") == frozenset(Audience)
    assert audience_of("nobody") == frozenset()


def test_params_merge_only_known_keys() -> None:
    assert merged_params(Event.LOSS_SALES, {"streak": 5, "x": 1}) == {"streak": 5}
    assert merged_params(Event.DAILY_SUMMARY, None) == {"at": "09:00"}
    assert parse_hhmm("07:30") == time(7, 30)
    with pytest.raises(ValueError):
        parse_hhmm("7")


@pytest.mark.parametrize(
    ("at", "start", "end", "quiet"),
    [
        (time(23, 0), time(22, 0), time(8, 0), True),
        (time(7, 59), time(22, 0), time(8, 0), True),
        (time(8, 0), time(22, 0), time(8, 0), False),
        (time(13, 0), time(12, 0), time(14, 0), True),
        (time(14, 0), time(12, 0), time(14, 0), False),
        (time(3, 0), None, time(8, 0), False),
        (time(3, 0), time(8, 0), time(8, 0), False),
    ],
)
def test_quiet_hours(at: time, start: time | None, end: time | None, quiet: bool) -> None:
    assert in_quiet(at, start, end) is quiet


def test_due_at_moves_to_end_of_quiet_hours_unless_critical() -> None:
    q = (time(22, 0), time(8, 0))
    night = datetime(2026, 11, 15, 23, 30)
    assert due_at(night, *q, critical=False) == datetime(2026, 11, 16, 8, 0)
    assert due_at(datetime(2026, 11, 16, 6, 0), *q, critical=False) == datetime(2026, 11, 16, 8, 0)
    assert due_at(night, *q, critical=True) == night
    day = datetime(2026, 11, 16, 12, 0)
    assert due_at(day, *q, critical=False) == day


@given(st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2027, 1, 1)))
def test_due_at_is_never_inside_quiet_hours(now: datetime) -> None:
    q = (time(22, 0), time(8, 0))
    out = due_at(now, *q, critical=False)
    assert out >= now and not in_quiet(out.time(), *q)


def test_summary_due() -> None:
    assert summary_due(datetime(2026, 11, 15, 9, 0), time(9, 0))
    assert not summary_due(datetime(2026, 11, 15, 8, 59), time(9, 0))
    # B6.4 (A6): haftalik xulosa ham faqat dushanba emas — vaqti kelgan har kuni (hafta kaliti takrorni to'sadi).
    assert summary_due(datetime(2026, 11, 15, 10, 0), time(9, 0))  # yakshanba
    assert summary_due(datetime(2026, 11, 17, 9, 0), time(9, 0))  # seshanba
    assert not summary_due(datetime(2026, 11, 17, 8, 0), time(9, 0))
    assert week_start(date(2026, 11, 15)) == date(2026, 11, 9)


def test_f53_loss_streak() -> None:
    assert loss_streak([D(5), D(-1), D(-2), D(-3)], 3)
    assert not loss_streak([D(-1), D(-2), D(0)], 3)
    assert not loss_streak([D(-1), None, D(-2), D(-3)][:3], 3)
    assert not loss_streak([D(-1), D(-2)], 3)
    assert not loss_streak([D(-1)], 0)


def test_line_profit() -> None:
    assert line_profit(D(9000), D(10000)) == D(-1000)
    assert line_profit(None, D(1)) is None
    assert line_profit(D(1), None) is None


def test_returns_spike_needs_user_choice_and_double_share() -> None:
    """B5.4 (Temur qarori): N kiritilmaguncha signal yo'q; 7 kun ulushi ≥ 2 × 30 kunlik va qaytish soni ≥ N."""
    assert CATALOG[Event.RETURNS_SPIKE].stage is None
    assert merged_params(Event.RETURNS_SPIKE, None) == {"level": None, "min_returns": None}
    # 7 kun: 80 sotildi, 20 qaytdi = 20%; 30 kun: 400 sotildi, 40 qaytdi = 9,1% → 2,2 barobar
    assert returns_spike(80, 20, 400, 40, 5)
    assert not returns_spike(80, 20, 400, 40, None)  # N yo'q
    assert not returns_spike(80, 20, 400, 40, 21)  # N dan kam
    assert not returns_spike(90, 10, 400, 40, 5)  # 10% va 9,1% — oshmagan
    assert not returns_spike(0, 0, 0, 0, 1)  # ma'lumot yo'q
    assert not returns_spike(0, 0, 100, 5, 1)  # 7 kunda qaytish yo'q
    assert returns_spike(0, 3, 97, 3, 3)  # 7 kunda hammasi qaytgan, avval hech biri

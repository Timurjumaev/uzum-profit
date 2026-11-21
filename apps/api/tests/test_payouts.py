"""B5.7 to'lov prognozi (F38, haqiqiy PostgreSQL): jadval Sozlamalardan, qoidalar ma'lumotnomadan; yechilgan qatorlar
kirmaydi, yechishga tayyor va Jarayondagi (R bilan, taxminiy) alohida, topshirilmagani — sana noma'lum."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import test_purchases as tp
from psycopg.types.json import Jsonb
from test_purchases import ok, send
from test_reports import World
from upapi.reports.common import today

db = tp.db
world = tp.world

D = Decimal


def _line(
    w: World, ext: int, status: str, profit: int, issued: datetime | None, withdrawn: int = 0
) -> None:
    a = w.a
    a.insert(
        "sale_items",
        shop_id=a.shop_id,
        external_id=ext,
        order_id=ext,
        status=status,
        ordered_at=datetime.now(UTC) - timedelta(days=30),
        sell_price=profit,
        amount=1,
        seller_profit=profit,
        issued_at=issued,
        raw=Jsonb({"withdrawnProfit": withdrawn}),
    )


def test_forecast_without_schedule_is_empty_and_not_invented(world: World) -> None:
    body = ok(send(world, "GET", "payouts/forecast"))
    assert body["schedule"] is None and body["events"] == []
    assert body["rules"]["lag_days"] == 10  # qoidalar boshlang'ich (ma'lumotnoma)


def test_forecast_available_processing_and_unknown(world: World) -> None:
    """Qoida (Temur, 2026-11-22): to'lov sanasi D ga olib ketilgan kuni ≤ D − 11 bo'lganlar kiradi; ``withdrawnProfit`` ahamiyatsiz —
    to'lovi allaqachon yaratilgan qator (``withdrawnProfit`` = 0 bo'lsa ham) prognozga kirmaydi."""
    from upcore.cash import SEED_SCHEDULES, ScheduleKind, scheduled_on_or_before

    w = world
    now = datetime.now(UTC)
    ok(send(w, "POST", "payout-schedules", kind="biweekly", valid_from="2026-01-01"), 201)
    terms = SEED_SCHEDULES[ScheduleKind.BIWEEKLY]
    prev = scheduled_on_or_before(today(), terms)  # oxirgi yaratilgan to'lov sanasi (≤ bugun)
    at = lambda day: datetime(day.year, day.month, day.day, 7, tzinfo=UTC)  # noqa: E731
    base = 9_000_000
    # Oxirgi to'lovdan keyin olib ketilgan, 10 kun o'tgan — yechishga tayyor (kesim: prev − 11 kun).
    _line(w, base + 1, "TO_WITHDRAW", 100_000, at(prev - timedelta(days=10)))
    _line(w, base + 3, "PROCESSING", 200_000, now - timedelta(days=3))  # 7 kundan keyin yakunlanadi
    _line(w, base + 4, "PROCESSING", 30_000, None)  # olib ketilmagan — sana noma'lum
    _line(w, base + 5, "CANCELED", 999_999, at(prev - timedelta(days=10)))  # hisobga kirmaydi
    body = ok(send(w, "GET", "payouts/forecast"))
    assert body["schedule"] == "biweekly" and D(str(body["fee_pct"])) == 0
    assert D(str(body["available"])) >= 100_000  # boshqa testlardan qolgan qatorlar bo'lishi mumkin
    assert D(str(body["unknown_date"])) >= 30_000
    assert body["events"], body
    first = body["events"][0]
    assert first["expected"] > today().isoformat() and first["latest"] >= first["expected"]
    assert D(str(first["net"])) == D(str(first["gross"])) - D(str(first["fee"]))
    assert isinstance(first["estimated"], bool)
    # Kesimdagi qator (prev − 11 kun olib ketilgan): to'lovi prev da yaratilgan — withdrawnProfit = 0 bo'lsa ham kirmaydi.
    _line(w, base + 2, "TO_WITHDRAW", 70_000, at(prev - timedelta(days=11)), withdrawn=0)
    again = ok(send(w, "GET", "payouts/forecast"))
    assert again["available"] == body["available"]
    assert [e["gross"] for e in again["events"]] == [e["gross"] for e in body["events"]]


def test_forecast_subtracts_estimated_services(world: World) -> None:
    """Ushlanmalar: oxirgi 30 kun reklama/saqlash/jarima o'rtachasi × to'lov davri uzunligi to'lovdan ayiriladi (yechish haqi kirmaydi)."""
    from upcore.cash import SEED_SCHEDULES, ScheduleKind, scheduled_on_or_before

    w = world
    send(
        w, "POST", "payout-schedules", kind="biweekly", valid_from="2026-01-01"
    )  # oldingi testda bo'lsa — 409, zarar yo'q
    prev = scheduled_on_or_before(today(), SEED_SCHEDULES[ScheduleKind.BIWEEKLY])
    _line(
        w,
        9_100_001,
        "TO_WITHDRAW",
        5_000_000,
        datetime(prev.year, prev.month, prev.day, 7, tzinfo=UTC) - timedelta(days=10),
    )
    before = ok(send(w, "GET", "payouts/forecast"))
    total_before = sum(D(str(e["gross"])) for e in before["events"])
    w.a.insert(
        "mp_expenses",
        shop_id=w.a.shop_id,
        external_id=9_100_100,
        category="advertising",
        type="OUTCOME",
        amount=D(300_000),
        created_on=datetime.now(UTC) - timedelta(days=1),
    )
    w.a.insert(  # yechish haqi hisobga kirmaydi
        "mp_expenses",
        shop_id=w.a.shop_id,
        external_id=9_100_101,
        category="withdrawal_fee",
        type="OUTCOME",
        amount=D(900_000),
        created_on=datetime.now(UTC) - timedelta(days=1),
    )
    after = ok(send(w, "GET", "payouts/forecast"))
    total_after = sum(D(str(e["gross"])) for e in after["events"])
    held = total_before - total_after
    # 300 000 / 30 kun = 10 000 so'm/kun × (14..16 kun) × kamida bitta to'lov davri — yechish haqi (900 000) ta'sir qilmagan.
    assert D(130_000) <= held <= D(320_000), held


def test_forecast_requires_finance_role(world: World) -> None:
    assert send(world, "GET", "payouts/forecast", role="warehouse").status_code == 403
    assert send(world, "GET", "payouts/forecast", role="accountant").status_code == 200


def test_rules_follow_reference_tables(world: World) -> None:
    w = world
    w.api.admin(
        "INSERT INTO ref_amounts (code, valid_from, amount, note) "
        "VALUES ('payout_lag_days', '2026-11-01', 20, 'test-payout')"
    )
    try:
        body: dict[str, Any] = ok(send(w, "GET", "payouts/forecast"))
        assert body["rules"]["lag_days"] == 20  # ma'lumotnoma ustun, kod emas
    finally:
        w.api.admin("DELETE FROM ref_amounts WHERE note = 'test-payout'")

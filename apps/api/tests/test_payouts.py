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
    w = world
    now = datetime.now(UTC)
    ok(send(w, "POST", "payout-schedules", kind="biweekly", valid_from="2026-01-01"), 201)
    base = 9_000_000
    _line(w, base + 1, "TO_WITHDRAW", 100_000, now - timedelta(days=40))  # yechishga tayyor
    _line(
        w, base + 2, "TO_WITHDRAW", 70_000, now - timedelta(days=40), withdrawn=70_000
    )  # yechilgan
    _line(w, base + 3, "PROCESSING", 200_000, now - timedelta(days=3))  # 7 kundan keyin yakunlanadi
    _line(w, base + 4, "PROCESSING", 30_000, None)  # topshirilmagan — sana noma'lum
    _line(w, base + 5, "CANCELED", 999_999, now - timedelta(days=40))  # hisobga kirmaydi
    body = ok(send(w, "GET", "payouts/forecast"))
    assert body["schedule"] == "biweekly" and D(str(body["fee_pct"])) == 0
    # Boshqa testlardan qolgan qatorlar bo'lishi mumkin — kamida shu qatorlar hisoblanadi.
    assert D(str(body["available"])) >= 100_000
    assert D(str(body["unknown_date"])) >= 30_000
    assert body["events"], body
    first = body["events"][0]
    assert first["expected"] > today().isoformat() and first["latest"] >= first["expected"]
    assert D(str(first["net"])) == D(str(first["gross"])) - D(str(first["fee"]))
    total = sum(D(str(e["gross"])) for e in body["events"])
    assert total >= 100_000  # yechilgan (70 000) va bekor (999 999) kirmaydi


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

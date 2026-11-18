"""TM9.6 kelmagan tovar va qaytarilgan pul — o'z tovariga (haqiqiy PostgreSQL, ADR-068 (6), F20, F55): umuman kelmagan
qatorning tovar summasi va xarid ichidagi chiqim ulushi boshqa tovarga yuklanmaydi — "Kelmagan tovar zarari" (F55, sanash
kuniga, foyda hisobida alohida qator); sotuvchi qaytargan summa qatorga (standart — kam kelgan qatorlarga), qatorning
tovar summasidan oshgani — rad; qisman kelgan qator — avvalgidek (tannarx oshadi)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import test_purchases as tp
from test_purchases import ok, send
from test_reports import World

db = tp.db
world = tp.world

D = Decimal


def two_lines(w: World, name: str) -> dict[str, Any]:
    _ia, sku_a = w.a.item(f"{name}-A")
    _ib, sku_b = w.a.item(f"{name}-B")
    return dict(
        ok(
            send(
                w,
                "POST",
                "purchases/quick",
                lines=[
                    {"sku_id": str(sku_a), "qty": 10, "line_sum": "600000"},
                    {"sku_id": str(sku_b), "qty": 10, "line_sum": "400000"},
                ],
                paid_amount="1100000",  # 100 000 — ichki yetkazish (qator summasiga mutanosib)
                currency="UZS",
                ordered_on="2026-10-01",
            ),
            201,
        )
    )


def test_missing_line_is_loss_and_refund_goes_to_it(world: World) -> None:
    w = world
    det = two_lines(w, "Kelmadi")
    pid = det["purchase"]["id"]
    a, b = det["lines"][0]["id"], det["lines"][1]["id"]
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            counted_on="2026-10-05",
            refund_amount="150000",
            refund_currency="UZS",
            lines=[{"line_id": a, "received_qty": 10}, {"line_id": b, "received_qty": 0}],
        )
    )
    lines = {x["id"]: x for x in out["lines"]}
    # Standart: qaytarilgan summa kam kelgan qatorga (B); A ga hech narsa yuklanmadi.
    assert D(lines[b]["refund_amount"]) == D(150_000) and lines[a]["refund_amount"] is None
    assert D(lines[a]["cost"]["total"]) == D(660_000)  # 600 000 + 60 000 ichki yetkazish
    assert D(lines[b]["missing_loss"]) == D(400_000 + 40_000 - 150_000)
    assert out["purchase"]["missing_lines"] == 1
    assert D(out["purchase"]["missing_loss"]) == D(290_000)
    # Foyda hisobida alohida qator, sanash kuniga.
    w.a.recalc(datetime.now(UTC))
    rows = w.a.sql("SELECT day, amount FROM missing_losses WHERE purchase_line_id = %s", [b])
    assert rows == [(datetime(2026, 10, 5).date(), D("290000.00"))]
    pnl = ok(send(w, "GET", "pnl?start=2026-10-01&end=2026-10-31"))
    assert "own:Kelmagan tovar zarari" in {r["code"] for r in pnl["rows"]}
    # Omborchi summalarni ko'rmaydi.
    hidden = ok(send(w, "GET", f"purchases/{pid}", "warehouse"))
    assert hidden["purchase"]["missing_loss"] is None and hidden["purchase"]["missing_lines"] == 1


def test_explicit_line_refund_and_limit(world: World) -> None:
    w = world
    det = two_lines(w, "Qaytar")
    pid = det["purchase"]["id"]
    a, b = det["lines"][0]["id"], det["lines"][1]["id"]
    # Qatorning tovar summasidan (A: 600 000 + 60 000) ko'p — rad, hech narsa saqlanmaydi.
    r = send(
        w,
        "POST",
        f"purchases/{pid}/count",
        refund_currency="UZS",
        lines=[
            {"line_id": a, "received_qty": 8, "refund_amount": "700000"},
            {"line_id": b, "received_qty": 10},
        ],
    )
    assert r.status_code == 422 and r.json()["code"] == "bad_refund"
    assert ok(send(w, "GET", f"purchases/{pid}"))["purchase"]["units_received"] is None
    # Qisman kelgan qatorga yozilgan summa — faqat o'sha qatordan; B o'zgarmaydi.
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            refund_currency="UZS",
            lines=[
                {"line_id": a, "received_qty": 8, "refund_amount": "60000"},
                {"line_id": b, "received_qty": 10},
            ],
        )
    )
    lines = {x["id"]: x for x in out["lines"]}
    assert D(lines[a]["cost"]["total"]) == D(600_000)
    assert D(lines[a]["cost"]["unit_cost"]) == D(75_000)  # 8 dona — tannarx oshdi (ADR-061 §6)
    assert D(lines[b]["cost"]["total"]) == D(440_000)
    assert D(out["purchase"]["refund_amount"]) == D(60_000)
    assert out["purchase"]["missing_lines"] == 0
    # Keyin PATCH bilan (qatorsiz) — standart bo'yicha kam kelgan qatorga.
    out = ok(send(w, "PATCH", f"purchases/{pid}", refund_amount="20000", refund_currency="UZS"))
    lines = {x["id"]: x for x in out["lines"]}
    assert D(lines[a]["refund_amount"]) == D(20_000) and lines[b]["refund_amount"] is None

"""TM5 Omborim (haqiqiy PostgreSQL, ADR-061 §6–§7, §10): SKU bo'yicha qoldiq (sanalgan xaridlardan), boshqa SKU'ga
o'tkazish (tannarx bilan, bekor qilish), keyin topilgan brak — "Brak zarari" (F51) foyda hisobida, lotlar va sotuvlar."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import test_purchases as tp
from test_purchases import D, ok, send
from test_reports import World

db = tp.db
world = tp.world


def counted(w: World, qty: int, sku: str = "sku", paid: str = "1000000") -> dict[str, Any]:
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": str(w.ids[sku]), "qty": qty}],
            paid_amount=paid,
            currency="UZS",
            ordered_on="2026-10-01",
            on_hand=True,
        ),
        201,
    )
    return det


def rows_by_sku(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r["sku_id"]): r for r in body["items"] if r["sku_id"] is not None}


def test_warehouse_and_transfer(world: World) -> None:
    w, a = world, world.a
    sku, sku2 = str(w.ids["sku"]), str(w.ids["sku2"])
    det = counted(w, 100)
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    a.recalc(datetime.now(UTC))  # lot narxlari hisob ishidan
    body = ok(send(w, "GET", "warehouse"))
    row = rows_by_sku(body)[sku]
    assert row["qty"] >= 100 and D(row["unit_cost"]) > 0
    source = next(x for x in row["sources"] if x["line_id"] == line)
    assert source["qty"] == 100 and D(source["unit_cost"]) == D(10_000)
    before2 = rows_by_sku(body).get(sku2, {"qty": 0})["qty"]
    # O'tkazish: 30 dona boshqa SKU'ga — birlik tannarxi bilan.
    body = ok(
        send(w, "POST", "warehouse/transfer", source_line_id=line, to_sku_id=sku2, qty=30), 201
    )
    rows = rows_by_sku(body)
    assert rows[sku2]["qty"] == before2 + 30
    moved = rows[sku2]["transfers_in"][-1]
    assert moved["qty"] == 30 and moved["from_sku_id"] == sku
    pdet = ok(send(w, "GET", f"purchases/{pid}"))
    by_id = {x["id"]: x for x in pdet["lines"]}
    assert by_id[moved["line_id"]]["source_line_id"] == line
    assert D(by_id[moved["line_id"]]["cost"]["unit_cost"]) == D(10_000)
    assert D(by_id[line]["cost"]["unit_cost"]) == D(10_000)
    assert by_id[line]["cost"]["total"] == "700000.00" or D(by_id[line]["cost"]["total"]) == D(
        700_000
    )
    assert pdet["purchase"]["units_ordered"] == 100  # o'tkazilgan qator ikki marta sanalmaydi
    a.recalc(datetime.now(UTC))
    lots = {str(r[0]): (r[1], D(r[2])) for r in a.sql("SELECT purchase_line_id, qty, total FROM lots WHERE purchase_line_id = ANY(%s)", [[line, moved["line_id"]]])}  # fmt: skip
    assert lots[line] == (70, D(700_000)) and lots[moved["line_id"]] == (30, D(300_000))

    # Xatolar: ortiqcha dona, o'sha SKU, o'tkazilgan qatordan qayta, o'tkazilgan qatorni tahrirlash / sanash.
    r = send(w, "POST", "warehouse/transfer", source_line_id=line, to_sku_id=sku2, qty=71)
    assert r.status_code == 422 and r.json()["code"] == "bad_transfer"
    r = send(w, "POST", "warehouse/transfer", source_line_id=line, to_sku_id=sku, qty=1)
    assert r.status_code == 422
    r = send(w, "POST", "warehouse/transfer", source_line_id=moved["line_id"], to_sku_id=sku, qty=1)
    assert r.status_code == 422
    r = send(
        w, "POST", "warehouse/transfer", source_line_id=str(uuid.uuid4()), to_sku_id=sku, qty=1
    )
    assert r.status_code == 404
    r = send(w, "PATCH", f"purchases/{pid}/lines/{moved['line_id']}", received_qty=1)
    assert r.status_code == 409 and r.json()["code"] == "transfer_line"
    r = send(w, "DELETE", f"purchases/{pid}/lines/{line}")
    assert r.status_code == 409 and r.json()["code"] == "line_in_use"
    r = send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": line, "received_qty": 20}])
    assert r.status_code == 422
    r = send(
        w,
        "POST",
        f"purchases/{pid}/count",
        lines=[{"line_id": moved["line_id"], "received_qty": 1}],
    )
    assert r.status_code == 409
    assert send(w, "POST", "warehouse/transfer", "accountant", source_line_id=line, to_sku_id=sku2, qty=1).status_code == 403  # fmt: skip

    # Bekor qilish: donalar manba SKU'ga qaytadi.
    assert send(w, "DELETE", f"warehouse/transfers/{moved['line_id']}").status_code == 204
    assert send(w, "DELETE", f"warehouse/transfers/{line}").status_code == 404
    pdet = ok(send(w, "GET", f"purchases/{pid}"))
    assert len(pdet["lines"]) == 1 and D(pdet["lines"][0]["cost"]["total"]) == D(1_000_000)


def test_warehouse_hides_amounts_for_warehouse_role(world: World) -> None:
    w = world
    counted(w, 5)
    body = ok(send(w, "GET", "warehouse", "warehouse"))
    assert body["amounts"] is False and body["total_value"] is None
    assert all(r["unit_cost"] is None and r["value"] is None for r in body["items"])
    assert all(s["unit_cost"] is None for r in body["items"] for s in r["sources"])


def test_defect_writeoff_is_pnl_loss(world: World) -> None:
    w, a = world, world.a
    sku = str(w.ids["sku"])
    item = str(w.ids["item"])
    det = counted(w, 10, paid="100000")
    line = det["lines"][0]["id"]
    before = rows_by_sku(ok(send(w, "GET", "warehouse")))[sku]["qty"]
    move = ok(
        send(
            w,
            "POST",
            "stock-moves",
            item_id=item,
            kind="writeoff",
            qty=2,
            day="2026-10-10",
            reason="defect",
            sku_id=sku,
            purchase_line_id=line,
        ),
        201,
    )
    assert move["reason"] == "defect" and move["sku_id"] == sku
    assert rows_by_sku(ok(send(w, "GET", "warehouse")))[sku]["qty"] == before - 2
    a.recalc(datetime.now(UTC))
    cost = a.sql("SELECT cost FROM stock_moves WHERE id = %s", [move["id"]])[0][0]
    assert cost is not None and cost > 0
    moves = ok(send(w, "GET", f"items/{item}/stock-moves"))["items"]
    assert D(next(x for x in moves if x["id"] == move["id"])["cost"]) == cost
    assert next(x for x in ok(send(w, "GET", f"items/{item}/stock-moves", "warehouse"))["items"] if x["id"] == move["id"])["cost"] is None  # fmt: skip
    pnl = ok(send(w, "GET", "pnl?start=2026-10-01&end=2026-10-31"))
    codes = {r["code"]: r for r in pnl["rows"]}
    assert "own:Brak zarari" in codes
    # Sabab faqat hisobdan chiqarishda; SKU boshqa tovarniki — rad.
    r = send(
        w,
        "POST",
        "stock-moves",
        item_id=item,
        kind="adjust",
        qty=1,
        day="2026-10-10",
        reason="defect",
    )
    assert r.status_code == 422
    r = send(
        w,
        "POST",
        "stock-moves",
        item_id=item,
        kind="writeoff",
        qty=1,
        day="2026-10-10",
        sku_id=str(w.ids["sku2"]),
    )
    assert r.status_code == 422
    r = send(
        w,
        "POST",
        "stock-moves",
        item_id=item,
        kind="writeoff",
        qty=1,
        day="2026-10-10",
        sku_id=str(uuid.uuid4()),
    )
    assert r.status_code == 404

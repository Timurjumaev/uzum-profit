"""TM9.3 butunlik himoyasi (haqiqiy PostgreSQL, ADR-068 (3); 02 M10): jo'natilgan, o'tkazilgan yoki hisobdan chiqarilgan
donasi bor xarid va qator o'chirilmaydi, soni shulardan kamga tushmaydi, SKU'si almashtirilmaydi; qabul qilingan
postavkaga bog'langan jo'natma bekor qilinmaydi; M10 tenglamasi har SKU uchun; manfiy qoldiq 0 ga qisilmaydi
(Omborim ``broken``, ``realcheck`` ``supply``)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import test_purchases as tp
from test_purchases import ok, send
from test_reports import World
from upapi import realcheck as rc
from upapi.reports import integrity

db = tp.db
world = tp.world

_ext = iter(range(81_000, 82_000))
_barcode = iter(range(4_780_000_100_000, 4_780_000_200_000))


def fresh_sku(w: World, name: str) -> str:
    """Har test o'z SKU'si bilan (baza modul bo'yicha umumiy)."""
    item, sku = w.a.item(name)
    w.a.sql("UPDATE mp_skus SET barcode = %s WHERE id = %s", [str(next(_barcode)), sku])
    w.ids[name] = sku
    w.ids[f"{name}:item"] = item
    return str(sku)


def counted(w: World, sku: str, qty: int) -> dict[str, Any]:
    return ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": sku, "qty": qty}],
            paid_amount=str(qty * 10_000),
            currency="UZS",
            ordered_on="2026-10-01",
            on_hand=True,
        ),
        201,
    )


def dispatch(w: World, sku: str, qty: int) -> str:
    out = ok(
        send(
            w, "POST", "dispatches", shop_id=str(w.a.shop_id), items=[{"sku_id": sku, "qty": qty}]
        ),
        201,
    )
    return str(out["id"])


def row_of(w: World, sku: str) -> dict[str, Any] | None:
    return next(
        (r for r in ok(send(w, "GET", "warehouse"))["items"] if r["sku_id"] == sku),
        None,
    )


def code(r: Any) -> tuple[int, str]:
    return r.status_code, r.json().get("code")


def test_dispatched_units_protect_purchase(world: World) -> None:
    w, a = world, world.a
    sku = fresh_sku(w, "Integrity-1")
    det = counted(w, sku, 10)
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    a.recalc(datetime.now(UTC))
    did = dispatch(w, sku, 6)

    assert code(send(w, "DELETE", f"purchases/{pid}")) == (409, "units_dispatched")
    assert code(send(w, "DELETE", f"purchases/{pid}/lines/{line}")) == (409, "units_dispatched")
    r = send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": line, "received_qty": 5}])
    assert code(r) == (409, "units_dispatched")
    r = send(w, "PATCH", f"purchases/{pid}/lines/{line}", received_qty=5)
    assert code(r) == (409, "units_dispatched")  # sog' 5 < jo'natilgan 6
    other = fresh_sku(w, "Integrity-1b")
    r = send(w, "PATCH", f"purchases/{pid}/lines/{line}", sku_id=other)
    assert code(r) == (409, "units_dispatched")
    r = send(w, "PATCH", f"purchases/{pid}", dates={"received": None})
    assert code(r) == (409, "units_dispatched")
    # Jo'natilgan donadan ortig'i o'tkazilmaydi: omborimda 4 dona.
    r = send(w, "POST", "warehouse/transfer", source_line_id=line, to_sku_id=other, qty=5)
    assert code(r) == (422, "bad_transfer")

    # Ruxsat etilgani: sog' dona jo'natilgandan kam emas (8 ≥ 6) — Omborimda 2.
    ok(send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": line, "received_qty": 8}]))
    row = row_of(w, sku)
    assert row is not None and row["qty"] == 2 and row["broken"] is False
    # Jo'natma bekor — himoya tushadi.
    ok(send(w, "POST", f"dispatches/{did}/cancel"))
    assert send(w, "DELETE", f"purchases/{pid}").status_code == 204
    assert row_of(w, sku) is None


def test_transfers_and_writeoffs_protect(world: World) -> None:
    w, a = world, world.a
    sku, sku2 = fresh_sku(w, "Integrity-2"), fresh_sku(w, "Integrity-2b")
    det = counted(w, sku, 10)
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    a.recalc(datetime.now(UTC))
    moved = ok(
        send(w, "POST", "warehouse/transfer", source_line_id=line, to_sku_id=sku2, qty=4), 201
    )
    moved_line = next(x for x in moved["items"] if x["sku_id"] == sku2)["transfers_in"][0][
        "line_id"
    ]
    # O'tkazilib kelgan donalar jo'natilgan — o'tkazmani bekor qilib bo'lmaydi.
    did = dispatch(w, sku2, 3)
    r = send(w, "DELETE", f"warehouse/transfers/{moved_line}")
    assert code(r) == (409, "units_dispatched")
    ok(send(w, "POST", f"dispatches/{did}/cancel"))
    assert send(w, "DELETE", f"warehouse/transfers/{moved_line}").status_code == 204

    # SKU bo'yicha (qatorga bog'lanmagan) hisobdan chiqarish: 7 dona — Omborimda 3; sanalganni 5 ga tushirib bo'lmaydi.
    ok(
        send(
            w,
            "POST",
            "stock-moves",
            item_id=str(w.ids["Integrity-2:item"]),
            sku_id=sku,
            kind="writeoff",
            qty=7,
            day="2026-10-05",
            reason="defect",
        ),
        201,
    )
    r = send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": line, "received_qty": 5}])
    assert code(r) == (409, "units_written_off")
    assert code(send(w, "DELETE", f"purchases/{pid}")) == (409, "units_written_off")
    # Qatorga yozilgan hisobdan chiqarish — qator darajasida.
    ok(
        send(
            w,
            "POST",
            "stock-moves",
            item_id=str(w.ids["Integrity-2:item"]),
            sku_id=sku,
            purchase_line_id=line,
            kind="writeoff",
            qty=1,
            day="2026-10-05",
        ),
        201,
    )
    r = send(w, "PATCH", f"purchases/{pid}/lines/{line}", sku_id=sku2)
    assert code(r) == (409, "units_written_off")


def test_accepted_dispatch_not_canceled(world: World) -> None:
    w, a = world, world.a
    sku = fresh_sku(w, "Integrity-3")
    counted(w, sku, 5)
    a.recalc(datetime.now(UTC))
    did = dispatch(w, sku, 5)
    ext = next(_ext)
    inv = a.insert(
        "fbo_invoices",
        shop_id=a.shop_id,
        external_id=ext,
        number=ext,
        status="CREATED",
        created_on=datetime.now(UTC),
    )
    a.insert(
        "fbo_invoice_items",
        invoice_id=inv,
        sku_external_id=ext,
        sku_id=w.ids["Integrity-3"],
        quantity_to_stock=5,
        quantity_accepted=0,
    )
    ok(send(w, "POST", f"dispatches/{did}/link", invoice_id=str(inv)))
    a.sql("UPDATE fbo_invoices SET status = 'ACCEPTED' WHERE id = %s", [inv])
    assert code(send(w, "POST", f"dispatches/{did}/cancel")) == (409, "dispatch_accepted")
    r = send(w, "POST", f"dispatches/{did}/link", invoice_id=None)
    assert code(r) == (409, "dispatch_accepted")
    # Qabul qilinmagan postavkada bekor qilish mumkin (oldingi xulq).
    a.sql("UPDATE fbo_invoices SET status = 'CREATED' WHERE id = %s", [inv])
    assert ok(send(w, "POST", f"dispatches/{did}/cancel"))["status"] == "canceled"


def test_m10_equation_and_broken_stock(world: World) -> None:
    """M10: har SKU uchun Omborimda + Jo'natilmoqda/Uzumda + o'tkazilgan + hisobdan chiqarilgan − tuzatish = sanalgan sog'
    dona; Omborim API va daftar bir xil son beradi. Bazada buzilgan holat (son jo'natilgandan kam) — manfiy, xato."""
    w, a = world, world.a
    sku, sku2 = fresh_sku(w, "Integrity-4"), fresh_sku(w, "Integrity-4b")
    det = counted(w, sku, 20)
    counted(w, sku, 5)
    line = det["lines"][0]["id"]
    a.recalc(datetime.now(UTC))
    ok(send(w, "POST", "warehouse/transfer", source_line_id=line, to_sku_id=sku2, qty=3), 201)
    dispatch(w, sku, 12)
    dispatch(w, sku2, 2)
    ok(
        send(
            w,
            "POST",
            "stock-moves",
            item_id=str(w.ids["Integrity-4:item"]),
            sku_id=sku,
            kind="writeoff",
            qty=2,
            day="2026-10-05",
        ),
        201,
    )
    book = a.run(integrity.ledger)
    for key in (f"sku:{sku}", f"sku:{sku2}"):
        b = book.balances[key]
        assert b.on_hand >= 0 and b.dispatched == b.attributed
        assert b.on_hand + b.dispatched + b.transferred + b.written_off - b.adjusted == b.good
        api = row_of(w, key.removeprefix("sku:"))
        assert api is not None and api["qty"] == b.on_hand and api["broken"] is False
    assert book.balances[f"sku:{sku}"].on_hand == 25 - 3 - 12 - 2
    assert not [b for b in book.problems() if b.key in (f"sku:{sku}", f"sku:{sku2}")]

    # Buzilgan holat (API'siz, to'g'ridan-to'g'ri bazada): sanalgan son jo'natilgandan kam.
    a.sql(
        "UPDATE purchase_lines SET received_qty = 2 WHERE purchase_id = %s", [det["purchase"]["id"]]
    )
    row = row_of(w, sku)
    assert row is not None and row["broken"] is True and row["qty"] < 0
    report = a.run(rc.supply_check)
    bad = {x["key"]: x for x in report["problems"]}
    assert f"sku:{sku}" in bad and bad[f"sku:{sku}"]["on_hand"] == row["qty"]
    text = rc.summary({"orgs": [{"shops": [], "supply": report}]})
    assert any("XATO" in x for x in text)

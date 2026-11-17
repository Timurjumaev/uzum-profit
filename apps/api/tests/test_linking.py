"""TM9.1 postavka ↔ jo'natma har qanday yo'lda (haqiqiy PostgreSQL, ADR-068 (1)): SKU to'plami aynan teng bo'lmasa ham
nomzod (sotuvchi tasdiqlaydi), qo'lda tanlash — do'konning bog'lanmagan hamma postavkasidan; bog'langanda jo'natma soni
e'lon qilingan songa tenglashadi (kam — Omborimga qaytadi, yo'q SKU — qo'shiladi), kabinetda keyin o'zgartirilsa ham,
qabul qilingach qotadi; jo'natmasiz postavka — "Diqqat", "Omborimdan ketgan" yoki "Omborimdan emas"."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import test_purchases as tp
from test_purchases import ok, send
from test_reports import World

db = tp.db
world = tp.world

_ext = iter(range(91_000, 92_000))
_barcode = iter(range(4_780_000_500_000, 4_780_000_600_000))


def fresh_sku(w: World, name: str, stock: int) -> str:
    """Yangi SKU (shtrix-kodli) va unga sanalgan xarid — Omborimda ``stock`` dona."""
    _item, sku = w.a.item(name)
    w.a.sql("UPDATE mp_skus SET barcode = %s WHERE id = %s", [str(next(_barcode)), sku])
    ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": str(sku), "qty": stock}],
            paid_amount=str(stock * 10_000),
            currency="UZS",
            ordered_on="2026-10-01",
            on_hand=True,
        ),
        201,
    )
    return str(sku)


def dispatch(w: World, items: dict[str, int]) -> str:
    w.a.recalc(datetime.now(UTC))
    out = ok(
        send(
            w,
            "POST",
            "dispatches",
            shop_id=str(w.a.shop_id),
            items=[{"sku_id": s, "qty": q} for s, q in items.items()],
        ),
        201,
    )
    return str(out["id"])


def invoice(w: World, items: dict[str, int], status: str = "CREATED") -> str:
    a = w.a
    ext = next(_ext)
    inv = a.insert(
        "fbo_invoices",
        shop_id=a.shop_id,
        external_id=ext,
        number=ext,
        status=status,
        created_on=datetime.now(UTC),
    )
    for sku, qty in items.items():
        a.insert(
            "fbo_invoice_items",
            invoice_id=inv,
            sku_external_id=ext,
            sku_id=sku,
            quantity_to_stock=qty,
            quantity_accepted=0,
        )
    return str(inv)


def listing(w: World, dispatch_id: str) -> dict[str, Any]:
    return dict(
        next(x for x in ok(send(w, "GET", "dispatches"))["items"] if x["id"] == dispatch_id)
    )


def stock(w: World, sku: str) -> int:
    rows = ok(send(w, "GET", "warehouse"))["items"]
    return int(next((r["qty"] for r in rows if r["sku_id"] == sku), 0))


def items_of(d: dict[str, Any]) -> dict[str, int]:
    return {x["sku_id"]: x["qty"] for x in d["items"]}


def test_partial_candidate_manual_link_equalizes(world: World) -> None:
    """Kabinetda bitta SKU olib tashlangan: nomzod (1/2 SKU), o'zi bog'lanmaydi; tasdiqlangach olib tashlangan SKU
    Omborimga qaytadi va sotuvchiga ko'rsatiladi."""
    w = world
    a, b = fresh_sku(w, "Link-A", 10), fresh_sku(w, "Link-B", 5)
    did = dispatch(w, {a: 10, b: 5})
    inv = invoice(w, {a: 10})
    d = listing(w, did)
    assert d["status"] == "sending"
    cand = next(c for c in d["candidates"] if c["id"] == inv)
    assert (cand["common"], cand["union"]) == (1, 2)
    assert stock(w, b) == 0
    linked = ok(send(w, "POST", f"dispatches/{did}/link", invoice_id=inv))
    assert linked["status"] == "linked" and items_of(linked) == {a: 10}
    assert linked["adjustments"] == [
        {"sku_id": b, "title": "Link-B", "before": 5, "after": 0, "declared": 0}
    ]
    assert stock(w, b) == 5  # Omborimga qaytdi


def test_declared_less_and_more_then_frozen_after_acceptance(world: World) -> None:
    """Excel 20, kabinetda 15 e'lon qilindi — o'zi bog'lanadi va 15 ga tenglashadi (5 Omborimga); keyin kabinetda 18 ga
    oshirildi va yangi SKU qo'shildi — qayta tenglashadi (Omborimda bor qadar); qabul qilingach o'zgarmaydi."""
    w = world
    a, c = fresh_sku(w, "Link-C", 30), fresh_sku(w, "Link-D", 4)
    did = dispatch(w, {a: 20})
    inv = invoice(w, {a: 15})
    d = listing(w, did)
    assert d["status"] == "linked" and items_of(d) == {a: 15}
    assert stock(w, a) == 15
    w.a.sql("UPDATE fbo_invoice_items SET quantity_to_stock = 18 WHERE invoice_id = %s", [inv])
    w.a.insert(
        "fbo_invoice_items",
        invoice_id=inv,
        sku_external_id=1,
        sku_id=c,
        quantity_to_stock=6,  # Omborimda 4 bor — 4 qo'shiladi
        quantity_accepted=0,
    )
    d = listing(w, did)
    assert items_of(d) == {a: 18, c: 4}
    log = {x["sku_id"]: x for x in d["adjustments"]}
    assert (log[a]["before"], log[a]["after"], log[a]["declared"]) == (20, 18, 18)
    assert (log[c]["before"], log[c]["after"], log[c]["declared"]) == (0, 4, 6)
    assert stock(w, a) == 12 and stock(w, c) == 0
    # Qabul qilindi — tarkib qotadi (farq — "Qabul farqi").
    w.a.sql("UPDATE fbo_invoices SET status = 'ACCEPTED' WHERE id = %s", [inv])
    w.a.sql("UPDATE fbo_invoice_items SET quantity_to_stock = 10 WHERE invoice_id = %s", [inv])
    assert items_of(listing(w, did)) == {a: 18, c: 4}


def test_manual_choice_from_all_unlinked_invoices(world: World) -> None:
    w = world
    a = fresh_sku(w, "Link-E", 3)
    other = fresh_sku(w, "Link-F", 3)
    did = dispatch(w, {a: 3})
    inv = invoice(w, {other: 2})  # umumiy SKU yo'q — nomzod emas, lekin qo'lda tanlanadi
    assert all(c["id"] != inv for c in listing(w, did)["candidates"])
    choices = ok(send(w, "GET", f"dispatches/{did}/invoices"))
    assert any(x["id"] == inv for x in choices)
    assert send(w, "GET", f"dispatches/{did}/invoices", "accountant").status_code == 403


def test_orphan_invoice_sent_or_not_mine(world: World) -> None:
    """Kabinetda to'g'ridan-to'g'ri yaratilgan postavka: "Diqqat"da; "Omborimdan ketgan" — jo'natma postavka tarkibidan,
    donalar Omborimdan chiqadi (qabul qilinganda ham qaytib qo'shilmaydi); "Omborimdan emas" — Omborimni band qilmaydi."""
    w = world
    a = fresh_sku(w, "Link-G", 8)
    b = fresh_sku(w, "Link-H", 6)
    w.a.recalc(datetime.now(UTC))
    before = ok(send(w, "GET", "dashboard?start=2026-10-01&end=2026-10-31"))["attention"]
    inv = invoice(w, {a: 5}, status="ACCEPTED")
    other = invoice(w, {b: 6})
    orphans = {x["invoice"]["id"]: x for x in ok(send(w, "GET", "dispatches/orphans"))["items"]}
    assert set(orphans) >= {inv, other}
    assert orphans[inv]["items"] == [
        {"sku_id": a, "title": "Link-G", "declared": 5, "available": 8}
    ]
    assert orphans[inv]["accepted_on"] is not None
    after = ok(send(w, "GET", "dashboard?start=2026-10-01&end=2026-10-31"))["attention"]
    assert after["orphan_invoices"] == before["orphan_invoices"] + 2
    assert stock(w, a) == 8  # qabul qilingan postavka — Omborim ortiqcha (G1), hal qilinmaguncha
    assert stock(w, b) == 0  # ochiq postavka band qiladi (ADR-034)

    out = ok(send(w, "POST", f"dispatches/orphans/{inv}/sent"), 201)
    assert out["origin"] == "invoice" and out["status"] == "linked" and items_of(out) == {a: 5}
    assert stock(w, a) == 3
    assert send(w, "POST", f"dispatches/orphans/{inv}/sent").status_code == 404  # takror emas

    assert send(w, "POST", f"dispatches/orphans/{other}/not-mine", "accountant").status_code == 403
    r = send(w, "POST", f"dispatches/orphans/{other}/not-mine", note="boshlang'ich qoldiqdan")
    assert r.status_code == 204
    assert stock(w, b) == 6  # band qilmaydi
    ids = {x["invoice"]["id"] for x in ok(send(w, "GET", "dispatches/orphans"))["items"]}
    assert inv not in ids and other not in ids
    assert send(w, "DELETE", f"dispatches/orphans/{other}/not-mine").status_code == 204
    assert stock(w, b) == 0
    ids = {x["invoice"]["id"] for x in ok(send(w, "GET", "dispatches/orphans"))["items"]}
    assert other in ids

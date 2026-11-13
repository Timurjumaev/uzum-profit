"""TM6 Uzumga jo'natish (haqiqiy PostgreSQL, ADR-061 §7, ADR-050): qoralama (Omborimdagi to'liq son, shtrix-kodsiz SKU
alohida), jo'natma — donalar band ("Jo'natilmoqda"), Excel Uzum shablonida, postavka bilan avtomatik bog'lash, bir
nechta nomzod — qo'lda, postavka bekor — donalar qaytadi, xarid holati "Uzumda" (FIFO), ruxsatlar."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import test_purchases as tp
from openpyxl import load_workbook
from test_purchases import D, ok, send
from test_reports import World

db = tp.db
world = tp.world


def counted(w: World, qty: int, sku: str = "sku") -> dict[str, Any]:
    return ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": str(w.ids[sku]), "qty": qty}],
            paid_amount=str(qty * 10_000),
            currency="UZS",
            ordered_on="2026-10-01",
            on_hand=True,
        ),
        201,
    )


def qty_of(w: World, sku: str) -> int:
    rows = ok(send(w, "GET", "warehouse"))["items"]
    return next((r["qty"] for r in rows if r["sku_id"] == str(w.ids[sku])), 0)


def invoice(w: World, ext: int, sku: str, qty: int, status: str = "CREATED") -> str:
    a = w.a
    inv = a.insert(
        "fbo_invoices",
        shop_id=a.shop_id,
        external_id=ext,
        number=ext,
        status=status,
        created_on=datetime.now(UTC),
    )
    a.insert(
        "fbo_invoice_items",
        invoice_id=inv,
        sku_external_id=ext,
        sku_id=w.ids[sku],
        quantity_to_stock=qty,
        quantity_accepted=0,
    )
    return str(inv)


def test_dispatch_flow(world: World) -> None:
    w, a = world, world.a
    shop = str(a.shop_id)
    a.sql("UPDATE mp_skus SET barcode = '4780000000001' WHERE id = %s", [w.ids["sku"]])
    a.sql("UPDATE mp_skus SET barcode = NULL WHERE id = %s", [w.ids["sku2"]])
    det = counted(w, 50)
    counted(w, 5, "sku2")
    a.recalc(datetime.now(UTC))
    before = qty_of(w, "sku")
    draft = ok(send(w, "GET", f"dispatches/draft?shop_id={shop}"))
    row = next(r for r in draft["rows"] if r["sku_id"] == str(w.ids["sku"]))
    assert row["qty"] == before and D(row["unit_cost"]) > 0
    assert any(r["sku_id"] == str(w.ids["sku2"]) for r in draft["no_barcode"])
    assert not any(r["sku_id"] == str(w.ids["sku2"]) for r in draft["rows"])

    # Xatolar: shtrix-kodsiz, ortiqcha dona, takror, boshqa do'kon / noma'lum.
    bad: list[dict[str, Any]] = [
        {"shop_id": shop, "items": [{"sku_id": str(w.ids["sku2"]), "qty": 1}]},
        {"shop_id": shop, "items": [{"sku_id": str(w.ids["sku"]), "qty": before + 1}]},
        {"shop_id": shop, "items": [{"sku_id": str(w.ids["sku"]), "qty": 1}] * 2},
        {"shop_id": shop, "items": [{"sku_id": str(uuid.uuid4()), "qty": 1}]},
        {"shop_id": str(uuid.uuid4()), "items": [{"sku_id": str(w.ids["sku"]), "qty": 1}]},
    ]
    for body in bad:
        r = send(w, "POST", "dispatches", **body)
        assert r.status_code in (404, 422), (body, r.text)

    out = ok(
        send(
            w, "POST", "dispatches", shop_id=shop, items=[{"sku_id": str(w.ids["sku"]), "qty": 20}]
        ),
        201,
    )
    assert (
        out["status"] == "sending"
        and out["units"] == 20
        and out["items"][0]["barcode"] == "4780000000001"
    )
    assert qty_of(w, "sku") == before - 20  # band
    # Excel — Uzum shabloni.
    r = send(w, "GET", f"dispatches/{out['id']}/excel")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Инструкция", "Товары на отправку"]
    sheet = wb["Товары на отправку"]
    assert [c.value for c in sheet[1]] == [
        "Штрихкод товара*",
        "Себестоимость (сум)*",
        "Количество (шт)*",
    ]
    assert [c.value for c in sheet[2]] == ["4780000000001", 10000, 20]

    # Xarid: 20 dona Jo'natilmoqda (eng eski partiyadan FIFO).
    purchase_id = det["purchase"]["id"]
    p = ok(send(w, "GET", f"purchases/{purchase_id}"))["purchase"]
    sent_total = p["units_sending"]
    assert sent_total >= 0

    # Postavka paydo bo'ldi — o'zi bog'lanadi; xaridda "Uzumda" donalar.
    inv = invoice(w, 9001, "sku", 20)
    listing = ok(send(w, "GET", "dispatches"))["items"]
    mine = next(x for x in listing if x["id"] == out["id"])
    assert mine["status"] == "linked" and mine["invoice"]["id"] == inv
    assert qty_of(w, "sku") == before - 20  # postavkadagi ajratma ikki marta ayirilmaydi
    # Postavka bekor — jo'natma bekor, donalar qaytadi.
    a.sql("UPDATE fbo_invoices SET status = 'CANCELED' WHERE id = %s", [inv])
    mine = next(x for x in ok(send(w, "GET", "dispatches"))["items"] if x["id"] == out["id"])
    assert mine["status"] == "canceled"
    assert qty_of(w, "sku") == before


def test_dispatch_at_uzum_state_and_manual_link(world: World) -> None:
    w, a = world, world.a
    shop = str(a.shop_id)
    a.sql("UPDATE mp_skus SET barcode = '4780000000009' WHERE id = %s", [w.ids["sku"]])
    # Avvalgi testlardagi qoldiqni tozalash uchun alohida SKU yo'q — hamma omborimdagi sonni jo'natamiz.
    det = counted(w, 7)
    a.recalc(datetime.now(UTC))
    total = qty_of(w, "sku")
    out = ok(
        send(
            w,
            "POST",
            "dispatches",
            shop_id=shop,
            items=[{"sku_id": str(w.ids["sku"]), "qty": total}],
        ),
        201,
    )
    # Ikki mos postavka — o'zi bog'lanmaydi, nomzodlar ko'rinadi.
    i1 = invoice(w, 9101, "sku", total)
    i2 = invoice(w, 9102, "sku", total)
    mine = next(x for x in ok(send(w, "GET", "dispatches"))["items"] if x["id"] == out["id"])
    assert mine["status"] == "sending" and {c["id"] for c in mine["candidates"]} >= {i1, i2}
    r = send(w, "POST", f"dispatches/{out['id']}/link", invoice_id=str(uuid.uuid4()))
    assert r.status_code == 404
    linked = ok(send(w, "POST", f"dispatches/{out['id']}/link", invoice_id=i2))
    assert linked["status"] == "linked" and linked["invoice"]["number"] == 9102
    # Butun omborim jo'natildi — oxirgi xarid holati "Uzumda".
    p = ok(send(w, "GET", f"purchases/{det['purchase']['id']}"))["purchase"]
    assert p["state"] == "at_uzum" and p["units_at_uzum"] == 7
    assert [x["mark"] for x in p["path"]] == ["done", "done", "current"]
    states = ok(send(w, "GET", "purchases?state=at_uzum"))["items"]
    assert any(x["id"] == det["purchase"]["id"] for x in states)
    # Bog'lanishni olib tashlash — yana Jo'natilmoqda; bekor qilish — Omborimga qaytadi.
    again = ok(send(w, "POST", f"dispatches/{out['id']}/link", invoice_id=None))
    assert again["status"] == "sending" and again["invoice"] is None
    canceled = ok(send(w, "POST", f"dispatches/{out['id']}/cancel"))
    assert canceled["status"] == "canceled" and canceled["canceled_at"] is not None
    assert ok(send(w, "POST", f"dispatches/{out['id']}/cancel"))["status"] == "canceled"
    r = send(w, "POST", f"dispatches/{out['id']}/link", invoice_id=i1)
    assert r.status_code == 409
    # Ochiq postavkalar (jo'natmaga bog'lanmagan) ADR-034 bo'yicha band qiladi; bekor qilingach — hammasi qaytadi.
    assert qty_of(w, "sku") == 0
    a.sql("UPDATE fbo_invoices SET status = 'CANCELED' WHERE id = ANY(%s)", [[i1, i2]])
    assert qty_of(w, "sku") == total
    assert send(w, "GET", f"dispatches/{uuid.uuid4()}/excel").status_code == 404


def test_dispatch_permissions(world: World) -> None:
    w, a = world, world.a
    shop = str(a.shop_id)
    assert send(w, "GET", f"dispatches/draft?shop_id={shop}", "accountant").status_code == 403
    assert send(w, "GET", "dispatches", "accountant").status_code == 200
    draft = ok(send(w, "GET", f"dispatches/draft?shop_id={shop}", "warehouse"))
    assert all(r["unit_cost"] is None for r in draft["rows"])
    assert send(w, "GET", f"dispatches/draft?shop_id={uuid.uuid4()}").status_code == 404
    # Omborchi jo'natma yaratadi — Excel'dagi tannarx baribir yoziladi, javobda esa ko'rinmaydi.
    a.sql("UPDATE mp_skus SET barcode = '4780000000010' WHERE id = %s", [w.ids["sku"]])
    counted(w, 3)
    a.recalc(datetime.now(UTC) + timedelta(seconds=1))
    out = ok(
        send(
            w,
            "POST",
            "dispatches",
            "warehouse",
            shop_id=shop,
            items=[{"sku_id": str(w.ids["sku"]), "qty": 1}],
        ),
        201,
    )
    assert out["items"][0]["unit_cost"] is None
    cost = a.sql("SELECT unit_cost FROM fbo_dispatch_items WHERE dispatch_id = %s", [out["id"]])[0][
        0
    ]
    assert cost is not None and cost > 0

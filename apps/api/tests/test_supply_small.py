"""TM9.7 mayda tuzatishlar (haqiqiy PostgreSQL; 09 §17 G11–G13): jo'natma qoralamasida tannarx tahrirlanadi, noma'lum
bo'lsa Excel'ga 0 ketmaydi, taxminiy bo'lsa belgi; "Ikkiga bo'lish" sanalgandan keyin — sanalmagan qoldiq yangi
xaridga (kargo kelgan qismda); "Tovar qo'limda" — brak saqlashdan oldin, qadoq qo'shimchasi tovardan."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import test_purchases as tp
from openpyxl import load_workbook
from test_purchases import ok, send
from test_reports import World

db = tp.db
world = tp.world

D = Decimal


def sku_with_barcode(w: World, name: str, barcode: str) -> tuple[Any, str]:
    item, sku_id = w.a.item(name)
    w.a.sql("UPDATE mp_skus SET barcode = %s WHERE id = %s", [barcode, sku_id])
    return item, str(sku_id)


def draft_row(w: World, sku: str, role: str = "owner") -> dict[str, Any]:
    out = ok(send(w, "GET", f"dispatches/draft?shop_id={w.a.shop_id}", role))
    return next(x for x in out["rows"] if x["sku_id"] == sku)


def test_dispatch_cost_unknown_manual_estimated(world: World) -> None:
    w = world
    _i1, unknown = sku_with_barcode(w, "Narxsiz", "4780000777001")
    _i2, rough = sku_with_barcode(w, "Kargosiz", "4780000777002")
    # Tovar summasi kiritilmagan "Tovar qo'limda" — lot narxi 0: noma'lum.
    ok(send(w, "POST", "purchases/quick", lines=[{"sku_id": unknown, "qty": 5}], on_hand=True), 201)
    # Kargo kiritilmagan, sanalgan — taxminiy.
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": rough, "qty": 10}],
            paid_amount="100000",
            currency="UZS",
        ),
        201,
    )
    ok(
        send(
            w,
            "POST",
            f"purchases/{det['purchase']['id']}/count",
            lines=[{"line_id": det["lines"][0]["id"], "received_qty": 10}],
        )
    )
    w.a.recalc(datetime.now(UTC))
    a, b = draft_row(w, unknown), draft_row(w, rough)
    assert a["unknown"] is True and b["unknown"] is False
    assert b["estimated"] is True and D(b["unit_cost"]) == D(10_000)
    # Omborchi summani ko'rmaydi, belgini ko'radi.
    hidden = draft_row(w, rough, "warehouse")
    assert hidden["unit_cost"] is None and hidden["estimated"] is True
    # Noma'lum narx kiritilmasa — rad (Excel'ga 0 ketmaydi).
    items = [{"sku_id": unknown, "qty": 5}, {"sku_id": rough, "qty": 10}]
    r = send(w, "POST", "dispatches", shop_id=str(w.a.shop_id), items=items)
    assert r.status_code == 422 and r.json()["code"] == "cost_unknown"
    assert "Narxsiz" in r.json()["detail"]
    # Omborchi aniq narxni almashtira olmaydi, noma'lumini kiritadi.
    r = send(
        w,
        "POST",
        "dispatches",
        "warehouse",
        shop_id=str(w.a.shop_id),
        items=[{"sku_id": unknown, "qty": 5, "unit_cost": "12000"}, {**items[1], "unit_cost": "1"}],
    )
    assert r.status_code == 403
    out = ok(
        send(
            w,
            "POST",
            "dispatches",
            shop_id=str(w.a.shop_id),
            items=[{"sku_id": unknown, "qty": 5, "unit_cost": "12000"}, items[1]],
        ),
        201,
    )
    got = {x["sku_id"]: x for x in out["items"]}
    assert D(got[unknown]["unit_cost"]) == D(12_000) and got[unknown]["cost_mark"] == "manual"
    assert D(got[rough]["unit_cost"]) == D(10_000) and got[rough]["cost_mark"] == "estimated"
    r = w.api.client.get(f"/api/v1/orgs/{w.org_id}/dispatches/{out['id']}/excel")
    sheet = load_workbook(io.BytesIO(r.content))["Товары на отправку"]
    assert sorted(sheet.cell(row=i, column=2).value for i in (2, 3)) == [10_000, 12_000]


def test_split_after_counting_moves_uncounted_rest(world: World) -> None:
    w = world
    _ia, sku_a = w.a.item("Qoldiq-A")
    _ib, sku_b = w.a.item("Qoldiq-B")
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[
                {"sku_id": str(sku_a), "qty": 10, "line_sum": "600000"},
                {"sku_id": str(sku_b), "qty": 10, "line_sum": "400000"},
            ],
            paid_amount="1000000",
            currency="UZS",
        ),
        201,
    )
    pid = det["purchase"]["id"]
    by_sku = {x["sku_id"]: x["id"] for x in det["lines"]}  # bir tranzaksiyada tartib tasodifiy
    a, b = by_sku[str(sku_a)], by_sku[str(sku_b)]
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="cargo",
            amount="50000",
            currency="UZS",
        ),
        201,
    )
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            lines=[{"line_id": a, "received_qty": 6}, {"line_id": b, "received_qty": 0}],
        )
    )
    # Sanalgan qatordan qoldiqdan (4) ko'p — rad.
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": a, "qty": 5}])
    assert r.status_code == 422 and r.json()["code"] == "bad_line"
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/split",
            lines=[{"line_id": a, "qty": 4}, {"line_id": b, "qty": 10}],
        ),
        201,
    )
    old = out["purchase"]
    assert [(x["ordered_qty"], x["received_qty"]) for x in old["lines"]] == [(6, 6)]
    assert old["purchase"]["state"] == "in_stock"
    # Kargo kelgan qismda qoldi; tovar summasi dona bo'yicha: 6/20 — eski, 14/20 — yangi.
    kinds = {c["kind"]: D(c["amount"]) for c in old["components"]}
    assert kinds["cargo"] == D(50_000) and kinds["goods"] == D(300_000)
    new = ok(send(w, "GET", f"purchases/{out['new_purchase_id']}"))
    assert new["purchase"]["state"] == "in_transit"
    assert sorted((x["ordered_qty"], x["received_qty"]) for x in new["lines"]) == [
        (4, None),
        (10, None),
    ]
    assert {c["kind"] for c in new["components"]} == {"goods"}
    assert D(new["components"][0]["amount"]) == D(700_000)
    # Qaytarilgan summa bor sanalgan xarid — bo'linmaydi.
    ok(send(w, "PATCH", f"purchases/{pid}", refund_amount="1000", refund_currency="UZS"))
    det2 = ok(send(w, "GET", f"purchases/{pid}"))
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            lines=[{"line_id": det2["lines"][0]["id"], "received_qty": 5}],
        )
    )
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": a, "qty": 1}])
    assert r.status_code == 409 and r.json()["code"] == "split_refund"


def test_on_hand_defect_and_pack_from_item(world: World) -> None:
    w = world
    item, sku = w.a.item("Qolimda-Qadoq")
    w.a.sql("UPDATE items SET pack_unit_cost = 500 WHERE id = %s", [item])
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": str(sku), "qty": 10, "defect": 2}],
            paid_amount="80000",
            currency="UZS",
            on_hand=True,
        ),
        201,
    )
    line = det["lines"][0]
    assert line["received_qty"] == 10 and line["defect_qty"] == 2 and line["good_qty"] == 8
    assert D(line["pack_unit_cost"]) == D(500)
    assert D(line["cost"]["unit_cost"]) == D(10_000 + 500)  # 80 000 / 8 sog' dona + qadoq
    # Brak kelgandan ko'p — rad; "Yo'lda" xaridda brak — sanashda.
    r = send(
        w,
        "POST",
        "purchases/quick",
        lines=[{"sku_id": str(sku), "qty": 1, "defect": 2}],
        on_hand=True,
    )
    assert r.status_code == 422
    r = send(w, "POST", "purchases/quick", lines=[{"sku_id": str(sku), "qty": 3, "defect": 1}])
    assert r.status_code == 422

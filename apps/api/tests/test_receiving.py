"""TM7 Uzum qabulidagi farq (haqiqiy PostgreSQL, ADR-061 §8): qabul qilingan postavkada kam / ko'p; "Uzum yo'qotdi" —
kamomad ro'yxati va holatlari, F52 foyda hisobida; "sanashda adashganman" — xarid soni tuzatiladi; ortiqcha — ochiq
kamomad topildi yoki son oshiriladi; "Diqqat" sanog'i; C000007 jarimasi; ruxsatlar."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import test_purchases as tp
from test_purchases import D, ok, send
from test_reports import World

db = tp.db
world = tp.world

_ext = iter(range(70_000, 80_000))


def setup_dispatch(w: World, shipped: int, accepted: int, stock: int = 10) -> dict[str, Any]:
    """Sanalgan xarid → jo'natma → bog'langan va qabul qilingan postavka (``accepted`` dona)."""
    a = w.a
    a.sql("UPDATE mp_skus SET barcode = '4780000000777' WHERE id = %s", [w.ids["sku"]])
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": str(w.ids["sku"]), "qty": stock}],
            paid_amount=str(stock * 10_000),
            currency="UZS",
            ordered_on="2026-10-01",
            on_hand=True,
        ),
        201,
    )
    a.recalc(datetime.now(UTC))
    out = ok(
        send(
            w,
            "POST",
            "dispatches",
            shop_id=str(a.shop_id),
            items=[{"sku_id": str(w.ids["sku"]), "qty": shipped}],
        ),
        201,
    )
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
        sku_id=w.ids["sku"],
        quantity_to_stock=shipped,
        quantity_accepted=0,
    )
    ok(send(w, "POST", f"dispatches/{out['id']}/link", invoice_id=str(inv)))
    # Qabul qilinmaguncha farq yo'q.
    assert not [
        x for x in ok(send(w, "GET", "receiving"))["diffs"] if x["dispatch_id"] == out["id"]
    ]
    a.sql("UPDATE fbo_invoices SET status = 'ACCEPTED' WHERE id = %s", [inv])
    a.sql(
        "UPDATE fbo_invoice_items SET quantity_accepted = %s WHERE invoice_id = %s", [accepted, inv]
    )
    return {"purchase": det, "dispatch": out["id"], "invoice": str(inv)}


def diff_of(w: World, dispatch_id: str) -> dict[str, Any]:
    return next(
        x for x in ok(send(w, "GET", "receiving"))["diffs"] if x["dispatch_id"] == dispatch_id
    )


def test_lost_shortage_and_pnl(world: World) -> None:
    w, a = world, world.a
    s = setup_dispatch(w, shipped=10, accepted=8)
    d = diff_of(w, s["dispatch"])
    assert (d["shipped"], d["accepted"], d["diff"], d["resolution"]) == (10, 8, -2, None)
    assert D(d["unit_cost"]) == D(10_000)
    dash_before = ok(send(w, "GET", "dashboard?start=2026-10-01&end=2026-10-31"))["attention"][
        "receiving"
    ]
    assert dash_before >= 1
    # Noto'g'ri amal: ko'p qabul uchun amal kam qabulda.
    r = send(
        w,
        "POST",
        "receiving/resolve",
        dispatch_id=s["dispatch"],
        sku_id=str(w.ids["sku"]),
        action="found",
    )
    assert r.status_code == 422
    out = ok(
        send(
            w,
            "POST",
            "receiving/resolve",
            dispatch_id=s["dispatch"],
            sku_id=str(w.ids["sku"]),
            action="lost",
        )
    )
    short = next(x for x in out["shortages"] if x["dispatch_id"] == s["dispatch"])
    assert short["status"] == "open" and short["qty"] == 2 and D(short["amount"]) == D(20_000)
    r = send(
        w,
        "POST",
        "receiving/resolve",
        dispatch_id=s["dispatch"],
        sku_id=str(w.ids["sku"]),
        action="lost",
    )
    assert r.status_code == 409  # qaror bir marta
    # Kompensatsiya: summa shart; zarar = 20 000 − 5 000.
    r = send(w, "PATCH", f"receiving/shortages/{short['id']}", status="compensated")
    assert r.status_code == 422
    out = ok(
        send(
            w,
            "PATCH",
            f"receiving/shortages/{short['id']}",
            status="compensated",
            compensation="5000",
        )
    )
    short = next(x for x in out["shortages"] if x["id"] == short["id"])
    assert D(short["loss"]) == D(15_000) and short["closed_on"] is not None
    closed = short["closed_on"]
    pnl = ok(send(w, "GET", f"pnl?start={closed}&end={closed}"))
    row = next(x for x in pnl["rows"] if x["code"] == "own:Uzum qabulida yoʻqotish")
    assert D(row["amount"]) == D(-15_000)
    # Qayta ochish — zarar yo'qoladi; omborchi kompensatsiya kirita olmaydi.
    ok(send(w, "PATCH", f"receiving/shortages/{short['id']}", status="open"))
    pnl = ok(send(w, "GET", f"pnl?start={closed}&end={closed}"))
    assert not [x for x in pnl["rows"] if x["code"] == "own:Uzum qabulida yoʻqotish"]
    r = send(
        w,
        "PATCH",
        f"receiving/shortages/{short['id']}",
        "warehouse",
        status="compensated",
        compensation="1",
    )
    assert r.status_code == 403
    assert (
        send(w, "PATCH", f"receiving/shortages/{uuid.uuid4()}", status="found").status_code == 404
    )
    wh = ok(send(w, "GET", "receiving", "warehouse"))
    assert all(x["unit_cost"] is None and x["fines"] == [] for x in wh["diffs"])

    # Ortiqcha qabul boshqa jo'natmada: ochiq kamomad "Topildi" bo'lib yopiladi.
    s2 = setup_dispatch(w, shipped=3, accepted=5)
    d2 = diff_of(w, s2["dispatch"])
    assert d2["diff"] == 2 and d2["open_shortages"] == 2
    out = ok(
        send(
            w,
            "POST",
            "receiving/resolve",
            dispatch_id=s2["dispatch"],
            sku_id=str(w.ids["sku"]),
            action="found",
        )
    )
    assert next(x for x in out["shortages"] if x["id"] == short["id"])["status"] == "found"
    assert (
        next(x for x in out["diffs"] if x["dispatch_id"] == s2["dispatch"])["resolution"] == "found"
    )
    a.sql("DELETE FROM receiving_diffs")  # keyingi testlar uchun toza


def test_miscount_and_recount_fix_purchase(world: World) -> None:
    w, a = world, world.a
    s = setup_dispatch(w, shipped=6, accepted=5, stock=6)
    pid = s["purchase"]["purchase"]["id"]
    line = s["purchase"]["lines"][0]["id"]
    out = ok(
        send(
            w,
            "POST",
            "receiving/resolve",
            dispatch_id=s["dispatch"],
            sku_id=str(w.ids["sku"]),
            action="miscount",
            line_id=line,
        )
    )
    assert (
        next(x for x in out["diffs"] if x["dispatch_id"] == s["dispatch"])["resolution"]
        == "miscount"
    )
    det = ok(send(w, "GET", f"purchases/{pid}"))
    assert det["lines"][0]["received_qty"] == 5  # kelgan son tuzatildi
    a.recalc(datetime.now(UTC))
    det = ok(send(w, "GET", f"purchases/{pid}"))
    assert D(det["lines"][0]["cost"]["unit_cost"]) == D(12_000)  # 60 000 / 5
    item_qty = a.sql("SELECT qty FROM fbo_dispatch_items WHERE dispatch_id = %s", [s["dispatch"]])[
        0
    ][0]
    assert item_qty == 5

    s2 = setup_dispatch(w, shipped=4, accepted=6, stock=4)
    pid2 = s2["purchase"]["purchase"]["id"]
    r = send(
        w,
        "POST",
        "receiving/resolve",
        dispatch_id=s2["dispatch"],
        sku_id=str(w.ids["sku"]),
        action="found",
    )
    assert r.status_code == 409  # ochiq kamomad yo'q
    ok(
        send(
            w,
            "POST",
            "receiving/resolve",
            dispatch_id=s2["dispatch"],
            sku_id=str(w.ids["sku"]),
            action="recount",
            line_id=s2["purchase"]["lines"][0]["id"],
        )
    )
    det = ok(send(w, "GET", f"purchases/{pid2}"))
    assert det["lines"][0]["received_qty"] == 6
    r = send(
        w,
        "POST",
        "receiving/resolve",
        dispatch_id=str(uuid.uuid4()),
        sku_id=str(w.ids["sku"]),
        action="lost",
    )
    assert r.status_code == 404
    r = send(
        w,
        "POST",
        "receiving/resolve",
        "accountant",
        dispatch_id=s2["dispatch"],
        sku_id=str(w.ids["sku"]),
        action="lost",
    )
    assert r.status_code == 403


def test_related_fine_shown(world: World) -> None:
    w, a = world, world.a
    s = setup_dispatch(w, shipped=4, accepted=3, stock=4)
    a.insert(
        "mp_expenses",
        shop_id=a.shop_id,
        external_id=next(_ext),
        code="C000007",
        raw_code="C000007",
        category="fine",
        type="OUTCOME",
        amount=D(7_000),
        created_on=datetime.now(UTC),
    )
    d = diff_of(w, s["dispatch"])
    assert [D(x["amount"]) for x in d["fines"]] == [D(7_000)]

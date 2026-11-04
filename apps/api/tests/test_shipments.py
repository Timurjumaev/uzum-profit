"""B4.31 ``/shipments`` (haqiqiy PostgreSQL): bitta kargo — ko'p xarid (ADR-046): kargo xarajati hamma xaridlarning
tovarlariga bo'linadi (yig'indi tiyinigacha), sanalar kargodan, xaridni ajratish / o'chirish, lotlar, ruxsatlar."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import test_purchases as tp
from test_purchases import D, ok, send
from test_reports import World

db = (
    tp.db
)  # xarid testlari bilan umumiy fixture'lar (bir xil dunyo: tashkilot, tovarlar, rollar, kurslar)
world = tp.world


def shipment(w: World, **body: Any) -> dict[str, Any]:
    return ok(send(w, "POST", "shipments", **body), 201)


def purchase(w: World, title: str, **body: Any) -> str:
    return ok(send(w, "POST", "purchases", title=title, **body), 201)["purchase"]["id"]


def line(w: World, pid: str, item: str, qty: int, weight: str | None = None) -> str:
    body: dict[str, Any] = {"item_id": str(w.ids[item]), "ordered_qty": qty, "received_qty": qty}
    if weight is not None:
        body["unit_weight"] = weight
    det = ok(send(w, "POST", f"purchases/{pid}/lines", **body), 201)
    return det["lines"][-1]["id"]


def test_cargo_is_split_across_purchases_and_lots(world: World) -> None:
    w, a = world, world.a
    ship = shipment(w, title="Presslangan o'ram")["shipment"]["id"]
    pa = purchase(w, "A yetkazib beruvchi", shipment_id=ship)
    pb = purchase(w, "B yetkazib beruvchi", shipment_id=ship)
    la1 = line(w, pa, "item", 100, "0.5")  # 50 kg
    la2 = line(w, pa, "item2", 40, "1")  # 40 kg
    lb1 = line(w, pb, "item", 200, "0.2")  # 40 kg
    ok(
        send(
            w,
            "POST",
            f"purchases/{pa}/components",
            kind="packaging",
            amount="100000",
            currency="UZS",
        ),
        201,
    )
    det = ok(
        send(
            w,
            "POST",
            f"shipments/{ship}/components",
            kind="cargo",
            amount="2430000",
            currency="UZS",
            allocation="weight",
        ),
        201,
    )
    assert det["error"] is None and det["shipment"]["purchase_count"] == 2
    assert D(det["shipment"]["total"]) == D(2_430_000) and det["shipment"]["units"] == 340
    shares = {x["id"]: D(x["share"]) for x in det["lines"]}
    assert sum(shares.values()) == D(2_430_000)  # tiyinigacha
    assert (
        shares[la1] == D("934615.38")
        and shares[lb1] == D("747692.31")
        and shares[la2] == D("747692.31")
    )
    by_purchase = {x["id"]: x for x in det["purchases"]}
    assert D(by_purchase[pa]["share"]) + D(by_purchase[pb]["share"]) == D(2_430_000)
    # Xarid ichidagi komponent (qadoqlash) faqat A ga; B ning jami = faqat kargo ulushi.
    assert D(by_purchase[pa]["total"]) == D(by_purchase[pa]["share"]) + D(100_000)
    assert D(by_purchase[pb]["total"]) == D(by_purchase[pb]["share"])
    assert det["by_kind"] == {"cargo": "2430000.00"} or D(det["by_kind"]["cargo"]) == D(2_430_000)

    # Xarid sahifasi: kargo nomi, kargo xarajatlari (faqat o'qish), qatordagi tarkibda kargo, "kargo kiritilmagan" yo'q.
    pdet = ok(send(w, "GET", f"purchases/{pb}"))
    assert (
        pdet["purchase"]["shipment_id"] == ship
        and pdet["purchase"]["shipment_name"] == "Presslangan o'ram"
    )
    assert [c["kind"] for c in pdet["shipment_components"]] == ["cargo"] and pdet[
        "components"
    ] == []
    only = pdet["lines"][0]
    assert D(only["cost"]["breakdown"]["cargo"]) == shares[lb1]
    assert "cargo_missing" not in only["flags"]

    # Lotlar (hisob ishi): har qator uchun, jami = o'z xarajatlari + kargo ulushi.
    a.recalc(datetime.now(UTC))
    lots = {
        str(r[0]): D(r[1])
        for r in a.sql(
            "SELECT purchase_line_id, total FROM lots WHERE purchase_line_id = ANY(%s)",
            [[la1, la2, lb1]],
        )
    }
    assert lots[lb1] == shares[lb1] and lots[la1] + lots[la2] == shares[la1] + shares[la2] + D(
        100_000
    )


def test_dates_come_from_shipment(world: World) -> None:
    w = world
    ship = shipment(w, title="Sanalar", shipped_on="2026-10-10")["shipment"]["id"]
    own = purchase(w, "O'z sanasi bilan", dates={"arrived": "2026-10-20", "ordered": "2026-10-01"})
    pid = purchase(w, "Kargoli", shipment_id=ship, dates={"ordered": "2026-10-02"})
    assert ok(send(w, "GET", f"purchases/{pid}"))["purchase"]["dates"]["shipped"] == "2026-10-10"
    # Bog'langanda kargoda sana yo'q — xaridning o'zinikи yo'qolmaydi.
    ok(send(w, "PATCH", f"purchases/{own}", shipment_id=ship))
    det = ok(send(w, "GET", f"purchases/{own}"))
    assert (
        det["purchase"]["dates"]["arrived"] == "2026-10-20"
        and det["purchase"]["dates"]["shipped"] == "2026-10-10"
    )
    # Kargo sanalari faqat kargoda o'zgaradi.
    r = send(w, "PATCH", f"purchases/{pid}", dates={"shipped": "2026-10-11"})
    assert r.status_code == 422 and r.json()["code"] == "dates_from_shipment"
    assert (
        send(w, "POST", "purchases", shipment_id=ship, dates={"arrived": "2026-10-30"}).status_code
        == 422
    )
    # Kargo sanasi o'zgarsa — hamma xaridlarda (bo'sh ham); tartib tekshiriladi.
    ok(send(w, "PATCH", f"shipments/{ship}", arrived_on="2026-10-25", shipped_on=None))
    for x in (own, pid):
        dates = ok(send(w, "GET", f"purchases/{x}"))["purchase"]["dates"]
        assert dates["arrived"] == "2026-10-25" and dates["shipped"] is None
    r = send(w, "PATCH", f"shipments/{ship}", shipped_on="2026-10-30")
    assert r.status_code == 422 and r.json()["code"] == "bad_stage_dates"
    # Joriy bosqich ham kargodan: keldi → "arrived" (qabul qilinmaguncha).
    assert ok(send(w, "GET", f"purchases/{pid}"))["purchase"]["stage"] == "arrived"


def test_unlink_delete_and_recalc_of_siblings(world: World) -> None:
    w = world
    ship = shipment(w, title="Ajratish")["shipment"]["id"]
    pa, pb = purchase(w, "A", shipment_id=ship), purchase(w, "B", shipment_id=ship)
    la, lb = line(w, pa, "item", 10, "1"), line(w, pb, "item2", 10, "1")
    ok(
        send(
            w,
            "POST",
            f"shipments/{ship}/components",
            kind="cargo",
            amount="1000",
            currency="UZS",
            allocation="weight",
        ),
        201,
    )
    r = send(w, "DELETE", f"shipments/{ship}")
    assert r.status_code == 409 and r.json()["code"] == "shipment_in_use"
    ok(send(w, "PATCH", f"purchases/{pb}", shipment_id=None))
    det = ok(send(w, "GET", f"shipments/{ship}"))
    assert [x["id"] for x in det["purchases"]] == [pa] and D(det["lines"][0]["share"]) == D(1000)
    assert det["lines"][0]["id"] == la
    # Ajratilgan xarid endi kargosiz: "kargo kiritilmagan".
    only = ok(send(w, "GET", f"purchases/{pb}"))
    assert only["purchase"]["shipment_id"] is None and "cargo_missing" in only["lines"][0]["flags"]
    assert lb  # qator saqlanadi
    # Xaridni o'chirish kargoda qolganlarini qayta hisoblashga qo'yadi.
    assert send(w, "DELETE", f"purchases/{pa}").status_code == 204
    assert (
        send(w, "DELETE", f"shipments/{ship}").status_code == 204
    )  # xaridsiz — o'chadi (xarajatlari bilan)
    assert send(w, "GET", f"shipments/{ship}").status_code == 404
    assert send(w, "PATCH", f"purchases/{pb}", shipment_id=str(uuid.uuid4())).status_code == 404


def test_validation_and_permissions(world: World) -> None:
    w = world
    ship = shipment(w, title="Ruxsat")["shipment"]["id"]
    other = shipment(w, title="Boshqa kargo")["shipment"]["id"]
    pa = purchase(w, "A", shipment_id=ship)
    po = purchase(w, "Boshqa kargodagi", shipment_id=other)
    la = line(w, pa, "item", 5, "1")
    lo = line(w, po, "item2", 5, "1")
    comp = {"kind": "cargo", "amount": "500", "currency": "UZS"}
    # Komponent faqat shu kargodagi xarid tovarlariga tegishli bo'la oladi.
    assert send(w, "POST", f"shipments/{ship}/components", **comp, lines=[lo]).status_code == 404
    det = ok(send(w, "POST", f"shipments/{ship}/components", **comp, lines=[la]), 201)
    cid = det["components"][0]["id"]
    r = send(w, "PATCH", f"shipments/{ship}/components/{cid}", lines=[lo])
    assert r.status_code == 404
    assert send(w, "PATCH", f"shipments/{other}/components/{cid}", amount="1").status_code == 404
    assert send(w, "POST", "shipments", carrier_id=str(uuid.uuid4())).status_code == 404
    assert (
        send(
            w, "POST", "shipments", cn_warehouse_on="2026-10-10", shipped_on="2026-10-01"
        ).status_code
        == 422
    )
    # Ruxsatlar: buxgalter ko'radi, o'zgartirmaydi; omborchi o'zgartiradi, lekin summalarni ko'rmaydi.
    assert send(w, "POST", "shipments", role="accountant").status_code == 403
    seen = ok(send(w, "GET", f"shipments/{ship}", role="warehouse"))
    assert (
        seen["amounts"] is False and seen["components"] == [] and seen["shipment"]["total"] is None
    )
    assert all(x["share"] is None for x in seen["lines"]) and all(
        x["total"] is None for x in seen["purchases"]
    )
    assert (
        send(w, "POST", f"shipments/{ship}/components", role="warehouse", **comp).status_code == 403
    )
    lst = ok(send(w, "GET", "shipments", role="warehouse"))
    assert lst["amounts"] is False and all(x["total"] is None for x in lst["items"])
    full = {x["id"]: x for x in ok(send(w, "GET", "shipments"))["items"]}
    assert (
        D(full[ship]["total"]) == D(500)
        and full[ship]["purchase_count"] == 1
        and full[ship]["units"] == 5
    )
    ok(send(w, "DELETE", f"shipments/{ship}/components/{cid}"))
    assert ok(send(w, "GET", f"shipments/{ship}"))["components"] == []


def test_missing_rate_in_one_purchase_stops_the_whole_shipment(world: World) -> None:
    """Biror xarid hisoblanmasa (kurs yo'q) — kargo ulushi noto'g'ri bo'linmasin: hamma xarid xato bilan, raqam yo'q."""
    w = world
    ship = shipment(w, title="Kurs yo'q")["shipment"]["id"]
    good, bad = purchase(w, "Yaxshi", shipment_id=ship), purchase(w, "Kurssiz", shipment_id=ship)
    line(w, good, "item", 10, "1")
    line(w, bad, "item2", 10, "1")
    ok(
        send(
            w,
            "POST",
            f"purchases/{bad}/components",
            kind="goods",
            amount="100",
            currency="USD",
            paid_on="2001-01-01",
        ),
        201,
    )
    ok(
        send(w, "POST", f"shipments/{ship}/components", kind="cargo", amount="900", currency="UZS"),
        201,
    )
    det = ok(send(w, "GET", f"shipments/{ship}"))
    assert det["error"] and "kargo hisoblanmadi" in det["error"]
    assert all(x["error"] and x["total"] is None for x in det["purchases"])
    assert all(x["share"] is None for x in det["lines"])

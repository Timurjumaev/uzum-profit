"""TM3 ``/cargo-pool`` (haqiqiy PostgreSQL, ADR-061 §3–§4): kargo puli jadvali — trekli xaridga o'z summasi, kodli
quti (dona bo'yicha ulushlar, qo'lda o'zgartirilganlari saqlanadi, sanashdan keyin qolganlari qayta bo'linadi), "ikki
marta emas" qoidasi, ruxsatlar va xarajat turlari lug'ati."""

from __future__ import annotations

import uuid
from typing import Any

import test_purchases as tp
from test_purchases import D, ok, send
from test_reports import World

db = tp.db
world = tp.world


def quick(w: World, title: str, qty: int, item: str = "item", **body: Any) -> str:
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            title=title,
            lines=[{"item_id": str(w.ids[item]), "qty": qty}],
            paid_amount="1000000",
            currency="UZS",
            ordered_on="2026-10-01",
            **body,
        ),
        201,
    )
    return str(det["purchase"]["id"])


def pool(w: World, role: str = "owner", query: str = "") -> dict[str, dict[str, Any]]:
    out = ok(send(w, "GET", f"cargo-pool{query}", role))
    return {x["purchase_id"]: x for x in out["items"]}


def test_pool_and_tracked_cargo(world: World) -> None:
    w = world
    a = quick(w, "Trekli A", 10)
    b = quick(w, "Trekli B", 20, track_no="YT-1")
    hand = quick(w, "Qo'limda", 5, on_hand=True)
    rows = pool(w)
    assert {a, b} <= set(rows) and hand not in rows
    assert rows[b]["track_no"] == "YT-1" and rows[a]["units"] == 10
    assert rows[a]["items"] == ["Mashina"] and rows[a]["state"] == "in_transit"

    out = ok(
        send(
            w,
            "POST",
            "cargo-pool/tracked",
            currency="UZS",
            rows=[
                {"purchase_id": a, "amount": "50000", "weight_kg": "2.5", "track_no": " YT-9 "},
                {"purchase_id": b, "amount": "80000"},
            ],
        ),
        201,
    )
    assert out == {"created": 2}
    rows = pool(w)
    assert a not in rows and b not in rows  # kargo puli kiritildi
    det = ok(send(w, "GET", f"purchases/{a}"))
    cargo = [c for c in det["components"] if c["kind"] == "cargo"]
    assert len(cargo) == 1 and D(cargo[0]["amount"]) == D(50_000)
    assert D(cargo[0]["weight_kg"]) == D("2.5") and cargo[0]["allocation"] == "units"
    assert det["purchase"]["track_no"] == "YT-9"
    assert D(det["purchase"]["total"]) == D(1_050_000)
    assert "cargo_missing" not in det["lines"][0]["flags"]


def test_tracked_validation(world: World) -> None:
    w = world
    a = quick(w, "Tekshiruv", 3)
    bad: list[dict[str, Any]] = [
        {"rows": []},
        {"rows": [{"purchase_id": a, "amount": "0"}]},
        {"rows": [{"purchase_id": a, "amount": "5"}], "currency": "USD", "rate_mode": "manual"},
        {"rows": [{"purchase_id": str(uuid.uuid4()), "amount": "5"}]},
        {"rows": [{"purchase_id": a, "amount": "5"}, {"purchase_id": a, "amount": "6"}]},
    ]
    for body in bad:
        r = send(w, "POST", "cargo-pool/tracked", **body)
        assert r.status_code in (404, 422), (body, r.text)
    assert a in pool(w)  # hech narsa yozilmadi
    body = {"rows": [{"purchase_id": a, "amount": "5"}], "currency": "UZS"}
    assert send(w, "POST", "cargo-pool/tracked", "warehouse", **body).status_code == 403
    assert send(w, "POST", "cargo-pool/tracked", "accountant", **body).status_code == 403
    assert a in pool(w, "warehouse")  # omborchi ro'yxatni ko'radi
    assert ok(send(w, "GET", "cargo-pool", "warehouse"))["amounts"] is False


def test_box_shares_and_recount(world: World) -> None:
    w = world
    a = quick(w, "Quti A", 30)
    b = quick(w, "Quti B", 60)
    c = quick(w, "Quti C", 10, item="item2")
    ids = [a, b, c]
    shares = ok(
        send(w, "POST", "cargo-pool/shares", amount="100", currency="UZS", purchase_ids=ids)
    )
    assert {k: D(v) for k, v in shares["shares"].items()} == {a: 30, b: 60, c: 10}
    shares = ok(
        send(
            w,
            "POST",
            "cargo-pool/shares",
            amount="100",
            currency="UZS",
            purchase_ids=ids,
            fixed={b: "50"},
        )
    )
    assert {k: D(v) for k, v in shares["shares"].items()} == {a: D("37.50"), b: 50, c: D("12.50")}
    r = send(w, "POST", "cargo-pool/shares", amount="100", purchase_ids=ids, fixed={b: "101"})
    assert r.status_code == 422 and r.json()["code"] == "bad_shares"

    box = ok(
        send(
            w,
            "POST",
            "cargo-pool/box",
            title="KOD-77",
            amount="1000000",
            currency="UZS",
            purchase_ids=ids,
            fixed={b: "500000"},
        ),
        201,
    )
    ship = box["shipment_id"]
    rows = pool(w)
    assert not set(ids) & set(rows)
    det = ok(send(w, "GET", f"shipments/{ship}"))
    assert det["shipment"]["title"] == "KOD-77" and det["shipment"]["purchase_count"] == 3
    comp = det["components"][0]
    assert comp["kind"] == "cargo" and {k: D(v) for k, v in comp["purchase_shares"].items()} == {
        b: D(500_000)
    }
    by = {x["id"]: D(x["share"]) for x in det["purchases"]}
    assert by == {a: D(375_000), b: D(500_000), c: D(125_000)}

    # Sanash: A dan 20 ta keldi — qo'lda o'zgartirilmagan ulushlar kelgan dona bo'yicha qayta bo'linadi.
    line = ok(send(w, "GET", f"purchases/{a}"))["lines"][0]["id"]
    ok(send(w, "PATCH", f"purchases/{a}/lines/{line}", received_qty=20))
    det = ok(send(w, "GET", f"shipments/{ship}"))
    by = {x["id"]: D(x["share"]) for x in det["purchases"]}
    assert by[b] == D(500_000) and by[a] + by[c] == D(500_000)
    assert by[a] == D("333333.33") or by[a] == D("333333.34")

    # Qo'lda ulushlarni almashtirish: hammasi dona bo'yicha.
    out = ok(send(w, "PUT", f"shipments/{ship}/components/{comp['id']}/purchase-shares", fixed={}))
    assert sum(D(v) for v in out["shares"].values()) == D(1_000_000)
    det = ok(send(w, "GET", f"shipments/{ship}"))
    assert det["components"][0]["purchase_shares"] == {}
    # Komponent summasi tahrirlansa ham qo'lda ulushlar yo'qolmaydi.
    ok(
        send(
            w,
            "PUT",
            f"shipments/{ship}/components/{comp['id']}/purchase-shares",
            fixed={c: "100000"},
        )
    )
    ok(send(w, "PATCH", f"shipments/{ship}/components/{comp['id']}", amount="900000"))
    det = ok(send(w, "GET", f"shipments/{ship}"))
    assert D(det["components"][0]["purchase_shares"][c]) == D(100_000)
    r = send(
        w,
        "PUT",
        f"shipments/{ship}/components/{comp['id']}/purchase-shares",
        fixed={str(uuid.uuid4()): "1"},
    )
    assert r.status_code == 404


def test_box_and_tracked_are_exclusive(world: World) -> None:
    w = world
    own = quick(w, "O'z kargosi", 5)
    free = quick(w, "Bo'sh", 5)
    ok(
        send(
            w,
            "POST",
            "cargo-pool/tracked",
            currency="UZS",
            rows=[{"purchase_id": own, "amount": "1000"}],
        ),
        201,
    )
    r = send(
        w,
        "POST",
        "cargo-pool/box",
        title="X",
        amount="10",
        currency="UZS",
        purchase_ids=[own, free],
    )
    assert r.status_code == 409 and r.json()["code"] == "cargo_twice"
    box = ok(
        send(
            w, "POST", "cargo-pool/box", title="Y", amount="10", currency="UZS", purchase_ids=[free]
        ),
        201,
    )
    r = send(
        w,
        "POST",
        "cargo-pool/tracked",
        currency="UZS",
        rows=[{"purchase_id": free, "amount": "1000"}],
    )
    assert r.status_code == 409 and r.json()["code"] == "cargo_twice"
    r = send(
        w, "POST", "cargo-pool/box", title="Z", amount="10", currency="UZS", purchase_ids=[free]
    )
    assert r.status_code == 409 and r.json()["code"] == "purchase_in_shipment"
    assert box["shipment_id"]
    r = send(
        w,
        "POST",
        "cargo-pool/box",
        title="Z",
        amount="10",
        currency="UZS",
        purchase_ids=[quick(w, "Kompaniyasiz", 1)],
        carrier_id=str(uuid.uuid4()),
    )
    assert r.status_code == 404


def test_counted_purchases_in_pool_on_request(world: World) -> None:
    w = world
    pid = quick(w, "Sanalgan", 4)
    ok(send(w, "PATCH", f"purchases/{pid}", dates={"received": "2026-10-20"}))
    assert pid not in pool(w)
    assert pool(w, query="?counted=true")[pid]["state"] == "in_stock"


def test_cost_types_dictionary(world: World) -> None:
    w = world
    t = ok(send(w, "POST", "cost-types", name="  Ombor   ijarasi "), 201)
    assert t["name"] == "Ombor ijarasi"
    again = ok(send(w, "POST", "cost-types", name="ombor ijarasi"), 201)
    assert again["id"] == t["id"]
    assert [x["name"] for x in ok(send(w, "GET", "cost-types"))] == ["Ombor ijarasi"]
    assert send(w, "POST", "cost-types", "warehouse", name="X").status_code == 201
    assert send(w, "POST", "cost-types", "accountant", name="X").status_code == 403

    pid = quick(w, "Turli xarajat", 2)
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="customs",
            cost_type_id=t["id"],
            amount="7000",
            currency="UZS",
        ),
        201,
    )
    comp = next(c for c in det["components"] if c["cost_type_id"] == t["id"])
    assert comp["kind"] == "other" and comp["type_name"] == "Ombor ijarasi"
    assert send(w, "DELETE", f"cost-types/{t['id']}").status_code == 409
    # Tayyor turga o'tkazilsa — bog'lanish olib tashlanadi.
    det = ok(send(w, "PATCH", f"purchases/{pid}/components/{comp['id']}", kind="taxi_x"), 422)
    det = ok(send(w, "PATCH", f"purchases/{pid}/components/{comp['id']}", kind="local_delivery"))
    comp = next(c for c in det["components"] if c["id"] == comp["id"])
    assert comp["kind"] == "local_delivery" and comp["cost_type_id"] is None
    assert send(w, "DELETE", f"cost-types/{t['id']}").status_code == 204
    assert send(w, "DELETE", f"cost-types/{t['id']}").status_code == 404
    r = send(
        w,
        "POST",
        f"purchases/{pid}/components",
        kind="other",
        cost_type_id=str(uuid.uuid4()),
        amount="1",
        currency="UZS",
    )
    assert r.status_code == 404
    # Kargoda ham o'z turi.
    t2 = ok(send(w, "POST", "cost-types", name="Yuk tushirish"), 201)
    box = ok(
        send(
            w,
            "POST",
            "cargo-pool/box",
            title="Turli",
            amount="10",
            currency="UZS",
            purchase_ids=[quick(w, "Quti uchun", 1)],
        ),
        201,
    )
    det = ok(
        send(
            w,
            "POST",
            f"shipments/{box['shipment_id']}/components",
            kind="other",
            cost_type_id=t2["id"],
            amount="5000",
            currency="UZS",
        ),
        201,
    )
    assert any(c["type_name"] == "Yuk tushirish" for c in det["components"])


def test_shipments_pagination(world: World) -> None:
    w = world
    for i in range(3):
        ok(send(w, "POST", "shipments", title=f"Sahifa {i}"), 201)
    everything = ok(send(w, "GET", "shipments"))
    total = everything["total"]
    assert total == len(everything["items"]) >= 3 and everything["pages"] == 1
    first = ok(send(w, "GET", "shipments?limit=2&page=1"))
    assert len(first["items"]) == 2 and first["pages"] == -(-total // 2)
    last = ok(send(w, "GET", "shipments?limit=2&page=999"))
    assert last["page"] == first["pages"] and last["total"] == total
    seen = {x["id"] for x in first["items"]} | {x["id"] for x in last["items"]}
    assert len(seen) == len(first["items"]) + len(last["items"])

"""TM4 sanash va xaridni bo'lish (haqiqiy PostgreSQL, ADR-061 §5–§6): kelgan son, brak — chiqim sog' donaga; brak
narxi; qadoq qo'shimchasi (tovardan nusxa, eslab qolish); sotuvchi qaytargan summa (sanashda va keyin); qismlab keladigan
xaridni ikkiga bo'lish (chiqimlar dona bo'yicha); ruxsatlar."""

from __future__ import annotations

import uuid
from typing import Any

import test_purchases as tp
from test_purchases import D, ok, send
from test_reports import World

db = tp.db
world = tp.world


def quick(w: World, qty: int | list[int], paid: str = "1000000", **body: Any) -> dict[str, Any]:
    qtys = qty if isinstance(qty, list) else [qty]
    items = ["item", "item2"]
    lines = [{"item_id": str(w.ids[items[i]]), "qty": q} for i, q in enumerate(qtys)]
    return ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=lines,
            paid_amount=paid,
            currency="UZS",
            ordered_on="2026-10-01",
            **body,
        ),
        201,
    )


def test_count_defects_and_refund(world: World) -> None:
    w = world
    det = quick(w, 100)
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            counted_on="2026-10-20",
            lines=[{"line_id": line, "received_qty": 100, "defect_qty": 5}],
        )
    )
    p, ln = out["purchase"], out["lines"][0]
    assert p["state"] == "in_stock" and p["dates"]["received"] == "2026-10-20"
    assert ln["good_qty"] == 95 and ln["defect_qty"] == 5
    assert D(ln["cost"]["unit_cost"]) == (D(1_000_000) / 95).quantize(D("0.01")) or abs(
        D(ln["cost"]["unit_cost"]) - D(1_000_000) / 95
    ) < D("0.01")
    assert D(ln["defect_cost"]) == D(50_000)
    assert "not_received" not in ln["flags"]
    # Sotuvchi qaytargan summa — keyin, PATCH bilan: tovar summasidan ayriladi.
    out = ok(send(w, "PATCH", f"purchases/{pid}", refund_amount="50000", refund_currency="UZS"))
    assert D(out["purchase"]["refund_amount"]) == D(50_000)
    assert D(out["lines"][0]["cost"]["total"]) == D(950_000)
    out = ok(send(w, "PATCH", f"purchases/{pid}", refund_amount=None))
    assert out["purchase"]["refund_amount"] is None and out["purchase"]["refund_currency"] is None
    r = send(w, "PATCH", f"purchases/{pid}", refund_amount="10")
    assert r.status_code == 422 and r.json()["code"] == "bad_refund"
    # Sanashda qaytarilgan summa ham beriladi.
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            lines=[{"line_id": line, "received_qty": 90}],
            refund_amount="100000",
            refund_currency="UZS",
        )
    )
    assert D(out["lines"][0]["cost"]["total"]) == D(900_000)
    assert out["lines"][0]["defect_cost"] is None and out["lines"][0]["good_qty"] == 90


def test_count_pack_from_item_and_remember(world: World) -> None:
    w, a = world, world.a
    a.sql("UPDATE items SET pack_unit_cost = 500 WHERE id = %s", [w.ids["item"]])
    det = quick(w, 10, paid="100000")
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            lines=[{"line_id": line, "received_qty": 10}],
        )
    )
    ln = out["lines"][0]
    assert D(ln["pack_unit_cost"]) == D(500)
    assert D(ln["cost"]["unit_cost"]) == D(10_500)  # 100 000 / 10 + 500
    det = quick(w, 10, paid="100000")
    pid2, line2 = det["purchase"]["id"], det["lines"][0]["id"]
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid2}/count",
            remember_pack=True,
            lines=[{"line_id": line2, "received_qty": 10, "pack_unit_cost": "800"}],
        )
    )
    assert a.sql("SELECT pack_unit_cost FROM items WHERE id = %s", [w.ids["item"]])[0][0] == D(800)
    a.sql("UPDATE items SET pack_unit_cost = NULL WHERE id = %s", [w.ids["item"]])


def test_count_validation_and_permissions(world: World) -> None:
    w = world
    det = quick(w, [10, 4])
    pid, l1, l2 = det["purchase"]["id"], det["lines"][0]["id"], det["lines"][1]["id"]
    bad: list[dict[str, Any]] = [
        {"lines": []},
        {"lines": [{"line_id": l1, "received_qty": 5, "defect_qty": 6}]},
        {"lines": [{"line_id": str(uuid.uuid4()), "received_qty": 1}]},
        {"lines": [{"line_id": l1, "received_qty": 1}, {"line_id": l1, "received_qty": 2}]},
        {"lines": [{"line_id": l1, "received_qty": 1}], "refund_amount": "5"},
    ]
    for body in bad:
        r = send(w, "POST", f"purchases/{pid}/count", **body)
        assert r.status_code in (404, 422), (body, r.text)
    # Faqat bitta qator sanaldi — xarid hali "Yo'lda".
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            "warehouse",
            lines=[{"line_id": l1, "received_qty": 10}],
        )
    )
    assert out["purchase"]["state"] == "in_transit"
    r = send(
        w,
        "POST",
        f"purchases/{pid}/count",
        "warehouse",
        lines=[{"line_id": l2, "received_qty": 4, "pack_unit_cost": "1"}],
    )
    assert r.status_code == 403
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            "warehouse",
            lines=[{"line_id": l2, "received_qty": 4}],
        )
    )
    assert out["purchase"]["state"] == "in_stock"
    assert (
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            "accountant",
            lines=[{"line_id": l2, "received_qty": 4}],
        ).status_code
        == 403
    )
    r = send(w, "PATCH", f"purchases/{pid}", "warehouse", refund_amount="1", refund_currency="UZS")
    assert r.status_code == 403


def test_split_purchase(world: World) -> None:
    w = world
    det = quick(w, [60, 40], paid="1000000", track_no="T-1")
    pid = det["purchase"]["id"]
    by_qty = {x["ordered_qty"]: x["id"] for x in det["lines"]}
    l1, l2 = by_qty[60], by_qty[40]
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="agent_fee",
            amount="10000",
            currency="UZS",
            lines=[l2],
        ),
        201,
    )
    # Birinchi qatordan 20 tasi va ikkinchi qator butunlay keyin keladi.
    out = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/split",
            lines=[{"line_id": l1, "qty": 20}, {"line_id": l2, "qty": 40}],
        ),
        201,
    )
    old, new_id = out["purchase"], out["new_purchase_id"]
    assert [x["ordered_qty"] for x in old["lines"]] == [40]
    new = ok(send(w, "GET", f"purchases/{new_id}"))
    assert new["purchase"]["state"] == "in_transit" and new["purchase"]["track_no"] == "T-1"
    assert sorted(x["ordered_qty"] for x in new["lines"]) == [20, 40]
    assert any(x["id"] == l2 for x in new["lines"])  # butun qator o'zi ko'chdi
    goods_old = [c for c in old["components"] if c["kind"] == "goods"]
    goods_new = [c for c in new["components"] if c["kind"] == "goods"]
    assert D(goods_old[0]["amount"]) == D(400_000) and D(goods_new[0]["amount"]) == D(600_000)
    agent_new = [c for c in new["components"] if c["kind"] == "agent_fee"]
    assert D(agent_new[0]["amount"]) == D(10_000) and agent_new[0]["lines"] == [l2]
    assert not [c for c in old["components"] if c["kind"] == "agent_fee"]
    assert D(old["purchase"]["total"]) + D(new["purchase"]["total"]) == D(1_010_000)

    # Xatolar: hammasi ko'chmaydi, ortiqcha dona, sanalgan xarid.
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": l1, "qty": 40}])
    assert r.status_code == 422 and r.json()["code"] == "bad_split"
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": l1, "qty": 41}])
    assert r.status_code == 422
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": l2, "qty": 1}])
    assert r.status_code == 404
    ok(send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": l1, "received_qty": 40}]))
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": l1, "qty": 1}])
    assert r.status_code == 409 and r.json()["code"] == "split_counted"


def test_split_rejects_manual_shares(world: World) -> None:
    w = world
    det = quick(w, [5, 5])
    pid, l1, l2 = det["purchase"]["id"], det["lines"][0]["id"], det["lines"][1]["id"]
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="customs",
            amount="100",
            currency="UZS",
            allocation="manual",
            shares={l1: "1", l2: "3"},
        ),
        201,
    )
    r = send(w, "POST", f"purchases/{pid}/split", lines=[{"line_id": l1, "qty": 2}])
    assert r.status_code == 409 and r.json()["code"] == "split_manual_shares"

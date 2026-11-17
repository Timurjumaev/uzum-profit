"""TM9.8 "Keldi" — sanashdan oldin (haqiqiy PostgreSQL, ADR-069): kargo puli oynasida majburiy "Keldimi? Ha / Hali yo'q",
ro'yxatda "Keldi", sanash o'zi qo'yadi; "Omborimda · sanalmagan" (Omborim, jo'natma, F26, "Diqqat"); F21 tayyor sanasi —
keldi (kargo to'lov sanasi faqat eski yozuvlarda); eski yozuvlar o'zgarmaydi; 3 kun sanalmagan xarid — bildirishnoma."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import test_purchases as tp
from test_purchases import ok, send
from test_reports import World
from upapi import notify
from upapi import realcheck as rc
from upapi.reports.common import today

db = tp.db
world = tp.world

_barcode = iter(range(4_780_000_300_000, 4_780_000_400_000))


def fresh_sku(w: World, name: str) -> str:
    _item, sku = w.a.item(name)
    w.a.sql("UPDATE mp_skus SET barcode = %s WHERE id = %s", [str(next(_barcode)), sku])
    w.ids[name] = sku
    return str(sku)


def in_transit(w: World, sku: str, qty: int, ordered: date) -> dict[str, Any]:
    return ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": sku, "qty": qty}],
            paid_amount=str(qty * 10_000),
            currency="UZS",
            ordered_on=ordered.isoformat(),
        ),
        201,
    )


def purchase(w: World, pid: str) -> dict[str, Any]:
    return dict(ok(send(w, "GET", f"purchases/{pid}"))["purchase"])


def ready_on(w: World, line_id: str) -> date | None:
    w.a.recalc(datetime.now(UTC))
    rows = w.a.sql("SELECT ready_on FROM lots WHERE purchase_line_id = %s", [line_id])
    return rows[0][0] if rows else None


def test_cargo_pool_requires_answer(world: World) -> None:
    """ "Tovar qo'limga keldimi?" — standartsiz: javobsiz saqlanmaydi."""
    w = world
    det = in_transit(w, fresh_sku(w, "Keldi-0"), 3, today() - timedelta(days=10))
    body = {"currency": "UZS", "rows": [{"purchase_id": det["purchase"]["id"], "amount": "1000"}]}
    r = send(w, "POST", "cargo-pool/tracked", **body)
    assert r.status_code == 422 and r.json()["errors"][0]["loc"][-1] == "arrived"
    r = send(
        w,
        "POST",
        "cargo-pool/box",
        title="Q",
        amount="10",
        currency="UZS",
        purchase_ids=[det["purchase"]["id"]],
    )
    assert r.status_code == 422


def test_arrived_with_cargo_then_counted(world: World) -> None:
    w = world
    sku = fresh_sku(w, "Keldi-1")
    day = today()
    came = day - timedelta(days=4)
    det = in_transit(w, sku, 10, day - timedelta(days=20))
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    before = ok(send(w, "GET", "dashboard?start=2026-10-01&end=2026-10-31"))["attention"]
    ok(
        send(
            w,
            "POST",
            "cargo-pool/tracked",
            currency="UZS",
            paid_on=(day - timedelta(days=6)).isoformat(),
            arrived=True,
            arrived_on=came.isoformat(),
            rows=[{"purchase_id": pid, "amount": "50000"}],
        ),
        201,
    )
    p = purchase(w, pid)
    assert (p["state"], p["counted"], p["arrived_on"]) == ("in_stock", False, came.isoformat())
    assert p["path"][1]["mark"] == "current" and p["path"][1]["uncounted"] is True
    assert p["path"][1]["on"] == came.isoformat()
    assert any(x["id"] == pid for x in ok(send(w, "GET", "purchases?state=in_stock"))["items"])
    # F21: tayyor sana — keldi (kargo to'lovi emas).
    assert ready_on(w, line) == came
    # Omborim: sanalmagan qism alohida; sanalgan qoldiqqa (M10) va jo'natmaga kirmaydi.
    wh = ok(send(w, "GET", "warehouse"))
    mine = next(x for x in wh["uncounted"] if x["purchase_id"] == pid)
    assert mine["qty"] == 10 and mine["days"] == 4 and mine["lines"][0]["sku_id"] == sku
    assert not any(r["sku_id"] == sku for r in wh["items"])
    draft = ok(send(w, "GET", f"dispatches/draft?shop_id={w.a.shop_id}"))
    assert not any(r["sku_id"] == sku for r in draft["rows"]) and draft["uncounted"] >= 10
    # F26 joylari: sanalmagan dona "Omborimda" (buyurtma soni bilan), "Yo'lda" emas.
    inv = ok(send(w, "GET", "inventory?limit=100"))["items"]
    loc = next(r for r in inv if r["sku_id"] == sku)["locations"]
    assert (loc["own"], loc["road"]) == (10, 0)
    after = ok(send(w, "GET", "dashboard?start=2026-10-01&end=2026-10-31"))["attention"]
    assert after["uncounted"] == before["uncounted"] + 1
    # Sanash: "Keldi" sanasi saqlanadi, Omborimda sanalgan.
    ok(send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": line, "received_qty": 9}]))
    p = purchase(w, pid)
    assert p["counted"] is True and p["arrived_on"] == came.isoformat()
    assert p["path"][1]["uncounted"] is False
    assert ready_on(w, line) == came
    row = next(r for r in ok(send(w, "GET", "warehouse"))["items"] if r["sku_id"] == sku)
    assert row["qty"] == 9
    assert not any(x["purchase_id"] == pid for x in ok(send(w, "GET", "warehouse"))["uncounted"])


def test_not_yet_and_bulk_arrived(world: World) -> None:
    w = world
    sku = fresh_sku(w, "Keldi-2")
    day = today()
    det = in_transit(w, sku, 5, day - timedelta(days=15))
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    ok(
        send(
            w,
            "POST",
            "cargo-pool/tracked",
            currency="UZS",
            paid_on=(day - timedelta(days=3)).isoformat(),
            arrived=False,
            rows=[{"purchase_id": pid, "amount": "9000"}],
        ),
        201,
    )
    p = purchase(w, pid)
    assert p["state"] == "in_transit" and p["arrived_on"] is None
    # Kargo to'langan, tovar hali kelmagan — lot tayyor emas (eski qoidada kargo to'lov sanasi bo'lardi).
    assert ready_on(w, line) is None

    # Ro'yxatda "Keldi": sana — bugun (standart) yoki tanlangan; kelajak / buyurtmadan oldin — rad.
    r = send(w, "POST", "purchases/arrived", purchase_ids=[pid], arrived_on=str(day + timedelta(1)))
    assert r.status_code == 422
    r = send(
        w, "POST", "purchases/arrived", purchase_ids=[pid], arrived_on=str(day - timedelta(30))
    )
    assert r.status_code == 422 and r.json()["code"] == "bad_arrival"
    assert ok(send(w, "POST", "purchases/arrived", purchase_ids=[pid])) == {"updated": 1}
    p = purchase(w, pid)
    assert p["state"] == "in_stock" and p["arrived_on"] == day.isoformat()
    assert ready_on(w, line) == day
    # Bekor qilish — yana "Yo'lda".
    ok(send(w, "POST", "purchases/arrived", purchase_ids=[pid], arrived_on=None))
    assert purchase(w, pid)["state"] == "in_transit"
    assert send(w, "POST", "purchases/arrived", "accountant", purchase_ids=[pid]).status_code == 403
    # Sanalgan xaridda "Keldi" o'zgarmaydi; sanash "Keldi"ni o'zi qo'yadi (sanash kuni).
    ok(send(w, "POST", f"purchases/{pid}/count", lines=[{"line_id": line, "received_qty": 5}]))
    p = purchase(w, pid)
    assert p["arrived_on"] == day.isoformat() and p["counted"] is True
    r = send(w, "POST", "purchases/arrived", purchase_ids=[pid])
    assert r.status_code == 409 and r.json()["code"] == "bad_arrival"


def test_box_arrival_goes_to_shipment(world: World) -> None:
    w = world
    day = today()
    a = in_transit(w, fresh_sku(w, "Keldi-3a"), 4, day - timedelta(days=12))
    b = in_transit(w, fresh_sku(w, "Keldi-3b"), 6, day - timedelta(days=12))
    ids = [a["purchase"]["id"], b["purchase"]["id"]]
    box = ok(
        send(
            w,
            "POST",
            "cargo-pool/box",
            title="KOD-9",
            amount="100000",
            currency="UZS",
            paid_on=(day - timedelta(days=2)).isoformat(),
            arrived=True,
            purchase_ids=ids,
        ),
        201,
    )
    shipment = w.a.sql("SELECT arrived_on FROM shipments WHERE id = %s", [box["shipment_id"]])
    assert shipment[0][0] == day - timedelta(days=2)  # standart — kargo to'lov sanasi
    for pid in ids:
        p = purchase(w, pid)
        assert p["state"] == "in_stock" and p["arrived_on"] == str(day - timedelta(days=2))
    assert ready_on(w, a["lines"][0]["id"]) == day - timedelta(days=2)


def test_legacy_records_unchanged(world: World) -> None:
    """Eski yozuv (``arrival_marked`` NULL): eski "Toshkentga keldi" sanasi holatga ta'sir qilmaydi, lot tayyor sanasi —
    avvalgidek kargo to'lov sanasi (tannarx tiyinigacha o'zgarmaydi)."""
    w, a = world, world.a
    sku = fresh_sku(w, "Keldi-4")
    det = in_transit(w, sku, 7, date(2026, 9, 1))
    pid, line = det["purchase"]["id"], det["lines"][0]["id"]
    a.sql(
        "UPDATE purchases SET arrival_marked = NULL, arrived_on = '2026-09-20' WHERE id = %s",
        [pid],
    )
    a.insert(
        "cost_components",
        purchase_id=pid,
        kind="cargo",
        amount=7000,
        currency="UZS",
        paid_on=date(2026, 9, 18),
    )
    p = purchase(w, pid)
    assert p["state"] == "in_transit" and p["arrived_on"] is None
    assert ready_on(w, line) == date(2026, 9, 18)
    # realcheck (faqat o'qish): staging'da shunday xaridlar bormi — ro'yxat va xulosa qatori.
    found = {str(x["id"]): x for x in a.run(rc.legacy_arrived)}
    assert found[pid]["arrived_on"] == date(2026, 9, 20) and found[pid]["cargo"] is True
    report = {
        "shops": [],
        "supply": {"skus": 0, "problems": [], "legacy_arrived": list(found.values())},
    }
    assert any("Eski 'Toshkentga keldi'" in x for x in rc.summary({"orgs": [report]}))
    # Sanalganda — eski qoida: sanash sanasi; "Toshkentga keldi" bosqich sanasi saqlanadi (Tarix).
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/count",
            counted_on="2026-09-25",
            lines=[{"line_id": line, "received_qty": 7}],
        )
    )
    assert ready_on(w, line) == date(2026, 9, 25)
    marked = a.sql("SELECT arrival_marked, arrived_on FROM purchases WHERE id = %s", [pid])
    assert marked[0] == (None, date(2026, 9, 20))


def test_uncounted_notification_once(world: World) -> None:
    w = world
    day = today()
    det = in_transit(w, fresh_sku(w, "Keldi-5"), 2, day - timedelta(days=9))
    pid = det["purchase"]["id"]
    ok(
        send(
            w,
            "POST",
            "purchases/arrived",
            purchase_ids=[pid],
            arrived_on=str(day - timedelta(days=3)),
        )
    )
    now = datetime.combine(day, datetime.min.time(), ZoneInfo("Asia/Tashkent")) + timedelta(
        hours=11
    )
    w.a.run(lambda conn: notify.evaluate(conn, w.org_id, now))
    w.a.run(lambda conn: notify.evaluate(conn, w.org_id, now + timedelta(days=1)))
    rows = w.a.sql(
        "SELECT n.dedupe_key, n.payload, m.role FROM notifications n JOIN memberships m "
        "ON m.user_id = n.user_id AND m.org_id = n.org_id WHERE n.org_id = %s AND n.event = %s",
        [w.org_id, "uncounted_purchase"],
    )
    mine = [r for r in rows if r[0] == f"uncounted:{pid}"]
    assert {r[2] for r in mine} == {"owner", "manager", "warehouse"}  # har oluvchiga bir marta
    assert mine[0][1]["days"] == 3

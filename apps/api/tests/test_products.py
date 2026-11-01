"""B4.3 Mahsulotlar (M6) API'lari (haqiqiy PostgreSQL): jadval ustunlari va filtrlari, me'yoriy (bonussiz) foyda/dona
(F40, ADR-031), SKU sahifasi, unit kalkulyator (F35, F36) va tovar ↔ SKU bog'lash.

Dunyo (``world``) — ``test_reports`` dagi bilan bir xil, lekin shu modul uchun alohida baza. Testlar o'z ma'lumotini
(yangi SKU, boshqa oylar) qo'shadi va bonus davrlarini oxirida o'chiradi.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import test_reports
from test_reports import AUG, OCT, World, d, money
from upapi import calc
from upapi.auth.deps import COOKIE

db = test_reports.db
world = test_reports.world
D = Decimal


def send(w: World, method: str, path: str, role: str = "owner", **body: Any) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    url = f"/api/v1/orgs/{w.org_id}/{path}"
    if method == "delete":
        return w.api.client.delete(url)
    return getattr(w.api.client, method)(url, json=body)


@contextmanager
def bonus(w: World, day: str, *kinds: str, shop: Any = None, **extra: Any) -> Iterator[str]:
    """Bonus davri (bir kun) — blokdan chiqqach o'chiriladi."""
    r = send(
        w,
        "post",
        "fee-waivers",
        shop_id=str(shop or w.b.shop_id),
        start_on=day,
        end_on=extra.pop("end", day),
        kinds=list(kinds),
        **extra,
    )
    assert r.status_code == 201, r.text
    try:
        yield r.json()["id"]
    finally:
        assert send(w, "delete", f"fee-waivers/{r.json()['id']}").status_code == 204


def foreign_sku(w: World) -> uuid.UUID:
    """Boshqa tashkilot do'konidagi SKU (RLS: bizga ko'rinmaydi)."""
    shop = w.api.admin("SELECT id FROM shops WHERE org_id = %s LIMIT 1", [w.other])[0][0]
    sku = uuid.uuid4()
    w.api.admin(
        "INSERT INTO mp_skus (id, org_id, shop_id, external_id, sku_code) VALUES (%s, %s, %s, %s, 'Begona SKU')",
        [sku, w.other, shop, sku.int % 10**9],
    )
    return sku


def settle(w: World) -> None:
    """Yangi qo'shilgan faktlar bo'yicha tannarx va kunlik yig'indilarni qayta quradi."""
    w.b.run(lambda conn: calc.request_full(conn, w.b.org_id))
    assert w.b.recalc(datetime.now(UTC)).errors == {}


def rows(w: World, **params: Any) -> dict[str, dict[str, Any]]:
    return {r["sku_id"]: r for r in w.get("skus", **params)["items"]}


def lamp(w: World, **params: Any) -> dict[str, Any]:
    return rows(w, shop=str(w.b.shop_id), **{**AUG, **params})[str(w.ids["lb"])]


# --- Jadval ---------------------------------------------------------------------------------------


def test_table_columns_without_bonus(world: World) -> None:
    body = world.get("skus", **OCT)
    assert body["bonus"] == {"waivers": [], "unestimated_kinds": []}
    xa = {r["sku_id"]: r for r in body["items"]}[str(world.ids["xa"])]
    # Bonus yo'q — me'yoriy foyda haqiqiy foydaga teng (F40), "tejalgan" qiymat yo'q.
    assert xa["normative_state"] == "none" and xa["saved_per_unit"] is None
    assert xa["normative_profit_per_unit"] == xa["profit_per_unit"]
    # Xarajatlar ikki qismda (ADR-026) va P&L SKU ustuni bilan bir xil.
    col = {c["key"]: c for c in world.get("pnl", view="sku", **OCT)["columns"]}[
        str(world.ids["xa"])
    ]
    assert money(xa["expenses_direct"]) == money(col["statement"]["direct_total"])
    assert money(xa["expenses_allocated"]) == money(col["statement"]["allocated_total"])
    assert money(xa["expenses_direct"]) > 0 and money(xa["expenses_allocated"]) > 0
    # Qatorlar + bog'lanmagan + taqsimlanmagan = jami (M5 qabul mezoni), xarajat ustunlari ham.
    total = world.get("pnl", **OCT)["statement"]
    split = sum(
        money(r["expenses_direct"]) + money(r["expenses_allocated"])
        for r in rows(world, **OCT).values()
    )
    rest = sum(
        money(body[k]["direct_total"]) + money(body[k]["allocated_total"])
        for k in ("unlinked", "unallocated")
    )
    assert split + rest == money(total["uzum_total"]) + money(total["own_total"])


def test_table_filters_and_sorts(world: World) -> None:
    labels = {r["sku_id"]: r["label"] for r in rows(world, **OCT).values()}
    for label in ("profitable", "borderline", "loss", "no_data"):
        got = world.get("skus", label=label, **OCT)
        assert {r["sku_id"] for r in got["items"]} == {s for s, x in labels.items() if x == label}
        assert got["total"] == len(got["items"])
    assert world.call("skus", label="nope", **OCT).status_code == 422
    classes = {r["sku_id"]: r["abc"] for r in rows(world, **OCT).values()}
    for abc in ("A", "B", "C"):
        got = world.get("skus", abc=abc, **OCT)
        assert {r["sku_id"] for r in got["items"]} == {s for s, x in classes.items() if x == abc}
    assert world.call("skus", abc="D", **OCT).status_code == 422
    for key in (
        "avg_price",
        "profit_per_unit",
        "normative_profit_per_unit",
        "roi",
        "return_share",
        "cancel_share",
        "expenses_direct",
        "expenses_allocated",
    ):
        items = world.get("skus", sort=f"-{key}", **OCT)["items"]
        known = [money(r[key]) for r in items if r[key] is not None]
        assert known == sorted(known, reverse=True), key
        tail = [r[key] is None for r in items]
        assert tail == sorted(tail), key  # qiymatsizlar oxirida
    # Do'kon va qidiruv filtrlari bilan birga ishlaydi.
    only_b = world.get("skus", shop=str(world.b.shop_id), q="chiroq", **OCT)
    assert [r["sku_id"] for r in only_b["items"]] == [str(world.ids["zb"])]


# --- F40: me'yoriy foyda/dona ----------------------------------------------------------------------


def test_normative_sale_logistics_uses_last_paid_fee(world: World) -> None:
    # B: 10-avgust 3 dona logistikasiz (bonus), 11-avgust 1 dona 7 000 so'm bilan — oxirgi pullik tarif.
    with bonus(world, "2026-08-10", "sale_logistics", reason="Test"):
        row = lamp(world)
        assert row["normative_state"] == "adjusted"
        assert money(row["saved_per_unit"]) == D(5_250)  # 3 × 7 000 / 4 tannarxi ma'lum dona
        assert money(row["normative_profit_per_unit"]) == money(row["profit_per_unit"]) - D(5_250)
        # Haqiqiy foyda bonusdan o'zgarmaydi (ADR-031).
        after = lamp(world)
    assert money(after["net_profit"]) == money(row["net_profit"])
    plain = lamp(world)
    assert plain["normative_state"] == "none" and money(plain["net_profit"]) == money(
        row["net_profit"]
    )
    assert plain["normative_profit_per_unit"] == plain["profit_per_unit"]


def test_bonus_that_does_not_touch_the_sku_changes_nothing(world: World) -> None:
    with bonus(world, "2026-08-10", "sale_logistics", shop=world.a.shop_id):  # A do'koni davri
        assert lamp(world)["normative_state"] == "none"
    with bonus(world, "2026-08-10", "sale_logistics", dismissed=True):  # rad etilgan taklif
        assert lamp(world)["normative_state"] == "none"
    with bonus(
        world, "2026-08-11", "sale_logistics"
    ):  # 11-avgust logistika pullik edi — tejalgani yo'q
        assert lamp(world)["normative_state"] == "none"


def test_normative_unestimated_kinds_are_reported_not_guessed(world: World) -> None:
    with bonus(world, "2026-08-10", "sale_logistics", "fine"):
        body = world.get("skus", shop=str(world.b.shop_id), **AUG)
        row = {r["sku_id"]: r for r in body["items"]}[str(world.ids["lb"])]
        assert body["bonus"]["unestimated_kinds"] == ["fine"]
        assert [w["kinds"] for w in body["bonus"]["waivers"]] == [["sale_logistics", "fine"]]
        assert (
            row["normative_state"] == "adjusted"
        )  # baholanadigan qismi hisoblandi, qolgani aytilgan


def test_normative_fee_fallback_chain(world: World) -> None:
    b = world.b
    item = b.insert("items", name="Kabel")
    sku = b.insert("mp_skus", shop_id=b.shop_id, external_id=31, sku_code="Kabel", item_id=item)
    other = b.insert("mp_skus", shop_id=b.shop_id, external_id=32, sku_code="Boshqa")
    p = b.purchase(d(6, 1))
    b.line(p, item, 10)
    b.component(p, "goods", 100_000)
    b.sale(sku, d(6, 10), 2, price=100_000, logistics=0)
    settle(world)
    june = {"start": "2026-06-10", "end": "2026-06-10", "shop": str(b.shop_id)}

    def kabel() -> dict[str, Any]:
        return rows(world, **june)[str(sku)]

    with bonus(world, "2026-06-10", "sale_logistics"):
        # Hech qanday pullik tarif yo'q: taxmin yo'q, "me'yoriy baho yo'q".
        row = kabel()
        assert row["normative_state"] == "unavailable" and row["normative_profit_per_unit"] is None
        assert row["saved_per_unit"] is None and row["profit_per_unit"] is not None
        # Do'konning odatiy tarifi (oxirgi 90 kun): boshqa SKU'ning pullik qatori.
        b.sale(other, d(6, 5), 1, logistics=6_000)
        row = kabel()
        assert row["normative_state"] == "adjusted" and money(row["saved_per_unit"]) == D(6_000)
        # SKU'ning o'z oxirgi pullik tarifi odatiydan ustun; u bonus davridan oldin bo'lishi kerak.
        b.sale(sku, d(6, 8), 1, logistics=4_500)
        settle(world)
        row = kabel()
        assert row["normative_state"] == "adjusted"
        assert money(row["saved_per_unit"]) == D(9_000) / 2  # 2 dona × 4 500 / 2 (10-iyun davri)


def test_normative_storage_uses_sku_storage_price_and_stock_days(world: World) -> None:
    b, lb = world.b, world.ids["lb"]
    b.insert("sku_daily", sku_id=lb, day=d(8, 10), qty_active=5, qty_fbs=0)
    b.insert("sku_daily", sku_id=lb, day=d(8, 11), qty_active=4, qty_fbs=0)
    b.insert("sku_daily", sku_id=lb, day=d(8, 12), qty_active=3, qty_fbs=0)  # bonus tashqarisida
    with bonus(world, "2026-08-10", "storage", end="2026-08-11"):
        # Uzum saqlash narxini bermagan: baho yo'q.
        row = lamp(world)
        assert row["normative_state"] == "unavailable" and row["normative_profit_per_unit"] is None
        b.sql("UPDATE mp_skus SET storage_price = 100 WHERE id = %s", [lb])
        row = lamp(world)
        # (5 + 4) dona-kun × 100 = 900; tannarxi ma'lum 4 dona → 225 / dona.
        assert row["normative_state"] == "adjusted" and money(row["saved_per_unit"]) == D(225)
        assert money(row["normative_profit_per_unit"]) == money(row["profit_per_unit"]) - D(225)
        # Ikkala tur birga: tejamlar qo'shiladi.
        with bonus(world, "2026-08-10", "sale_logistics"):
            assert money(lamp(world)["saved_per_unit"]) == D(225) + D(5_250)
    b.sql("UPDATE mp_skus SET storage_price = NULL WHERE id = %s", [lb])


# --- SKU sahifasi ---------------------------------------------------------------------------------


def test_sku_detail(world: World) -> None:
    xa = world.ids["xa"]
    body = world.get(f"skus/{xa}", **OCT)
    row = rows(world, **OCT)[str(xa)]
    assert body["sku"] == row  # jadval bilan bir xil hisob
    assert body["statement"]["units"] == 6 and money(body["statement"]["revenue"]) == D(1_200_000)
    assert body["uzum_url"] is None
    # Kunlik tarix: sotuv kunlari + snapshot kunlari (1–20 oktabr); yig'indisi jadval bilan mos.
    days = {x["day"]: x for x in body["history"]}
    assert len(days) == 20 and sum(x["units"] for x in days.values()) == row["units"]
    assert sum(money(x["revenue"]) for x in days.values()) == money(row["revenue"])
    assert sum(money(x["net_profit"]) for x in days.values()) == money(row["net_profit"])
    assert days["2026-10-08"]["stock"] == 0 and days["2026-10-09"]["stock"] == 10
    assert days["2026-10-02"]["units"] == 2 and days["2026-10-02"]["profit_per_unit"] is not None
    assert days["2026-10-09"]["profit_per_unit"] is None and days["2026-10-09"]["price"] is None
    # Tannarx tarixi: tovar lotlari — tayyor (100 × 100 000) va yo'lda (20, sanasiz).
    lots = body["lots"]
    assert [(x["ready_on"], x["qty"]) for x in lots] == [("2026-09-01", 100), (None, 20)]
    assert money(lots[0]["unit_cost"]) == D(100_000) and money(lots[1]["unit_cost"]) == D(120_000)
    assert body["linked"]["name"] == "Mashina"
    assert [s["sku_id"] for s in body["linked"]["skus"]] == [str(xa)]
    assert body["stock_detail"]["active"] == 80 and body["stock_detail"]["fbs"] == 5
    assert body["stock_detail"]["defected"] == 2 and body["stock_detail"]["in_transit"] == 20
    assert body["bonus"] == {"waivers": [], "unestimated_kinds": []}


def test_sku_detail_returns_by_cause(world: World) -> None:
    xa = world.ids["xa"]
    assert world.get(f"skus/{xa}", **OCT)["returns"] == [{"cause": None, "units": 1}]
    world.a.sale(xa, d(10, 16), 3, amount_returns=2, return_cause="Defekt")
    world.a.sale(xa, d(10, 17), 2, amount_returns=1, return_cause="Defekt")
    world.a.sale(
        xa, d(10, 18), 1, "CANCELED", amount_returns=1, return_cause="Bekor"
    )  # qaytish emas
    assert world.get(f"skus/{xa}", **OCT)["returns"] == [
        {"cause": "Defekt", "units": 3},
        {"cause": None, "units": 1},
    ]
    world.a.run(lambda conn: calc.request_full(conn, world.a.org_id))
    assert world.a.recalc(datetime.now(UTC)).errors == {}


def test_sku_detail_calculator_defaults_and_sources(world: World) -> None:
    xa = world.ids["xa"]
    body = world.get(f"skus/{xa}", **OCT)
    c, row = body["calc"], body["sku"]
    assert c["sources"] == {
        "price": "period",
        "unit_cost": "last_lot",  # narx qo'yish uchun oxirgi partiya (ADR-033)
        "logistics": "last_paid",
        "commission_pct": "period",
        "tax_pct": "period",
        "ads_pct": "period",
    }
    assert money(c["price"]) == money(row["avg_price"]) and money(c["unit_cost"]) == D(100_000)
    assert money(c["logistics"]) == D(5_000) and money(c["packaging"]) == 0
    assert money(c["commission_pct"]) == D(20)  # komissiya sotuv narxining 20%
    assert money(c["tax_pct"]) == D(4)  # aylanmadan 4% (F11)
    assert money(c["ads_pct"]) == (D(row["acos"]) * 100).quantize(D("0.01"))
    # Davrda sotuv yo'q: narx va komissiya katalogdan, tannarx lotdan; qolgani noma'lum (taxmin yo'q).
    quiet = world.get(f"skus/{xa}", start="2026-07-01", end="2026-07-05")["calc"]
    assert quiet["sources"].get("unit_cost") == "last_lot" and money(quiet["unit_cost"]) == D(
        100_000
    )
    assert quiet["price"] is None and quiet["ads_pct"] is None and quiet["tax_pct"] is None
    assert quiet["commission_pct"] is None and "price" not in quiet["sources"]
    nothing = world.get(f"skus/{world.ids['ya']}", **OCT)["calc"]
    assert nothing["unit_cost"] is None and nothing["logistics"] is not None


def test_sku_detail_uzum_url_and_errors(world: World) -> None:
    ya = world.ids["ya"]
    product = world.a.insert(
        "mp_products", shop_id=world.a.shop_id, external_id=987654, title="Kruzhka"
    )
    world.a.sql("UPDATE mp_skus SET product_id = %s WHERE id = %s", [product, ya])
    assert world.get(f"skus/{ya}", **OCT)["uzum_url"] == "https://uzum.uz/ru/product/987654"
    assert world.call(f"skus/{uuid.uuid4()}", **OCT).status_code == 404
    other = foreign_sku(world)
    assert (
        world.call(f"skus/{other}", **OCT).status_code == 404
    )  # boshqa tashkilot SKU'si ko'rinmaydi
    assert world.call(f"skus/{ya}", role="warehouse", **OCT).status_code == 403
    assert world.call(f"skus/{ya}", role="accountant", **OCT).status_code == 200


# --- Unit kalkulyator (F35, F36) ------------------------------------------------------------------


def test_unit_calculator(world: World) -> None:
    got = world.get(
        "unit-calc",
        price=100_000,
        unit_cost=40_000,
        logistics=5_250,
        packaging=4_750,
        commission_pct=20,
        tax_pct=4,
        ads_pct=6,
        target_margin_pct=15,
    )
    assert money(got["fixed"]) == D(50_000) and money(got["share_pct"]) == D(30)
    assert money(got["profit"]) == D(20_000) and D(got["margin"]) == D("0.2")
    assert money(got["breakeven"]) == D("71428.57") and money(got["target_price"]) == D("90909.09")
    only_price = world.get("unit-calc", price=100_000, unit_cost=10_000, commission_pct=10)
    assert only_price["target_price"] is None and money(only_price["profit"]) == D(80_000)
    hopeless = world.get(
        "unit-calc",
        price=1,
        unit_cost=1,
        commission_pct=60,
        tax_pct=25,
        ads_pct=15,
        target_margin_pct=5,
    )
    assert hopeless["breakeven"] is None and hopeless["target_price"] is None
    # Tekshiruv va ruxsat.
    assert world.call("unit-calc", price=1, unit_cost=1, commission_pct=101).status_code == 422
    assert world.call("unit-calc", price=-1, unit_cost=1, commission_pct=1).status_code == 422
    assert world.call("unit-calc", unit_cost=1, commission_pct=1).status_code == 422
    assert (
        world.call(
            "unit-calc", role="warehouse", price=1, unit_cost=1, commission_pct=1
        ).status_code
        == 403
    )


# --- Tovar ↔ SKU bog'lash -------------------------------------------------------------------------


def audit(w: World, entity: str) -> list[tuple[str, Any, Any]]:
    rows_ = w.api.admin(
        "SELECT action, before, after FROM audit_log WHERE entity = %s ORDER BY created_at, action",
        [entity],
    )
    return [tuple(r) for r in rows_]


def test_items_list_and_search(world: World) -> None:
    world.api.admin(
        "INSERT INTO items (id, org_id, name) VALUES (%s, %s, 'Yashirin Mashina')",
        [uuid.uuid4(), world.other],
    )
    names = [x["name"] for x in world.get("items")["items"]]
    assert {"Mashina", "Chiroq"} <= set(names)  # ikkala do'kon tovari (bir tashkilot)
    assert "Yashirin Mashina" not in names  # boshqa tashkilot tovari ko'rinmaydi (RLS)
    found = world.get("items", q="MASHI")["items"]
    assert [x["name"] for x in found] == ["Mashina"] and found[0]["sku_count"] >= 1
    assert world.call("items", role="accountant").status_code == 403
    assert world.call("items", role="warehouse").status_code == 200


def test_link_new_existing_and_unlink(world: World) -> None:
    a = world.a
    sku = a.insert("mp_skus", shop_id=a.shop_id, external_id=41, sku_code="Termos 1L", item_id=None)
    path = f"skus/{sku}/item"
    # Yangi tovar: nom berilmasa SKU nomi.
    r = send(world, "put", path, mode="new")
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == "Termos 1L" and [s["sku_id"] for s in created["skus"]] == [str(sku)]
    assert audit(world, "item")[-1][0] == "item.create"
    # Mavjud tovarga: Mashina (xa) — ikki SKU bitta tovarda.
    x_item = world.api.admin("SELECT item_id FROM mp_skus WHERE id = %s", [world.ids["xa"]])[0][0]
    r = send(world, "put", path, mode="existing", item_id=str(x_item))
    assert r.status_code == 200 and r.json()["name"] == "Mashina"
    assert {s["sku_id"] for s in r.json()["skus"]} == {str(sku), str(world.ids["xa"])}
    queue = {(k, str(ref)) for k, ref, _ in a.queue()}
    assert ("item", str(x_item)) in queue and ("item", created["item_id"]) in queue
    assert ("shop", str(a.shop_id)) in queue
    # Ajratish: tovar qoladi, SKU tovarsiz.
    assert send(world, "put", path, mode="none").json() is None
    assert world.api.admin("SELECT item_id FROM mp_skus WHERE id = %s", [sku])[0][0] is None
    assert (
        world.api.admin(
            "SELECT count(*) FROM items WHERE id = %s", [uuid.UUID(created["item_id"])]
        )[0][0]
        == 1
    )
    actions = [x[0] for x in audit(world, "sku") if x[1] is not None or x[2] is not None]
    assert actions.count("sku.link_item") >= 3
    # O'zgarmasa audit yozilmaydi.
    before = len(audit(world, "sku"))
    assert send(world, "put", path, mode="none").status_code == 200
    assert len(audit(world, "sku")) == before


def test_link_changes_costs_after_recalc(world: World) -> None:
    a = world.a
    # Tovarsiz SKU sotuvi tannarxsiz; Mashina tovariga bog'langach — 100 000 so'mlik lot narxi bilan.
    ya = world.ids["ya"]
    row = rows(world, **OCT)[str(ya)]
    assert row["cogs_per_unit"] is None and row["uncovered_lines"] == 1
    x_item = world.api.admin("SELECT item_id FROM mp_skus WHERE id = %s", [world.ids["xa"]])[0][0]
    assert (
        send(world, "put", f"skus/{ya}/item", mode="existing", item_id=str(x_item)).status_code
        == 200
    )
    assert a.recalc(datetime.now(UTC)).errors == {}
    row = rows(world, **OCT)[str(ya)]
    assert row["cogs_per_unit"] is not None and row["uncovered_lines"] == 0
    assert world.get(f"skus/{ya}", **OCT)["linked"]["name"] == "Mashina"
    # Ajratilsa — yana tannarxsiz.
    assert send(world, "put", f"skus/{ya}/item", mode="none").status_code == 200
    assert a.recalc(datetime.now(UTC)).errors == {}
    row = rows(world, **OCT)[str(ya)]
    assert row["cogs_per_unit"] is None and row["uncovered_lines"] == 1


def test_link_errors_and_permissions(world: World) -> None:
    ya = world.ids["ya"]
    path = f"skus/{ya}/item"
    assert send(world, "put", f"skus/{uuid.uuid4()}/item", mode="none").status_code == 404
    other = foreign_sku(world)
    assert send(world, "put", f"skus/{other}/item", mode="none").status_code == 404
    assert send(world, "put", path, mode="existing").status_code == 422
    assert send(world, "put", path, mode="existing", item_id=str(uuid.uuid4())).status_code == 404
    foreign = uuid.uuid4()
    world.api.admin(
        "INSERT INTO items (id, org_id, name) VALUES (%s, %s, 'Begona')", [foreign, world.other]
    )
    assert send(world, "put", path, mode="existing", item_id=str(foreign)).status_code == 404
    nameless = world.a.insert("mp_skus", shop_id=world.a.shop_id, external_id=42)
    assert send(world, "put", f"skus/{nameless}/item", mode="new").status_code == 422
    assert send(world, "put", f"skus/{nameless}/item", mode="new", name="  ").status_code == 422
    assert send(world, "put", path, mode="nope").status_code == 422
    assert send(world, "put", path, role="accountant", mode="none").status_code == 403
    assert send(world, "put", path, role="warehouse", mode="none").status_code == 200
    assert send(world, "put", path, role="manager", mode="none").status_code == 200

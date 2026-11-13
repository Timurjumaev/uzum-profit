"""B4.6 ``/purchases`` (haqiqiy PostgreSQL): xarid hayoti (Partiya yo'li), qatorlar, xarajat komponentlari, kurs
rejimlari (CBU, qo'lda, kartadan yechilgan), taqsimot, jonli birlik tannarx (F20), ruxsatlar (omborchi — summasiz),
audit, "qayta buyurtma" va kech kiritilgan xarajatda qayta hisob (lotlar → o'tgan sotuvlar → P&L "qayta hisoblandi").
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from mptools import mp_api
from sellerfake import TOKEN, A, create_account
from test_calc import Org
from test_reports import World
from upapi.auth.deps import COOKIE

D = Decimal


def d(month: int, day: int) -> date:
    return date(2026, month, day)


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as urls:
        yield urls


@pytest.fixture(scope="module")
def world(db: dict[str, str]) -> Iterator[World]:
    settings = sf.settings_for(db)
    account = create_account(db, settings, TOKEN, [A])
    other = create_account(db, settings, TOKEN, [A])
    a = Org(db, account.org_id, account.shops[A])
    with mp_api(db) as api:
        w = World(api, a, a, other.org_id)
        w.ids["item"], w.ids["sku"] = a.item("Mashina")
        w.ids["item2"], w.ids["sku2"] = a.item("Qo'g'irchoq")
        a.sql(
            "INSERT INTO fx_rates (day, currency, source, rate) VALUES "
            "('2026-09-30', 'CNY', 'cbu', 1750), ('2026-09-30', 'USD', 'cbu', 12600) "
            "ON CONFLICT DO NOTHING"
        )
        for role in ("owner", "manager", "accountant", "warehouse"):
            phone = api.login()
            user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
            api.admin(
                "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, %s)",
                [a.org_id, user, role],
            )
            w.sessions[role] = api.client.cookies[COOKIE]
        yield w


def send(w: World, method: str, path: str, role: str = "owner", **json: Any) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.request(
        method,
        f"/api/v1/orgs/{w.org_id}/{path}",
        json=json if json else ({} if method in ("POST", "PATCH") else None),
        headers={"X-Requested-With": "fetch"},
    )


def ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, r.text
    return r.json() if r.content else None


def lines_by(detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["item_name"] or x["temp_name"]: x for x in detail["lines"]}


def new_purchase(w: World, **body: Any) -> dict[str, Any]:
    return ok(send(w, "POST", "purchases", **body), 201)


def test_stepwise_purchase_live_cost_and_late_cargo(world: World) -> None:
    """Legacy kabi bosqichma-bosqich: sarlavha → qatorlar → tovar summasi → (kech) kargo. Birlik tannarx jonli;
    kargo kiritilguncha "kargo kiritilmagan"; kech kargo o'tgan sotuv tannarxini qayta hisoblaydi."""
    w, a = world, world.a
    p = new_purchase(w, title="Oktabr partiyasi", dates={"ordered": "2026-09-30"})
    pid = p["purchase"]["id"]
    assert p["purchase"]["stage"] == "ordered" and p["lines"] == [] and p["recalc_pending"]
    ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/lines",
            item_id=str(w.ids["item"]),
            ordered_qty=100,
            received_qty=98,
            unit_weight="0.5",
        ),
        201,
    )
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/lines",
            temp_name="Yangi o'yinchoq",
            url="https://detail.1688.com/offer/1.html",
            variant="qizil × M",
            ordered_qty=50,
            unit_weight="1.5",
        ),
        201,
    )
    assert lines_by(det)["Mashina"]["shortage"] == 2  # kamomad
    assert lines_by(det)["Yangi o'yinchoq"]["flags"] == ["cargo_missing", "not_received"]
    # Tovar: 1 000 CNY, qo'lda kurs; standart taqsimot — qiymat (narx yo'q → dona, "base_fallback").
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="goods",
            amount="1480",
            currency="CNY",
            rate_mode="manual",
            rate="1800",
        ),
        201,
    )
    [goods] = det["components"]
    assert goods["allocation"] == "value" and D(goods["applied_rate"]) == 1800
    assert D(goods["amount_uzs"]) == D(1480 * 1800)
    car = lines_by(det)["Mashina"]
    assert D(car["cost"]["total"]) == D(1480 * 1800) * 98 / 148  # dona bo'yicha (98 + 50)
    assert "cargo_missing" in car["flags"] and "base_fallback" in car["flags"]
    assert D(det["purchase"]["total"]) == D(1480 * 1800)

    # Sotuv va hisob: tannarx kargosiz.
    a.sale(w.ids["sku"], d(10, 5))
    ok(send(w, "PATCH", f"purchases/{pid}", dates={"received": "2026-10-01"}))
    a.recalc(datetime.now(UTC))
    before = a.sql(
        "SELECT unit_cost FROM sale_costs sc JOIN sale_items s ON s.id = sc.sale_item_id "
        "WHERE s.sku_id = %s",
        [w.ids["sku"]],
    )[0][0]
    assert before == D(1480 * 1800) * 98 / 148 / 98

    # Kech kiritilgan kargo (20 kundan keyin): 2 000 000 so'm vazn bo'yicha — 49 kg / 75 kg.
    w.api.jobs.app.connector.reset()  # type: ignore[attr-defined]  # xotiradagi navbat: oldingi ishlar
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="cargo",
            amount="2000000",
            currency="UZS",
            paid_on="2026-10-21",
        ),
        201,
    )
    car = lines_by(det)["Mashina"]
    assert D(car["cost"]["breakdown"]["cargo"]) == (D(2_000_000) * 49 / 124).quantize(
        D("0.01")
    )  # 98×0,5 / (49 + 75)
    assert "cargo_missing" not in car["flags"]
    toy = lines_by(det)["Yangi o'yinchoq"]
    total = D(car["cost"]["breakdown"]["cargo"]) + D(toy["cost"]["breakdown"]["cargo"])
    assert total == D(2_000_000)  # tiyinigacha (F20, qoldiq eng katta qatorga)
    assert D(det["by_kind"]["cargo"]) == D(2_000_000) and det["recalc_pending"]
    # Hisob ishi commitdan keyin navbatga qo'yildi; u bajarilgach o'tgan sotuv tannarxi yangilanadi.
    calc_jobs = [j for j in w.api.queued if j["task_name"] == "calc.org"]
    assert [j["args"] for j in calc_jobs] == [{"org_id": str(a.org_id)}]
    a.recalc(datetime.now(UTC))
    after = a.sql(
        "SELECT unit_cost, changed_at, previous_cogs FROM sale_costs sc "
        "JOIN sale_items s ON s.id = sc.sale_item_id WHERE s.sku_id = %s",
        [w.ids["sku"]],
    )[0]
    assert after[0] > before and after[1] is not None and after[2] is not None
    pnl = w.get("pnl", start="2026-10-01", end="2026-10-20")
    assert pnl["recalculated"] >= 1  # P&L "qayta hisoblandi"
    assert not ok(send(w, "GET", f"purchases/{pid}"))["recalc_pending"]

    # Ro'yxatda: jonli jami, Partiya yo'li, tovar nomlari.
    listed = {x["id"]: x for x in w.get("purchases")["items"]}[pid]
    assert listed["stage"] == "received" and listed["line_count"] == 2
    assert listed["items"] == ["Mashina", "Yangi o'yinchoq"]
    assert D(listed["total"]) == D(1480 * 1800 + 2_000_000)
    assert listed["units_ordered"] == 150 and listed["units_received"] == 98
    stages = {s["stage"]: s["state"] for s in listed["timeline"]}
    assert stages["ordered"] == "done" and stages["received"] == "current"
    assert stages["paid"] == "done"  # o'tkazib yuborilgan bosqich
    assert w.get("purchases", stage=["draft"])["items"] == []
    actions = {
        r[0]
        for r in a.sql(
            "SELECT action FROM audit_log WHERE org_id = %s AND entity LIKE 'purchase%%' "
            "OR entity = 'cost_component'",
            [a.org_id],
        )
    }
    assert {"purchase.create", "purchase_line.create", "cost_component.create"} <= actions


def test_list_pages(world: World) -> None:
    """ADR-054: `limit` berilsa sahifa; berilmasa (Excel, biriktirish ro'yxati) hammasi."""
    ids = [new_purchase(world, title=f"Partiya {n}")["purchase"]["id"] for n in range(3)]
    everything = world.get("purchases")
    assert (everything["page"], everything["pages"]) == (1, 1)
    order = [x["id"] for x in everything["items"]]
    assert set(ids) <= set(order) and everything["total"] == len(order)
    seen: list[str] = []
    for n in range(1, len(order) + 1):
        got = world.get("purchases", limit=1, page=n)
        assert (got["page"], got["pages"], got["total"]) == (n, len(order), len(order))
        seen += [x["id"] for x in got["items"]]
    assert seen == order
    last = world.get("purchases", limit=2, page=999)
    assert last["page"] == last["pages"] == -(-len(order) // 2)
    assert (
        world.get("purchases", limit=1, stage=["draft"])["total"] == 3
    )  # bosqich filtri sahifalashdan oldin
    assert world.get("purchases", limit=1, stage=["closed"])["total"] == 0
    assert world.call("purchases", limit=101).status_code == 422


def test_rate_modes_cbu_and_card_charge(world: World) -> None:
    """Kurs rejimlari: CBU (to'lov sanasi; dam olish kunida oxirgi ish kuni) va "kartadan yechilgan summa":
    1 000 CNY uchun USD kartadan 142,50 $ → effektiv kurs = 142,50 × 12 600 / 1 000."""
    w = world
    pid = new_purchase(w, title="Kurslar")["purchase"]["id"]
    send(w, "POST", f"purchases/{pid}/lines", item_id=str(w.ids["item2"]), ordered_qty=10)
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="goods",
            amount="1000",
            currency="CNY",
            paid_on="2026-10-04",  # yakshanba — CBU kursi 30.09 dan (bazada shu)
        ),
        201,
    )
    cbu = det["components"][0]
    assert D(cbu["applied_rate"]) == 1750 and cbu["rate_day"] == "2026-09-30"
    assert "cbu_rate" in det["lines"][0]["flags"]
    det = ok(
        send(
            w,
            "PATCH",
            f"purchases/{pid}/components/{cbu['id']}",
            rate_mode="effective",
            charged_amount="142.50",
            charged_currency="USD",
        )
    )
    eff = det["components"][0]
    assert D(eff["applied_rate"]) == D("1795.5")  # 142,50 × 12 600 / 1 000
    assert D(det["lines"][0]["cost"]["unit_cost"]) == D("179550")
    assert "cbu_rate" not in det["lines"][0]["flags"]
    # Kurs o'zgarsa — tannarx darhol (qo'lda kurs).
    det = ok(
        send(w, "PATCH", f"purchases/{pid}/components/{eff['id']}", rate_mode="manual", rate="1810")
    )
    assert D(det["lines"][0]["cost"]["unit_cost"]) == D(181_000)


def test_allocation_targets_and_manual_shares(world: World) -> None:
    w = world
    pid = new_purchase(w)["purchase"]["id"]
    det = ok(send(w, "POST", f"purchases/{pid}/lines", temp_name="A", ordered_qty=10), 201)
    det = ok(send(w, "POST", f"purchases/{pid}/lines", temp_name="B", ordered_qty=30), 201)
    ids = {x["temp_name"]: x["id"] for x in det["lines"]}
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="packaging",
            amount="90000",
            currency="UZS",
            lines=[ids["A"]],
        ),
        201,
    )
    assert D(lines_by(det)["A"]["cost"]["total"]) == 90_000
    assert lines_by(det)["B"]["cost"]["total"] == "0.00"
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="customs",
            amount="100000",
            currency="UZS",
            allocation="manual",
            shares={ids["A"]: "1", ids["B"]: "3"},
        ),
        201,
    )
    assert D(lines_by(det)["B"]["cost"]["breakdown"]["customs"]) == 75_000
    # Komponentda tanlangan qatorni o'chirib bo'lmaydi; boshqa xarid qatori — 404.
    assert send(w, "DELETE", f"purchases/{pid}/lines/{ids['A']}").status_code == 409
    other = new_purchase(w)["purchase"]["id"]
    r = send(
        w,
        "POST",
        f"purchases/{other}/components",
        kind="other",
        amount="5",
        currency="UZS",
        lines=[ids["A"]],
    )
    assert r.status_code == 404
    # Qo'lda ulush yetishmasa — hisoblab bo'lmaydi: summasiz, sababi bilan (raqam o'ylab topilmaydi).
    comp = next(c for c in det["components"] if c["kind"] == "customs")
    det = ok(send(w, "PATCH", f"purchases/{pid}/components/{comp['id']}", shares={ids["A"]: "1"}))
    assert det["purchase"]["error"] and det["purchase"]["total"] is None
    assert all(x["cost"] is None for x in det["lines"])


def test_validation(world: World) -> None:
    w = world
    bad_dates = {"ordered": "2026-10-10", "paid": "2026-10-01"}
    assert send(w, "POST", "purchases", dates=bad_dates).status_code == 422
    assert send(w, "POST", "purchases", dates={"draft": "2026-10-01"}).status_code == 422
    assert send(w, "POST", "purchases", supplier_id=str(uuid.uuid4())).status_code == 404
    pid = new_purchase(w, dates={"shipped": "2026-10-12"})["purchase"]["id"]
    r = send(w, "PATCH", f"purchases/{pid}", dates={"arrived": "2026-10-01"})
    assert r.status_code == 422 and r.json()["code"] == "bad_stage_dates"
    assert send(w, "POST", f"purchases/{pid}/lines", ordered_qty=5).status_code == 422
    r = send(w, "POST", f"purchases/{pid}/lines", temp_name="x", ordered_qty=5, unit_price="2")
    assert r.status_code == 422  # narx valyutasiz
    assert (
        send(w, "POST", f"purchases/{pid}/lines", temp_name="x", ordered_qty=0).status_code == 422
    )
    comp = {"kind": "goods", "amount": "100", "currency": "CNY"}
    assert (
        send(w, "POST", f"purchases/{pid}/components", **comp, rate_mode="manual").status_code
        == 422
    )
    r = send(
        w,
        "POST",
        f"purchases/{pid}/components",
        **comp,
        rate_mode="effective",
        charged_amount="10",
        charged_currency="CNY",
    )
    assert r.status_code == 422
    assert (
        send(w, "POST", f"purchases/{pid}/components", **{**comp, "amount": "0"}).status_code == 422
    )
    assert send(w, "GET", f"purchases/{uuid.uuid4()}").status_code == 404


def test_permissions_warehouse_without_amounts(world: World) -> None:
    w = world
    pid = new_purchase(w, title="Ruxsat")["purchase"]["id"]
    send(
        w,
        "POST",
        f"purchases/{pid}/lines",
        temp_name="Narxli",
        ordered_qty=4,
        unit_price="10",
        currency="CNY",
    )
    send(w, "POST", f"purchases/{pid}/components", kind="goods", amount="40", currency="UZS")
    # Omborchi: ko'radi, qabul donasini kiritadi, summalarni ko'rmaydi va o'zgartirmaydi.
    det = ok(send(w, "GET", f"purchases/{pid}", "warehouse"))
    assert not det["amounts"] and det["components"] == [] and det["by_kind"] == {}
    line = det["lines"][0]
    assert line["unit_price"] is None and line["cost"] is None and det["purchase"]["total"] is None
    det = ok(send(w, "PATCH", f"purchases/{pid}/lines/{line['id']}", "warehouse", received_qty=3))
    assert det["lines"][0]["received_qty"] == 3
    r = send(w, "PATCH", f"purchases/{pid}/lines/{line['id']}", "warehouse", unit_price="9")
    assert r.status_code == 403
    r = send(
        w,
        "POST",
        f"purchases/{pid}/components",
        "warehouse",
        kind="cargo",
        amount="1",
        currency="UZS",
    )
    assert r.status_code == 403
    assert all(x["total"] is None for x in w.get("purchases", "warehouse")["items"])
    # Buxgalter: summalar bilan ko'radi, o'zgartirmaydi. Boshqa tashkilot xaridi ko'rinmaydi.
    assert ok(send(w, "GET", f"purchases/{pid}", "accountant"))["amounts"]
    assert send(w, "PATCH", f"purchases/{pid}", "accountant", title="x").status_code == 403
    assert send(w, "PATCH", f"purchases/{pid}", "manager", title="Menejer").status_code == 200
    w.api.client.cookies.set(COOKIE, w.sessions["owner"])
    foreign = w.api.client.get(f"/api/v1/orgs/{w.other}/purchases")
    assert foreign.status_code == 404


def test_expected_date_from_history_and_suppliers(world: World) -> None:
    """Kutilgan sana (F25): tashkilot tarixidagi kargo yo'li medianasi (12 → 27: 15 kun)."""
    w = world
    sup = ok(send(w, "POST", "suppliers", name="Yiwu Toys", platform="1688"), 201)
    car = ok(send(w, "POST", "carriers", name="Cargo Express", pricing="kg"), 201)
    assert sup["id"] in {s["id"] for s in w.get("suppliers")}
    assert car["id"] in {c["id"] for c in w.get("carriers")}
    new_purchase(w, dates={"shipped": "2026-08-01", "arrived": "2026-08-16"})
    det = new_purchase(
        w,
        supplier_id=sup["id"],
        carrier_id=car["id"],
        dates={"ordered": "2026-09-20", "shipped": "2026-10-12"},
    )
    assert det["purchase"]["supplier_name"] == "Yiwu Toys"
    assert det["purchase"]["carrier_name"] == "Cargo Express"
    cur = next(s for s in det["purchase"]["timeline"] if s["state"] == "current")
    assert cur["stage"] == "shipped" and cur["expected"] == "2026-10-27"


def test_copy_and_delete(world: World) -> None:
    w, a = world, world.a
    pid = new_purchase(w, title="Qayta buyurtma", dates={"ordered": "2026-10-01"})["purchase"]["id"]
    send(
        w,
        "POST",
        f"purchases/{pid}/lines",
        item_id=str(w.ids["item2"]),
        ordered_qty=20,
        received_qty=20,
        unit_price="3.5",
        currency="CNY",
        unit_weight="0.2",
    )
    send(w, "POST", f"purchases/{pid}/lines", temp_name="Ikkinchi", ordered_qty=5)
    send(w, "POST", f"purchases/{pid}/components", kind="cargo", amount="70000", currency="UZS")
    copy = ok(send(w, "POST", f"purchases/{pid}/copy"), 201)
    assert copy["purchase"]["id"] != pid and copy["purchase"]["title"] == "Qayta buyurtma"
    assert copy["purchase"]["stage"] == "draft" and copy["components"] == []
    assert [
        (x["item_name"] or x["temp_name"], x["ordered_qty"], x["received_qty"])
        for x in copy["lines"]
    ] == [
        ("Qo'g'irchoq", 20, None),
        ("Ikkinchi", 5, None),
    ]
    assert D(copy["lines"][0]["unit_price"]) == D("3.5")
    # Xarid o'chirilsa: lotlari ketadi, tovari qayta hisoblanadi.
    a.recalc(datetime.now(UTC))
    lots_of = "SELECT count(*) FROM lots WHERE item_id = %s"
    assert a.sql(lots_of, [w.ids["item2"]])[0][0] >= 1
    assert send(w, "DELETE", f"purchases/{copy['purchase']['id']}").status_code == 204
    assert send(w, "DELETE", f"purchases/{pid}").status_code == 204
    queued = a.sql(
        "SELECT kind FROM recalc_queue WHERE org_id = %s AND ref_id = %s",
        [a.org_id, w.ids["item2"]],
    )
    assert queued == [("item",)]
    a.recalc(datetime.now(UTC))
    remaining = a.sql(
        "SELECT count(*) FROM lots l JOIN purchase_lines pl ON pl.id = l.purchase_line_id "
        "WHERE pl.purchase_id = %s",
        [pid],
    )
    assert remaining[0][0] == 0
    assert send(w, "GET", f"purchases/{pid}").status_code == 404


def test_sku_picker_lists_every_sku_and_lines_from_skus(world: World) -> None:
    """Tanlov hamma SKU'ni ko'rsatadi (tovarsiz, arxivlangan, bloklangan ham); SKU tanlansa tovar yaratiladi,
    bor bo'lsa ishlatiladi; ommaviy qo'shish — hammasi yoki hech biri."""
    w, a = world, world.a
    product = a.insert("mp_products", shop_id=a.shop_id, external_id=7_001, title="Ko'ylak")
    a_sku = a.insert(
        "mp_skus",
        shop_id=a.shop_id,
        external_id=7_101,
        product_id=product,
        sku_code="Ko'ylak-Qora-M",
        status="ACTIVE",
        qty_active=5,
    )
    archived = a.insert(
        "mp_skus",
        shop_id=a.shop_id,
        external_id=7_102,
        product_id=product,
        sku_code="Ko'ylak-Oq-L",
        status="ARCHIVED",
    )
    blocked = a.insert(
        "mp_skus",
        shop_id=a.shop_id,
        external_id=7_103,
        sku_code="Bloklangan",
        status="BLOCKED",
    )
    orphan = a.insert("items", name="SKU'siz tovar")
    rows = ok(send(w, "GET", "sku-picker"))
    assert rows["truncated"] is False
    by_sku = {r["sku_id"]: r for r in rows["rows"] if r["sku_id"]}
    assert {str(a_sku), str(archived), str(blocked), str(w.ids["sku"])} <= set(by_sku)
    assert (
        by_sku[str(archived)]["status"] == "ARCHIVED" and by_sku[str(archived)]["item_id"] is None
    )
    assert by_sku[str(a_sku)]["product_title"] == "Ko'ylak" and by_sku[str(a_sku)]["stock"] == 5
    assert by_sku[str(w.ids["sku"])]["item_id"] == str(w.ids["item"])
    assert any(r["sku_id"] is None and r["item_id"] == str(orphan) for r in rows["rows"])
    order = [r["sku_id"] for r in rows["rows"]]
    assert order.index(str(a_sku)) < order.index(str(archived))  # qoldig'i borlar oldinda
    assert send(w, "GET", "sku-picker", role="accountant").status_code == 403

    pid = new_purchase(w, title="SKU'dan")["purchase"]["id"]
    items_before = a.sql("SELECT count(*) FROM items WHERE org_id = %s", [a.org_id])[0][0]
    det = ok(send(w, "POST", f"purchases/{pid}/lines", sku_id=str(archived), ordered_qty=10), 201)
    made = a.sql(
        "SELECT item_id, (SELECT name FROM items i WHERE i.id = k.item_id) FROM mp_skus k WHERE id = %s",
        [archived],
    )[0]
    assert (
        made[0] is not None and made[1] == "Ko'ylak"
    )  # tovar nomi — mahsulot (Uzum kartochkasi) nomi
    assert det["lines"][0]["item_id"] == str(made[0])
    # Tovari bor SKU — o'sha tovar, yangisi yaratilmaydi.
    det = ok(
        send(w, "POST", f"purchases/{pid}/lines", sku_id=str(w.ids["sku"]), ordered_qty=3), 201
    )
    assert det["lines"][1]["item_id"] == str(w.ids["item"])
    assert (
        a.sql("SELECT count(*) FROM items WHERE org_id = %s", [a.org_id])[0][0] == items_before + 1
    )

    # Ommaviy: ikkita SKU bitta so'rovda (har SKU — alohida tovar).
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/lines/bulk",
            lines=[
                {"sku_id": str(a_sku), "ordered_qty": 4, "variant": "M"},
                {"sku_id": str(blocked), "ordered_qty": 6},
            ],
        ),
        201,
    )
    assert len(det["lines"]) == 4
    name_of = "SELECT name FROM items WHERE id = (SELECT item_id FROM mp_skus WHERE id = %s)"
    assert a.sql(name_of, [a_sku])[0][0] == "Ko'ylak"
    assert a.sql(name_of, [blocked])[0][0] == "Bloklangan"  # mahsulotsiz SKU — SKU nomi
    # Hammasi yoki hech biri: oxirgisi noto'g'ri — oldingilari ham yozilmaydi.
    r = send(
        w,
        "POST",
        f"purchases/{pid}/lines/bulk",
        lines=[
            {"temp_name": "Yangi", "ordered_qty": 1},
            {"sku_id": str(uuid.uuid4()), "ordered_qty": 1},
        ],
    )
    assert r.status_code == 404
    assert len(ok(send(w, "GET", f"purchases/{pid}"))["lines"]) == 4
    # Tekshiruvlar: ikkalasi birga, bo'sh ro'yxat, boshqa tashkilot SKU'si.
    both = {"sku_id": str(a_sku), "item_id": str(w.ids["item"]), "ordered_qty": 1}
    assert send(w, "POST", f"purchases/{pid}/lines", **both).status_code == 422
    assert send(w, "POST", f"purchases/{pid}/lines/bulk", lines=[]).status_code == 422
    # Tahrirda SKU tanlansa — qator tovari almashadi.
    line = det["lines"][0]["id"]
    det = ok(send(w, "PATCH", f"purchases/{pid}/lines/{line}", sku_id=str(w.ids["sku2"])))
    assert next(x for x in det["lines"] if x["id"] == line)["item_id"] == str(w.ids["item2"])


def test_missing_rate_date_queues_cbu_archive_job(world: World) -> None:
    """To'lov sanasi kursi bazada yo'q bo'lsa — xarid saqlanganda `fx.cbu` ishi `since` bilan qo'yiladi; kurs
    yetarli bo'lsa — yo'q."""
    w = world
    jobs = w.api.jobs.app.connector.jobs  # type: ignore[attr-defined]

    def fx_jobs() -> list[dict[str, Any]]:
        return [j["args"] for j in jobs.values() if j["task_name"] == "fx.cbu"]

    pid = new_purchase(w, title="Kurs yo'q", dates={"ordered": "2026-08-01"})["purchase"]["id"]
    comp = {"kind": "goods", "amount": "830", "currency": "CNY"}
    ok(send(w, "POST", f"purchases/{pid}/components", **comp, paid_on="2026-09-30"), 201)
    assert fx_jobs() == []  # 2026-09-30 kursi bor (fixture)
    ok(send(w, "POST", f"purchases/{pid}/components", **comp, paid_on="2026-08-01"), 201)
    assert fx_jobs() == [{"since": "2026-08-01"}]
    ok(
        send(w, "POST", f"purchases/{pid}/components", kind="cargo", amount="5", currency="UZS"),
        201,
    )
    assert fx_jobs() == [
        {"since": "2026-08-01"}
    ]  # so'm kurs talab qilmaydi; navbatda allaqachon bor


def test_market_rate_fallback_is_used_and_flagged(world: World) -> None:
    """CBU kursi bo'lmagan kunni zaxira bozor kursi yopadi (ADR-045): tannarx hisoblanadi, kurs manbasi va lotdagi
    `market_rate` belgisi ko'rinadi, CBU kursi kech bo'lsa u ustun; kurs yetarli bo'lgani uchun arxiv ishi qo'yilmaydi."""
    w, a = world, world.a
    jobs = w.api.jobs.app.connector.jobs  # type: ignore[attr-defined]
    before = len([j for j in jobs.values() if j["task_name"] == "fx.cbu"])
    a.sql(
        "INSERT INTO fx_rates (day, currency, source, rate) VALUES "
        "('2026-07-01', 'CNY', 'market', 1650.5) ON CONFLICT DO NOTHING"
    )
    pid = new_purchase(w, title="Bozor kursi", dates={"ordered": "2026-07-01"})["purchase"]["id"]
    ok(send(w, "POST", f"purchases/{pid}/lines", item_id=str(w.ids["item"]), ordered_qty=10), 201)
    det = ok(
        send(
            w,
            "POST",
            f"purchases/{pid}/components",
            kind="goods",
            amount="100",
            currency="CNY",
            paid_on="2026-07-01",
        ),
        201,
    )
    comp = det["components"][0]
    assert comp["error"] is None and comp["rate_source"] == "market"
    assert D(comp["applied_rate"]) == D("1650.5") and comp["amount_uzs"] is not None
    assert "market_rate" in det["lines"][0]["flags"] and "cbu_rate" not in det["lines"][0]["flags"]
    assert len([j for j in jobs.values() if j["task_name"] == "fx.cbu"]) == before
    # Shu kunda CBU kursi ham bo'lsa — u ustun va belgi chiqmaydi.
    a.sql(
        "INSERT INTO fx_rates (day, currency, source, rate) VALUES "
        "('2026-07-01', 'CNY', 'cbu', 1790) ON CONFLICT DO NOTHING"
    )
    det = ok(send(w, "GET", f"purchases/{pid}"))
    assert det["components"][0]["rate_source"] == "cbu"
    assert "market_rate" not in det["lines"][0]["flags"]


# --- Ta'minot qayta loyihasi (ADR-061): tez xarid, uch holat ---


def test_quick_purchase_one_request_in_transit(world: World) -> None:
    """TM2 (ADR-061 §2): tovarlar, jami to'landi, kurs va trek — bitta so'rovda; darhol "Yo'lda"; jami qator
    summalariga mutanosib (farq — ichki yetkazish), F20."""
    w = world
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[
                {"sku_id": str(w.ids["sku"]), "qty": 50, "line_sum": "700"},
                {"sku_id": str(w.ids["sku2"]), "qty": 30, "line_sum": "80"},
            ],
            paid_amount="800",
            currency="CNY",
            rate_mode="manual",
            rate="1800",
            ordered_on="2026-10-01",
            track_no="  YT123  ",
        ),
        201,
    )
    p = det["purchase"]
    assert p["state"] == "in_transit" and p["track_no"] == "YT123" and not p["on_hand"]
    assert [x["mark"] for x in p["path"]] == ["current", "upcoming", "upcoming"]
    assert p["path"][0]["on"] == "2026-10-01"
    assert D(p["total"]) == D(800 * 1800)
    rows = lines_by(det)
    assert rows["Mashina"]["sku_id"] == str(w.ids["sku"])
    assert D(rows["Mashina"]["line_sum"]) == D(700) and rows["Mashina"]["good_qty"] == 50
    assert D(rows["Mashina"]["cost"]["total"]) == (D(800 * 1800) * 700 / 780).quantize(D("0.01"))
    assert "no_line_sums" not in rows["Mashina"]["flags"]
    assert "cargo_missing" in rows["Mashina"]["flags"]  # kargo puli hali kiritilmagan — taxminiy
    (goods,) = det["components"]
    assert goods["kind"] == "goods" and goods["allocation"] == "line_sum"
    assert goods["paid_on"] == "2026-10-01" and D(goods["applied_rate"]) == D(1800)
    # Ro'yxat holat bo'yicha filtrlanadi.
    ids = {x["id"] for x in w.get("purchases", state="in_transit")["items"]}
    assert p["id"] in ids
    assert p["id"] not in {x["id"] for x in w.get("purchases", state="in_stock")["items"]}
    # Trek va "Tovar qo'limda" keyin ham o'zgaradi.
    det = ok(send(w, "PATCH", f"purchases/{p['id']}", track_no="YT999", on_hand=True))
    assert det["purchase"]["track_no"] == "YT999" and det["purchase"]["on_hand"]
    assert "cargo_missing" not in lines_by(det)["Mashina"]["flags"]


def test_quick_purchase_on_hand_is_counted_and_cbu_rate(world: World) -> None:
    """ "Tovar qo'limda" (mahalliy xarid): darhol sanalgan — "Omborimda", kargo kutilmaydi. Qator summasi yo'q —
    dona bo'yicha, eslatma (taxminiy emas). CNY — buyurtma kunidagi Markaziy bank kursi."""
    w = world
    det = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": str(w.ids["sku"]), "qty": 30}, {"temp_name": "Yangi", "qty": 10}],
            paid_amount="400000",
            currency="UZS",
            ordered_on="2026-10-05",
            on_hand=True,
        ),
        201,
    )
    p = det["purchase"]
    assert p["state"] == "in_stock" and p["on_hand"] and p["units_received"] == 40
    assert [x["mark"] for x in p["path"]] == ["done", "current", "upcoming"]
    rows = lines_by(det)
    assert D(rows["Mashina"]["cost"]["unit_cost"]) == D(10_000)
    assert rows["Mashina"]["flags"] == ["no_line_sums"]
    cny = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"item_id": str(w.ids["item"]), "qty": 10}],
            paid_amount="100",
            ordered_on="2026-10-03",
        ),
        201,
    )
    assert D(cny["purchase"]["total"]) == D(
        175_000
    )  # 30-sentabr kursi 1 750 (dam olish kuni — oxirgi ish kuni)
    assert cny["lines"][0]["sku_id"] is None
    assert set(cny["lines"][0]["flags"]) == {"cargo_missing", "not_received", "cbu_rate"}


def test_quick_purchase_validation_and_permissions(world: World) -> None:
    w = world
    line = {"sku_id": str(w.ids["sku"]), "qty": 5}
    bad = [
        {"lines": []},
        {"lines": [{"qty": 5}], "paid_amount": "10", "currency": "UZS"},  # tovar ham, nom ham yo'q
        {"lines": [line], "paid_amount": "10", "rate_mode": "manual"},  # qo'lda kurs yo'q
        {"lines": [{**line, "line_sum": "11"}], "paid_amount": "10", "currency": "UZS"},
        {"lines": [{**line, "item_id": str(w.ids["item"])}]},  # item_id va sku_id birga
        {"lines": [line], "supplier_id": str(uuid.uuid4())},
    ]
    before = w.get("purchases")["total"]
    for body in bad:
        r = send(w, "POST", "purchases/quick", **body)
        assert r.status_code in (404, 422), (body, r.text)
    assert w.get("purchases")["total"] == before  # hammasi yoki hech biri
    # Omborchi: summasiz yaratadi; summa bilan — 403.
    r = send(w, "POST", "purchases/quick", "warehouse", lines=[line], paid_amount="5")
    assert r.status_code == 403
    det = ok(send(w, "POST", "purchases/quick", "warehouse", lines=[line]), 201)
    assert det["components"] == [] and det["purchase"]["state"] == "in_transit"
    assert send(w, "POST", "purchases/quick", "accountant", lines=[line]).status_code == 403


def test_old_stages_map_to_three_states(world: World) -> None:
    """ADR-061 §11: eski bosqichli xaridlar o'chmaydi — holat sanalardan; "Yo'lda" muddati tarixdan (F25)."""
    w = world
    old = new_purchase(w, dates={"ordered": "2026-07-01", "arrived": "2026-07-20"})["purchase"]
    assert old["state"] == "in_transit" and old["stage"] == "arrived"
    done = new_purchase(w, dates={"ordered": "2026-07-01", "received": "2026-07-21"})["purchase"]
    assert done["state"] == "in_stock" and done["path"][1]["on"] == "2026-07-21"
    sent = new_purchase(
        w, dates={"ordered": "2026-07-01", "received": "2026-07-21", "closed": "2026-07-30"}
    )["purchase"]
    assert sent["state"] == "at_uzum" and [x["mark"] for x in sent["path"]] == [
        "done",
        "done",
        "current",
    ]
    fresh = ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"temp_name": "Kutilmoqda", "qty": 1}],
            ordered_on="2026-10-10",
        ),
        201,
    )["purchase"]
    assert fresh["path"][0]["expected"] is not None  # tarixda buyurtma → sanash bor (20 kun)

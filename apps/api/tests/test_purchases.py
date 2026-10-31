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

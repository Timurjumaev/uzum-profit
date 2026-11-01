"""B4.12 ``/opening`` — boshlang'ich holat (F41, ADR-033), haqiqiy PostgreSQL bilan: jadval (tovarlar va tovarsiz
SKU'lar, tushum tartibi, qoldiq taklifi), saqlash (tovarsiz SKU uchun tovar yaratiladi), tannarx dvigatelida natija
(tarixiy sotuv lotni yemaydi, boshlang'ich qoldiq — birinchi lot, oldingi lot ishlatilmaydi), ombor qiymati, unit
kalkulyator, ruxsatlar, tekshiruvlar, audit, o'chirish.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from mptools import mp_api
from sellerfake import TOKEN, A, create_account
from test_calc import Org
from test_reports import World
from test_stock_moves import ok, send
from upapi import calc
from upapi.auth.deps import COOKIE
from upapi.reports.common import today

D = Decimal
TODAY = today()


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


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
        w.ids["item"], w.ids["sku"] = a.item("Soat")
        a.sql("UPDATE mp_skus SET qty_active = 100, qty_fbs = 20 WHERE id = %s", [w.ids["sku"]])
        w.ids["lone"] = a.insert(
            "mp_skus", shop_id=a.shop_id, external_id=900, sku_code="Lone-1", qty_active=7
        )
        w.ids["other_item"] = Org(db, other.org_id, other.shops[A]).item("Begona")[0]
        for role in ("owner", "manager", "accountant", "warehouse"):
            phone = api.login()
            user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
            api.admin(
                "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, %s)",
                [a.org_id, user, role],
            )
            w.sessions[role] = api.client.cookies[COOKIE]
        yield w


def rows(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["item_id"] or r["sku_id"]: r for r in body["rows"]}


def recalc(w: World) -> None:
    assert w.a.recalc(datetime.now(UTC)).errors == {}


def test_read_lists_items_and_unlinked_skus(world: World) -> None:
    w = world
    body = ok(send(w, "GET", "opening"))
    assert body["start_on"] is None and body["as_of"] == TODAY.isoformat()
    assert body["stock_source"] == "current" and body["coverage"] is None  # tushum yo'q
    got = rows(body)
    item, lone = got[str(w.ids["item"])], got[str(w.ids["lone"])]
    assert item["skus"] == ["Soat"] and item["uzum_suggested"] == 120 and item["prices"] == []
    assert item["uzum_qty"] is None and item["lots_after"] == 0
    assert lone["item_id"] is None and lone["uzum_suggested"] == 7 and lone["name"] == "Lone-1"
    assert str(w.ids["other_item"]) not in got  # boshqa tashkilot
    # O'tgan sana — oldingi kun snapshoti; snapshot yo'q — noma'lum.
    w.a.insert("sku_daily", sku_id=w.ids["sku"], day=day(-11), qty_active=50, qty_fbs=5)
    past = ok(send(w, "GET", f"opening?start={day(-10).isoformat()}"))
    assert past["stock_source"] == "snapshot" and past["as_of"] == day(-10).isoformat()
    assert rows(past)[str(w.ids["item"])]["uzum_suggested"] == 55
    assert rows(past)[str(w.ids["lone"])]["uzum_suggested"] is None
    assert ok(send(w, "GET", f"opening?start={day(-30).isoformat()}"))["stock_source"] == "none"


def test_opening_costs_history_and_feeds_fifo(world: World) -> None:
    w, a = world, world.a
    item, sku = w.ids["item"], w.ids["sku"]
    old = a.purchase(day(-40), ordered_on=day(-50))  # boshlashdan oldin — qoldiqqa kirgan
    a.component(old, "goods", 9_000 * 50)
    a.line(old, item, 50)
    new = a.purchase(day(-9), ordered_on=day(-20))  # boshlashdan keyin (kargosiz — lot belgisi)
    a.component(new, "goods", 13_000 * 200)
    a.line(new, item, 200)
    a.run(lambda conn: calc.request_full(conn, a.org_id))
    history = a.sale(sku, day(-20), 30)
    after = [a.sale(sku, day(-9 + i), 30) for i in range(5)]  # 150 dona: 120 qoldiqdan, 30 yangidan
    recalc(w)
    # Boshlang'ich holatsiz: tarixiy sotuv eski partiyadan (lot bilan).
    assert a.costs()[history][3][0]["lot"] is not None

    body = ok(
        send(
            w,
            "PUT",
            "opening",
            start_on=day(-10).isoformat(),
            rows=[
                {"item_id": str(item), "uzum_qty": 110, "own_qty": 10,
                 "prices": [{"valid_from": None, "unit_cost": "11000"},
                            {"valid_from": day(-30).isoformat(), "unit_cost": "12000"}]},
                {"sku_id": str(w.ids["lone"]), "uzum_qty": 7, "prices": [{"unit_cost": "5000"}]},
            ],
        )
    )  # fmt: skip
    assert body["start_on"] == day(-10).isoformat()
    got = rows(body)
    mine = got[str(item)]
    assert (mine["uzum_qty"], mine["own_qty"]) == (110, 10)
    assert [p["unit_cost"] for p in mine["prices"]] == ["11000.00", "12000.00"]
    assert (mine["lots_before"], mine["lots_after"]) == (1, 1)
    created = [r for r in body["rows"] if r["skus"] == ["Lone-1"]]
    assert len(created) == 1 and created[0]["item_id"] is not None  # tovar yaratildi va bog'landi
    assert str(w.ids["lone"]) not in got
    assert {k for k, *_ in a.queue()} >= {"item"}
    recalc(w)

    costs = a.costs()
    cogs, _unit, flags, allocations, *_ = costs[history]
    assert flags == ["historical"] and cogs == D(30 * 12_000)  # -20 kun: 12 000 davri
    assert allocations == [{"lot": None, "qty": 30, "unit": "12000.000000"}]
    took: dict[str | None, int] = {}
    for sale in after:
        assert not {"early_sale", "historical", "lot_shortage"} & set(costs[sale][2])
        for x in costs[sale][3]:
            took[x["lot"]] = took.get(x["lot"], 0) + x["qty"]
    assert took.pop("opening") == 120 and list(took.values()) == [30]
    assert sum(costs[s][0] for s in after) == D(120 * 12_000 + 30 * 13_000)
    # Bekor qilinmagan: qayta hisob "qayta hisoblandi" belgisini qo'yadi (avval erta sotuv edi).
    assert costs[history][4] is not None

    audit = {x[0] for x in a.sql("SELECT action FROM audit_log WHERE org_id = %s", [w.org_id])}
    assert {"opening.start", "opening.item", "item.create"} <= audit
    # Takroriy bir xil saqlash — qayta hisob so'rovi qo'yilmaydi.
    ok(send(w, "PUT", "opening", start_on=day(-10).isoformat(), rows=[
        {"item_id": str(item), "uzum_qty": 110, "own_qty": 10,
         "prices": [{"valid_from": day(-30).isoformat(), "unit_cost": "12000"},
                    {"valid_from": None, "unit_cost": "11000.00"}]}]))  # fmt: skip
    assert a.queue() == []

    # Unit kalkulyator — oxirgi partiya narxi (narx qo'yish uchun).
    calc_ = w.get(f"skus/{sku}", start=day(-10).isoformat(), end=TODAY.isoformat())["calc"]
    assert calc_["sources"]["unit_cost"] == "last_lot" and D(calc_["unit_cost"]) == D(13_000)


def test_stock_value_falls_back_to_opening_price(world: World) -> None:
    w = world
    lone_item = next(
        r["item_id"] for r in ok(send(w, "GET", "opening"))["rows"] if r["skus"] == ["Lone-1"]
    )
    inv = ok(send(w, "GET", f"inventory?as_of={TODAY.isoformat()}"))
    row = next(r for r in inv["items"] if r["sku_id"] == str(w.ids["lone"]))
    assert lone_item and D(row["unit_cost"]) == D(5_000)  # partiya yo'q — boshlang'ich narx
    frozen = {k: D(v) for k, v in inv["totals"]["frozen_money"].items()}
    assert frozen["fbo"] >= D(7 * 5_000)


def test_permissions_and_validation(world: World) -> None:
    w = world
    assert send(w, "GET", "opening", role="accountant").status_code == 200
    assert send(w, "GET", "opening", role="warehouse").status_code == 403
    assert send(w, "PUT", "opening", role="accountant", start_on=None).status_code == 403
    tomorrow = day(1).isoformat()
    assert send(w, "PUT", "opening", start_on=tomorrow).status_code == 422
    assert send(w, "GET", f"opening?start={tomorrow}").status_code == 422
    start = day(-10).isoformat()
    both = {"item_id": str(w.ids["item"]), "sku_id": str(w.ids["sku"])}
    assert send(w, "PUT", "opening", start_on=start, rows=[both]).status_code == 422
    dup = {"item_id": str(w.ids["item"]), "prices": [{"unit_cost": "1"}, {"unit_cost": "2"}]}
    assert send(w, "PUT", "opening", start_on=start, rows=[dup]).status_code == 422
    neg = {"item_id": str(w.ids["item"]), "uzum_qty": -1}
    assert send(w, "PUT", "opening", start_on=start, rows=[neg]).status_code == 422
    foreign = {"item_id": str(w.ids["other_item"]), "prices": [{"unit_cost": "1"}]}
    assert send(w, "PUT", "opening", start_on=start, rows=[foreign]).status_code == 404
    unknown = {"sku_id": str(w.ids["other_item"]), "prices": [{"unit_cost": "1"}]}
    assert send(w, "PUT", "opening", start_on=start, rows=[unknown]).status_code == 404
    twice = {"item_id": str(w.ids["item"]), "prices": [{"unit_cost": "1"}]}
    assert send(w, "PUT", "opening", start_on=start, rows=[twice, twice]).status_code == 422


def test_turn_off_restores_lot_costing_and_clears_row(world: World) -> None:
    w, a = world, world.a
    item = w.ids["item"]
    body = ok(send(w, "PUT", "opening", start_on=None, rows=[{"item_id": str(item)}]))
    assert body["start_on"] is None
    mine = rows(body)[str(item)]
    assert mine["prices"] == [] and mine["uzum_qty"] is None  # bo'sh qator o'chirildi
    recalc(w)
    flags = {f for _, _, fl, *_ in a.costs().values() for f in fl}
    assert "historical" not in flags

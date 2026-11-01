"""B4.7 ``/stock-moves`` va ombor joylari (haqiqiy PostgreSQL): hisobdan chiqarish va inventarizatsiya tuzatishi,
o'z omborim qoldig'iga ta'siri (``/inventory`` joylari, F29 qiymati), tannarx dvigatelida lotdan chiqim (F21) va
qayta hisob so'rovi, ruxsatlar (omborchi yoza oladi, buxgalter — faqat o'qiydi), tekshiruvlar, audit, boshqa tashkilot.
"""

from __future__ import annotations

import uuid
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
from upapi import calc
from upapi.auth.deps import COOKIE

D = Decimal
TODAY = datetime.now(UTC).date()


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
        w.ids["item"], w.ids["sku"] = a.item("Mashina")
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


def send(w: World, method: str, path: str, role: str = "owner", **json: Any) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.request(
        method,
        f"/api/v1/orgs/{w.org_id}/{path}",
        json=json if json else ({} if method == "POST" else None),
        headers={"X-Requested-With": "fetch"},
    )


def ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, r.text
    return r.json() if r.content else None


def row(w: World) -> dict[str, Any]:
    body = ok(send(w, "GET", f"inventory?as_of={TODAY.isoformat()}"))
    return next(r for r in body["items"] if r["sku_id"] == str(w.ids["sku"]))


def test_locations_follow_purchase_stage(world: World) -> None:
    """Xarid bosqichi → joy: Xitoyda / yo'lda / o'z omborim; Uzumga yuborilgan — FBO qoldig'ida (joylarda yo'q)."""
    w, a = world, world.a
    item = w.ids["item"]
    for stage, qty in [
        ({"ordered_on": day(-30)}, 10),  # Xitoyda
        ({"ordered_on": day(-30), "paid_on": day(-29), "cn_warehouse_on": day(-20)}, 20),  # Xitoyda
        ({"ordered_on": day(-30), "shipped_on": day(-10)}, 40),  # yo'lda
        ({"ordered_on": day(-30), "shipped_on": day(-10), "arrived_on": day(-2)}, 80),  # yo'lda
        ({"ordered_on": day(-30), "received_on": day(-1)}, 160),  # o'z omborim
        ({"ordered_on": day(-60), "received_on": day(-40), "sent_to_uzum_on": day(-35)}, 320),
        ({}, 640),  # qoralama — hali buyurtma berilmagan
    ]:
        p = a.insert("purchases", **stage)
        a.line(p, item, qty, received=qty if "received_on" in stage else None)
        a.component(p, "goods", qty * 1_000)
    a.run(lambda conn: calc.request_full(conn, a.org_id))
    assert a.recalc(datetime.now(UTC)).errors == {}
    r = row(w)
    assert (r["locations"]["china"], r["locations"]["road"], r["locations"]["own"]) == (
        30,
        120,
        160,
    )
    assert r["in_transit"] == 150  # Xitoyda + yo'lda
    body = ok(send(w, "GET", f"inventory?as_of={TODAY.isoformat()}"))
    frozen = {k: D(v) for k, v in body["totals"]["frozen_money"].items()}
    # Qiymat — qatorning lot tannarxi bilan (komponent faqat tovar: 1 000 so'm/dona).
    assert (frozen["china"], frozen["road"], frozen["own"]) == (D(30_000), D(120_000), D(160_000))
    assert body["totals"]["units"]["own"] == 160


def test_writeoff_and_adjust_change_own_stock_and_audit(world: World) -> None:
    w = world
    item = str(w.ids["item"])
    before = row(w)["locations"]["own"]
    move = ok(
        send(w, "POST", "stock-moves", item_id=item, kind="writeoff", qty=5, day=day(-1).isoformat(),
             note="Qabulda brak"),
        201,
    )  # fmt: skip
    assert move["kind"] == "writeoff" and move["qty"] == 5 and move["note"] == "Qabulda brak"
    assert row(w)["locations"]["own"] == before - 5
    # Manfiy tuzatish (inventarizatsiyada kam chiqdi) — kamaytiradi, musbat — oshiradi.
    minus = ok(
        send(w, "POST", "stock-moves", item_id=item, kind="adjust", qty=-3, day=day(0).isoformat()),
        201,
    )
    assert row(w)["locations"]["own"] == before - 8
    ok(
        send(w, "POST", "stock-moves", item_id=item, kind="adjust", qty=10, day=day(0).isoformat()),
        201,
    )
    assert row(w)["locations"]["own"] == before + 2
    listed = ok(send(w, "GET", f"items/{item}/stock-moves"))["items"]
    assert [x["qty"] for x in listed] == [10, -3, 5]  # kun va yaratilish bo'yicha yangisi birinchi
    assert {x["id"] for x in listed} >= {move["id"], minus["id"]}
    # Qayta hisob so'rovi shu tranzaksiyada qo'yilgan (tovar bo'yicha), audit yozilgan.
    queued = w.a.sql("SELECT kind, ref_id FROM recalc_queue WHERE org_id = %s", [w.org_id])
    assert ("item", uuid.UUID(item)) in {(k, r) for k, r in queued}
    actions = {x[0] for x in w.a.sql("SELECT action FROM audit_log WHERE org_id = %s", [w.org_id])}
    assert "stock_move.create" in actions
    # O'chirish (xato yozuvni qaytarish): qoldiq tiklanadi.
    ok(send(w, "DELETE", f"stock-moves/{move['id']}"), 204)
    assert row(w)["locations"]["own"] == before + 7
    assert "stock_move.delete" in {
        x[0] for x in w.a.sql("SELECT action FROM audit_log WHERE org_id = %s", [w.org_id])
    }
    assert send(w, "DELETE", f"stock-moves/{move['id']}").status_code == 404


def test_own_stock_never_negative(world: World) -> None:
    w = world
    ok(
        send(
            w,
            "POST",
            "stock-moves",
            item_id=str(w.ids["item"]),
            kind="writeoff",
            qty=100_000,
            day=day(0).isoformat(),
        ),
        201,
    )
    assert row(w)["locations"]["own"] == 0


def test_validation(world: World) -> None:
    w, item = world, str(world.ids["item"])
    today = day(0).isoformat()
    bad = [
        {"kind": "writeoff", "qty": 0},
        {"kind": "writeoff", "qty": -2},
        {"kind": "adjust", "qty": 0},
        {"kind": "receive", "qty": 3},
        {"kind": "writeoff", "qty": 1, "note": "x" * 501},
    ]
    for extra in bad:
        r = send(w, "POST", "stock-moves", item_id=item, day=today, **extra)
        assert r.status_code == 422, (extra, r.text)
    future = send(
        w, "POST", "stock-moves", item_id=item, kind="writeoff", qty=1, day=day(3).isoformat()
    )
    assert future.status_code == 422 and future.json()["code"] == "bad_day"
    missing = send(
        w, "POST", "stock-moves", item_id=str(uuid.uuid4()), kind="writeoff", qty=1, day=today
    )
    assert missing.status_code == 404 and missing.json()["code"] == "item_not_found"
    # Boshqa tashkilot tovari ko'rinmaydi (RLS): 404.
    foreign = send(
        w,
        "POST",
        "stock-moves",
        item_id=str(w.ids["other_item"]),
        kind="writeoff",
        qty=1,
        day=today,
    )
    assert foreign.status_code == 404
    # Qator boshqa tovarniki bo'lsa — rad.
    other_line = w.a.line(w.a.purchase(ordered_on=day(-5)), w.a.item("Boshqa")[0], 1)
    mismatch = send(
        w,
        "POST",
        "stock-moves",
        item_id=item,
        kind="writeoff",
        qty=1,
        day=today,
        purchase_line_id=str(other_line),
    )
    assert mismatch.status_code == 422 and mismatch.json()["code"] == "line_item_mismatch"
    ghost = send(
        w,
        "POST",
        "stock-moves",
        item_id=item,
        kind="writeoff",
        qty=1,
        day=today,
        purchase_line_id=str(uuid.uuid4()),
    )
    assert ghost.status_code == 404 and ghost.json()["code"] == "purchase_line_not_found"


def test_roles(world: World) -> None:
    w, item = world, str(world.ids["item"])
    body = {"item_id": item, "kind": "adjust", "qty": 1, "day": day(0).isoformat()}
    for role in ("owner", "manager", "warehouse"):  # omborchi ham yozadi (summa yo'q)
        assert send(w, "POST", "stock-moves", role=role, **body).status_code == 201
    assert send(w, "POST", "stock-moves", role="accountant", **body).status_code == 403
    for role in ("owner", "manager", "accountant", "warehouse"):
        assert send(w, "GET", f"items/{item}/stock-moves", role=role).status_code == 200
    assert send(w, "DELETE", f"stock-moves/{uuid.uuid4()}", role="accountant").status_code == 403


def test_writeoff_reduces_cost_lots(world: World) -> None:
    """Hisobdan chiqarish F21 da lotdan chiqim: keyingi sotuv qimmatroq lotdan (FIFO) hisoblanadi."""
    w, a = world, world.a
    item, sku = a.item("Chiroq")
    cheap = a.purchase(day(-40), ordered_on=day(-45))
    a.line(cheap, item, 10)
    a.component(cheap, "goods", 10 * 1_000)
    dear = a.purchase(day(-30), ordered_on=day(-35))
    a.line(dear, item, 10)
    a.component(dear, "goods", 10 * 2_000)
    sale = a.sale(sku, day(-1), 1)
    a.run(lambda conn: calc.request_full(conn, a.org_id))
    a.recalc(datetime.now(UTC))
    cost = lambda: a.sql("SELECT unit_cost FROM sale_costs WHERE sale_item_id = %s", [sale])[0][0]  # noqa: E731
    assert D(cost()) == 1_000  # eng eski lot
    ok(
        send(
            w,
            "POST",
            "stock-moves",
            item_id=str(item),
            kind="writeoff",
            qty=10,
            day=day(-20).isoformat(),
        ),
        201,
    )
    a.recalc(datetime.now(UTC))  # navbat (commitdan keyin ish; testda qo'lda)
    assert D(cost()) == 2_000  # arzon lot to'liq hisobdan chiqdi


def test_inbound_invoice_location(world: World) -> None:
    """ADR-034: qabul qilinmagan postavka — "postavkada"; o'z omborimdan ayiriladi; qabul qilingani va bekori — yo'q."""
    w, a = world, world.a
    before = row(w)["locations"]
    own_before = before["own"]
    for ext, status, qty in [(9001, "CREATED", 7), (9002, "ACCEPTED", 100), (9003, "CANCELED", 50)]:
        inv = a.insert(
            "fbo_invoices", shop_id=a.shop_id, external_id=ext, status=status, to_stock=qty
        )
        a.insert(
            "fbo_invoice_items",
            invoice_id=inv,
            sku_external_id=1,
            sku_id=w.ids["sku"],
            quantity_to_stock=qty,
        )
    r = row(w)
    assert r["locations"]["inbound"] == 7
    assert r["locations"]["own"] == max(0, own_before - 7)
    body = ok(send(w, "GET", f"inventory?as_of={TODAY.isoformat()}"))
    assert body["totals"]["units"]["inbound"] == 7
    assert D(body["totals"]["frozen_money"]["inbound"]) >= 0
    # Boshlang'ich holat taklifi postavkani ham qo'shadi.
    opening = ok(send(w, "GET", "opening"))
    mine = next(x for x in opening["rows"] if x["item_id"] == str(w.ids["item"]))
    assert mine["inbound"] == 7 and mine["uzum_suggested"] >= 7

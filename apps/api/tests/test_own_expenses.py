"""B4.5 ``/own-expenses`` (haqiqiy PostgreSQL): o'z xarajatlarim — qo'shish (bir martalik, amortizatsiya, takroriy),
tahrirlash, o'chirish, toifalar, ruxsatlar, audit va P&L bilan bog'liqlik (``GET /expenses`` va ``/pnl``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from mptools import mp_api
from sellerfake import TOKEN, A, B, create_account
from test_calc import Org
from test_reports import OCT, World
from upapi.auth.deps import COOKIE

D = Decimal


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as urls:
        yield urls


@pytest.fixture(scope="module")
def world(db: dict[str, str]) -> Iterator[World]:
    settings = sf.settings_for(db)
    account = create_account(db, settings, TOKEN, [A, B])
    other = create_account(db, settings, TOKEN, [A])
    a = Org(db, account.org_id, account.shops[A])
    b = Org(db, account.org_id, account.shops[B], _ext=1_000)
    with mp_api(db) as api:
        w = World(api, a, b, other.org_id)
        w.ids["xa"] = a.insert("mp_skus", shop_id=a.shop_id, external_id=11, sku_code="Mashina")
        w.ids["item"] = a.insert("items", name="Mashina")
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
    csrf = {"X-Requested-With": "fetch"}
    return w.api.client.request(
        method,
        f"/api/v1/orgs/{w.org_id}/{path}",
        json=json if json or method == "GET" else ({} if method != "DELETE" else None),
        headers=csrf,
    )


def own(w: World, **params: Any) -> list[dict[str, Any]]:
    return w.get("expenses", **params)["own_items"]


def test_create_once_and_period_in_expenses_and_pnl(world: World) -> None:
    r = send(
        world,
        "POST",
        "own-expenses",
        category="ijara",
        amount="310000",
        start_on="2026-10-01",
        end_on="2026-10-31",
    )
    assert r.status_code == 201, r.text
    [row] = r.json()
    assert row["category"] == "ijara" and row["recurrence"] is None
    once = send(
        world, "POST", "own-expenses", category="Yangi toifa", amount="50000", start_on="2026-10-10"
    )
    assert once.json()[0]["end_on"] == "2026-10-10"
    oct_ = world.get("expenses", **OCT)
    assert D(oct_["own_total"]) == D(310_000) * 20 / 31 + D(
        50_000
    )  # F10: 1–20 oktabr qismi + bir martalik
    assert {c["category"] for c in oct_["own"]} == {"ijara", "Yangi toifa"}
    pnl = world.get("pnl", **OCT)["statement"]
    assert D(pnl["own_total"]) == D(
        oct_["own_total"]
    )  # P&L = xarajatlar sahifasi, qayta hisob kerak emas
    assert D(pnl["own_expenses"]["ijara"]) == D(200_000)
    cats = world.get("own-expense-categories")["items"]
    assert "ijara" in cats and "Yangi toifa" in cats and "ish haqi" in cats  # mavjud + tavsiya
    assert len(cats) == len(set(cats))


def test_monthly_series_creates_one_row_per_month(world: World) -> None:
    r = send(
        world,
        "POST",
        "own-expenses",
        category="internet",
        amount="100000",
        start_on="2026-01-31",
        repeat_months=3,
        note="Beeline",
    )
    rows = r.json()
    assert [x["start_on"] for x in rows] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
    ]  # oy oxiri qisqartiriladi
    assert all(x["start_on"] == x["end_on"] and x["recurrence"] == "monthly" for x in rows)
    q = own(world, start="2026-01-01", end="2026-03-31")
    assert sum(D(x["in_period"]) for x in q if x["category"] == "internet") == D(300_000)


def test_validation(world: World) -> None:
    ok = {"category": "x", "amount": "1000", "start_on": "2026-10-05"}
    assert send(world, "POST", "own-expenses", **{**ok, "end_on": "2026-10-01"}).status_code == 422
    assert send(world, "POST", "own-expenses", **{**ok, "amount": "0"}).status_code == 422
    assert send(world, "POST", "own-expenses", **{**ok, "amount": "-5"}).status_code == 422
    assert send(world, "POST", "own-expenses", **{**ok, "category": " "}).status_code in (201, 422)
    assert (
        send(
            world, "POST", "own-expenses", **{**ok, "repeat_months": 2, "end_on": "2026-11-05"}
        ).status_code
        == 422
    )
    assert send(world, "POST", "own-expenses", **{**ok, "repeat_months": 99}).status_code == 422
    assert (
        send(world, "POST", "own-expenses", **{**ok, "shop_id": str(uuid.uuid4())}).status_code
        == 404
    )
    assert (
        send(world, "POST", "own-expenses", **{**ok, "item_id": str(uuid.uuid4())}).status_code
        == 404
    )


def test_item_and_shop_links(world: World) -> None:
    r = send(
        world,
        "POST",
        "own-expenses",
        category="qadoq",
        amount="20000",
        start_on="2026-10-12",
        item_id=str(world.ids["item"]),
    )
    assert r.status_code == 201 and r.json()[0]["item_id"] == str(world.ids["item"])
    s = send(
        world,
        "POST",
        "own-expenses",
        category="transport",
        amount="30000",
        start_on="2026-10-12",
        shop_id=str(world.b.shop_id),
    )
    assert s.status_code == 201
    only_b = [
        x for x in own(world, shop=str(world.b.shop_id), **OCT) if x["category"] == "transport"
    ]
    assert len(only_b) == 1 and only_b[0]["scope"] == "shop"


def test_update_and_delete_with_audit(world: World) -> None:
    created = send(
        world, "POST", "own-expenses", category="bank", amount="10000", start_on="2026-10-15"
    ).json()[0]
    path = f"own-expenses/{created['id']}"
    patched = send(
        world,
        "PATCH",
        path,
        amount="25000",
        category="komissiya",
        note="yangilandi",
        end_on="2026-10-16",
    )
    assert patched.status_code == 200, patched.text
    assert D(patched.json()["amount"]) == D(25_000) and patched.json()["category"] == "komissiya"
    row = next(x for x in own(world, **OCT) if x["id"] == created["id"])
    assert (
        row["category"] == "komissiya"
        and row["note"] == "yangilandi"
        and D(row["in_period"]) == D(25_000)
    )
    assert (
        send(world, "PATCH", path, end_on="2026-10-01").status_code == 422
    )  # davr oxiri boshidan oldin
    assert send(world, "PATCH", path, amount=None).status_code == 422
    assert send(world, "PATCH", path).status_code == 200  # bo'sh o'zgarish — o'zgarishsiz
    assert send(world, "DELETE", path).status_code == 204
    assert all(x["id"] != created["id"] for x in own(world, **OCT))
    assert send(world, "DELETE", path).status_code == 404
    assert send(world, "PATCH", path, amount="1").status_code == 404
    actions = [
        a
        for (a,) in world.api.admin(
            "SELECT action FROM audit_log WHERE entity_id = %s ORDER BY created_at", [created["id"]]
        )
    ]
    assert actions == ["own_expense.create", "own_expense.update", "own_expense.delete"]


@pytest.mark.parametrize("role", ["manager"])
def test_manager_can_write(world: World, role: str) -> None:
    r = send(
        world, "POST", "own-expenses", role, category="ijara", amount="1000", start_on="2026-10-02"
    )
    assert r.status_code == 201


@pytest.mark.parametrize("role", ["accountant", "warehouse"])
def test_read_only_roles_cannot_write(world: World, role: str) -> None:
    r = send(
        world, "POST", "own-expenses", role, category="ijara", amount="1000", start_on="2026-10-02"
    )
    assert r.status_code == 403
    first = own(world, **OCT)[0]["id"]
    assert send(world, "PATCH", f"own-expenses/{first}", role, amount="1").status_code == 403
    assert send(world, "DELETE", f"own-expenses/{first}", role).status_code == 403


def test_categories_visibility(world: World) -> None:
    assert world.call("own-expense-categories", "accountant").status_code == 200
    assert world.call("own-expense-categories", "warehouse").status_code == 403


def test_other_org_is_invisible(world: World) -> None:
    mine = own(world, **OCT)[0]["id"]
    r = world.api.client.request(
        "DELETE",
        f"/api/v1/orgs/{world.other}/own-expenses/{mine}",
        headers={"X-Requested-With": "fetch"},
    )
    assert r.status_code in (403, 404)
    assert any(x["id"] == mine for x in own(world, **OCT))

"""B4.4 ``/orders/analysis`` (haqiqiy PostgreSQL): bekor (F17) va qaytish (F18) tahlili, sabablar, qaytim saqlash.

Ma'lumot ``test_reports`` dagi kabi superuser bilan yoziladi; hosila jadvallar haqiqiy hisob ishi bilan quriladi.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from mptools import mp_api
from sellerfake import TOKEN, A, B, create_account
from test_calc import Org
from test_reports import OCT, World, at, d
from upapi import calc
from upapi.auth.deps import COOKIE

D = Decimal


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as urls:
        yield urls


def _populate(w: World) -> None:
    a, b = w.a, w.b
    w.ids["xa"] = a.insert("mp_skus", shop_id=a.shop_id, external_id=11, sku_code="Mashina")
    w.ids["ya"] = a.insert("mp_skus", shop_id=a.shop_id, external_id=12, sku_code="Krujka")
    w.ids["zb"] = b.insert("mp_skus", shop_id=b.shop_id, external_id=21, sku_code="Chiroq")
    xa, ya = w.ids["xa"], w.ids["ya"]
    # X: 6 dona yakunlangan, 2 qaytgan (sabablar), 2 bekor (1 tasi topshirilgandan keyin).
    a.sale(xa, d(10, 2), 3, amount_returns=1, return_cause="Sifat yomon")
    a.sale(xa, d(10, 3), 3, amount_returns=1, return_cause="Sifat yomon")
    a.sale(xa, d(10, 4), 0, "CANCELED", amount_returns=1, return_cause="Mijoz fikrini o'zgartirdi")
    a.sale(
        xa,
        d(10, 5),
        0,
        "CANCELED",
        amount_returns=1,
        issued_at=at(d(10, 5)),
        return_cause="Mijoz fikrini o'zgartirdi",
    )
    a.sale(xa, d(10, 6), 1, "PROCESSING")  # na bekor, na yakunlangan
    # Y: 2 yakunlangan, qaytish yo'q, 2 bekor (sabab ko'rsatilmagan).
    a.sale(ya, d(10, 3), 2)
    a.sale(ya, d(10, 7), 0, "CANCELED", amount_returns=2)
    # Bog'lanmagan sotuv: 1 dona, 1 qaytgan (sabab yo'q).
    a.sale(None, d(10, 4), 1, amount_returns=1)
    # Boshqa davr (sentabr) — oktabr tahlilida ko'rinmasin.
    a.sale(xa, d(9, 20), 5, amount_returns=5, return_cause="Sentabr")
    # B do'koni: 4 dona yakunlangan, 1 bekor.
    b.sale(w.ids["zb"], d(10, 2), 4)
    b.sale(w.ids["zb"], d(10, 3), 0, "CANCELED", amount_returns=1, issued_at=at(d(10, 3)))

    # Qaytim saqlash (C000004): chiqim 30 000 + 20 000, kompensatsiya 5 000; chiqarilgani va boshqa toifa hisobga kirmaydi.
    w.expense(a, d(10, 2), "return_storage", 30_000)
    w.expense(a, d(10, 8), "return_storage", 20_000)
    w.expense(a, d(10, 9), "return_storage", 5_000, "INCOME")
    w.expense(a, d(10, 9), "return_storage", 99_000, excluded="status")
    w.expense(a, d(10, 9), "storage", 77_000)
    w.expense(b, d(10, 2), "return_storage", 4_000)

    a.run(lambda conn: calc.request_full(conn, a.org_id))
    assert a.recalc(datetime.now(UTC)).errors == {}


@pytest.fixture(scope="module")
def world(db: dict[str, str]) -> Iterator[World]:
    settings = sf.settings_for(db)
    account = create_account(db, settings, TOKEN, [A, B])
    other = create_account(db, settings, TOKEN, [A])
    a = Org(db, account.org_id, account.shops[A])
    b = Org(db, account.org_id, account.shops[B], _ext=1_000)
    o = Org(db, other.org_id, other.shops[A])
    o.sale(None, d(10, 2), 9, amount_returns=9)  # boshqa tashkilot — ko'rinmasligi kerak
    o.run(lambda conn: calc.request_full(conn, o.org_id))
    o.recalc(datetime.now(UTC))
    with mp_api(db) as api:
        w = World(api, a, b, other.org_id)
        _populate(w)
        for role in ("owner", "manager", "accountant", "warehouse"):
            phone = api.login()
            user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
            api.admin(
                "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, %s)",
                [a.org_id, user, role],
            )
            w.sessions[role] = api.client.cookies[COOKIE]
        yield w


def causes(rows: list[dict[str, Any]]) -> dict[str | None, int]:
    return {r["cause"]: r["units"] for r in rows}


def test_summary_shares_and_costs(world: World) -> None:
    s = world.get("orders/analysis", **OCT)["summary"]
    # Yakunlangan: X 6 + Y 2 + bog'lanmagan 1 + B 4 = 13; bekor: 1+1+2+1 = 5; qaytgan: 1+1+1 = 3 (+ bekor qatorlarniki emas).
    assert (s["units"], s["canceled"], s["returns"]) == (13, 5, 3)
    assert s["cancel_share"] == "0.277778"  # 5 / 18  (F17)
    assert s["return_share"] == "0.187500"  # 3 / 16  (F18)
    assert s["canceled_after_issue"] == 2 and s["after_issue_share"] == "0.400000"
    assert D(s["return_storage_cost"]) == D(49_000)  # 30 000 + 20 000 − 5 000 + 4 000


def test_shop_filter(world: World) -> None:
    s = world.get("orders/analysis", shop=str(world.b.shop_id), **OCT)["summary"]
    assert (s["units"], s["canceled"], s["returns"]) == (4, 1, 0)
    assert s["canceled_after_issue"] == 1 and s["after_issue_share"] == "1.000000"
    assert D(s["return_storage_cost"]) == D(4_000)


def test_causes(world: World) -> None:
    out = world.get("orders/analysis", **OCT)
    assert causes(out["return_causes"]) == {"Sifat yomon": 2, None: 1}
    # Eng ko'pi birinchi; bir xil bo'lsa sababsizi oxirda.
    assert [r["cause"] for r in out["return_causes"]] == ["Sifat yomon", None]
    assert causes(out["cancel_causes"]) == {"Mijoz fikrini o'zgartirdi": 2, None: 3}


def test_by_sku(world: World) -> None:
    rows = world.get("orders/analysis", **OCT)["by_sku"]
    assert [r["title"] for r in rows] == ["Mashina", "Krujka", "Chiroq", None]
    x = rows[0]
    assert (x["units"], x["canceled"], x["returns"]) == (6, 2, 2)
    assert x["cancel_share"] == "0.250000" and x["return_share"] == "0.250000"
    assert rows[3]["sku_id"] is None  # bog'lanmagan sotuvlar alohida qatorda
    assert rows[3]["returns"] == 1


def test_daily_trend_sums_to_summary(world: World) -> None:
    out = world.get("orders/analysis", **OCT)
    days = out["daily"]
    assert [x["day"] for x in days] == sorted(x["day"] for x in days)
    assert sum(x["units"] for x in days) == out["summary"]["units"]
    assert sum(x["canceled"] for x in days) == out["summary"]["canceled"]
    assert sum(x["returns"] for x in days) == out["summary"]["returns"]
    oct4 = next(x for x in days if x["day"] == "2026-10-04")
    assert oct4["units"] == 1 and oct4["canceled"] == 1 and oct4["cancel_share"] == "0.500000"


def test_period_excludes_other_months(world: World) -> None:
    sep = world.get("orders/analysis", start="2026-09-01", end="2026-09-30")
    assert sep["summary"]["returns"] == 5 and causes(sep["return_causes"]) == {"Sentabr": 5}
    empty = world.get("orders/analysis", start="2026-01-01", end="2026-01-31")
    assert empty["summary"]["cancel_share"] is None and empty["daily"] == []
    assert empty["by_sku"] == [] and empty["summary"]["return_storage_cost"] == "0.00"


@pytest.mark.parametrize("role", ["owner", "manager", "accountant"])
def test_finance_roles_can_read(world: World, role: str) -> None:
    assert world.call("orders/analysis", role, **OCT).status_code == 200


def test_warehouse_has_no_finance(world: World) -> None:
    assert world.call("orders/analysis", "warehouse", **OCT).status_code == 403


def test_other_org_is_invisible(world: World) -> None:
    r = world.call("orders/analysis", org=uuid.uuid4(), **OCT)
    assert r.status_code in (403, 404)
    assert (
        world.get("orders/analysis", **OCT)["summary"]["returns"] == 3
    )  # boshqa tashkilotning 9 tasi yo'q

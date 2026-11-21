"""B5.8 ``/goals`` (haqiqiy PostgreSQL): oylik maqsad (tushum, sof foyda, dona), fakt va prognoz Bosh sahifadagi bilan bir hisob,
F59 holati, upsert, ruxsat, kelgusi/o'tgan oy. Ma'lumot — ``test_reports`` dunyosi."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import test_reports as tr
from upapi.auth.deps import COOKIE
from upapi.reports.common import today

D = Decimal
db = tr.db
world = tr.world


def send(w: tr.World, method: str, path: str, role: str = "owner", **json: Any) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.request(
        method,
        f"/api/v1/orgs/{w.org_id}/{path}",
        json=json if method in ("PUT", "POST") else None,
        headers={"X-Requested-With": "fetch"},
    )


def shift(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def test_goals_set_progress_and_forecast(world: tr.World) -> None:
    w = world
    now = today()
    first = now.replace(day=1)
    assert w.get("goals")["goals"] == []
    r = send(w, "PUT", "goals", month=now.isoformat(), metric="revenue", target="10000000")
    assert r.status_code == 200, r.text
    goal = r.json()
    assert goal["shop_id"] is None and D(goal["target"]) == D(10_000_000)
    # Qayta belgilash — yangilanadi (bitta qator)
    r2 = send(w, "PUT", "goals", month=first.isoformat(), metric="revenue", target="12000000")
    assert r2.json()["id"] == goal["id"] and D(r2.json()["target"]) == D(12_000_000)
    send(
        w,
        "PUT",
        "goals",
        month=now.isoformat(),
        metric="units",
        target="100",
        shop_id=str(w.a.shop_id),
    )
    out = w.get("goals")
    assert out["month"] == first.isoformat() and len(out["goals"]) == 2
    assert [s["id"] for s in out["shops"]]  # do'konlar ro'yxati (forma uchun)

    # Fakt va prognoz Bosh sahifadagi bilan bir hisob
    dash = w.get("dashboard")
    periods = {p["key"]: p for p in dash["periods"]}
    rev = next(g for g in out["goals"] if g["metric"] == "revenue" and g["shop_id"] is None)
    assert D(rev["fact"]) == D(periods["this_month"]["revenue"])
    fc = dash["forecast"]["revenue"]
    assert (None if rev["forecast"] is None else D(rev["forecast"])) == (
        None if fc is None else D(fc)
    )
    assert D(rev["percent"]) == (D(rev["fact"]) * 100 / D(12_000_000)).quantize(D("0.1"))
    if rev["forecast"] is None:
        assert rev["status"] == "unknown" and rev["forecast_percent"] is None
    else:
        assert rev["status"] in ("on_track", "behind", "ahead")

    # Kelgusi oy — fakt 0, prognoz yo'q; o'tgan oy — prognoz = fakt
    nxt = shift(first, 1)
    send(w, "PUT", "goals", month=nxt.isoformat(), metric="revenue", target="1000")
    future = w.get("goals", month=nxt.isoformat())["goals"][0]
    assert D(future["fact"]) == 0 and future["forecast"] is None and future["status"] == "unknown"
    prev = shift(first, -1)
    send(w, "PUT", "goals", month=prev.isoformat(), metric="net_profit", target="1000")
    past = w.get("goals", month=prev.isoformat())["goals"][0]
    assert past["forecast"] == past["fact"]

    # Tekshiruv, ruxsat, o'chirish
    assert (
        send(w, "PUT", "goals", month=now.isoformat(), metric="revenue", target="0").status_code
        == 422
    )
    assert (
        send(w, "PUT", "goals", month=now.isoformat(), metric="bad", target="1").status_code == 422
    )
    unknown_shop = "00000000-0000-0000-0000-000000000001"
    assert (
        send(
            w,
            "PUT",
            "goals",
            month=now.isoformat(),
            metric="units",
            target="1",
            shop_id=unknown_shop,
        ).status_code
        == 404
    )
    assert (
        send(
            w, "PUT", "goals", "accountant", month=now.isoformat(), metric="units", target="5"
        ).status_code
        == 403
    )
    assert w.call("goals", "warehouse").status_code == 403
    gid = goal["id"]
    assert send(w, "DELETE", f"goals/{gid}").status_code == 204
    assert send(w, "DELETE", f"goals/{gid}").status_code == 404

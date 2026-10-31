"""B4.8 ``/settings`` (haqiqiy PostgreSQL): tannarx usuli (o'zgarsa — qayta hisob), soliq profili (sana bo'yicha, rejimga
mos maydonlar), Uzum to'lov jadvali, standart yetkazish muddatlari (F25) va ABC qamrov (F27) hisobotlarga ta'siri,
ruxsatlar (buxgalter o'qiydi, omborchi ko'rmaydi), tekshiruvlar, audit, boshqa tashkilot.
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
        a.sql(
            "INSERT INTO ref_tax_rates (code, valid_from, rate_pct, note) VALUES "
            "('turnover_ecommerce', '2026-01-01', 4, 'e-tijorat') ON CONFLICT DO NOTHING"
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
        json=json if json else ({} if method in ("POST", "PUT") else None),
        headers={"X-Requested-With": "fetch"},
    )


def ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, r.text
    return r.json() if r.content else None


def audited(w: World) -> set[str]:
    return {x[0] for x in w.a.sql("SELECT action FROM audit_log WHERE org_id = %s", [w.org_id])}


def test_defaults(world: World) -> None:
    body = ok(send(world, "GET", "settings"))
    assert body["cost_method"] == "fifo" and body["tax_profiles"] == []
    assert body["payout_schedules"] == []
    assert {t["kind"] for t in body["payout_terms"]} == {"daily", "weekly", "biweekly", "monthly"}
    weekly = next(t for t in body["payout_terms"] if t["kind"] == "weekly")
    assert weekly["days_of_month"] == [7, 14, 21, 28] and D(weekly["fee_pct"]) == 1
    assert next(t for t in body["payout_terms"] if t["kind"] == "daily")["days_of_month"] is None
    inv = body["inventory"]
    assert inv["lead_days"] is None
    assert inv["stages"] == ["prep", "china", "cargo", "receive", "handover"]
    assert inv["cover_days"] == inv["cover_defaults"] == {"A": 60, "B": 30, "C": 14}
    assert [(r["code"], D(r["rate_pct"])) for r in body["tax_rates"]] == [("turnover_ecommerce", 4)]


def test_tax_profiles(world: World) -> None:
    w = world
    body = ok(
        send(w, "POST", "tax-profiles", valid_from="2026-01-01", regime="turnover", rate_pct="4", base="payout"),
        201,
    )  # fmt: skip
    [first] = body["tax_profiles"]
    assert first["regime"] == "turnover" and D(first["rate_pct"]) == 4 and first["base"] == "payout"
    assert (
        send(w, "POST", "tax-profiles", valid_from="2026-01-01", regime="none").status_code == 409
    )
    # Aylanma solig'ida stavka 0 dan katta bo'lishi shart.
    zero = send(w, "POST", "tax-profiles", valid_from="2026-06-01", regime="turnover", rate_pct="0")
    assert zero.status_code == 422 and zero.json()["code"] == "tax_rate_required"
    assert (
        send(
            w, "POST", "tax-profiles", valid_from="2026-06-01", regime="turnover", rate_pct="101"
        ).status_code
        == 422
    )
    # Rejimga tegishli bo'lmagan maydonlar nolga qaytadi (agent: stavka ham baza ham yo'q).
    body = ok(
        send(
            w,
            "POST",
            "tax-profiles",
            valid_from="2026-07-01",
            regime="agent",
            rate_pct="4",
            vat_pct="12",
        ),
        201,
    )
    assert [p["valid_from"] for p in body["tax_profiles"]] == [
        "2026-07-01",
        "2026-01-01",
    ]  # yangisi tepada
    agent = body["tax_profiles"][0]
    assert (D(agent["rate_pct"]), agent["base"], D(agent["vat_pct"])) == (0, "revenue", 0)
    # Tahrirlash: QQS + foyda rejimiga o'tish; boshqa profil sanasiga to'qnashish — 409.
    patched = ok(
        send(
            w,
            "PATCH",
            f"tax-profiles/{agent['id']}",
            regime="vat_profit",
            vat_pct="12",
            profit_pct="15",
        )
    )
    row = next(p for p in patched["tax_profiles"] if p["id"] == agent["id"])
    assert (row["regime"], D(row["vat_pct"]), D(row["profit_pct"])) == ("vat_profit", 12, 15)
    clash = send(w, "PATCH", f"tax-profiles/{agent['id']}", valid_from="2026-01-01")
    assert clash.status_code == 409 and clash.json()["code"] == "tax_profile_exists"
    ok(send(w, "PATCH", f"tax-profiles/{agent['id']}", valid_from="2026-08-01"))
    body = ok(send(w, "DELETE", f"tax-profiles/{agent['id']}"))
    assert [p["valid_from"] for p in body["tax_profiles"]] == ["2026-01-01"]
    assert send(w, "DELETE", f"tax-profiles/{agent['id']}").status_code == 404
    assert send(w, "PATCH", f"tax-profiles/{uuid.uuid4()}", regime="none").status_code == 404
    assert {"tax_profile.create", "tax_profile.update", "tax_profile.delete"} <= audited(w)


def test_tax_profile_drives_pnl(world: World) -> None:
    """Profil F11 hisobiga kiradi: aylanma 4% — P&L'da soliq paydo bo'ladi (hisob `upcore` da, bu yerda faqat ulanish)."""
    w, a = world, world.a
    sku = w.ids["sku"]
    a.sale(sku, day(-2), 1, price=100_000)
    a.run(lambda conn: calc.request_full(conn, a.org_id))
    a.recalc(datetime.now(UTC))
    start, end = day(-5).isoformat(), day(0).isoformat()
    body = ok(send(w, "GET", f"pnl?start={start}&end={end}"))
    assert D(str(body["statement"]["tax"])) > 0


def test_payout_schedules(world: World) -> None:
    w = world
    shop = str(w.a.shop_id)
    body = ok(
        send(w, "POST", "payout-schedules", shop_id=shop, kind="weekly", valid_from="2026-01-01"),
        201,
    )
    [row] = body["payout_schedules"]
    assert row["shop_id"] == shop and row["kind"] == "weekly"
    dup = send(w, "POST", "payout-schedules", shop_id=shop, kind="daily", valid_from="2026-01-01")
    assert dup.status_code == 409 and dup.json()["code"] == "payout_schedule_exists"
    ghost = send(
        w,
        "POST",
        "payout-schedules",
        shop_id=str(uuid.uuid4()),
        kind="daily",
        valid_from="2026-02-01",
    )
    assert ghost.status_code == 404 and ghost.json()["code"] == "shop_not_found"
    assert (
        send(
            w, "POST", "payout-schedules", shop_id=shop, kind="yearly", valid_from="2026-02-01"
        ).status_code
        == 422
    )
    body = ok(
        send(w, "POST", "payout-schedules", shop_id=shop, kind="monthly", valid_from="2026-09-01"),
        201,
    )
    assert [p["kind"] for p in body["payout_schedules"]] == ["monthly", "weekly"]  # yangisi tepada
    body = ok(send(w, "DELETE", f"payout-schedules/{row['id']}"))
    assert [p["kind"] for p in body["payout_schedules"]] == ["monthly"]
    assert send(w, "DELETE", f"payout-schedules/{row['id']}").status_code == 404
    assert {"payout_schedule.create", "payout_schedule.delete"} <= audited(w)


def test_cost_method_requests_full_recalc(world: World) -> None:
    w = world
    w.a.sql("DELETE FROM recalc_queue WHERE org_id = %s", [w.org_id])
    # O'zgarmasa — hech narsa (navbat bo'sh, audit yo'q).
    ok(send(w, "PUT", "settings/cost-method", cost_method="fifo"))
    assert w.a.sql("SELECT count(*) FROM recalc_queue WHERE org_id = %s", [w.org_id])[0][0] == 0
    assert "settings.cost_method" not in audited(w)
    body = ok(send(w, "PUT", "settings/cost-method", cost_method="average"))
    assert body["cost_method"] == "average"
    kinds = {x[0] for x in w.a.sql("SELECT kind FROM recalc_queue WHERE org_id = %s", [w.org_id])}
    assert {"purchase", "item", "shop"} <= kinds  # hamma tovar, xarid va do'kon
    assert "settings.cost_method" in audited(w)
    assert send(w, "PUT", "settings/cost-method", cost_method="lifo").status_code == 422
    ok(send(w, "PUT", "settings/cost-method", cost_method="fifo"))


def test_inventory_settings_drive_reports(world: World) -> None:
    w, a = world, world.a
    item, sku = a.item("Chiroq")
    for i in range(1, 8):  # tezlik > 0: oxirgi 7 kunda har kuni 2 dona
        a.sale(sku, day(-i), 2, price=100_000)
    a.run(lambda conn: calc.request_full(conn, a.org_id))
    a.recalc(datetime.now(UTC))

    def row() -> dict[str, Any]:
        body = ok(send(w, "GET", f"inventory?as_of={TODAY.isoformat()}"))
        return next(r for r in body["items"] if r["sku_id"] == str(sku))

    # Muddat sozlanmagan, tarix yo'q: holat, buyurtma sanasi va tavsiya — yo'q (taxmin qilinmaydi).
    before = row()
    assert before["lead_time"] is None and before["reorder"] is None and before["order_by"] is None
    lead = {"prep": 8, "china": 2, "cargo": 13, "receive": 7, "handover": 2}
    body = ok(
        send(w, "PUT", "settings/inventory", lead_days=lead, cover_days={"A": 60, "B": 30, "C": 14})
    )
    assert body["inventory"]["lead_days"] == lead
    after = row()
    assert D(after["lead_time"]["total"]) == 32 and after["lead_time"]["learned"] == []
    assert after["reorder"]["qty"] > 0 and after["order_by"] is not None
    # Qamrov kamaysa — tavsiya miqdor kamayadi (F27).
    ok(send(w, "PUT", "settings/inventory", lead_days=lead, cover_days={"A": 1, "B": 1, "C": 1}))
    assert row()["reorder"]["qty"] < after["reorder"]["qty"]
    # Standart muddat xarid sahifasidagi kutilgan sanaga ham ta'sir qiladi (F25).
    p = a.insert("purchases", ordered_on=day(-3))
    a.line(p, item, 5)
    detail = ok(send(w, "GET", f"purchases/{p}"))
    current = next(x for x in detail["purchase"]["timeline"] if x["state"] == "current")
    assert (
        current["stage"] == "ordered" and current["expected"] == day(5).isoformat()
    )  # -3 + prep 8
    # Tozalash — xaritalar boshiga qaytadi.
    body = ok(send(w, "PUT", "settings/inventory"))
    assert body["inventory"]["lead_days"] is None
    assert body["inventory"]["cover_days"] == {"A": 60, "B": 30, "C": 14}
    assert row()["lead_time"] is None
    assert "settings.inventory" in audited(w)


def test_inventory_settings_validation(world: World) -> None:
    w = world
    partial = send(w, "PUT", "settings/inventory", lead_days={"prep": 5})
    assert partial.status_code == 422 and partial.json()["code"] == "bad_lead_days"
    lead = {"prep": 8, "china": 2, "cargo": 13, "receive": 7, "handover": 2}
    assert send(w, "PUT", "settings/inventory", lead_days={**lead, "prep": -1}).status_code == 422
    assert send(w, "PUT", "settings/inventory", lead_days={**lead, "prep": 9999}).status_code == 422
    bad = send(w, "PUT", "settings/inventory", cover_days={"A": 60})
    assert bad.status_code == 422 and bad.json()["code"] == "bad_cover_days"


def test_roles(world: World) -> None:
    w = world
    assert ok(send(w, "GET", "settings", role="accountant"))["cost_method"] == "fifo"
    assert send(w, "GET", "settings", role="warehouse").status_code == 403
    writes = [
        ("PUT", "settings/cost-method", {"cost_method": "fifo"}),
        ("POST", "tax-profiles", {"valid_from": "2027-01-01", "regime": "none"}),
        ("PUT", "settings/inventory", {}),
        ("POST", "payout-schedules", {"shop_id": str(w.a.shop_id), "kind": "daily", "valid_from": "2027-01-01"}),
        ("DELETE", f"tax-profiles/{uuid.uuid4()}", {}),
        ("DELETE", f"payout-schedules/{uuid.uuid4()}", {}),
    ]  # fmt: skip
    for method, path, body in writes:
        for role in ("accountant", "warehouse"):
            r = send(w, method, path, role=role, **body)
            assert r.status_code == 403, (method, path, role, r.status_code)
    assert (
        send(
            w, "POST", "tax-profiles", role="manager", valid_from="2027-01-01", regime="none"
        ).status_code
        == 201
    )


def test_other_org_is_invisible(world: World) -> None:
    """Boshqa tashkilotning profili ro'yxatda ko'rinmaydi; uning profilini o'zgartirib ham bo'lmaydi (RLS)."""
    w = world
    foreign = uuid.uuid4()
    w.a.sql(
        "INSERT INTO tax_profiles (id, org_id, valid_from, regime) VALUES (%s, %s, '2026-03-03', 'none')",
        [foreign, w.other],
    )
    ids = {p["id"] for p in ok(send(w, "GET", "settings"))["tax_profiles"]}
    assert str(foreign) not in ids
    assert send(w, "PATCH", f"tax-profiles/{foreign}", regime="agent").status_code == 404
    assert send(w, "DELETE", f"tax-profiles/{foreign}").status_code == 404


def test_parse_ignores_garbage() -> None:
    from upapi import orgsettings
    from upcore.inventory import DEFAULT, AbcClass

    assert orgsettings.parse(None) == orgsettings.OrgSettings()
    assert orgsettings.parse([1, 2]) == orgsettings.OrgSettings()
    bad = {
        "lead_days": {"prep": -1, "nope": 3, "china": "x", "cargo": 4},
        "cover_days": {"A": 5, "Z": 9, "B": -2},
    }
    got = orgsettings.parse(bad)
    assert got.lead_days == {"cargo": 4} and got.cover_days == {AbcClass.A: 5}
    assert orgsettings.parse({"lead_days": 3, "cover_days": "x"}) == orgsettings.OrgSettings()
    # Qisman qamrov standartni to'ldiradi; bo'sh — aynan standart.
    assert got.inventory().cover_days == {**DEFAULT.cover_days, AbcClass.A: 5}
    assert orgsettings.OrgSettings().inventory() is DEFAULT
    assert orgsettings.dump(got) == {"lead_days": {"cargo": 4}, "cover_days": {"A": 5}}

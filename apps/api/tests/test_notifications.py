"""B6.1 bildirishnomalar (haqiqiy PostgreSQL, 02 M15): sozlamalar (shaxsiy qoidalar, chegaralar, tinch soatlar),
hodisalarni topish (kunlik va haftalik xulosa, F53 zarar zanjiri, tannarxsiz sotuv, jarima, postavka kamomadi, sinxron
to'xtadi), rol bo'yicha oluvchilar, takror yo'q, tinch soatlar va eski sinxronda xulosa yuborilmasligi."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import sellerfake as sf
import test_purchases as tp
from test_purchases import D, ok, send
from test_receiving import setup_dispatch
from test_reports import World
from upapi import calc, notify
from upapi.auth.deps import COOKIE
from upapi.sync import jobs

db = tp.db
world = tp.world

TZ = ZoneInfo("Asia/Tashkent")
NOW = datetime(2026, 11, 16, 10, 0, tzinfo=TZ)  # dushanba 10:00
YESTERDAY = date(2026, 11, 15)


def evaluate(w: World, now: datetime = NOW) -> int:
    return int(w.a.run(lambda conn: notify.evaluate(conn, w.org_id, now)))


def queue(w: World) -> list[dict[str, Any]]:
    rows = w.a.sql(
        "SELECT u.phone, m.role, n.event, n.dedupe_key, n.critical, n.payload, n.due_at "
        "FROM notifications n JOIN memberships m ON m.user_id = n.user_id AND m.org_id = n.org_id "
        "JOIN users u ON u.id = n.user_id WHERE n.org_id = %s ORDER BY n.created_at, n.event",
        [w.org_id],
    )
    keys = ("phone", "role", "event", "key", "critical", "payload", "due_at")
    return [dict(zip(keys, r, strict=True)) for r in rows]


def phone_of(w: World, role: str) -> str:
    """World'ning ``role`` foydalanuvchisi (tashkilotda sellerfake egasi ham bor — u boshqa telefon)."""
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return str(w.api.client.get("/api/v1/auth/me").json()["user"]["phone"])


def fresh(w: World, at: datetime) -> None:
    w.a.sql(
        "INSERT INTO sync_state (org_id, shop_id, kind, last_success_at) VALUES (%s, %s, 'orders', %s) "
        "ON CONFLICT (org_id, shop_id, kind) DO UPDATE SET last_success_at = EXCLUDED.last_success_at",
        [w.org_id, w.a.shop_id, at],
    )


def test_settings_defaults_update_and_validation(world: World) -> None:
    w = world
    got = ok(send(w, "GET", "notifications/settings"))
    events = {x["event"]: x for x in got["events"]}
    assert events["daily_summary"] == {
        "event": "daily_summary",
        "enabled": True,
        "params": {"at": "09:00"},
        "critical": False,
        "available": True,
        "stage": None,
    }
    assert events["payout_late"]["available"] is False and events["payout_late"]["stage"] == "B5.7"
    assert events["sync_stopped"]["critical"] is True
    assert (got["quiet_from"], got["quiet_to"]) == ("22:00:00", "08:00:00")
    # Omborchiga moliya xulosasi tegishli emas, qoldiq — tegishli.
    wh = {
        x["event"]: x for x in ok(send(w, "GET", "notifications/settings", "warehouse"))["events"]
    }
    assert not wh["daily_summary"]["available"] and wh["stock_critical"]["available"]

    out = ok(
        send(
            w,
            "PUT",
            "notifications/settings",
            role="manager",
            rules=[
                {"event": "daily_summary", "enabled": True, "params": {"at": "7:30"}},
                {"event": "stock_critical", "enabled": False},
                {"event": "loss_sales", "enabled": True, "params": {"streak": 4}},
            ],
            quiet_from="23:00",
            quiet_to="07:00",
        )
    )
    mine = {x["event"]: x for x in out["events"]}
    assert mine["daily_summary"]["params"] == {"at": "07:30"}
    assert not mine["stock_critical"]["enabled"] and mine["loss_sales"]["params"] == {"streak": 4}
    assert (out["quiet_from"], out["quiet_to"]) == ("23:00:00", "07:00:00")
    # Shaxsiy: egasining sozlamasi o'zgarmadi.
    owner = {x["event"]: x for x in ok(send(w, "GET", "notifications/settings"))["events"]}
    assert owner["stock_critical"]["enabled"]
    for rule in (
        {"event": "loss_sales", "enabled": True, "params": {"streak": 50}},
        {"event": "loss_sales", "enabled": True, "params": {"streak": True}},
        {"event": "daily_summary", "enabled": True, "params": {"at": "25:00"}},
        {"event": "daily_summary", "enabled": True, "params": {"x": 1}},
    ):
        r = send(w, "PUT", "notifications/settings", rules=[rule])
        assert r.status_code == 422 and r.json()["code"] == "bad_notification_params", rule
    r = send(w, "PUT", "notifications/settings", quiet_from="22:00", quiet_to=None)
    assert r.status_code == 422 and r.json()["code"] == "bad_quiet_hours"
    # Manager qoidasini standartga qaytarish (keyingi testlar uchun), tinch soat — o'chiq.
    ok(
        send(
            w,
            "PUT",
            "notifications/settings",
            role="manager",
            rules=[
                {"event": "daily_summary", "enabled": True, "params": {"at": "09:00"}},
                {"event": "loss_sales", "enabled": True, "params": {"streak": 3}},
            ],
            quiet_from=None,
            quiet_to=None,
        )
    )


def test_events_recipients_dedupe_and_quiet_hours(world: World) -> None:
    w, a = world, world.a
    # Zarar zanjiri (F53): tannarx 300 000 > Uzum to'lovi 150 000, ketma-ket 3 sotuv.
    p = a.purchase(received=date(2026, 10, 1))
    a.line(p, w.ids["item"], 100)
    a.component(p, "goods", 100 * 300_000)
    for day in (12, 13, 15):
        a.sale(w.ids["sku"], date(2026, 11, day), seller_profit=D(150_000))
    # Tannarxsiz sotuv kecha (xaridsiz SKU).
    a.sale(w.ids["sku2"], YESTERDAY, seller_profit=D(150_000))
    a.insert(
        "mp_expenses",
        shop_id=a.shop_id,
        external_id=990_001,
        category="fine",
        code="C000007",
        type="OUTCOME",
        amount=D(-7_000),
        name="Kamomad jarimasi",
        created_on=NOW - timedelta(days=1),
    )
    a.request(calc.Scope.PURCHASE)
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW)
    fresh(w, NOW - timedelta(hours=1))
    # Egasi: tinch soat 09:00–12:00 (kritik bo'lmagani 12:00 da).
    ok(send(w, "PUT", "notifications/settings", quiet_from="09:00", quiet_to="12:00"))

    created = evaluate(w)
    rows = queue(w)
    assert created == len(rows) > 0
    by_role: dict[str, set[str]] = {}
    for r in rows:
        by_role.setdefault(r["role"], set()).add(r["event"])
    finance = {"daily_summary", "weekly_summary", "loss_sales", "uncosted_sales", "new_fine"}
    assert finance <= by_role["owner"] and finance <= by_role["manager"]
    assert finance <= by_role["accountant"]
    assert not (finance & by_role.get("warehouse", set()))
    me = phone_of(w, "owner")
    daily = next(r for r in rows if r["phone"] == me and r["event"] == "daily_summary")
    assert daily["key"] == "daily:2026-11-15"
    assert daily["payload"]["start"] == "2026-11-15" and daily["payload"]["orders"] == 2
    assert D(daily["payload"]["revenue"]) == D(400_000)
    assert daily["payload"]["uncosted_lines"] == 1
    assert daily["due_at"] == datetime(2026, 11, 16, 12, 0, tzinfo=TZ)  # tinch soat tugaganda
    manager = next(r for r in rows if r["role"] == "manager" and r["event"] == "daily_summary")
    assert manager["due_at"] == NOW
    loss = next(r for r in rows if r["role"] == "owner" and r["event"] == "loss_sales")
    assert loss["payload"]["count"] == 1 and loss["payload"]["skus"][0]["title"] == "Mashina"
    fine = next(r for r in rows if r["role"] == "owner" and r["event"] == "new_fine")
    assert fine["payload"]["amount"] == "7000.00" and fine["payload"]["code"] == "C000007"
    # Takror yo'q.
    assert evaluate(w) == 0
    assert evaluate(w, NOW + timedelta(minutes=5)) == 0

    # O'chirilgan hodisa kelmaydi; haftalik faqat dushanba.
    ok(
        send(
            w,
            "PUT",
            "notifications/settings",
            role="manager",
            rules=[{"event": "new_fine", "enabled": False}],
            quiet_from=None,
            quiet_to=None,
        )
    )
    a.insert(
        "mp_expenses",
        shop_id=a.shop_id,
        external_id=990_002,
        category="fine",
        type="OUTCOME",
        amount=D(-1_000),
        created_on=NOW,
    )
    evaluate(w)
    new = [r for r in queue(w) if r["event"] == "new_fine" and r["payload"]["amount"] == "1000.00"]
    assert {r["role"] for r in new} == {"owner", "accountant"}


def test_stale_sync_skips_summary_and_alerts_critical(world: World) -> None:
    w = world
    tuesday = NOW + timedelta(days=1)  # seshanba 10:00 — kecha (dushanba) uchun xulosa
    fresh(w, tuesday - timedelta(hours=20))  # kecha 14:00 da to'xtagan
    evaluate(w, tuesday)
    rows = [r for r in queue(w) if r["role"] == "owner"]
    assert not [r for r in rows if r["key"] == "daily:2026-11-16"]  # "sotuv yo'q" deb yuborilmaydi
    stopped = [r for r in rows if r["event"] == "sync_stopped"]
    assert (
        len({r["key"] for r in stopped}) == 1
    )  # bitta do'kon, kuniga bir marta (egasi ikkita — har biriga)
    assert all(r["critical"] and r["payload"]["reason"] == "stale" for r in stopped)
    assert all(r["due_at"] == tuesday for r in stopped)  # tinch soatda ham (09:00–12:00) darhol
    assert not [
        r for r in queue(w) if r["event"] == "weekly_summary" and r["key"] != "weekly:2026-11-09"
    ]
    # Sinxron tiklandi — xulosa keyingi tekshiruvda keladi.
    fresh(w, tuesday)
    evaluate(w, tuesday + timedelta(minutes=5))
    assert [r for r in queue(w) if r["role"] == "owner" and r["key"] == "daily:2026-11-16"]


def test_receiving_shortage_and_list(world: World) -> None:
    w = world
    s = setup_dispatch(w, shipped=10, accepted=7)
    evaluate(w, NOW + timedelta(days=1, hours=1))
    rows = [r for r in queue(w) if r["event"] == "receiving_shortage"]
    assert {r["role"] for r in rows} == {"owner", "manager", "warehouse"}
    assert rows[0]["key"] == f"receiving:{s['dispatch']}:{w.ids['sku']}"
    assert rows[0]["payload"]["missing"] == 3
    # Foydalanuvchining ro'yxati (faqat o'zi).
    items = ok(send(w, "GET", "notifications?limit=100", "warehouse"))["items"]
    assert items and {x["event"] for x in items} <= {
        "receiving_shortage",
        "stock_critical",
        "sync_stopped",
    }
    assert {x["status"] for x in items} == {"pending"}
    assert send(w, "GET", "notifications?limit=0").status_code == 422


def test_job_runs_every_org_and_reports_invalid_key(world: World) -> None:
    """``notify.tick`` (har 5 daqiqa): ulangan har tashkilot; kalit yaroqsiz — kritik "sinxron to'xtadi"."""
    w = world
    w.a.sql("UPDATE mp_accounts SET status = 'invalid' WHERE org_id = %s", [w.org_id])
    later = NOW + timedelta(days=3)
    with sf.runtime(w.a.db, sf.FakeSeller(sf.TOKEN, [sf.A]), sf.Clock(later)) as run:
        created = run(jobs.notify_all)
    assert created > 0
    invalid = [
        r
        for r in queue(w)
        if r["event"] == "sync_stopped" and r["payload"]["reason"] == "key_invalid"
    ]
    assert invalid and all(r["key"].endswith("2026-11-19") for r in invalid)
    w.a.sql("UPDATE mp_accounts SET status = 'active' WHERE org_id = %s", [w.org_id])

"""B6.1 bildirishnomalar (haqiqiy PostgreSQL, 02 M15): sozlamalar (shaxsiy qoidalar, chegaralar, tinch soatlar),
hodisalarni topish (kunlik va haftalik xulosa, F53 zarar zanjiri, tannarxsiz sotuv, jarima, postavka kamomadi, sinxron
to'xtadi), rol bo'yicha oluvchilar, takror yo'q, tinch soatlar va eski sinxronda xulosa yuborilmasligi."""

from __future__ import annotations

import math
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
from upapi.reports.purchases import org_lead
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
    assert daily["payload"]["uncosted_lines"] >= 1
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
    # B6.4 (A4): "yangilanmayapti" — sotuvchi qila olmaydi, kritik emas (tunda yuborilmaydi); har to'xtash uchun bir marta.
    assert all(not r["critical"] and r["payload"]["reason"] == "stale" for r in stopped)
    assert all(r["key"].startswith("sync_stale:") for r in stopped)
    assert all(r["due_at"] >= tuesday for r in stopped)  # kritik emas — tinch soatlarga bo'ysunadi
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
    assert invalid and all(r["key"].startswith("sync_key:") and r["critical"] for r in invalid)
    w.a.sql("UPDATE mp_accounts SET status = 'active' WHERE org_id = %s", [w.org_id])


def test_telegram_link_url(world: World) -> None:
    """B6.2: ulash havolasi — bot sozlanmagan bo'lsa 503; bo'lsa t.me/<bot>?start=<tashkilot><token>, xeshi bazada."""
    w = world
    r = send(w, "POST", "notifications/telegram")
    assert r.status_code == 503 and r.json()["code"] == "telegram_not_configured"
    state = w.api.client.app.state  # type: ignore[attr-defined]
    original = state.settings
    state.settings = original.model_copy(update={"telegram_bot_username": "sellermax_bot"})
    try:
        out = ok(send(w, "POST", "notifications/telegram", "warehouse"))
    finally:
        state.settings = original
    prefix = f"https://t.me/sellermax_bot?start={w.org_id.hex}"
    assert out["url"].startswith(prefix) and len(out["url"]) - len(prefix) == 24
    token = out["url"][len(prefix) :]
    assert w.a.sql(
        "SELECT count(*) FROM notification_links WHERE token_hash = sha256(%s::bytea)",
        [token.encode()],
    ) == [(1,)]


def _clean(w: World) -> None:
    """Testlar umumiy bazada ishlaydi — oldingi testlardan qolgan navbat bazaviy ro'yxatga ta'sir qilmasin."""
    w.a.sql("DELETE FROM notifications WHERE org_id = %s", [w.org_id])


def _rows(w: World, role: str, event: str) -> list[dict[str, Any]]:
    """World'ning ``role`` foydalanuvchisi uchun qatorlar (egasi ikkita — sellerfake egasi ham bor)."""
    me = phone_of(w, role)
    return [r for r in queue(w) if r["phone"] == me and r["event"] == event]


def test_stock_and_loss_notify_only_new_skus(world: World, monkeypatch: Any) -> None:
    """B6.4 (A2): "Qoldiq kritik" va "Zarar bilan sotuv" holat o'zgarmasa takrorlanmaydi — faqat ro'yxatga YANGI SKU
    kirganda. Ro'yxat qisqarsa baza yangilanadi (SKU qaytib kirsa — yana yangi), qisqarish xabar emas."""
    w = world
    _clean(w)
    sku_a, sku_b = w.ids["sku"], w.ids["sku2"]
    state: dict[str, list[Any]] = {"crit": [], "loss": []}

    async def crit(conn: Any, today: date) -> list[Any]:
        return [(i, D(5)) for i in state["crit"]]

    async def loss(conn: Any, today: date, streak: int) -> list[Any]:
        return sorted(state["loss"], key=str)

    monkeypatch.setattr(notify, "critical_stock", crit)
    monkeypatch.setattr(notify, "losing_skus", loss)
    fresh(w, NOW + timedelta(days=2))

    def hour(k: int) -> datetime:
        return NOW + timedelta(hours=k)  # har soatning boshi — og'ir tekshiruv ishlaydi

    def step(at: datetime) -> int:
        """``evaluate`` + yangi qatorlarning ``created_at`` ini qadam vaqtiga qo'yadi: test muhitida hamma qadam bitta
        tranzaksiya vaqtida bo'lib, "oxirgi qator" tartibi tasodifiy bo'lib qolmasin (ishda har tick alohida tranzaksiya)."""
        created = evaluate(w, at)
        w.a.sql(
            "UPDATE notifications SET created_at = %s WHERE org_id = %s "
            "AND created_at = (SELECT max(created_at) FROM notifications WHERE org_id = %s)",
            [at, w.org_id, w.org_id],
        )
        return created

    def stock_rows() -> list[dict[str, Any]]:
        return _rows(w, "owner", "stock_critical")

    def loss_rows() -> list[dict[str, Any]]:
        return _rows(w, "owner", "loss_sales")

    # 1) Birinchi marta: A yangi.
    state["crit"], state["loss"] = [sku_a], [sku_a]
    step(hour(0))
    assert [
        (r["payload"]["count"], r["payload"]["total"], r["payload"]["new"]) for r in stock_rows()
    ] == [(1, 1, True)]
    assert [(r["payload"]["count"], r["payload"]["total"]) for r in loss_rows()] == [(1, 1)]
    # 2) Holat o'zgarmadi — keyingi soat ham, keyingi kun ham xabar yo'q.
    step(hour(1))
    step(hour(25))
    assert len(stock_rows()) == 1 and len(loss_rows()) == 1
    # 3) Ro'yxat bo'shadi — xabar emas, baza yangilandi (skipped).
    state["crit"], state["loss"] = [], []
    step(hour(26))
    assert len(stock_rows()) == 2 and stock_rows()[-1]["payload"] == {"ids": []}
    assert len(loss_rows()) == 2
    sent = w.a.sql(
        "SELECT n.status FROM notifications n JOIN users u ON u.id = n.user_id "
        "WHERE u.phone = %s AND n.event = 'stock_critical' ORDER BY n.created_at, n.id",
        [phone_of(w, "owner")],
    )
    assert [s[0] for s in sent] == ["pending", "skipped"]
    # 4) A qaytib kirdi — yana yangi.
    state["crit"], state["loss"] = [sku_a], [sku_a]
    step(hour(27))
    assert len(stock_rows()) == 3 and stock_rows()[-1]["payload"]["count"] == 1
    # 5) B qo'shildi — faqat B yangi (jami 2).
    state["crit"], state["loss"] = [sku_a, sku_b], [sku_a, sku_b]
    step(hour(28))
    last = stock_rows()[-1]["payload"]
    assert (last["count"], last["total"], len(last["skus"])) == (1, 2, 1)
    assert last["skus"][0]["sku_id"] == str(sku_b)
    assert loss_rows()[-1]["payload"]["total"] == 2 and loss_rows()[-1]["payload"]["streak"] == 3
    # 6) Soat boshida emas (har 5 daqiqa) — og'ir tekshiruv bajarilmaydi (A10).
    state["crit"] = [sku_a, sku_b]
    calls: list[int] = []

    async def spy(conn: Any, today: date) -> list[Any]:
        calls.append(1)
        return []

    monkeypatch.setattr(notify, "critical_stock", spy)
    step(hour(29) + timedelta(minutes=10))
    assert calls == []
    step(hour(30))
    assert calls == [1]


def test_uncosted_alert_only_for_new_sku(world: World) -> None:
    """B6.4 (A3): tannarxsiz sotuv haqida alohida xabar — faqat YANGI SKU (har SKU bir marta); qatorlar soni —
    kunlik xulosada."""
    w, a = world, world.a
    _clean(w)
    a.sale(w.ids["sku2"], YESTERDAY, seller_profit=D(150_000))
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW)
    fresh(w, NOW - timedelta(hours=1))
    evaluate(w)
    rows = _rows(w, "owner", "uncosted_sales")
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["count"] == 1 and payload["lines"] >= 1 and payload["skus"][0]["title"]
    assert payload["day"] == "2026-11-15" and rows[0]["key"].startswith("uncosted:")
    # Kunlik xulosada qatorlar soni bor (alohida xabar uni takrorlamaydi).
    daily = next(r for r in _rows(w, "owner", "daily_summary"))
    assert daily["payload"]["uncosted_lines"] >= 1
    # Takror: keyingi soat va keyingi kun (shu SKU yana sotilsa ham) — yangi xabar yo'q.
    evaluate(w, NOW + timedelta(hours=1))
    a.sale(w.ids["sku2"], date(2026, 11, 16), seller_profit=D(150_000))
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW + timedelta(days=1))
    fresh(w, NOW + timedelta(days=1))
    evaluate(w, NOW + timedelta(days=1))
    assert len(_rows(w, "owner", "uncosted_sales")) == 1


def test_weekly_summary_any_day_and_not_recomputed(world: World, monkeypatch: Any) -> None:
    """B6.4 (A6, A10): haftalik xulosa dushanba kuni yetib kelmasa ham hafta ichida birinchi imkoniyatda keladi; kalit
    bor bo'lsa og'ir hisob (kitob) qayta bajarilmaydi."""
    w = world
    _clean(w)
    wednesday = NOW + timedelta(days=2)  # chorshanba 10:00 — o'tgan hafta (2–8 → 9–15 noyabr)
    fresh(w, wednesday - timedelta(hours=1))
    evaluate(w, wednesday)
    weekly = _rows(w, "owner", "weekly_summary")
    assert [r["key"] for r in weekly] == ["weekly:2026-11-09"]
    assert (
        weekly[0]["payload"]["start"] == "2026-11-09"
        and weekly[0]["payload"]["end"] == "2026-11-15"
    )
    # Kalitlar bor — keyingi tekshiruvda xulosa qayta hisoblanmaydi.
    calls: list[date] = []
    real = notify.summary

    async def spy(conn: Any, period: Any, today: date, **kw: Any) -> Any:
        calls.append(period.start)
        return await real(conn, period, today, **kw)

    monkeypatch.setattr(notify, "summary", spy)
    evaluate(w, wednesday + timedelta(minutes=5))
    assert calls == []


def _set_outage(w: World, since: datetime | None) -> None:
    w.a.sql(
        "INSERT INTO provider_health (provider, outage_since) VALUES ('uzum', %s) "
        "ON CONFLICT (provider) DO UPDATE SET outage_since = EXCLUDED.outage_since",
        [since],
    )


def test_sync_key_invalid_reminds_every_three_days(world: World) -> None:
    """B6.4 (A4): kalit yaroqsiz — kritik, bir marta; tuzalmasa to'xtagan kundan boshlab har 3 kunda eslatma."""
    w = world
    _clean(w)
    _set_outage(w, None)
    fresh(w, NOW - timedelta(hours=2))  # 16.11 08:00 da oxirgi muvaffaqiyat
    w.a.sql("UPDATE mp_accounts SET status = 'invalid' WHERE org_id = %s", [w.org_id])
    evaluate(w)
    rows = _rows(w, "owner", "sync_stopped")
    assert len(rows) == 1 and rows[0]["critical"] and rows[0]["payload"]["reason"] == "key_invalid"
    assert rows[0]["key"].endswith(":2026-11-16:0")
    evaluate(w, NOW + timedelta(minutes=5))  # takror emas
    evaluate(w, NOW + timedelta(days=2))  # hali 0-davr
    assert len(_rows(w, "owner", "sync_stopped")) == 1
    evaluate(w, NOW + timedelta(days=3))  # 1-davr — eslatma
    reminders = _rows(w, "owner", "sync_stopped")
    assert len(reminders) == 2 and reminders[-1]["key"].endswith(":2026-11-16:1")
    w.a.sql("UPDATE mp_accounts SET status = 'active' WHERE org_id = %s", [w.org_id])


def test_sync_stale_once_not_during_outage_and_restored(world: World) -> None:
    """B6.4 (A4): "yangilanmayapti" — kritik emas, har to'xtash uchun bir marta, Uzum uzilishi paytida yo'q; sinxron
    tiklanganda bitta "tiklandi" xabari."""
    w = world
    _clean(w)
    w.a.sql("UPDATE mp_accounts SET status = 'active' WHERE org_id = %s", [w.org_id])
    # Uzum uzilishi belgilangan — "yangilanmayapti" yuborilmaydi.
    _set_outage(w, NOW - timedelta(hours=1))
    fresh(w, NOW - timedelta(hours=5))
    evaluate(w)
    assert _rows(w, "owner", "sync_stopped") == []
    # Uzilish tugadi, sinxron hali yangilanmagan — bir marta.
    _set_outage(w, None)
    evaluate(w, NOW + timedelta(minutes=5))
    evaluate(w, NOW + timedelta(minutes=10))
    stale = _rows(w, "owner", "sync_stopped")
    assert len(stale) == 1 and stale[0]["payload"]["reason"] == "stale" and not stale[0]["critical"]
    assert stale[0]["payload"]["shop_id"] == str(w.a.shop_id)
    # Tiklandi — bitta xabar, takror yo'q.
    fresh(w, NOW + timedelta(hours=1))
    evaluate(w, NOW + timedelta(hours=1))
    evaluate(w, NOW + timedelta(hours=1, minutes=5))
    rows = _rows(w, "owner", "sync_stopped")
    assert [r["payload"]["reason"] for r in rows] == ["stale", "restored"]
    assert rows[1]["key"] == f"sync_restored:{rows[0]['key']}" and not rows[1]["critical"]
    # Sog'lom do'konda boshqa "to'xtadi" bo'lmasa — yangi xabar yo'q.
    evaluate(w, NOW + timedelta(hours=2))
    assert len(_rows(w, "owner", "sync_stopped")) == 2


def test_cargo_late_event_once_per_purchase(world: World) -> None:
    """B5.1: "Kargo kechikmoqda" — kutilgan keldi sanasi (F25 "yo'l", bu yerda standart 20 kun) + 5 kundan o'tgan "Yo'lda"
    xarid; har xarid bir marta; ombor roli oladi."""
    w, a = world, world.a
    _clean(w)
    w.a.sql(
        "UPDATE orgs SET settings = jsonb_set(coalesce(settings, '{}'::jsonb), '{lead_days}', "
        '\'{"transit": 20, "handover": 2}\') WHERE id = %s',
        [w.org_id],
    )
    try:
        p = a.purchase(None, ordered_on=date(2026, 9, 1), title="Presslangan o'ram")
        a.line(p, w.ids["item"], 10)
        evaluate(w)
        rows = _rows(w, "warehouse", "cargo_late")
        assert len(rows) == 1 and rows[0]["key"] == f"cargo_late:{p}"
        payload = rows[0]["payload"]
        assert payload["purchase_id"] == str(p) and payload["title"] == "Presslangan o'ram"
        lead = w.a.run(lambda conn: org_lead(conn))[
            "transit"
        ]  # umumiy bazadagi boshqa xaridlar medianani o'zgartirishi mumkin
        expected = date(2026, 9, 1) + timedelta(days=math.ceil(lead))
        assert payload["expected"] == expected.isoformat()
        assert payload["days_late"] == (NOW.date() - expected).days
        assert _rows(w, "owner", "cargo_late") and not _rows(w, "accountant", "cargo_late")
        evaluate(w, NOW + timedelta(hours=1))  # takror emas
        assert len(_rows(w, "warehouse", "cargo_late")) == 1
        # "Keldi" belgilangach — yangi xabar yo'q (boshqa xarid ham kechikmagan).
        w.a.sql(
            "UPDATE purchases SET arrival_marked = true, arrived_on = %s WHERE id = %s",
            [date(2026, 11, 1), p],
        )
        evaluate(w, NOW + timedelta(days=1))
        assert len(_rows(w, "warehouse", "cargo_late")) == 1
    finally:
        w.a.sql("UPDATE orgs SET settings = settings - 'lead_days' WHERE id = %s", [w.org_id])


def test_ship_needed_notifies_only_new_skus(world: World, monkeypatch: Any) -> None:
    """B6.5: "Uzumga yuborish kerak" — `stock_critical` kabi: faqat ro'yxatga YANGI SKU kirganda bir marta; ro'yxat
    qisqarsa baza yangilanadi (xabar emas); ombor roli oladi, buxgalter olmaydi."""
    w = world
    _clean(w)
    sku_a, sku_b = w.ids["sku"], w.ids["sku2"]
    state: dict[str, list[Any]] = {"items": []}

    async def ship(conn: Any, today: date) -> list[Any]:
        return list(state["items"])

    monkeypatch.setattr(notify, "ship_needed", ship)
    fresh(w, NOW + timedelta(days=2))

    def step(at: datetime) -> None:
        evaluate(w, at)
        w.a.sql(
            "UPDATE notifications SET created_at = %s WHERE org_id = %s "
            "AND created_at = (SELECT max(created_at) FROM notifications WHERE org_id = %s)",
            [at, w.org_id, w.org_id],
        )

    def rows() -> list[
        dict[str, Any]
    ]:  # yuborilganlar (bazaviy ro'yxatni yangilovchi "skipped" qatorlarsiz)
        return [r for r in _rows(w, "warehouse", "ship_needed") if ":state:" not in r["key"]]

    state["items"] = [(sku_a, D("1.5"), 30)]
    step(NOW)
    assert [(r["payload"]["count"], r["payload"]["total"]) for r in rows()] == [(1, 1)]
    assert rows()[0]["payload"]["skus"][0]["qty"] == 30
    assert rows()[0]["payload"]["skus"][0]["days"] == "1.50"
    assert not _rows(w, "accountant", "ship_needed") and not rows()[0]["critical"]
    step(NOW + timedelta(hours=1))  # holat o'zgarmadi — takror yo'q
    step(NOW + timedelta(hours=25))
    assert len(rows()) == 1
    state["items"] = [(sku_a, D("1.5"), 30), (sku_b, D("0.5"), 10)]  # B yangi
    step(NOW + timedelta(hours=26))
    assert [(r["payload"]["count"], r["payload"]["total"]) for r in rows()][-1] == (1, 2)
    assert len(rows()) == 2
    state["items"] = []  # ro'yxat bo'shadi — xabar yo'q, baza yangilanadi
    step(NOW + timedelta(hours=27))
    assert len(rows()) == 2
    state["items"] = [(sku_a, D("1.5"), 30)]  # A qaytib kirdi — yana yangi
    step(NOW + timedelta(hours=28))
    assert len(rows()) == 3


def test_ship_needed_uses_plan_qty_or_own(world: World) -> None:
    """B6.5: yuboriladigan dona — F54 rejasi (maqsad qamrov sozlangan bo'lsa), aks holda omborimdagi son."""
    w, a = world, world.a
    item = a.insert("items", name="Yuborilsin")
    sku = a.insert(
        "mp_skus", shop_id=a.shop_id, external_id=9_401, sku_code="Yb", item_id=item, qty_active=2
    )
    a.sql(
        "UPDATE orgs SET settings = jsonb_set(coalesce(settings, '{}'::jsonb), '{lead_days}', "
        '\'{"transit": 20, "handover": 5}\') WHERE id = %s',
        [w.org_id],
    )
    today = NOW.date()
    for i in range(14):
        day = today - timedelta(days=i + 1)
        a.sale(sku, day, 2)
        a.insert("sku_daily", sku_id=sku, day=day, qty_active=2, qty_fbs=0)
    p = a.insert(
        "purchases", ordered_on=today - timedelta(days=40), received_on=today - timedelta(days=2)
    )
    a.line(p, item, 30, received=30)
    a.request(calc.Scope.PURCHASE)
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW)
    try:
        found = {s: (d, q) for s, d, q in w.a.run(lambda conn: notify.ship_needed(conn, today))}
        assert sku in found and found[sku][1] == 30  # reja sozlanmagan — omborimdagi son
        assert found[sku][0] <= 5  # Uzumda ~1 kun: topshirish muddatidan oz
        a.sql(
            "UPDATE orgs SET settings = jsonb_set(settings, '{ship_cover_days}', "
            '\'{"A": 5, "B": 5, "C": 5}\'::jsonb) WHERE id = %s',
            [w.org_id],
        )
        found = {s: (d, q) for s, d, q in w.a.run(lambda conn: notify.ship_needed(conn, today))}
        assert (
            0 < found[sku][1] < 30
        )  # F54 rejasi: tezlik × (5 + 5) − Uzumda 2 — omborimdagi 30 dan kam
    finally:
        a.sql(
            "UPDATE orgs SET settings = (settings - 'lead_days') - 'ship_cover_days' WHERE id = %s",
            [w.org_id],
        )


def test_lost_goods_from_quantity_missing_only_new_skus(world: World) -> None:
    """B5.4 (F31 (c)): "Yo'qolgan tovar" — faqat Uzumning `quantityMissing > 0` maydoni; ro'yxatga yangi SKU kirganda bir
    marta; qisqarsa jim; ombor roli oladi. Balans usuli ishlatilmaydi (real o'lchovda shovqinli)."""
    w, a = world, world.a
    _clean(w)
    sku = a.insert("mp_skus", shop_id=a.shop_id, external_id=9_501, sku_code="Yo'q")
    a.sql("UPDATE mp_skus SET raw = jsonb_build_object('quantityMissing', 3) WHERE id = %s", [sku])
    other = w.ids["sku"]
    a.sql(
        "UPDATE mp_skus SET raw = jsonb_build_object('quantityMissing', 0) WHERE id = %s", [other]
    )
    fresh(w, NOW + timedelta(days=2))
    try:
        found = w.a.run(lambda conn: notify.missing_skus(conn))
        assert (sku, 3) in found and all(i != other for i, _ in found)  # 0 — signal emas

        def step(at: datetime) -> None:
            evaluate(w, at)
            w.a.sql(
                "UPDATE notifications SET created_at = %s WHERE org_id = %s "
                "AND created_at = (SELECT max(created_at) FROM notifications WHERE org_id = %s)",
                [at, w.org_id, w.org_id],
            )

        def rows() -> list[dict[str, Any]]:
            return [r for r in _rows(w, "warehouse", "lost_goods") if ":state:" not in r["key"]]

        step(NOW)
        assert len(rows()) == 1 and str(sku) in rows()[0]["payload"]["ids"]
        assert any(s["qty"] == 3 for s in rows()[0]["payload"]["skus"])
        assert not _rows(w, "accountant", "lost_goods")
        step(NOW + timedelta(hours=1))  # o'zgarmadi — takror yo'q
        step(NOW + timedelta(hours=25))
        assert len(rows()) == 1
        a.sql(
            "UPDATE mp_skus SET raw = jsonb_build_object('quantityMissing', 0) WHERE id = %s", [sku]
        )
        step(NOW + timedelta(hours=26))  # signal yo'qoldi — xabar emas
        assert len(rows()) == 1
    finally:
        a.sql("UPDATE mp_skus SET raw = NULL WHERE id = %s", [sku])

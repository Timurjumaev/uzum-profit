"""Bot mantiqi (haqiqiy PostgreSQL, B6.2): bog'lash (bir martalik token, muddat, boshqa foydalanuvchiga ulangan),
``telegram_memberships()``, buyruqlar (rol bo'yicha), navbatni yuborish (faqat ulangan chatga, 24 soat oynasi, doimiy
va vaqtinchalik xato, takror yuborilmaydi)."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import test_purchases as tp
from psycopg.types.json import Jsonb
from test_reports import World
from upapi.db.session import make_engine
from upapi.routes.notifications import link_hash
from upbot import service
from upbot.service import LinkResult, SendError

db = tp.db
world = tp.world

NOW = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)  # Toshkent 10:00
TG_OWNER, TG_ACC = 7001, 7002


def run(w: World, fn: Any) -> Any:
    async def main() -> Any:
        engine = make_engine(w.a.db["app"])
        try:
            return await fn(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def user_of(w: World, role: str) -> Any:
    return w.a.sql(
        "SELECT m.user_id FROM memberships m JOIN users u ON u.id = m.user_id "
        "WHERE m.org_id = %s AND m.role = %s ORDER BY u.created_at DESC LIMIT 1",
        [w.org_id, role],
    )[0][0]


def new_link(w: World, role: str, expires: datetime = NOW + timedelta(minutes=15)) -> str:
    token = secrets.token_urlsafe(18)
    w.a.insert(
        "notification_links",
        user_id=user_of(w, role),
        token_hash=link_hash(token),
        expires_at=expires,
    )
    return w.org_id.hex + token


def link(w: World, param: str, tg: int) -> tuple[LinkResult, str | None]:
    return run(w, lambda e: service.link(e, param, tg, tg, NOW))  # type: ignore[no-any-return]


class FakeSender:
    def __init__(self, fail: dict[int, SendError] | None = None) -> None:
        self.sent: list[tuple[int, str, str | None]] = []
        self.langs: list[str] = []
        self.fail = fail or {}

    async def send(self, chat_id: int, text: str, url: str | None, lang: str = "uz") -> None:
        if chat_id in self.fail:
            raise self.fail[chat_id]
        self.sent.append((chat_id, text, url))
        self.langs.append(lang)


def test_link_once_expiry_and_taken(world: World) -> None:
    w = world
    assert link(w, "x", TG_OWNER) == (LinkResult.INVALID, None)
    assert link(w, "0" * 32 + "abc", TG_OWNER) == (
        LinkResult.INVALID,
        None,
    )  # boshqa (yo'q) tashkilot
    assert link(w, "z" * 40, TG_OWNER) == (LinkResult.INVALID, None)
    assert (
        link(w, new_link(w, "owner", NOW - timedelta(seconds=1)), TG_OWNER)[0] is LinkResult.EXPIRED
    )
    param = new_link(w, "owner")
    result, org = link(w, param, TG_OWNER)
    assert result is LinkResult.OK and org
    assert link(w, param, TG_OWNER) == (LinkResult.INVALID, None)  # bir marta
    owner = user_of(w, "owner")
    assert w.a.sql(
        "SELECT target, active FROM notification_channels WHERE user_id = %s AND kind = 'telegram'",
        [owner],
    ) == [(str(TG_OWNER), True)]
    # Qayta ulash — eski chat almashadi (bitta kanal).
    assert link(w, new_link(w, "owner"), TG_OWNER)[0] is LinkResult.OK
    assert len(w.a.sql("SELECT 1 FROM notification_channels WHERE user_id = %s", [owner])) == 1
    # Shu chat (shaxsiy chat id = Telegram id) tashkilotda boshqa foydalanuvchiga ulana olmaydi.
    assert link(w, new_link(w, "manager"), TG_OWNER) == (LinkResult.TAKEN, None)
    assert link(w, new_link(w, "accountant"), TG_ACC)[0] is LinkResult.OK
    people = run(w, lambda e: service.identities(e, TG_OWNER))
    assert [(p.org_id, p.role) for p in people] == [(w.org_id, "owner")]
    assert run(w, lambda e: service.identities(e, 999)) == []
    # API: holat ko'rinadi; uzish — shu tashkilotda.
    assert tp.ok(tp.send(w, "GET", "notifications/settings"))["telegram_linked"] is True
    assert tp.ok(tp.send(w, "GET", "notifications/settings", "manager"))["telegram_linked"] is False


def test_commands_by_role(world: World) -> None:
    w = world
    out = run(w, lambda e: service.command(e, TG_OWNER, "kecha", NOW, "https://app.example"))
    assert len(out) == 1 and out[0].text.startswith("📊 Kecha, 15.11.2026")
    assert out[0].path == "/pnl?from=2026-11-15&to=2026-11-15"
    assert (
        "Buyurtmalar hali yangilanmagan" in out[0].text
    )  # sinxron yo'q — to'liq emas deb aytiladi
    for name, head in (
        ("bugun", "📊 Bugun"),
        ("hafta", "📊 Hafta: 16.11.2026"),
        ("oy", "📊 Oy: 01.11.2026"),
    ):
        assert run(w, lambda e, n=name: service.command(e, TG_OWNER, n, NOW, ""))[
            0
        ].text.startswith(head)
    stock = run(w, lambda e: service.command(e, TG_OWNER, "qoldiq", NOW, ""))
    assert stock[0].text == "Kritik qoldiq yoʻq." and stock[0].path == "/inventory"
    assert run(w, lambda e: service.command(e, TG_ACC, "qoldiq", NOW, ""))[0].text.startswith(
        "Bu maʼlumot"
    )
    assert (
        run(w, lambda e: service.command(e, TG_OWNER, "sozlamalar", NOW, ""))[0].path == "/settings"
    )
    assert "Buyruqlar" in run(w, lambda e: service.command(e, TG_OWNER, "nima", NOW, ""))[0].text
    assert run(w, lambda e: service.command(e, 999, "kecha", NOW, ""))[0].text.startswith(
        "Bu Telegram hali"
    )
    assert service.page_url("https://app.example/", "/x") == "https://app.example/x"
    assert service.page_url("http://localhost:5173", "/x") is None
    assert service.page_url("https://a", None) is None


def _queue(
    w: World, role: str, event: str, key: str, payload: dict[str, Any], **extra: Any
) -> None:
    w.a.insert(
        "notifications",
        user_id=user_of(w, role),
        event=event,
        dedupe_key=key,
        payload=Jsonb(payload),
        due_at=extra.pop("due_at", NOW - timedelta(minutes=1)),
        **extra,
    )


def test_deliver_sends_once_and_handles_errors(world: World) -> None:
    w = world
    fine = {
        "amount": "7000.00",
        "name": "Jarima",
        "shop": "byDurii",
        "on": "2026-11-15",
        "code": None,
    }
    _queue(w, "owner", "new_fine", "fine:1", fine)
    _queue(
        w, "owner", "new_fine", "fine:later", fine, due_at=NOW + timedelta(hours=1)
    )  # tinch soat
    _queue(
        w, "owner", "new_fine", "fine:old", fine, created_at=NOW - timedelta(days=2)
    )  # eski navbat
    _queue(w, "manager", "new_fine", "fine:1", fine)  # Telegram ulanmagan
    _queue(w, "owner", "payout_late", "bad:1", {})  # matni yo'q hodisa
    _queue(w, "accountant", "new_fine", "fine:1", fine)
    sender = FakeSender(fail={TG_ACC: SendError("RetryAfter", permanent=False)})
    assert run(w, lambda e: service.deliver(e, sender, "https://app.example", NOW)) == 1
    assert sender.sent[0][0] == TG_OWNER
    assert sender.sent[0][1].startswith("Yangi jarima: 7 000 soʻm")
    assert sender.sent[0][2] == "https://app.example/expenses"
    status = dict(
        w.a.sql(
            "SELECT n.dedupe_key || ':' || m.role, n.status FROM notifications n JOIN memberships m "
            "ON m.user_id = n.user_id AND m.org_id = n.org_id WHERE n.event IN ('new_fine', 'payout_late')"
        )
    )
    assert status["fine:1:owner"] == "sent" and status["fine:later:owner"] == "pending"
    assert status["fine:old:owner"] == "pending" and status["fine:1:manager"] == "pending"
    assert status["bad:1:owner"] == "failed" and status["fine:1:accountant"] == "pending"
    # Takror yuborilmaydi; vaqtinchalik xato — 5 urinishdan keyin failed.
    for _ in range(4):
        assert run(w, lambda e: service.deliver(e, sender, "", NOW)) == 0
    assert w.a.sql(
        "SELECT n.status, n.attempts FROM notifications n JOIN memberships m ON m.user_id = n.user_id "
        "AND m.org_id = n.org_id WHERE m.role = 'accountant' AND n.dedupe_key = 'fine:1'"
    ) == [("failed", 5)]
    # Doimiy xato (bot bloklangan) — failed va kanal o'chadi.
    _queue(w, "owner", "new_fine", "fine:2", fine)
    blocked = FakeSender(fail={TG_OWNER: SendError("TelegramForbiddenError", permanent=True)})
    assert run(w, lambda e: service.deliver(e, blocked, "", NOW)) == 0
    owner = user_of(w, "owner")
    assert w.a.sql("SELECT active FROM notification_channels WHERE user_id = %s", [owner]) == [
        (False,)
    ]
    assert tp.ok(tp.send(w, "GET", "notifications/settings"))["telegram_linked"] is False
    # Uzish (API) — kanal o'chiriladi.
    assert tp.send(w, "DELETE", "notifications/telegram", "accountant").status_code == 204
    assert not w.a.sql(
        "SELECT 1 FROM notification_channels WHERE user_id = %s", [user_of(w, "accountant")]
    )


FINE = {"amount": "7000.00", "name": "Jarima", "shop": "byDurii", "on": "2026-11-15", "code": None}


def _status(w: World, key: str) -> tuple[Any, ...]:
    row = w.a.sql(
        "SELECT status, attempts, error, due_at FROM notifications WHERE dedupe_key = %s", [key]
    )[0]
    return tuple(row)


def _owner_channel(w: World) -> None:
    """Oldingi testlar kanalni o'chirgan bo'lishi mumkin (umumiy ``world``) — owner kanali faol, boshqa navbat bo'sh."""
    w.a.sql(
        "UPDATE notification_channels SET active = true WHERE user_id = %s", [user_of(w, "owner")]
    )
    w.a.sql("DELETE FROM notifications WHERE status = 'pending'")


def test_bad_request_fails_message_but_keeps_channel(world: World) -> None:
    """B6.4 (A5): Telegram'ning ``BadRequest`` (matn uzun, tugma havolasi noto'g'ri) — bizning xatomiz: faqat shu xabar
    ``failed``, foydalanuvchining Telegram'i uzilmaydi va qayta urinilmaydi."""
    w = world
    _owner_channel(w)
    _queue(w, "owner", "new_fine", "fine:bad", FINE)
    sender = FakeSender(fail={TG_OWNER: SendError("TelegramBadRequest", final=True)})
    assert run(w, lambda e: service.deliver(e, sender, "", NOW)) == 0
    status, attempts, error, _ = _status(w, "fine:bad")
    assert (status, attempts, error) == ("failed", 1, "TelegramBadRequest")
    assert w.a.sql(
        "SELECT active FROM notification_channels WHERE user_id = %s", [user_of(w, "owner")]
    ) == [(True,)]
    # Keyingi xabar yetib boradi — kanal faol.
    _queue(w, "owner", "new_fine", "fine:next", FINE)
    ok_sender = FakeSender()
    assert run(w, lambda e: service.deliver(e, ok_sender, "", NOW)) == 1


def test_retry_after_waits_without_burning_attempts(world: World) -> None:
    """B6.4 (A5): ``retry_after`` — urinish sanalmaydi, xabar kutish muddatidan keyin qayta yuboriladi, shu aylanishda
    boshqa xabar yuborilmaydi (Telegram baribir rad etadi)."""
    w = world
    _owner_channel(w)
    _queue(w, "owner", "new_fine", "fine:a", FINE)
    _queue(w, "owner", "new_fine", "fine:b", FINE, due_at=NOW - timedelta(seconds=30))
    sender = FakeSender(fail={TG_OWNER: SendError("retry_after", retry_after=20.0)})
    assert run(w, lambda e: service.deliver(e, sender, "", NOW)) == 0
    # Birinchi navbatdagi (fine:a, due_at eskiroq) — kutishga o'tdi; ikkinchisiga tegilmadi.
    status_a = _status(w, "fine:a")
    assert status_a[:3] == ("pending", 0, "retry_after")
    assert status_a[3] == NOW + timedelta(seconds=21)
    assert _status(w, "fine:b")[:3] == ("pending", 0, None)
    # Kutish tugagach — yuboriladi (urinishlar yoqilmagan).
    later = NOW + timedelta(seconds=30)
    ok_sender = FakeSender()
    assert run(w, lambda e: service.deliver(e, ok_sender, "", later)) == 2
    assert _status(w, "fine:a")[0] == "sent" and _status(w, "fine:b")[0] == "sent"


def test_purge_old_keeps_pending_and_recent(world: World) -> None:
    """B6.4 (A9): 90 kundan eski yuborilgan / muvaffaqiyatsiz qatorlar o'chadi; pending va yangilari qoladi."""
    w = world
    old = NOW - timedelta(days=91)
    _queue(w, "owner", "new_fine", "old:sent", FINE, created_at=old, status="sent")
    _queue(w, "owner", "new_fine", "old:failed", FINE, created_at=old, status="failed")
    _queue(w, "owner", "new_fine", "old:pending", FINE, created_at=old)
    _queue(
        w, "owner", "new_fine", "new:sent", FINE, created_at=NOW - timedelta(days=10), status="sent"
    )
    assert run(w, lambda e: service.purge_old(e, w.org_id, NOW)) == 2
    keys = {
        r[0]
        for r in w.a.sql("SELECT dedupe_key FROM notifications WHERE dedupe_key ~ '^(old|new):'")
    }
    assert keys == {"old:pending", "new:sent"}


SUMMARY = {
    "start": "2026-11-15",
    "end": "2026-11-15",
    "orders": 12,
    "units": 14,
    "revenue": "1234567.50",
    "net_profit": "276709.00",
    "net_profit_expected": "120000.00",
    "rate": "0.613",
    "canceled": 2,
    "uncosted_lines": 0,
    "fresh_at": "2026-11-16T04:30:00+00:00",
}


def test_deliver_expired_skipped_monday_merged_and_footer(world: World) -> None:
    """B6.4 (A18–A21): o'z kunidan o'tgan kunlik xulosa yuborilmaydi (``skipped``); dushanba kuni haftalik va kunlik
    xulosa — bitta xabar; "— tashkilot" imzosi faqat bir necha tashkilotda (bu yerda bitta — yo'q); til yuboruvchiga
    uzatiladi ("Batafsil" tugmasi uchun)."""
    w = world
    _owner_channel(w)
    weekly = {**SUMMARY, "start": "2026-11-09", "end": "2026-11-15"}
    _queue(w, "owner", "weekly_summary", "weekly:2026-11-09", weekly)
    _queue(w, "owner", "daily_summary", "daily:2026-11-15", SUMMARY)
    old = {**SUMMARY, "start": "2026-11-13", "end": "2026-11-13"}
    _queue(w, "owner", "daily_summary", "daily:2026-11-13", old)  # 2 kun oldingi — muddati o'tgan
    sender = FakeSender()
    assert run(w, lambda e: service.deliver(e, sender, "https://app.example", NOW)) == 2
    assert len(sender.sent) == 1 and sender.langs == ["uz"]
    chat, text, url = sender.sent[0]
    assert chat == TG_OWNER and url == "https://app.example/pnl?from=2026-11-09&to=2026-11-15"
    assert text.index("📊 Hafta: 09.11.2026") < text.index("📊 Kunlik xulosa, 15.11.2026")
    assert "\n\n— " not in text  # bitta tashkilot — imzo yo'q
    assert (
        _status(w, "weekly:2026-11-09")[0] == "sent" and _status(w, "daily:2026-11-15")[0] == "sent"
    )
    old_status = _status(w, "daily:2026-11-13")
    assert old_status[0] == "skipped" and old_status[2] == "expired"


def test_commands_unfinished_note_and_previous_period(world: World) -> None:
    """B6.4 (A18–A21): tugamagan davr — izoh; ``/hafta`` va ``/oy`` davr boshida — yonida oldingi to'liq davr."""
    w = world
    monday = run(w, lambda e: service.command(e, TG_OWNER, "hafta", NOW, ""))[0].text
    assert "Davr hali tugamagan" in monday
    assert "Oldingi toʻliq davr:" in monday and "📊 Hafta: 09.11.2026 – 15.11.2026" in monday
    today_text = run(w, lambda e: service.command(e, TG_OWNER, "bugun", NOW, ""))[0].text
    assert "Davr hali tugamagan" in today_text and "Oldingi" not in today_text
    # Davr o'rtasida — oldingi davr yo'q.
    thursday = NOW + timedelta(days=3)
    assert (
        "Oldingi"
        not in run(w, lambda e: service.command(e, TG_OWNER, "hafta", thursday, ""))[0].text
    )
    # Oy: 1-2-kun — oldingi oy; 16-kun — yo'q.
    assert "Oldingi" not in run(w, lambda e: service.command(e, TG_OWNER, "oy", NOW, ""))[0].text
    first = datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    month = run(w, lambda e: service.command(e, TG_OWNER, "oy", first, ""))[0].text
    assert "Oldingi toʻliq davr:" in month and "📊 Oy: 01.11.2026 – 30.11.2026" in month
    # "Kecha" — tugagan davr, izohsiz.
    assert (
        "Davr hali tugamagan"
        not in run(w, lambda e: service.command(e, TG_OWNER, "kecha", NOW, ""))[0].text
    )


def test_dashboard_attention_telegram_lost(world: World) -> None:
    """B6.4 (A5): kanal uzilgan (doimiy yetkazish xatosi — ``active = false``) bo'lsa ilovada "Diqqat" sanog'i 1; faol yoki
    o'zi uzgan (qator o'chadi) yoki hech qachon ulanmagan — 0."""
    w = world
    _owner_channel(w)
    owner = user_of(w, "owner")

    def lost() -> int:
        dash = tp.ok(tp.send(w, "GET", "dashboard?start=2026-11-01&end=2026-11-16"))
        return int(dash["attention"]["telegram_lost"])

    assert lost() == 0  # faol kanal
    w.a.sql("UPDATE notification_channels SET active = false WHERE user_id = %s", [owner])
    assert lost() == 1  # uzilgan — "qayta ulang"
    w.a.sql("UPDATE notifications SET channel_id = NULL WHERE user_id = %s", [owner])
    w.a.sql("DELETE FROM notification_channels WHERE user_id = %s", [owner])
    assert lost() == 0  # o'zi uzgan / ulanmagan — qator yo'q

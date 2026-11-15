"""Bot mantiqi (B6.2, 02 M15) — aiogram'siz, testlanadigan: bog'lash, buyruqlar, navbatdagi xabarlarni yuborish.

- **Bog'lash**: ilova ``t.me/<bot>?start=<tashkilot id'si 32 belgi><token>`` beradi (``upapi.routes.notifications``).
  Bot tashkilot tranzaksiyasida token xeshini tekshiradi (15 daqiqa, bir marta) va chatni ``notification_channels`` ga
  yozadi (shaxsiy chat id = Telegram foydalanuvchi id; buyruqlar shu orqali — ``telegram_memberships()``). Bitta chat
  tashkilot ichida bitta foydalanuvchiga.
- **Buyruqlar**: ``/bugun``, ``/kecha``, ``/hafta``, ``/oy`` — xulosa (moliya ko'radigan rollar), ``/qoldiq`` — kritik
  qoldiq (ombor ko'radigan rollar), ``/sozlamalar`` — ilovadagi sozlamalar. Har tashkilot alohida xabar.
- **Yuborish**: har 30 soniyada ulangan tashkilotlar bo'yicha ``pending`` va vaqti kelgan (``due_at``) qatorlar —
  foydalanuvchining faol Telegram chatiga. Oxirgi 24 soatdagisi (ulanishdan oldingi eski navbat yog'ilib ketmasin).
  Bloklangan / topilmagan chat — ``failed`` va kanal o'chiriladi; vaqtinchalik xato — qayta (5 urinishgacha).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine
from upapi import notify
from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.logs import get_logger
from upapi.routes.notifications import link_hash
from upapi.sync.jobs import due_accounts
from upcore.metrics import Period
from upcore.notify import Audience, audience_of, week_start

from upbot import messages as msg

MAX_ATTEMPTS = 5
WINDOW = timedelta(hours=24)
BATCH = 50
COMMANDS = ("bugun", "kecha", "hafta", "oy", "qoldiq", "sozlamalar")
_log = get_logger("upbot")


@dataclass(frozen=True)
class Identity:
    org_id: UUID
    user_id: UUID
    role: str
    org_name: str
    language: str


class LinkResult(StrEnum):
    OK = "ok"
    INVALID = "invalid"
    EXPIRED = "expired"
    TAKEN = "taken"


class SendError(Exception):
    """Yuborilmadi. ``permanent`` — chat yo'q / bot bloklangan (qayta urinilmaydi, kanal o'chadi)."""

    def __init__(self, reason: str, *, permanent: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.permanent = permanent


class Sender(Protocol):
    async def send(self, chat_id: int, text: str, url: str | None) -> None: ...


def page_url(web_url: str, path: str | None) -> str | None:
    """ "Batafsil" havolasi — faqat HTTPS (Telegram ``localhost`` tugmasini qabul qilmaydi)."""
    if path is None or not web_url.startswith("https://"):
        return None
    return web_url.rstrip("/") + path


async def identities(engine: AsyncEngine, tg_user_id: int) -> list[Identity]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT org_id, user_id, role, org_name, language FROM telegram_memberships(:tg)"),
            {"tg": tg_user_id},
        )
        return [Identity(r.org_id, r.user_id, r.role, r.org_name, r.language) for r in rows]


def parse_start(param: str) -> tuple[UUID, str] | None:
    if len(param) < 33:
        return None
    try:
        return uuid.UUID(hex=param[:32]), param[32:]
    except ValueError:
        return None


async def link(
    engine: AsyncEngine, param: str, tg_user_id: int, chat_id: int, now: datetime
) -> tuple[LinkResult, str | None]:
    """``/start <param>``: chatni foydalanuvchiga bog'laydi. Qaytaradi: natija va tashkilot nomi."""
    parsed = parse_start(param)
    if parsed is None:
        return LinkResult.INVALID, None
    org_id, token = parsed
    nl = m.notification_links
    async with org_transaction(engine, org_id) as conn:
        row = (
            await conn.execute(
                select(nl).where(nl.c.token_hash == link_hash(token)).with_for_update()
            )
        ).first()
        if row is None or row.used_at is not None:
            return LinkResult.INVALID, None
        if row.expires_at <= now:
            return LinkResult.EXPIRED, None
        user_id = row.user_id
    nc = m.notification_channels
    async with org_transaction(engine, org_id, user_id) as conn:
        other = await conn.scalar(
            select(nc.c.user_id).where(
                nc.c.kind == "telegram", nc.c.target == str(chat_id), nc.c.user_id != user_id
            )
        )
        if other is not None:
            return LinkResult.TAKEN, None
        await conn.execute(update(nl).where(nl.c.id == row.id).values(used_at=now))
        await conn.execute(delete(nc).where(nc.c.user_id == user_id, nc.c.kind == "telegram"))
        await conn.execute(
            insert(nc).values(org_id=org_id, user_id=user_id, kind="telegram", target=str(chat_id))
        )
        name = await conn.scalar(select(m.orgs.c.name).where(m.orgs.c.id == org_id))
    _log.info("telegram_linked", org_id=str(org_id))
    return LinkResult.OK, name


def periods(today: date) -> dict[str, tuple[Period, str]]:
    yesterday = today - timedelta(days=1)
    return {
        "bugun": (Period(today, today), "today"),
        "kecha": (Period(yesterday, yesterday), "yesterday"),
        "hafta": (Period(week_start(today), today), "week"),
        "oy": (Period(today.replace(day=1), today), "month"),
    }


async def command(
    engine: AsyncEngine, tg_user_id: int, name: str, now: datetime, web_url: str
) -> list[msg.Message]:
    """Buyruq javoblari (har tashkilot — alohida xabar)."""
    people = await identities(engine, tg_user_id)
    if not people:
        return [msg.Message(msg.t("uz", "not_linked"), None)]
    today = now.astimezone(msg.TASHKENT).date()
    out: list[msg.Message] = []
    for who in people:
        lang = msg.lang_of(who.language)
        footer = f"\n\n— {who.org_name}" if len(people) > 1 else ""
        if name == "sozlamalar":
            out.append(msg.Message(msg.t(lang, "settings") + footer, "/settings"))
            continue
        if name not in COMMANDS:
            out.append(msg.Message(msg.t(lang, "help"), None))
            break
        audience = audience_of(who.role)
        async with org_transaction(engine, who.org_id, who.user_id) as conn:
            if name == "qoldiq":
                if Audience.STOCK not in audience:
                    out.append(msg.Message(msg.t(lang, "no_access") + footer, None))
                    continue
                found = await notify.stock_critical(conn, today)
                text_ = (
                    msg.notification(found.event.value, found.payload, lang).text
                    if found
                    else msg.t(lang, "no_stock_critical")
                )
                out.append(msg.Message(text_ + footer, "/inventory"))
                continue
            if Audience.FINANCE not in audience:
                out.append(msg.Message(msg.t(lang, "no_access") + footer, None))
                continue
            period, title = periods(today)[name]
            data = await notify.summary(conn, period, today, require_fresh=False)
            assert data is not None
            path = f"/pnl?from={period.start}&to={period.end}"
            out.append(msg.Message(msg.summary(data, lang, title, partial=True) + footer, path))
    return out


async def deliver(engine: AsyncEngine, sender: Sender, web_url: str, now: datetime) -> int:
    """Navbatdagi xabarlarni yuboradi. Qaytaradi: yuborilganlar soni."""
    sent = 0
    for org_id in sorted({org for org, _ in await due_accounts(engine)}):
        try:
            sent += await _deliver_org(engine, org_id, sender, web_url, now)
        except Exception as exc:
            _log.warning("deliver_failed", org_id=str(org_id), error_code=type(exc).__name__)
    return sent


async def _deliver_org(
    engine: AsyncEngine, org_id: UUID, sender: Sender, web_url: str, now: datetime
) -> int:
    n, nc, u = m.notifications, m.notification_channels, m.users
    sent = 0
    async with org_transaction(engine, org_id) as conn:
        org = await conn.scalar(select(m.orgs.c.name).where(m.orgs.c.id == org_id))
        rows = list(
            await conn.execute(
                select(n, nc.c.id.label("ch"), nc.c.target, u.c.language)
                .join(nc, (nc.c.user_id == n.c.user_id) & (nc.c.kind == "telegram") & nc.c.active)
                .join(u, u.c.id == n.c.user_id)
                .where(n.c.status == "pending", n.c.due_at <= now, n.c.created_at >= now - WINDOW)
                .order_by(n.c.due_at, n.c.created_at, n.c.id)
                .limit(BATCH)
                .with_for_update(of=n, skip_locked=True)
            )
        )
        for r in rows:
            values: dict[str, object]
            try:
                lang = msg.lang_of(r.language)
                body = msg.notification(r.event, r.payload, lang, org)
                await sender.send(int(r.target), body.text, page_url(web_url, body.path))
                values = {"status": "sent", "sent_at": now, "channel_id": r.ch, "error": None}
                sent += 1
            except SendError as exc:
                attempts = r.attempts + 1
                values = {"attempts": attempts, "error": exc.reason[:200]}
                if exc.permanent or attempts >= MAX_ATTEMPTS:
                    values["status"] = "failed"
                if exc.permanent:
                    await conn.execute(update(nc).where(nc.c.id == r.ch).values(active=False))
            except (ValueError, KeyError) as exc:
                values = {"status": "failed", "error": type(exc).__name__}
            await conn.execute(
                update(n).where(n.c.id == r.id).values(**values, updated_at=func.now())
            )
    return sent

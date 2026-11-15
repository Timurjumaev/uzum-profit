"""Bildirishnomalar: hodisalarni topish va navbatga yozish (B6.1, 02 M15).

Har 5 daqiqada (``notify.tick``) har tashkilot uchun: a'zolar va ularning qoidalari (``notification_rules``, yo'q bo'lsa
katalog standarti — ``upcore.notify.CATALOG``) yuklanadi, yoqilgan hodisalar topiladi va har oluvchiga bitta
``notifications`` qatori yoziladi. Takror yo'q: ``UNIQUE (org_id, user_id, dedupe_key)`` — ``ON CONFLICT DO NOTHING``
(02 M15: "bitta hodisa takror yuborilmaydi"). Tinch soatlarda kritik bo'lmagan hodisa ``due_at`` — tinch soat
tugaganda (``upcore.notify.due_at``). Yuborish — B6.2 (Telegram), shu jadvaldan.

Hodisalar (ishlaydiganlari; qolganlari katalogda ``stage`` bilan):

- **Kunlik xulosa** — foydalanuvchi tanlagan vaqtdan keyin, kecha: buyurtmalar (F45), tushum (F3), sof foyda (F12),
  bekorlar (F17). Buyurtmalar sinxroni kecha oxirigacha yetib kelmagan bo'lsa yuborilmaydi (keyingi tekshiruvda) —
  Uzum uzilishida "sotuv yo'q" xabari bormasin.
- **Haftalik xulosa** — dushanba, o'tgan hafta (xuddi shu ko'rsatkichlar).
- **Qoldiq kritik** (F26) — kuniga bir marta, kritik SKU'lar soni va birinchi 5 tasi.
- **Zarar bilan sotuv** (F53) — SKU'ning oxirgi N ta sotuvi zararda; kuniga bir marta, SKU'lar ro'yxati.
- **Tannarxsiz sotuvlar** — kecha tannarxi noma'lum sotuv qatorlari bo'lsa, kuniga bir marta.
- **Yangi jarima** — oxirgi 3 kunda paydo bo'lgan jarima xarajati (har biri bir marta).
- **Postavka kamomadi** — Uzum kam qabul qilgan va qaror yozilmagan farq (TM7).
- **Sinxron to'xtadi** (kritik) — faol do'kon buyurtmalari N soatdan beri yangilanmagan yoki kalit yaroqsiz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from upcore.expenses import ExpenseCategory
from upcore.inventory import StockStatus
from upcore.metrics import COUNTED, Period, status_group
from upcore.notify import (
    CATALOG,
    QUIET_FROM,
    QUIET_TO,
    Event,
    audience_of,
    due_at,
    line_profit,
    loss_streak,
    merged_params,
    parse_hhmm,
    summary_due,
    week_start,
)

from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.logs import get_logger
from upapi.reports import cells as rc
from upapi.reports import receiving as rr
from upapi.reports.common import Filters, freshness, sku_catalog
from upapi.reports.stock import load_stock

TASHKENT = ZoneInfo("Asia/Tashkent")
TOP = 5
FINE_DAYS = 3
_log = get_logger("upapi.notify")


@dataclass(frozen=True)
class Found:
    """Topilgan hodisa (tashkilot darajasida): har oluvchiga shu ``dedupe_key`` bilan bitta qator."""

    event: Event
    dedupe_key: str
    payload: dict[str, Any]


@dataclass
class Recipient:
    user_id: UUID
    role: str
    rules: dict[Event, tuple[bool, dict[str, Any]]] = field(default_factory=dict)
    quiet_from: time | None = QUIET_FROM
    quiet_to: time | None = QUIET_TO

    def wants(self, event: Event) -> bool:
        spec = CATALOG[event]
        if spec.stage is not None or spec.audience not in audience_of(self.role):
            return False
        enabled, _ = self.rules.get(event, (spec.default_enabled, {}))
        return enabled

    def params(self, event: Event) -> dict[str, Any]:
        return merged_params(event, self.rules.get(event, (True, {}))[1])


async def recipients(conn: AsyncConnection) -> list[Recipient]:
    """Tashkilot a'zolari, qoidalari va tinch soatlari bilan."""
    out = {
        r.user_id: Recipient(r.user_id, r.role)
        for r in await conn.execute(select(m.memberships.c.user_id, m.memberships.c.role))
    }
    nr, npf = m.notification_rules, m.notification_prefs
    known = {e.value for e in Event}
    for r in await conn.execute(select(nr.c.user_id, nr.c.event, nr.c.enabled, nr.c.params)):
        if r.user_id in out and r.event in known:
            out[r.user_id].rules[Event(r.event)] = (r.enabled, dict(r.params or {}))
    for q in await conn.execute(select(npf.c.user_id, npf.c.quiet_from, npf.c.quiet_to)):
        if q.user_id in out:
            out[q.user_id].quiet_from, out[q.user_id].quiet_to = q.quiet_from, q.quiet_to
    return sorted(out.values(), key=lambda x: str(x.user_id))


# --- Hodisalar ------------------------------------------------------------------------------


def _num(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


async def summary(
    conn: AsyncConnection, period: Period, today: date, *, require_fresh: bool = True
) -> dict[str, Any] | None:
    """Davr xulosasi (Dashboard bilan bitta hisob — ``reports.cells``). Buyurtmalar sinxroni davr oxirigacha yetib
    kelmagan bo'lsa ``None`` (raqam yo'q ≠ sotuv yo'q, tamoyil 8); ``require_fresh=False`` (bot buyrug'i, davr hali
    tugamagan) — raqamlar beriladi, ``fresh_at`` bilan (xabarda "ma'lumot yangiligi")."""
    fresh = (await freshness(conn, ["orders"]))["orders"]
    end = datetime.combine(period.end + timedelta(days=1), time(0), TASHKENT)
    if require_fresh and (fresh is None or fresh < end):
        return None
    f = Filters(period, None, today)
    book = await rc.load_book(conn, period, today)
    s = book.scoped(f, period).statement()
    counts = await rc.order_counts(conn, f, period)
    flow = (await rc.sale_sums(conn, f, period=period)).get(None)
    return {
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "orders": sum(c[0] for c in counts.values()),
        "units": s.units,
        "revenue": _num(s.revenue.amount),
        "net_profit": _num(s.net_profit.amount),
        "canceled": flow.canceled if flow else 0,
        "uncosted_lines": s.uncovered_lines,
        "fresh_at": None if fresh is None else fresh.isoformat(),
    }


async def stock_critical(conn: AsyncConnection, today: date) -> Found | None:
    stock = await load_stock(conn, None, today)
    critical = sorted(
        (x for x in stock.skus.values() if x.status is StockStatus.CRITICAL),
        key=lambda x: (
            x.days_of_stock if x.days_of_stock is not None else Decimal(0),
            str(x.sku_id),
        ),
    )
    if not critical:
        return None
    catalog = await sku_catalog(conn, ids=[x.sku_id for x in critical[:TOP]])
    return Found(
        Event.STOCK_CRITICAL,
        f"stock_critical:{today.isoformat()}",
        {
            "count": len(critical),
            "skus": [
                {
                    "sku_id": str(x.sku_id),
                    "title": catalog[x.sku_id].title if x.sku_id in catalog else None,
                    "days": None if x.days_of_stock is None else str(x.days_of_stock),
                }
                for x in critical[:TOP]
            ],
        },
    )


async def loss_sales(conn: AsyncConnection, today: date, streak: int) -> Found | None:
    """F53: har SKU'ning oxirgi ``streak`` ta hisobga olinadigan sotuvi (oxirgi 30 kun)."""
    si, sc = m.sale_items, m.sale_costs
    rows = await conn.execute(
        select(si.c.sku_id, si.c.status, si.c.seller_profit, sc.c.cogs)
        .join(sc, sc.c.sale_item_id == si.c.id, isouter=True)
        .where(
            si.c.sku_id.is_not(None),
            si.c.ordered_at >= datetime.combine(today - timedelta(days=30), time(0), TASHKENT),
        )
        .order_by(si.c.sku_id, si.c.ordered_at, si.c.external_id)
    )
    by_sku: dict[UUID, list[Decimal | None]] = {}
    for r in rows:
        if status_group(r.status) in COUNTED:
            by_sku.setdefault(r.sku_id, []).append(line_profit(r.seller_profit, r.cogs))
    losing = sorted(k for k, v in by_sku.items() if loss_streak(v, streak))
    if not losing:
        return None
    catalog = await sku_catalog(conn, ids=losing[:TOP])
    return Found(
        Event.LOSS_SALES,
        f"loss_sales:{today.isoformat()}",
        {
            "count": len(losing),
            "streak": streak,
            "skus": [
                {"sku_id": str(k), "title": catalog[k].title if k in catalog else None}
                for k in losing[:TOP]
            ],
        },
    )


async def new_fines(conn: AsyncConnection, now: datetime) -> list[Found]:
    e = m.mp_expenses
    shops = {r.id: r.alias or r.name for r in await conn.execute(select(m.shops))}
    rows = await conn.execute(
        select(e.c.id, e.c.shop_id, e.c.amount, e.c.name, e.c.code, e.c.created_on)
        .where(
            e.c.category == ExpenseCategory.FINE.value,
            e.c.excluded.is_(None),
            e.c.amount != 0,
            e.c.created_on >= now - timedelta(days=FINE_DAYS),
        )
        .order_by(e.c.created_on, e.c.id)
    )
    return [
        Found(
            Event.NEW_FINE,
            f"fine:{r.id}",
            {
                "shop": shops.get(r.shop_id),
                "amount": _num(abs(r.amount)),
                "name": r.name,
                "code": r.code,
                "on": r.created_on.astimezone(TASHKENT).date().isoformat(),
            },
        )
        for r in rows
    ]


async def receiving_shortages(conn: AsyncConnection) -> list[Found]:
    found = [x for x in await rr.diffs(conn) if x.resolution is None and x.diff < 0]
    catalog = await sku_catalog(conn, ids=[x.sku_id for x in found]) if found else {}
    return [
        Found(
            Event.RECEIVING_SHORTAGE,
            f"receiving:{x.dispatch_id}:{x.sku_id}",
            {
                "invoice_number": x.invoice_number,
                "title": catalog[x.sku_id].title if x.sku_id in catalog else None,
                "shipped": x.shipped,
                "accepted": x.accepted,
                "missing": -x.diff,
            },
        )
        for x in found
    ]


async def sync_stopped(conn: AsyncConnection, now: datetime, hours: int) -> list[Found]:
    """Faol do'kon: kalit yaroqsiz yoki buyurtmalar ``hours`` soatdan beri yangilanmagan (birinchi sinxron hali
    tugamagan do'kon — hisobga olinmaydi)."""
    s, a, st = m.shops, m.mp_accounts, m.sync_state
    rows = await conn.execute(
        select(s.c.id, s.c.name, s.c.alias, a.c.status, st.c.last_success_at)
        .join(a, a.c.id == s.c.account_id)
        .join(st, (st.c.shop_id == s.c.id) & (st.c.kind == "orders"), isouter=True)
        .where(s.c.active)
        .order_by(s.c.id)
    )
    out = []
    day = now.astimezone(TASHKENT).date().isoformat()
    for r in rows:
        if r.status == "invalid":
            reason = "key_invalid"
        elif r.last_success_at is not None and now - r.last_success_at >= timedelta(hours=hours):
            reason = "stale"
        else:
            continue
        out.append(
            Found(
                Event.SYNC_STOPPED,
                f"sync_stopped:{r.id}:{day}",
                {
                    "shop": r.alias or r.name,
                    "reason": reason,
                    "since": None if r.last_success_at is None else r.last_success_at.isoformat(),
                },
            )
        )
    return out


# --- Baholash -------------------------------------------------------------------------------


async def evaluate(conn: AsyncConnection, org_id: UUID, now: datetime) -> int:
    """Bitta tashkilot (``org_transaction`` ichida): hodisalarni topib navbatga yozadi. Qaytaradi: yangi qatorlar."""
    local = now.astimezone(TASHKENT)
    today = local.date()
    people = await recipients(conn)
    wanted = {e for e in Event if any(p.wants(e) for p in people)}
    if not wanted:
        return 0
    common: list[Found] = []  # hamma oluvchiga bir xil
    personal: list[tuple[Recipient, Found]] = []  # oluvchining vaqti / chegarasi bilan
    yesterday = Period(today - timedelta(days=1), today - timedelta(days=1))
    cache: dict[Period, dict[str, Any] | None] = {}

    async def summary_of(period: Period) -> dict[str, Any] | None:
        if period not in cache:
            cache[period] = await summary(conn, period, today)
        return cache[period]

    last_week = Period(week_start(today) - timedelta(days=7), week_start(today) - timedelta(days=1))
    for person in people:
        for event, period, key, weekly in (
            (Event.DAILY_SUMMARY, yesterday, f"daily:{yesterday.start}", False),
            (Event.WEEKLY_SUMMARY, last_week, f"weekly:{last_week.start}", True),
        ):
            if not person.wants(event):
                continue
            try:
                at = parse_hhmm(str(person.params(event)["at"]))
            except (ValueError, KeyError):
                at = parse_hhmm(str(CATALOG[event].params["at"]))
            if not summary_due(local.replace(tzinfo=None), at, weekly=weekly):
                continue
            data = await summary_of(period)
            if data is not None:
                personal.append((person, Found(event, key, data)))
    if Event.LOSS_SALES in wanted:
        for streak in sorted(
            {int(p.params(Event.LOSS_SALES)["streak"]) for p in people if p.wants(Event.LOSS_SALES)}
        ):
            found = await loss_sales(conn, today, streak)
            if found is not None:
                personal += [
                    (p, found)
                    for p in people
                    if p.wants(Event.LOSS_SALES)
                    and int(p.params(Event.LOSS_SALES)["streak"]) == streak
                ]
    if Event.SYNC_STOPPED in wanted:
        for hours in sorted(
            {
                int(p.params(Event.SYNC_STOPPED)["hours"])
                for p in people
                if p.wants(Event.SYNC_STOPPED)
            }
        ):
            for found in await sync_stopped(conn, now, hours):
                personal += [
                    (p, found)
                    for p in people
                    if p.wants(Event.SYNC_STOPPED)
                    and int(p.params(Event.SYNC_STOPPED)["hours"]) == hours
                ]
    if Event.STOCK_CRITICAL in wanted and (found := await stock_critical(conn, today)) is not None:
        common.append(found)
    if Event.UNCOSTED_SALES in wanted:
        data = await summary_of(yesterday)
        if data is not None and data["uncosted_lines"] > 0:
            common.append(
                Found(
                    Event.UNCOSTED_SALES,
                    f"uncosted:{yesterday.start}",
                    {"day": data["start"], "lines": data["uncosted_lines"]},
                )
            )
    if Event.NEW_FINE in wanted:
        common += await new_fines(conn, now)
    if Event.RECEIVING_SHORTAGE in wanted:
        common += await receiving_shortages(conn)

    rows = [(p, f) for f in common for p in people if p.wants(f.event)] + personal
    created = 0
    for person, found in rows:
        critical = CATALOG[found.event].critical
        when = due_at(local, person.quiet_from, person.quiet_to, critical=critical)
        result = await conn.execute(
            insert(m.notifications)
            .values(
                org_id=org_id,
                user_id=person.user_id,
                event=found.event.value,
                dedupe_key=found.dedupe_key,
                critical=critical,
                payload=found.payload,
                due_at=when,
            )
            .on_conflict_do_nothing(index_elements=["org_id", "user_id", "dedupe_key"])
        )
        created += result.rowcount or 0
    return created


async def evaluate_org(engine: AsyncEngine, org_id: UUID, now: datetime) -> int:
    async with org_transaction(engine, org_id) as conn:
        created = await evaluate(conn, org_id, now)
    if created:
        _log.info("notifications_queued", org_id=str(org_id), created=created)
    return created

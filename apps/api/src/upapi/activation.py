"""Foydalanish hodisalari (B8.9, ADR-057 Q13): B9.4 o'lchovlari — betadan **oldin** yig'ila boshlaydi (keyin tiklab bo'lmaydi).

``events`` jadvaliga (tashkilot doirasida, faqat qo'shiladi) yoziladigan nomlar:

- ``org_created`` — tashkilot ochildi (ro'yxatdan o'tish vaqti — ``users.created_at``);
- ``mp_account_connected`` — kalit ulandi (``routes.accounts``, avvaldan);
- ``history_loaded`` — hamma faol do'konning tarixi yuklandi;
- ``first_cost`` — birinchi tannarx (``item_costs`` yoki xarid qatori);
- ``costs_60`` — tushumning ≥ 60% ida tannarx bor (B9.4: "48 soatda" — ``mp_account_connected`` bilan solishtiriladi);
- ``telegram_linked`` — Telegram ulandi;
- ``daily_visit`` — foydalanuvchi shu kuni (Toshkent) kirdi (kuniga bir marta; ``routes.auth``).

Bosqichlar (``history_loaded`` ... ``telegram_linked``) har tashkilot uchun **bir marta** yoziladi — ``notify_all`` aylanishida
(har 5 daqiqa) holatdan aniqlanadi; props'da faqat sana/vaqt, sotuvchi ma'lumoti yo'q.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from upapi.db import models as m
from upapi.db.session import org_transaction

TASHKENT = ZoneInfo("Asia/Tashkent")
COST_SHARE = Decimal("0.6")

_COVERAGE = text(
    """
    SELECT coalesce(sum(s.sell_price * s.amount) FILTER (WHERE c.unit_cost IS NOT NULL), 0) AS covered,
           coalesce(sum(s.sell_price * s.amount), 0) AS total
    FROM sale_items s LEFT JOIN sale_costs c ON c.sale_item_id = s.id
    WHERE s.status <> 'CANCELED'
    """
)


async def _recorded(conn: AsyncConnection, org_id: UUID) -> set[str]:
    rows = await conn.execute(select(m.events.c.name).where(m.events.c.org_id == org_id).distinct())
    return {r.name for r in rows}


async def _reached(conn: AsyncConnection) -> dict[str, bool]:
    shops = (
        await conn.execute(select(m.shops.c.history_status).where(m.shops.c.active.is_(True)))
    ).all()
    history = bool(shops) and all(s.history_status is not None for s in shops)
    first_cost = bool(
        await conn.scalar(select(m.item_costs.c.id).limit(1))
        or await conn.scalar(select(m.purchase_lines.c.id).limit(1))
    )
    coverage = (await conn.execute(_COVERAGE)).one()
    costs_60 = bool(coverage.total > 0 and coverage.covered >= coverage.total * COST_SHARE)
    telegram = bool(
        await conn.scalar(
            select(m.notification_channels.c.id).where(
                m.notification_channels.c.kind == "telegram",
                m.notification_channels.c.active.is_(True),
            )
        )
    )
    return {
        "history_loaded": history,
        "first_cost": first_cost,
        "costs_60": costs_60,
        "telegram_linked": telegram,
    }


async def track(conn: AsyncConnection, org_id: UUID, now: datetime) -> list[str]:
    """Hali yozilmagan, lekin erishilgan bosqichlarni bir martadan yozadi; yangi yozilganlar nomini qaytaradi."""
    done = await _recorded(conn, org_id)
    if {"history_loaded", "first_cost", "costs_60", "telegram_linked"} <= done:
        return []
    new = [name for name, ok in (await _reached(conn)).items() if ok and name not in done]
    for name in new:
        await conn.execute(
            insert(m.events).values(org_id=org_id, name=name, props={"at": now.isoformat()})
        )
    return new


async def record_visit(engine: AsyncEngine, org_id: UUID, user_id: UUID, now: datetime) -> bool:
    """Foydalanuvchining kunlik kirishi (Toshkent kuni bo'yicha bir marta). ``True`` — yangi yozildi."""
    local = now.astimezone(TASHKENT)
    start = datetime.combine(local.date(), time.min, tzinfo=TASHKENT)
    e = m.events
    async with org_transaction(engine, org_id, user_id) as conn:
        seen = await conn.scalar(
            select(e.c.id)
            .where(e.c.user_id == user_id, e.c.name == "daily_visit", e.c.created_at >= start)
            .limit(1)
        )
        if seen is not None:
            return False
        await conn.execute(
            insert(e).values(
                org_id=org_id,
                user_id=user_id,
                name="daily_visit",
                props={"day": local.date().isoformat()},
            )
        )
        return True

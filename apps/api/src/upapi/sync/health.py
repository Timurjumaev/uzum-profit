"""Uzum uzilishi rejimi (03 §6, 02 M3; masalan, 2026-10-08/09 hodisasi).

- Bir necha do'konda (``sync_outage_shops``) qisqa oynada (``sync_outage_window_minutes``) tarmoq/5xx xatosi →
  **uzilish**: hamma sinxron ``sync_outage_pause_minutes`` ga to'xtaydi.
- Pauza tugagach bitta ish **sinov** huquqini oladi (qolganlari kutadi); sinov muvaffaqiyatli bo'lsa uzilish tugaydi
  va uzilish davri (``recovered_from`` .. ``recovered_at``) keyingi sotuv/xarajat sinxronida chuqur to'ldiriladi.
- Holat ``provider_health`` tizim jadvalida (tashkilotsiz, sirsiz): ishchi jarayonlari orasida umumiy, "Ma'lumotlar
  holati" sahifasida sariq banner shundan. Uzilish paytidagi "sotuv yo'q" asosida ogohlantirish yuborilmaydi (B6
  bildirishnomalari shu holatni tekshiradi).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from upapi.db import models as m
from upapi.logs import get_logger
from upapi.settings import Settings

PROVIDER = "uzum"
_log = get_logger("upapi.sync.health")


class Gate(StrEnum):
    OPEN = "open"  # uzilish yo'q
    PAUSED = "paused"  # uzilish, pauza davom etmoqda — ish bajarilmaydi
    PROBE = "probe"  # uzilish, shu ish sinov huquqini oldi


@dataclass(frozen=True, slots=True)
class Outage:
    active: bool
    since: datetime | None = None
    paused_until: datetime | None = None
    recovered_from: datetime | None = None
    recovered_at: datetime | None = None


async def _locked(conn: AsyncConnection) -> Any:
    """Provayder qatori (yo'q bo'lsa yaratiladi), ``FOR UPDATE`` bilan — ishchilar orasida bir vaqtda bitta."""
    await conn.execute(
        pg_insert(m.provider_health).values(provider=PROVIDER).on_conflict_do_nothing()
    )
    return (
        await conn.execute(
            select(m.provider_health)
            .where(m.provider_health.c.provider == PROVIDER)
            .with_for_update()
        )
    ).one()


async def outage(engine: AsyncEngine) -> Outage:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(m.provider_health).where(m.provider_health.c.provider == PROVIDER)
            )
        ).first()
    if row is None:
        return Outage(False)
    return Outage(
        row.outage_since is not None,
        row.outage_since,
        row.paused_until,
        row.recovered_from,
        row.recovered_at,
    )


async def gate(engine: AsyncEngine, settings: Settings, now: datetime) -> Gate:
    """Ish boshida: uzilish bo'lmasa ``OPEN``; pauza davom etsa ``PAUSED``; pauza tugagan bo'lsa birinchi so'ragan
    ish ``PROBE`` oladi va keyingi pauza belgilanadi (boshqalar yana ``PAUSED``)."""
    current = await outage(engine)
    if not current.active:
        return Gate.OPEN
    async with engine.begin() as conn:
        row = await _locked(conn)
        if row.outage_since is None:
            return Gate.OPEN
        if row.paused_until is not None and row.paused_until > now:
            return Gate.PAUSED
        await conn.execute(
            update(m.provider_health)
            .where(m.provider_health.c.provider == PROVIDER)
            .values(
                paused_until=now + timedelta(minutes=settings.sync_outage_pause_minutes),
                updated_at=now,
            )
        )
    _log.info("uzum_outage_probe")
    return Gate.PROBE


async def record_failure(
    engine: AsyncEngine, settings: Settings, shop_id: UUID, now: datetime
) -> bool:
    """Do'kon sinxronida tarmoq/5xx xatosi. Oynada yetarli do'kon bo'lsa uzilish e'lon qilinadi; ``True`` — uzilish
    (yangi yoki davom etayotgan)."""
    window = now - timedelta(minutes=settings.sync_outage_window_minutes)
    async with engine.begin() as conn:
        row = await _locked(conn)
        failures = {
            shop: at
            for shop, at in dict(row.failures or {}).items()
            if datetime.fromisoformat(at) > window
        }
        failures[str(shop_id)] = now.isoformat()
        values: dict[str, Any] = {"failures": failures, "updated_at": now}
        started = row.outage_since is None and len(failures) >= settings.sync_outage_shops
        if started:
            values["outage_since"] = now
            values["paused_until"] = now + timedelta(minutes=settings.sync_outage_pause_minutes)
        await conn.execute(
            update(m.provider_health)
            .where(m.provider_health.c.provider == PROVIDER)
            .values(**values)
        )
    if started:
        _log.warning("uzum_outage_started", shops=len(failures))
    return started or row.outage_since is not None


async def record_success(engine: AsyncEngine, now: datetime) -> bool:
    """Uzum javob berdi. Uzilish bo'lsa tugaydi (davri saqlanadi — chuqur to'ldirish uchun); ``True`` — tugadi."""
    current = await outage(engine)
    if not current.active:
        return False
    async with engine.begin() as conn:
        row = await _locked(conn)
        if row.outage_since is None:
            return False
        await conn.execute(
            update(m.provider_health)
            .where(m.provider_health.c.provider == PROVIDER)
            .values(
                outage_since=None,
                paused_until=None,
                failures={},
                recovered_from=row.outage_since,
                recovered_at=now,
                updated_at=now,
            )
        )
    _log.warning("uzum_outage_recovered", since=row.outage_since.isoformat())
    return True

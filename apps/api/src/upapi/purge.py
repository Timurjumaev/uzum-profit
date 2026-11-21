"""Tashkilotni butunlay o'chirish (B8.13): muddati (``routes.org_deletion.GRACE``) o'tgan so'rovlar bo'yicha.

``purge_due_orgs()`` (0048, ``up_sync`` egasida) faqat id'larni beradi; har tashkilot o'z tranzaksiyasida (RLS) ``DELETE FROM
orgs`` bilan o'chadi — hamma tashkilot jadvallari ``ON DELETE CASCADE`` (sotuvlar, xaridlar, kalit, a'zolik, audit, eksport
fayllari ...). Foydalanuvchi yozuvlari (telefon) o'chmaydi — ular boshqa tashkilotlarga ham tegishli bo'lishi mumkin.
Xato bitta tashkilotni to'xtatmaydi (keyingi kunda qayta). Log: faqat id (nom emas).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine

from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.logs import get_logger
from upapi.routes.org_deletion import GRACE

_log = get_logger("upapi.purge")


async def due(engine: AsyncEngine, now: datetime) -> list[UUID]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT org_id FROM purge_due_orgs(:c)"), {"c": now - GRACE})
        return [r.org_id for r in rows]


async def purge_all(engine: AsyncEngine, now: datetime) -> int:
    purged = 0
    for org_id in await due(engine, now):
        try:
            async with org_transaction(engine, org_id) as conn:
                await conn.execute(delete(m.orgs).where(m.orgs.c.id == org_id))
            purged += 1
            _log.info("org_purged", org_id=str(org_id))
        except Exception as exc:
            _log.warning("org_purge_failed", org_id=str(org_id), error_code=type(exc).__name__)
    return purged

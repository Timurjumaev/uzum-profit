"""Qayta hisob navbati (``recalc_queue``): manba o'zgargani haqidagi yozuv.

Yozuv o'zgargan ma'lumot bilan **bitta tranzaksiyada** qo'yiladi (sinxron sahifasi, B4 dagi xarid tahriri) — ma'lumot
yozilib, navbat yozilmay qolishi mumkin emas. Takroriy so'rov bitta qatorga birlashadi (``since`` — eng erta kun).

Turlar:

- ``purchase`` (xarid id) — xarid, qatorlari yoki komponentlari o'zgardi → lotlar (F20) va ularning tovarlari.
- ``item`` (tovar id) — tovarning lotlari, SKU bog'lanishi yoki hisobdan chiqarishlari o'zgardi → F21.
- ``shop`` (do'kon id, ``since``) — sotuvlar o'zgardi → shu kundan sotuvi bor tovarlar (F21) va kunlik agregat.
- ``metrics`` (do'kon id, ``since``) — faqat xarajatlar (reklama) o'zgardi → kunlik agregat.

``ref_id=None`` — shu turdagi hammasi (masalan, tungi to'liq qayta qurish); ``since=None`` — butun tarix.
B4 eslatmasi: xarid qatori o'chirilsa uning loti FK bilan o'chadi — tovari uchun ``item`` so'rovi ham qo'yiladi;
SKU'ning tovari almashtirilsa — eski va yangi tovar (``item``) va do'kon (``shop``) so'rovlari.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import case, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from upapi.db import models as m


class Scope(StrEnum):
    PURCHASE = "purchase"
    ITEM = "item"
    SHOP = "shop"
    METRICS = "metrics"


async def request(
    conn: AsyncConnection,
    org_id: UUID,
    scope: Scope,
    ref_id: UUID | None = None,
    since: date | None = None,
) -> None:
    """Qayta hisob so'rovi (tashkilot tranzaksiyasida). Bor so'rov bilan birlashadi: ``since`` — kichigi,
    ``None`` (butun tarix) ustun."""
    q = m.recalc_queue
    stmt = pg_insert(q).values(org_id=org_id, kind=scope.value, ref_id=ref_id, since=since)
    merged = case(
        (or_(q.c.since.is_(None), stmt.excluded.since.is_(None)), None),
        else_=func.least(q.c.since, stmt.excluded.since),
    )
    await conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["org_id", "kind", "ref_id"],
            set_={"since": merged, "updated_at": func.now()},
        )
    )


async def request_full(conn: AsyncConnection, org_id: UUID) -> None:
    """Hamma hosila jadvallarni manbadan qayta qurish (03 §5): hamma xaridlar, tovarlar va do'konlar."""
    for scope in (Scope.PURCHASE, Scope.ITEM, Scope.SHOP):
        await request(conn, org_id, scope)

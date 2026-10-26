"""Uzum bonuslari (ADR-031) bazadan: ``fee_waivers`` davrlari va tizim takliflari.

- Davrlar — foydalanuvchi kiritgani (yoki tasdiqlagan taklif): do'kon yoki hammasi, sanalar, bepul turlar, sabab.
  Haqiqiy P&L'ga ta'sir qilmaydi (bepul xarajat 0 bo'lib qoladi) — faqat belgilash: hisobotda banner va grafik soyasi,
  sotuv qatorida ``waiver_id`` ("Bonus davri").
- Takliflar — do'kon × kun bo'yicha Yakunlangan qatorlarning ≥ 90% ida logistika 0 (``upcore.tariffs.is_free_day``),
  mavjud yozuvlar (faol yoki rad etilgan) qoplamagan kunlar (``upcore.waivers.suggestions``). Tasdiqlanmaguncha
  hech narsaga ta'sir qilmaydi.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import StatusGroup, statuses
from upcore.tariffs import is_free_day
from upcore.waivers import FeeWaiver, active, suggestions

from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.common import Filters


class WaiverOut(BaseModel):
    """Bonus davri (ADR-031): ``shop_id`` ``null`` — hamma do'kon; ``dismissed`` — rad etilgan taklif."""

    id: UUID
    shop_id: UUID | None
    start_on: date
    end_on: date
    kinds: list[str]
    reason: str
    source: str  # manual | detected
    dismissed: bool
    created_at: datetime

    @classmethod
    def of(cls, r: Any) -> WaiverOut:
        return cls(
            id=r.id,
            shop_id=r.shop_id,
            start_on=r.start_on,
            end_on=r.end_on,
            kinds=list(r.kinds),
            reason=r.reason,
            source=r.source,
            dismissed=r.dismissed_at is not None,
            created_at=r.created_at,
        )


class SuggestionOut(BaseModel):
    """Taklif: do'konda Uzum logistikani olmagan kunlar — "bonus davrimi?" (tasdiqlanmagan)."""

    shop_id: UUID
    start_on: date
    end_on: date
    kinds: list[str]


def core(r: Any) -> FeeWaiver:
    return FeeWaiver(
        id=str(r.id),
        shop=None if r.shop_id is None else str(r.shop_id),
        start=r.start_on,
        end=r.end_on,
        kinds=frozenset(r.kinds),
        reason=r.reason,
        dismissed=r.dismissed_at is not None,
    )


async def rows(conn: AsyncConnection) -> list[Any]:
    """Hamma yozuvlar (faol va rad etilgan) — tashkilotda bir necha o'nta, filtrsiz o'qiladi."""
    t = m.fee_waivers
    query = select(t).order_by(t.c.start_on.desc(), t.c.created_at.desc(), t.c.id)
    return list(await conn.execute(query))


def in_report(found: list[Any], f: Filters) -> list[WaiverOut]:
    """Davr va do'konlar bilan kesishadigan faol davrlar (hisobot banneri, grafik soyasi)."""
    shops = None if f.shops is None else frozenset(str(s) for s in f.shops)
    return [
        WaiverOut.of(r)
        for r in sorted(found, key=lambda r: (r.start_on, str(r.id)))
        if r.dismissed_at is None and core(r).overlaps(f.period, shops)
    ]


async def detected_days(conn: AsyncConnection, f: Filters) -> dict[str, set[date]]:
    """Ma'lumotdan: do'kon × kun, Yakunlangan qatorlarning ≥ 90% ida logistika 0 (F40 taklifi)."""
    s = m.sale_items
    day = cast(func.timezone("Asia/Tashkent", s.c.ordered_at), Date)  # F1: Toshkent sanasi
    where = [
        s.c.ordered_at >= day_start(f.period.start),
        s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
        func.upper(func.trim(s.c.status)).in_(statuses(StatusGroup.COMPLETED)),
    ]
    if f.shops:
        where.append(s.c.shop_id.in_(f.shops))
    query = (
        select(s.c.shop_id, day, func.count(), func.count().filter(s.c.logistics_fee == 0))
        .where(*where)
        .group_by(s.c.shop_id, day)
    )
    out: dict[str, set[date]] = defaultdict(set)
    for shop, d, lines, free in await conn.execute(query):
        if is_free_day(int(lines), int(free)):
            out[str(shop)].add(d)
    return dict(out)


async def suggested(conn: AsyncConnection, f: Filters, found: list[Any]) -> list[SuggestionOut]:
    days = await detected_days(conn, f)
    return [
        SuggestionOut(
            shop_id=UUID(x.shop), start_on=x.period.start, end_on=x.period.end, kinds=list(x.kinds)
        )
        for x in suggestions(days, [core(r) for r in found])
    ]


async def active_waivers(conn: AsyncConnection) -> list[FeeWaiver]:
    return active(core(r) for r in await rows(conn))

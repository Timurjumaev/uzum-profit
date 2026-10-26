"""Bepul logistika kunlari (Uzum bonusi, ADR-031) bazadan — kunlik grafik soyasi uchun.

- Bepul kunlar — har do'kon uchun ma'lumotdan aniqlanadi (``upcore.tariffs.is_free_day``: kunlik Yakunlangan
  qatorlarning ≥ 90% ida logistika 0) va ``free_logistics_periods`` jadvalidagi davrlar (do'kon bo'yicha)
  qo'shiladi (legacy ``.env`` sanalari o'rniga). Jadval B4.2a da ``fee_waivers`` bilan almashtiriladi.
- Haqiqiy P&L'ga ta'sir qilmaydi: bonus davrida bepul xarajat 0 bo'lib qoladi (ADR-031). Bonus davrlari jadvali
  (``fee_waivers``: do'kon yoki hammasi, bepul turlar, sabab), "bonus davri" belgisi — B4.2a; me'yoriy (bonussiz)
  tarif — faqat SKU baholash va narx uchun (B4.3).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import Period, StatusGroup, statuses
from upcore.tariffs import is_free_day, to_periods

from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.common import Filters


@dataclass(frozen=True, slots=True)
class FreeDays:
    """Bepul logistika kunlari do'kon bo'yicha."""

    by_shop: dict[str, set[date]]

    def has(self, shop: str, day: date) -> bool:
        return day in self.by_shop.get(shop, ())

    def periods(self) -> list[Period]:
        """Grafik soyasi uchun: hamma do'konlar kunlari birlashmasi, ketma-ket kunlar — bitta davr."""
        return to_periods(sorted({d for days in self.by_shop.values() for d in days}))


def _completed(column: Any) -> Any:
    return func.upper(func.trim(column)).in_(statuses(StatusGroup.COMPLETED))


def _in_period(s: Any, f: Filters) -> list[Any]:
    where = [
        s.c.ordered_at >= day_start(f.period.start),
        s.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
        _completed(s.c.status),
    ]
    if f.shops:
        where.append(s.c.shop_id.in_(f.shops))
    return where


async def free_days(conn: AsyncConnection, f: Filters) -> FreeDays:
    """Davrdagi bepul kunlar: ma'lumotdan aniqlangan + jadvaldagi davrlar."""
    s, t = m.sale_items, m.free_logistics_periods
    day = cast(func.timezone("Asia/Tashkent", s.c.ordered_at), Date)  # F1: Toshkent sanasi
    rows = await conn.execute(
        select(
            s.c.shop_id,
            day,
            func.count(),
            func.count().filter(s.c.logistics_fee == 0),
        )
        .where(*_in_period(s, f))
        .group_by(s.c.shop_id, day)
    )
    out: dict[str, set[date]] = defaultdict(set)
    for shop, d, lines, free in rows:
        if is_free_day(int(lines), int(free)):
            out[str(shop)].add(d)
    query = select(t.c.shop_id, t.c.start_on, t.c.end_on).where(
        t.c.start_on <= f.period.end, t.c.end_on >= f.period.start
    )
    for shop, start, end in await conn.execute(query):
        if f.shops and shop not in f.shops:
            continue
        first, last = max(start, f.period.start), min(end, f.period.end)
        out[str(shop)].update(first + timedelta(days=i) for i in range((last - first).days + 1))
    return FreeDays(dict(out))

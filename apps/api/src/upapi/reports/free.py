"""Bepul logistika davrlari va standart tarif bo'yicha foyda (F40) bazadan.

- Bepul kunlar — har do'kon uchun ma'lumotdan aniqlanadi (``upcore.tariffs.is_free_day``: kunlik Yakunlangan
  qatorlarning ≥ 90% ida logistika 0) va ``free_logistics_periods`` jadvalidagi davrlar (do'kon bo'yicha)
  qo'shiladi. Admin tasdiqlash jadvali — B8 (M17); legacy ``.env`` sanalari o'rniga.
- Standart tarif — SKU'ning oxirgi pullik logistikasi, bo'lmasa do'konning odatiy (eng ko'p uchraydigan) tarifi
  (``upcore.tariffs.standard_fee_of``). Hisob — ``upcore.pnl.standard_logistics`` + ``Cells.with_logistics``: P&L
  kataklari faqat bepul kunlardagi logistikasi 0 qatorlar katagida o'zgaradi, qolgani — xuddi P&L'ning o'zi.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import Period, StatusGroup, business_date, statuses
from upcore.money import Money
from upcore.pnl import CellKey, Cells, FreeSale, StandardLogistics, Statement, standard_logistics
from upcore.tariffs import is_free_day, paid_unit_fee, standard_fee_of, to_periods, typical_fee

from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.cells import UNLINKED, sku_key
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


async def _fees(
    conn: AsyncConnection, skus: set[UUID], shops: set[UUID]
) -> tuple[dict[str, Money], dict[str, Money]]:
    """SKU'ning oxirgi pullik logistikasi (bir dona) va do'konning odatiy tarifi — butun tarix bo'yicha."""
    s = m.sale_items
    paid = [s.c.logistics_fee > 0, s.c.amount > 0, _completed(s.c.status)]
    last: dict[str, Money] = {}
    if skus:
        rows = await conn.execute(
            select(s.c.sku_id, s.c.logistics_fee, s.c.amount)
            .ext(distinct_on(s.c.sku_id))
            .where(s.c.sku_id.in_(skus), *paid)
            .order_by(s.c.sku_id, s.c.ordered_at.desc(), s.c.id.desc())
        )
        last = {str(sku): paid_unit_fee(fee, amount) for sku, fee, amount in rows}
    counts: dict[str, dict[Decimal, int]] = defaultdict(lambda: defaultdict(int))
    grouped = await conn.execute(
        select(s.c.shop_id, s.c.logistics_fee, s.c.amount, func.count())
        .where(s.c.shop_id.in_(shops), *paid)
        .group_by(s.c.shop_id, s.c.logistics_fee, s.c.amount)
    )
    for shop, fee, amount, n in grouped:
        counts[str(shop)][paid_unit_fee(fee, amount).amount] += int(n)
    typical = {shop: fee for shop, c in counts.items() if (fee := typical_fee(c)) is not None}
    return last, typical


async def standard(
    conn: AsyncConnection, f: Filters, cells: Cells, days: FreeDays
) -> tuple[Statement, StandardLogistics] | None:
    """F40: bepul kunlardagi logistikasi 0 Yakunlangan qatorlarga standart tarif qo'shilgan P&L (tanlangan
    kataklar). Bunday qator yo'q — ``None`` (qator ko'rsatilmaydi)."""
    if not days.by_shop:
        return None
    s, c = m.sale_items, m.sale_costs
    rows = await conn.execute(
        select(s.c.shop_id, s.c.sku_id, s.c.ordered_at, s.c.amount, c.c.cogs)
        .outerjoin(c, c.c.sale_item_id == s.c.id)
        .where(*_in_period(s, f), s.c.logistics_fee == 0, s.c.amount > 0)
    )
    sales: list[FreeSale] = []
    skus: set[UUID] = set()
    shops: set[UUID] = set()
    for shop_id, sku_id, ordered, amount, cogs in rows:
        shop, day = str(shop_id), business_date(ordered)
        if not days.has(shop, day):
            continue
        sales.append(FreeSale(CellKey(day, shop, sku_key(sku_id)), amount, cogs is not None))
        shops.add(shop_id)
        if sku_id is not None:
            skus.add(sku_id)
    if not sales:
        return None
    last, typical = await _fees(conn, skus, shops)
    fee = standard_fee_of(last, typical)
    extra = standard_logistics(sales, lambda x: fee(x.key.shop, x.key.sku or UNLINKED))
    return cells.with_logistics(extra.extra).statement(), extra

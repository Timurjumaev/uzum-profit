"""Mahsulotlar (M6) bazadan: me'yoriy (bonussiz) foyda/dona (F40, ADR-031) va SKU sahifasi ma'lumotlari.

- **Me'yoriy qiymat** faqat davrga tushgan faol bonus davrlari bo'lsa hisoblanadi (bo'lmasa qo'shimcha so'rov yo'q):
  - ``sale_logistics`` — bonus davridagi logistikasi 0 bo'lgan Yakunlangan (tannarxi ma'lum) dona × SKU'ning bonus
    davridan tashqaridagi oxirgi pullik logistikasi, bo'lmasa do'konning odatiy (eng ko'p, oxirgi 90 kun) tarifi;
  - ``storage`` — SKU ``storage_price`` × bonus kunlaridagi qoldiq-kunlar (``sku_daily.qty_active``);
  - boshqa tur — baholovchisi yo'q: foyda/dona unga tegmaydi, javobda ``unestimated_kinds`` bilan ochiq aytiladi.
  F37 (hajm bo'yicha tarif) o'lchamlar bazada to'lgach qo'shiladi (``items`` o'lchamlarini tahrirlash — B4.6).
- Hamma formula ``upcore`` da (``waivers.normative_profit``, ``unit.unit_calc``); bu yerda faqat faktlar o'qiladi.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, not_, select, true
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import StatusGroup, business_date, statuses
from upcore.money import Currency, Money
from upcore.tariffs import paid_unit_fee, standard_fee_of, typical_fee
from upcore.waivers import (
    SALE_LOGISTICS,
    STORAGE,
    FeeWaiver,
    Normative,
    logistics_saving,
    normative_profit,
    storage_saving,
    waiver_for,
)

from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.common import Filters, SkuInfo

UZS = Currency.UZS
TYPICAL_DAYS = 90  # F40: do'konning odatiy tarifi — oxirgi 90 kunlik pullik qatorlardan
ESTIMABLE = frozenset({SALE_LOGISTICS, STORAGE})


@dataclass(frozen=True, slots=True)
class Fees:
    """F40 me'yoriy bir dona logistika: SKU'ning oxirgi pullik tarifi, bo'lmasa do'konning odatiy tarifi."""

    last_paid: Mapping[str, Money]
    typical: Mapping[str, Money]

    def of(self, shop: UUID, sku: UUID) -> tuple[Money | None, str | None]:
        """(tarif, manba): manba ``last_paid`` | ``shop_typical`` | ``None``."""
        if (fee := self.last_paid.get(str(sku))) is not None:
            return fee, "last_paid"
        if (fee := standard_fee_of({}, self.typical)(str(shop), str(sku))) is not None:
            return fee, "shop_typical"
        return None, None


def _outside_waivers(waivers: Iterable[FeeWaiver]) -> list[ColumnElement[bool]]:
    """Pullik qatorlar bonus davridan tashqarida bo'lishi uchun SQL shartlari (sotuv logistikasi bonuslari)."""
    s = m.sale_items
    out: list[ColumnElement[bool]] = []
    for w in waivers:
        if SALE_LOGISTICS not in w.kinds or w.dismissed:
            continue
        inside = and_(
            s.c.ordered_at >= day_start(w.start),
            s.c.ordered_at < day_start(w.end + timedelta(days=1)),
            true() if w.shop is None else s.c.shop_id == UUID(w.shop),
        )
        out.append(not_(inside))
    return out


async def load_fees(
    conn: AsyncConnection, end: date, waivers: list[FeeWaiver], skus: Mapping[UUID, UUID]
) -> Fees:
    """F40 tariflari ``skus`` (sku → do'kon) uchun; ``end`` — hisobot davri oxiri."""
    if not skus:
        return Fees({}, {})
    s = m.sale_items
    paid = [
        s.c.logistics_fee > 0,
        s.c.amount > 0,
        func.upper(func.trim(s.c.status)).in_(statuses(StatusGroup.COMPLETED)),
        s.c.ordered_at < day_start(end + timedelta(days=1)),
        *_outside_waivers(waivers),
    ]
    last = {
        str(r.sku_id): paid_unit_fee(r.logistics_fee, r.amount)
        for r in await conn.execute(
            select(s.c.sku_id, s.c.logistics_fee, s.c.amount)
            .ext(distinct_on(s.c.sku_id))
            .where(*paid, s.c.sku_id.in_(list(skus)))
            .order_by(s.c.sku_id, s.c.ordered_at.desc(), s.c.id.desc())
        )
    }
    unit = func.round(s.c.logistics_fee / s.c.amount, 2)
    counts: dict[str, dict[Decimal, int]] = defaultdict(dict)
    for r in await conn.execute(
        select(s.c.shop_id, unit, func.count())
        .where(
            *paid,
            s.c.ordered_at >= day_start(end - timedelta(days=TYPICAL_DAYS - 1)),
            s.c.shop_id.in_(set(skus.values())),
        )
        .group_by(s.c.shop_id, unit)
    ):
        counts[str(r[0])][Decimal(r[1])] = int(r[2])
    typical = {shop: fee for shop, c in counts.items() if (fee := typical_fee(c)) is not None}
    return Fees(last, typical)


@dataclass(slots=True)
class BonusBook:
    """Davrdagi bonus ta'siri: SKU → (tur → me'yoriy qiymat yoki ``None``); ``unestimated`` — baholovchisiz turlar."""

    savings: dict[UUID, dict[str, Money | None]] = field(default_factory=dict)
    unestimated: list[str] = field(default_factory=list)

    def normative(self, sku: UUID, profit_per_unit: Money | None, covered_units: int) -> Normative:
        return normative_profit(profit_per_unit, covered_units, self.savings.get(sku, {}))


async def load_bonus(
    conn: AsyncConnection,
    f: Filters,
    waivers: list[FeeWaiver],
    catalog: Mapping[UUID, SkuInfo],
) -> BonusBook:
    """F40: davr (va do'konlar) bilan kesishadigan faol bonus davrlari bo'yicha SKU tejamlari."""
    shops = None if f.shops is None else frozenset(str(x) for x in f.shops)
    relevant = [w for w in waivers if not w.dismissed and w.overlaps(f.period, shops)]
    book = BonusBook(
        unestimated=sorted({k for w in relevant for k in w.kinds if k not in ESTIMABLE})
    )
    if not relevant:
        return book
    lo = max(f.period.start, min(w.start for w in relevant))
    hi = min(f.period.end, max(w.end for w in relevant))

    logistics = [w for w in relevant if SALE_LOGISTICS in w.kinds]
    waived: dict[UUID, int] = defaultdict(int)  # sku → bonus davridagi tannarxi ma'lum dona
    if logistics:
        s, c = m.sale_items, m.sale_costs
        query = (
            select(s.c.sku_id, s.c.shop_id, s.c.ordered_at, s.c.amount, c.c.cogs.is_not(None))
            .select_from(s.outerjoin(c, c.c.sale_item_id == s.c.id))
            .where(
                s.c.sku_id.is_not(None),
                s.c.logistics_fee == 0,
                s.c.ordered_at >= day_start(lo),
                s.c.ordered_at < day_start(hi + timedelta(days=1)),
                func.upper(func.trim(s.c.status)).in_(statuses(StatusGroup.COMPLETED)),
            )
        )
        if f.shops:
            query = query.where(s.c.shop_id.in_(f.shops))
        for sku, shop, at, amount, covered in await conn.execute(query):
            if covered and waiver_for(logistics, str(shop), business_date(at)) is not None:
                waived[sku] += int(amount)
    if waived:
        fees = await load_fees(
            conn,
            f.period.end,
            waivers,
            {sku: catalog[sku].shop_id for sku in waived if sku in catalog},
        )
        for sku, units in waived.items():
            if sku in catalog:
                fee, _ = fees.of(catalog[sku].shop_id, sku)
                book.savings.setdefault(sku, {})[SALE_LOGISTICS] = logistics_saving(units, fee)

    storage = [w for w in relevant if STORAGE in w.kinds]
    if storage:
        d, k = m.sku_daily, m.mp_skus
        query = (
            select(d.c.sku_id, k.c.shop_id, d.c.day, d.c.qty_active)
            .join(k, k.c.id == d.c.sku_id)
            .where(d.c.day >= lo, d.c.day <= hi, d.c.qty_active > 0)
        )
        if f.shops:
            query = query.where(k.c.shop_id.in_(f.shops))
        days: dict[UUID, int] = defaultdict(int)
        for sku, shop, day, qty in await conn.execute(query):
            if waiver_for(storage, str(shop), day) is not None:
                days[sku] += int(qty)
        for sku, stock_days in days.items():
            if sku in catalog:
                price = catalog[sku].storage_price
                book.savings.setdefault(sku, {})[STORAGE] = storage_saving(
                    None if price is None else Money(price, UZS), stock_days
                )
    return book

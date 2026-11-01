"""Mahsulotlar (M6) bazadan: unit kalkulyator uchun standart logistika/dona (F40, ADR-035).

- SKU'ning oxirgi pullik (logistika > 0) Yakunlangan sotuvi, bo'lmasa do'konning odatiy (eng ko'p, oxirgi 90 kun) tarifi.
  Logistikasi 0 qatorlar (sababi qanday bo'lmasin) hisobga olinmaydi — sotuvchidan hech narsa so'ralmaydi.
  F37 (hajm bo'yicha tarif) o'lchamlar bazada to'lgach qo'shiladi (``items`` o'lchamlarini tahrirlash — B4.6).
- Hamma formula ``upcore`` da (``tariffs``, ``unit.unit_calc``); bu yerda faqat faktlar o'qiladi.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import StatusGroup, statuses
from upcore.money import Currency, Money
from upcore.tariffs import paid_unit_fee, standard_fee_of, typical_fee

from upapi.calc.costs import day_start
from upapi.db import models as m

UZS = Currency.UZS
TYPICAL_DAYS = 90  # F40: do'konning odatiy tarifi — oxirgi 90 kunlik pullik qatorlardan


@dataclass(frozen=True, slots=True)
class Fees:
    """F40 standart bir dona logistika: SKU'ning oxirgi pullik tarifi, bo'lmasa do'konning odatiy tarifi."""

    last_paid: Mapping[str, Money]
    typical: Mapping[str, Money]

    def of(self, shop: UUID, sku: UUID) -> tuple[Money | None, str | None]:
        """(tarif, manba): manba ``last_paid`` | ``shop_typical`` | ``None``."""
        if (fee := self.last_paid.get(str(sku))) is not None:
            return fee, "last_paid"
        if (fee := standard_fee_of({}, self.typical)(str(shop), str(sku))) is not None:
            return fee, "shop_typical"
        return None, None


async def load_fees(conn: AsyncConnection, end: date, skus: Mapping[UUID, UUID]) -> Fees:
    """F40 tariflari ``skus`` (sku → do'kon) uchun; ``end`` — hisobot davri oxiri."""
    if not skus:
        return Fees({}, {})
    s = m.sale_items
    paid = [
        s.c.logistics_fee > 0,
        s.c.amount > 0,
        func.upper(func.trim(s.c.status)).in_(statuses(StatusGroup.COMPLETED)),
        s.c.ordered_at < day_start(end + timedelta(days=1)),
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

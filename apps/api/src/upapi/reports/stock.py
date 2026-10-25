"""Ombor ko'rsatkichlari (M10 asos, F23–F30) bazadan → ``upcore.inventory``.

- Qoldiq — ``mp_skus`` (Uzum FBO ``quantityActive`` + FBS ``quantityFbs``, M10 qabul mezoni), brak, kutilayotgan.
- Kunlik statistika (F23) — ``daily_sku_metrics`` (Yakunlangan dona, qaytgan dona) va ``sku_daily`` snapshotlari
  (qoldiq 0 kun — tezlikdan chiqariladi; snapshot yo'q kun hisobga olinadi). Oynadagi har kun beriladi (sotuvsiz
  kun — 0). Tovar "paydo bo'lgan" kun — birinchi sotuv yoki birinchi snapshot.
- To'liq muddat (F25) — tovar xaridlari sanalaridan, bosqichlar: tayyorlash (to'lov/buyurtma → Xitoy ombori), Xitoy
  ichki (→ jo'natildi), kargo yo'li (→ keldi), qabul (→ qabul qilindi), Uzumga topshirish (→ Uzumga yuborildi).
  Standart muddatlar sozlamasi B4 da (M16); hozircha biror bosqich tarixi bo'lmasa muddat noma'lum — holat (F26)
  va tavsiya miqdor (F27) ko'rsatilmaydi (tamoyil 9, raqam o'ylab topilmaydi). Harakatsiz holat muddatsiz ham.
- Lot narxi (F27, F29) — tovarning tayyor bo'lgan eng oxirgi loti; yo'ldagi (tayyor bo'lmagan) lotlar — "yo'lda"
  (F27 ``in_transit``, F29 joyi). Tovarning bir necha SKU'si bo'lsa yo'ldagi dona har biriga to'liq hisoblanadi
  (tavsiya kamroq chiqadi) — tovar darajasidagi to'liq reja B5 da.
- ABC (F28) — oxirgi 30 kun tushumi, tanlangan do'konlar SKU'lari ichida; XYZ — oxirgi 8 hafta.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.inventory import (
    AbcClass,
    DayStat,
    Holding,
    LeadTime,
    Liquidity,
    Reorder,
    StockStatus,
    Velocity,
    XyzClass,
    abc_classes,
    average_days_to_sell,
    days_of_stock,
    frozen_money,
    lead_time,
    liquidity,
    product_status,
    reorder,
    stock_status,
    velocity,
    weekly_sales,
    xyz_class,
)
from upcore.money import Currency, Money

from upapi.db import models as m

UZS = Currency.UZS
WINDOW_DAYS = 56  # F28 XYZ: 8 hafta (F23 uchun 30 kun ham shu ichida)
ABC_DAYS = 30
STAGES = ("prep", "china", "cargo", "receive", "handover")
LOCATIONS = ("fbo", "fbs", "defected", "in_transit")


@dataclass(frozen=True, slots=True)
class SkuStock:
    sku_id: UUID
    shop_id: UUID
    item_id: UUID | None
    product_id: UUID | None
    qty_active: int
    qty_fbs: int
    qty_defected: int
    qty_pending: int
    velocity: Velocity
    days_of_stock: Decimal | None
    lead: LeadTime | None
    status: StockStatus | None
    abc: AbcClass
    xyz: XyzClass | None
    liquidity: Liquidity | None
    last_sale: date | None
    sold_30d: int
    in_transit: int
    unit_cost: Money | None
    stock_value: Money | None
    reorder: Reorder | None

    @property
    def stock(self) -> int:
        """F24 qoldig'i: FBO ``quantityActive`` + FBS ``quantityFbs``."""
        return self.qty_active + self.qty_fbs


@dataclass(frozen=True, slots=True)
class StockBook:
    skus: dict[UUID, SkuStock]
    products: dict[UUID, StockStatus | None]  # F26 mahsulot darajasida
    frozen: dict[str, Money]  # F29 joylar bo'yicha
    average_days: Decimal | None  # F29 o'rtacha sotilish muddati
    uncosted: int  # qoldig'i bor, lot narxi yo'q SKU'lar (muzlagan pulga kirmadi)


def _stages(p: Any) -> dict[str, int]:
    """Xarid sanalari → bosqich kunlari (ikkala sana bor va tartib to'g'ri bo'lsa)."""
    marks = [
        p.paid_on or p.ordered_on,
        p.cn_warehouse_on,
        p.shipped_on,
        p.arrived_on,
        p.received_on,
        p.sent_to_uzum_on,
    ]
    out = {}
    for stage, a, b in zip(STAGES, marks, marks[1:], strict=False):
        if a is not None and b is not None and b >= a:
            out[stage] = (b - a).days
    return out


async def _lead_history(
    conn: AsyncConnection, items: Iterable[UUID]
) -> dict[UUID, dict[str, list[int]]]:
    p, pl = m.purchases, m.purchase_lines
    rows = await conn.execute(
        select(pl.c.item_id, p)
        .join(p, p.c.id == pl.c.purchase_id)
        .where(pl.c.item_id.in_(list(items)))
        .distinct()
        .order_by(p.c.ordered_on.nulls_first(), p.c.created_at)
    )
    out: dict[UUID, dict[str, list[int]]] = {}
    for r in rows:
        for stage, days in _stages(r).items():
            out.setdefault(r.item_id, {}).setdefault(stage, []).append(days)
    return out


@dataclass
class _ItemLots:
    unit_cost: Money | None = None
    ready_on: date | None = None
    transit: list[Holding] | None = None
    last_price: Money | None = None

    @property
    def in_transit(self) -> int:
        return sum(h.qty for h in self.transit or [])


async def _lots(conn: AsyncConnection, items: Iterable[UUID], as_of: date) -> dict[UUID, _ItemLots]:
    lt, p, pl = m.lots, m.purchases, m.purchase_lines
    out: dict[UUID, _ItemLots] = {}
    rows = await conn.execute(
        select(
            lt.c.item_id,
            lt.c.ready_on,
            lt.c.qty,
            lt.c.unit_cost,
            pl.c.unit_price,
            pl.c.currency,
            p.c.ordered_on,
        )
        .join(pl, pl.c.id == lt.c.purchase_line_id)
        .join(p, p.c.id == pl.c.purchase_id)
        .where(lt.c.item_id.in_(list(items)))
        .order_by(p.c.ordered_on.nulls_first(), lt.c.created_at)
    )
    for r in rows:
        x = out.setdefault(r.item_id, _ItemLots(transit=[]))
        cost = Money(r.unit_cost, UZS)
        if r.ready_on is not None and r.ready_on <= as_of:
            if x.ready_on is None or r.ready_on >= x.ready_on:
                x.unit_cost, x.ready_on = cost, r.ready_on
        else:
            assert x.transit is not None
            x.transit.append(Holding("in_transit", r.qty, cost))
        if r.unit_price is not None and r.currency in Currency.__members__:
            x.last_price = Money(r.unit_price, Currency(r.currency))
    return out


def _days(
    metrics: dict[date, tuple[int, int]], snaps: dict[date, bool], as_of: date
) -> list[DayStat]:
    start = as_of - timedelta(days=WINDOW_DAYS - 1)
    out = []
    for i in range(WINDOW_DAYS):
        day = start + timedelta(days=i)
        sold, returned = metrics.get(day, (0, 0))
        out.append(DayStat(day, sold, returned, snaps.get(day)))
    return out


async def load_stock(
    conn: AsyncConnection,
    shops: Sequence[UUID] | None,
    as_of: date,
    sku_ids: set[UUID] | None = None,
) -> StockBook:
    k, d, sd = m.mp_skus, m.daily_sku_metrics, m.sku_daily
    query = select(k).order_by(k.c.shop_id, k.c.external_id)
    if shops:
        query = query.where(k.c.shop_id.in_(shops))
    if sku_ids is not None:
        query = query.where(k.c.id.in_(sku_ids))
    skus = list(await conn.execute(query))
    ids = [r.id for r in skus]
    since = as_of - timedelta(days=WINDOW_DAYS - 1)
    metrics: dict[UUID, dict[date, tuple[int, int]]] = {}
    revenue30: dict[UUID, Money] = {}
    abc_from = as_of - timedelta(days=ABC_DAYS - 1)
    for mr in await conn.execute(
        select(d.c.sku_id, d.c.day, d.c.units, d.c.returns, d.c.revenue).where(
            d.c.sku_id.in_(ids), d.c.day >= since, d.c.day <= as_of
        )
    ):
        metrics.setdefault(mr.sku_id, {})[mr.day] = (mr.units, mr.returns)
        if mr.day >= abc_from:
            revenue30[mr.sku_id] = revenue30.get(mr.sku_id, Money.zero(UZS)) + Money(
                mr.revenue, UZS
            )
    snaps: dict[UUID, dict[date, bool]] = {}
    for sr in await conn.execute(
        select(sd.c.sku_id, sd.c.day, sd.c.qty_active, sd.c.qty_fbs).where(
            sd.c.sku_id.in_(ids), sd.c.day >= since, sd.c.day <= as_of
        )
    ):
        snaps.setdefault(sr.sku_id, {})[sr.day] = (sr.qty_active or 0) + (sr.qty_fbs or 0) > 0
    sales = {
        r.sku_id: (r.first, r.last)
        for r in await conn.execute(
            select(d.c.sku_id, func.min(d.c.day).label("first"), func.max(d.c.day).label("last"))
            .where(d.c.sku_id.in_(ids), d.c.units > 0, d.c.day <= as_of)
            .group_by(d.c.sku_id)
        )
    }
    first_snap = {
        r.sku_id: r.first
        for r in await conn.execute(
            select(sd.c.sku_id, func.min(sd.c.day).label("first"))
            .where(sd.c.sku_id.in_(ids))
            .group_by(sd.c.sku_id)
        )
    }
    items = {r.item_id for r in skus if r.item_id is not None}
    lots = await _lots(conn, items, as_of) if items else {}
    history = await _lead_history(conn, items) if items else {}
    abc = abc_classes({str(r.id): revenue30.get(r.id, Money.zero(UZS)) for r in skus})

    out: dict[UUID, SkuStock] = {}
    holdings: list[Holding] = []
    weighted: list[tuple[Decimal | None, Money]] = []
    uncosted = 0
    for r in skus:
        first_sale, last_sale = sales.get(r.id, (None, None))
        firsts = [x for x in (first_sale, first_snap.get(r.id)) if x is not None]
        days = _days(metrics.get(r.id, {}), snaps.get(r.id, {}), as_of)
        v = velocity(days, as_of, min(firsts) if firsts else None)
        active, fbs = r.qty_active or 0, r.qty_fbs or 0
        defected = r.qty_defected or 0
        stock = active + fbs
        lead = None
        if r.item_id is not None:
            learned = lead_time(history.get(r.item_id, {}), {})
            lead = learned if set(learned.stages) >= set(STAGES) else None
        if lead is not None:
            status = stock_status(stock, v.value, lead.total)
        else:  # muddatsiz faqat "Harakatsiz" aniq (tezlik 0)
            status = stock_status(stock, v.value, 0) if v.value <= 0 else None
        item = lots.get(r.item_id) if r.item_id is not None else None
        unit = item.unit_cost if item else None
        cover = days_of_stock(active, fbs, v.value)
        value = None
        if unit is not None:
            parts = [Holding("fbo", active, unit), Holding("fbs", fbs, unit)]
            parts.append(Holding("defected", defected, unit))
            holdings += parts
            value = unit * stock
            weighted.append((cover, value))
        elif stock + defected > 0:
            uncosted += 1
        cls = abc[str(r.id)]
        plan = None
        if lead is not None:
            prices = [p for p in (unit, item.last_price if item else None) if p is not None]
            plan = reorder(
                v.value,
                lead.total,
                cls,
                stock,
                in_transit=item.in_transit if item else 0,
                last_unit_prices=prices,
            )
        out[r.id] = SkuStock(
            sku_id=r.id,
            shop_id=r.shop_id,
            item_id=r.item_id,
            product_id=r.product_id,
            qty_active=active,
            qty_fbs=fbs,
            qty_defected=defected,
            qty_pending=r.qty_pending or 0,
            velocity=v,
            days_of_stock=cover,
            lead=lead,
            status=status,
            abc=cls,
            xyz=xyz_class(weekly_sales(days, as_of)),
            liquidity=liquidity(stock, v.value, last_sale, as_of),
            last_sale=last_sale,
            sold_30d=sum(x.sold for x in days if x.day >= as_of - timedelta(days=ABC_DAYS - 1)),
            in_transit=item.in_transit if item else 0,
            unit_cost=unit,
            stock_value=value,
            reorder=plan,
        )
    for x in lots.values():
        holdings += x.transit or []
    variants: dict[UUID, list[tuple[StockStatus | None, int]]] = {}
    for s in out.values():
        if s.product_id is not None:
            variants.setdefault(s.product_id, []).append((s.status, s.sold_30d))
    frozen = {loc: Money.zero(UZS) for loc in LOCATIONS} | frozen_money(holdings)
    return StockBook(
        skus=out,
        products={p: product_status(v) for p, v in variants.items()},
        frozen=frozen,
        average_days=average_days_to_sell(weighted),
        uncosted=uncosted,
    )

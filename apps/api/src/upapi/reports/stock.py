"""Ombor ko'rsatkichlari (M10 asos, F23–F30) bazadan → ``upcore.inventory``.

- Qoldiq — ``mp_skus`` (Uzum FBO ``quantityActive`` + FBS ``quantityFbs``, M10 qabul mezoni), brak, kutilayotgan.
- Kunlik statistika (F23) — ``daily_sku_metrics`` (Yakunlangan dona, qaytgan dona) va ``sku_daily`` snapshotlari
  (qoldiq 0 kun — tezlikdan chiqariladi; snapshot yo'q kun hisobga olinadi). Oynadagi har kun beriladi (sotuvsiz
  kun — 0). Tovar "paydo bo'lgan" kun — birinchi sotuv yoki birinchi snapshot.
- To'liq muddat (F25) — tovar xaridlari sanalaridan, bosqichlar: tayyorlash (to'lov/buyurtma → Xitoy ombori), Xitoy
  ichki (→ jo'natildi), kargo yo'li (→ keldi), qabul (→ qabul qilindi), Uzumga topshirish (→ Uzumga yuborildi).
  Standart muddatlar sozlamasi B4 da (M16); hozircha biror bosqich tarixi bo'lmasa muddat noma'lum — holat (F26)
  va tavsiya miqdor (F27) ko'rsatilmaydi (tamoyil 9, raqam o'ylab topilmaydi). Harakatsiz holat muddatsiz ham.
- Lot narxi (F27, F29) — tovarning tayyor bo'lgan eng oxirgi loti (lot tayyorligi — F21, tannarx uchun).
  Boshlang'ich holat (F41) bo'lsa va boshlashdan keyin tayyor lot yo'q — boshlash sanasidagi tarixiy narx.
- Postavkada (ADR-034, B4.14) — qabul qilinmagan FBO postavkalar (``fbo_invoices`` holati yopiq emas) tarkibi, SKU
  bo'yicha: sotuvchida yoki Uzum logistikasi bilan omborga yo'lda. Qiymati lot narxida; F27 da yo'ldagi tovarga qo'shiladi;
  o'z omborimdan ayiriladi (ikki marta sanalmaydi).
- Joylar (M10, B4.7) — xarid bosqichidan (``current_stage``): ``china`` (buyurtma / to'langan / Xitoy omborida),
  ``road`` (yo'lda / Toshkentga keldi), ``own`` (qabul qilindi, Uzumga yuborilmagan; ``stock_moves`` tuzatish va
  hisobdan chiqarish bilan, ``upcore.inventory.own_warehouse_qty``). Uzumga yuborilgan xarid — FBO qoldig'ida. Qiymat —
  qatorning lot tannarxi bilan. F27: yo'lda + o'z omborim — ``in_transit``, Xitoyda — ``ordered``. Tovarning bir necha
  SKU'si bo'lsa joylar har biriga to'liq hisoblanadi (tavsiya kamroq chiqadi), F29 jamlari esa tovar bo'yicha bir
  marta — tovar darajasidagi to'liq reja B5 da.
- Buyurtma sanasi (F27) — ``upcore.inventory.order_by``: zaxira kunlari (F24) va to'liq muddat (F25) farqi.
- ABC (F28) — oxirgi 30 kun tushumi, tanlangan do'konlar SKU'lari ichida; XYZ — oxirgi 8 hafta.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
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
    OrderBy,
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
    order_by,
    own_warehouse_qty,
    product_status,
    reorder,
    stock_status,
    velocity,
    weekly_sales,
    xyz_class,
)
from upcore.money import Currency, Money
from upcore.purchasing import LEAD_STAGES, Stage, current_stage, stage_days

from upapi import orgsettings
from upapi.calc.costs import openings
from upapi.db import models as m
from upapi.reports.purchases import stage_dates

UZS = Currency.UZS
WINDOW_DAYS = 56  # F28 XYZ: 8 hafta (F23 uchun 30 kun ham shu ichida)
ABC_DAYS = 30
STAGES = tuple(name for name, _, _ in LEAD_STAGES)
LOCATIONS = ("china", "road", "own", "inbound", "fbo", "fbs", "defected")
# ADR-034: postavka (``fbo_invoices``) shu holatlarda yopiq; qolgani — "postavkada" (qabul qilinmagan: sotuvchida yoki
# Uzum logistikasi bilan omborga yo'lda — ikkalasi ham Uzum qoldig'ida yo'q, o'z omborimda bo'sh emas).
CLOSED_INVOICES = frozenset({"ACCEPTED", "CANCELED", "CANCELLED", "REJECTED", "DELETED"})
CHINA_STAGES = frozenset({Stage.ORDERED, Stage.PAID, Stage.CN_WAREHOUSE})
ROAD_STAGES = frozenset({Stage.SHIPPED, Stage.ARRIVED})


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
    china: int  # buyurtma qilingan, Xitoyda
    road: int  # yo'lda
    own: int  # o'z omborimda (Uzumga yuborilmagan, postavkadagisi ayirilgan)
    inbound: int  # postavkada — qabul qilinmagan (ADR-034)
    unit_cost: Money | None
    stock_value: Money | None
    reorder: Reorder | None
    order_by: OrderBy | None

    @property
    def in_transit(self) -> int:
        """Xitoyda + yo'lda (hali Toshkentda qabul qilinmagan)."""
        return self.china + self.road

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
    units: dict[
        str, int
    ]  # joylar bo'yicha dona (Xitoyda, yo'lda, o'z omborim — tovar bo'yicha bir marta)


def _stages(p: Any) -> dict[str, int]:
    """Xarid sanalari → F25 bosqich kunlari (``upcore.purchasing.stage_days``)."""
    return stage_days(stage_dates(p))


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
    last_price: Money | None = None


async def _lots(conn: AsyncConnection, items: Iterable[UUID], as_of: date) -> dict[UUID, _ItemLots]:
    lt, p, pl = m.lots, m.purchases, m.purchase_lines
    out: dict[UUID, _ItemLots] = {}
    rows = await conn.execute(
        select(
            lt.c.item_id,
            lt.c.ready_on,
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
        x = out.setdefault(r.item_id, _ItemLots())
        newer = x.ready_on is None or (r.ready_on is not None and r.ready_on >= x.ready_on)
        if r.ready_on is not None and r.ready_on <= as_of and newer:
            x.unit_cost, x.ready_on = Money(r.unit_cost, UZS), r.ready_on
        if r.unit_price is not None and r.currency in Currency.__members__:
            x.last_price = Money(r.unit_price, Currency(r.currency))
    # F41 (ADR-033): boshlashdan keyin tayyor partiya bo'lmasa — boshlang'ich holat narxi (qoldiq shu narxda).
    start = await conn.scalar(select(m.orgs.c.cost_start_on))
    if start is not None:
        for item_id, opening in (await openings(conn, start, set(items))).items():
            unit = opening.price_on(start)
            x = out.setdefault(item_id, _ItemLots())
            if unit is not None and (x.ready_on is None or x.ready_on < start):
                x.unit_cost, x.ready_on = unit, start
    return out


@dataclass
class _Places:
    """Tovarning Uzumdan tashqaridagi joylari (xarid bosqichi bo'yicha) va ularning qiymati (lot tannarxi)."""

    china: int = 0
    road: int = 0
    received: int = 0  # qabul qilingan, Uzumga yuborilmagan (tuzatishsiz)
    reserved: int = (
        0  # ADR-034: qabul qilinmagan postavkalarga ajratilgan (o'z omborimdan ayiriladi)
    )
    adjust: int = 0
    writeoff: int = 0
    # (dona, birlik tannarx) — tannarxi hisoblangan qatorlar bo'yicha
    china_lots: list[tuple[int, Decimal]] = field(default_factory=list)
    road_lots: list[tuple[int, Decimal]] = field(default_factory=list)
    own_lots: list[tuple[int, Decimal]] = field(default_factory=list)

    @property
    def own(self) -> int:
        return max(0, own_warehouse_qty(self.received, self.adjust, self.writeoff) - self.reserved)

    def own_unit_cost(self) -> Decimal | None:
        """O'z omboridagi tovarning o'rtacha birlik tannarxi (qatorlar donasi bo'yicha vaznli)."""
        qty = sum(q for q, _ in self.own_lots)
        return sum((q * c for q, c in self.own_lots), Decimal(0)) / qty if qty else None


async def inbound_by_sku(conn: AsyncConnection) -> dict[UUID, int]:
    """ADR-034: SKU → qabul qilinmagan postavkalardagi dona (``quantityToStock``; yopiq holatdagilar — yo'q)."""
    v, i = m.fbo_invoices, m.fbo_invoice_items
    rows = await conn.execute(
        select(i.c.sku_id, func.sum(i.c.quantity_to_stock).label("qty"))
        .join(v, v.c.id == i.c.invoice_id)
        .where(
            i.c.sku_id.is_not(None),
            func.upper(func.coalesce(v.c.status, "")).not_in(CLOSED_INVOICES),
        )
        .group_by(i.c.sku_id)
    )
    return {r.sku_id: int(r.qty or 0) for r in rows if r.qty}


async def _places(conn: AsyncConnection, items: Iterable[UUID]) -> dict[UUID, _Places]:
    p, pl, lt, sm = m.purchases, m.purchase_lines, m.lots, m.stock_moves
    out: dict[UUID, _Places] = {}
    rows = await conn.execute(
        select(pl.c.item_id, pl.c.ordered_qty, pl.c.received_qty, lt.c.unit_cost, p)
        .join(p, p.c.id == pl.c.purchase_id)
        .join(lt, lt.c.purchase_line_id == pl.c.id, isouter=True)
        .where(pl.c.item_id.in_(list(items)))
    )
    for r in rows:
        stage = current_stage(stage_dates(r))
        x = out.setdefault(r.item_id, _Places())
        cost = r.unit_cost
        if stage in CHINA_STAGES:
            x.china += r.ordered_qty
            if cost is not None:
                x.china_lots.append((r.ordered_qty, cost))
        elif stage in ROAD_STAGES:
            x.road += r.ordered_qty
            if cost is not None:
                x.road_lots.append((r.ordered_qty, cost))
        elif stage is Stage.RECEIVED:
            qty = r.received_qty if r.received_qty is not None else r.ordered_qty
            x.received += qty
            if cost is not None:
                x.own_lots.append((qty, cost))
    for mv in await conn.execute(
        select(sm.c.item_id, sm.c.kind, func.sum(sm.c.qty).label("qty"))
        .where(sm.c.item_id.in_(list(items)), sm.c.kind.in_(("adjust", "writeoff")))
        .group_by(sm.c.item_id, sm.c.kind)
    ):
        x = out.setdefault(mv.item_id, _Places())
        if mv.kind == "adjust":
            x.adjust = int(mv.qty)
        else:
            x.writeoff = abs(int(mv.qty))
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
    cfg = await orgsettings.load(conn)
    inv = cfg.inventory()
    lots = await _lots(conn, items, as_of) if items else {}
    history = await _lead_history(conn, items) if items else {}
    places = await _places(conn, items) if items else {}
    inbound = await inbound_by_sku(conn)
    # O'z omborimdan postavkaga ajratilgani ayiriladi (xarid "Uzumga yuborildi" deb belgilanmagan bo'lsa ikki marta
    # sanalmasin; belgilangan bo'lsa o'z omborim allaqachon 0 — manfiy bo'lmaydi).
    inbound_item: dict[UUID, int] = {}
    for r in skus:
        if r.item_id is not None and inbound.get(r.id):
            inbound_item[r.item_id] = inbound_item.get(r.item_id, 0) + inbound[r.id]
    for item_id, qty in inbound_item.items():
        if item_id in places:
            places[item_id].reserved = qty
    abc = abc_classes({str(r.id): revenue30.get(r.id, Money.zero(UZS)) for r in skus}, inv)

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
            learned = lead_time(history.get(r.item_id, {}), cfg.lead_days, inv)
            lead = learned if set(learned.stages) >= set(STAGES) else None
        if lead is not None:
            status = stock_status(stock, v.value, lead.total)
        else:  # muddatsiz faqat "Harakatsiz" aniq (tezlik 0)
            status = stock_status(stock, v.value, 0) if v.value <= 0 else None
        item = lots.get(r.item_id) if r.item_id is not None else None
        place = places.get(r.item_id) if r.item_id is not None else None
        china, road, own = (place.china, place.road, place.own) if place else (0, 0, 0)
        sku_inbound = inbound.get(r.id, 0)
        unit = item.unit_cost if item else None
        cover = days_of_stock(active, fbs, v.value)
        value = None
        if unit is not None:
            parts = [Holding("fbo", active, unit), Holding("fbs", fbs, unit)]
            parts.append(Holding("defected", defected, unit))
            parts.append(Holding("inbound", sku_inbound, unit))
            holdings += parts
            value = unit * stock
            weighted.append((cover, value))
        elif stock + defected + sku_inbound > 0:
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
                in_transit=road + own + sku_inbound,
                ordered=china,
                last_unit_prices=prices,
                s=inv,
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
            china=china,
            road=road,
            own=own,
            inbound=sku_inbound,
            unit_cost=unit,
            stock_value=value,
            reorder=plan,
            order_by=order_by(as_of, cover, lead.total) if lead is not None else None,
        )
    units = {"china": 0, "road": 0, "own": 0}
    for x in (
        places.values()
    ):  # F29: joylar tovar bo'yicha bir marta (bir necha SKU'da ikki marta sanalmaydi)
        holdings += [Holding("china", q, Money(c, UZS)) for q, c in x.china_lots]
        holdings += [Holding("road", q, Money(c, UZS)) for q, c in x.road_lots]
        own_cost = x.own_unit_cost()
        if own_cost is not None:
            holdings.append(Holding("own", x.own, Money(own_cost, UZS)))
        units["china"] += x.china
        units["road"] += x.road
        units["own"] += x.own
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
        units=units
        | {
            "fbo": sum(s.qty_active for s in out.values()),
            "fbs": sum(s.qty_fbs for s in out.values()),
            "defected": sum(s.qty_defected for s in out.values()),
            "inbound": sum(s.inbound for s in out.values()),
        },
    )

"""``/inventory``: qoldiq va zaxira (M10 asos; F23–F30). Ruxsat — ``view_purchases`` (omborchi ham); summalar
(lot narxi, qiymat, byudjet, muzlagan pul) faqat ``view_purchase_amounts`` bilan, aks holda ``null`` (03 §10:
omborchi summasiz).

Har SKU: Uzum qoldig'i (FBO, FBS, brak, kutilayotgan), sotuv tezligi (F23, tarkibi bilan), zaxira kunlari (F24),
to'liq muddat (F25), holat (F26, mahsulot darajasida ham), tavsiya miqdor va byudjet (F27), ABC/XYZ (F28),
nelikvid/sekin (F30), yo'ldagi dona. Jami: muzlagan pul joylar bo'yicha va o'rtacha sotilish muddati (F29).
Joylar (B4.7): Xitoyda, yo'lda, o'z omborim (xarid bosqichidan; ``stock_moves`` tuzatishlari bilan), FBO, FBS, brak;
buyurtma sanasi (F27: zaxira kunlari − to'liq muddat). Hisob — :mod:`upapi.reports.stock`; FBO yuborish rejasi,
postavkalar, yo'qolgan tovar (F31–F34) — B5.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from upcore.inventory import StockStatus
from upcore.metrics import Period
from upcore.money import Currency, total

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission, allowed
from upapi.reports.common import (
    Cursor,
    Filters,
    Heavy,
    Limit,
    Meta,
    decode_cursor,
    encode_cursor,
    fold,
    meta,
    sku_catalog,
    today,
)
from upapi.reports.schemas import amount
from upapi.reports.stock import SkuStock, load_stock

router = APIRouter(tags=["reports"])
Stock = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
KINDS = ["products", "snapshot", "orders"]
SEVERITY = {s: i for i, s in enumerate(StockStatus)}
UZS = Currency.UZS


class VelocityOut(BaseModel):
    value: Decimal  # F23, dona/kun
    base: Decimal
    return_rate: Decimal
    trend_ratio: Decimal | None
    trend_factor: Decimal
    days_counted: int


class LeadOut(BaseModel):
    total: Decimal  # F25, kun
    stages: dict[str, Decimal]
    learned: list[str]


class PriceOut(BaseModel):
    amount: Decimal
    currency: str


class ReorderOut(BaseModel):
    qty: int  # F27
    raw: Decimal
    budget: list[PriceOut] | None  # summasiz rolda null


class LocationsOut(BaseModel):
    """M10 joylar (dona): Uzum FBO/FBS/brak/kutilayotgan va Uzumdan tashqarida — Xitoyda, yo'lda, o'z omborimda."""

    fbo: int
    fbs: int
    defected: int
    pending: int
    china: int
    road: int
    own: int
    inbound: int  # postavkada — qabul qilinmagan (ADR-034)


class OrderByOut(BaseModel):
    day: date  # F27: shu kungacha buyurtma berilsa tovar tugamasdan keladi
    overdue: bool  # kechikkan — sana bugun


class StockRowOut(BaseModel):
    sku_id: UUID
    shop_id: UUID
    item_id: UUID | None
    product_id: UUID | None
    title: str | None
    product_title: str | None
    qty_active: int
    qty_fbs: int
    qty_defected: int
    qty_pending: int
    stock: int
    in_transit: int  # Xitoyda + yo'lda
    locations: LocationsOut
    velocity: VelocityOut
    days_of_stock: Decimal | None  # F24
    lead_time: LeadOut | None  # F25 (tarix yo'q — null)
    status: StockStatus | None  # F26
    product_status: StockStatus | None
    abc: str  # F28
    xyz: str | None
    liquidity: str | None  # F30
    last_sale_on: date | None
    order_by: OrderByOut | None  # F27 buyurtma sanasi (tezlik 0 yoki muddat noma'lum — null)
    reorder: ReorderOut | None
    unit_cost: Decimal | None  # lot narxi (so'm)
    stock_value: Decimal | None


class StockTotalsOut(BaseModel):
    frozen_money: (
        dict[str, Decimal] | None
    )  # F29 joylar bo'yicha (china, road, own, inbound, fbo, fbs, defected)
    frozen_total: Decimal | None
    average_days_to_sell: Decimal | None  # F29
    uncosted: int  # qoldig'i bor, lot narxi yo'q SKU'lar
    units: dict[str, int]  # joylar bo'yicha dona (summasiz rolda ham)
    statuses: dict[str, int]


class InventoryOut(BaseModel):
    meta: Meta
    as_of: date
    items: list[StockRowOut]
    total: int
    next_cursor: str | None
    totals: StockTotalsOut


def _order(s: SkuStock) -> tuple[int, Decimal, str]:
    """Eng og'ir holat birinchi, keyin zaxira kunlari eng kami birinchi."""
    rank = SEVERITY[s.status] if s.status is not None else len(SEVERITY)
    days = s.days_of_stock if s.days_of_stock is not None else Decimal("Infinity")
    return (rank, days, str(s.sku_id))


@router.get("/orgs/{org_id}/inventory", response_model=InventoryOut)
async def inventory(
    ctx: Stock,
    _: Heavy,
    shop: Annotated[list[UUID] | None, Query(description="Do'konlar")] = None,
    as_of: Annotated[date | None, Query(description="Qaysi kun holatiga; standart — bugun")] = None,
    status: StockStatus | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = 100,
    cursor: Cursor = None,
) -> InventoryOut:
    day = as_of or today()
    f = Filters(Period(day, day), frozenset(shop) if shop else None, today())
    amounts = allowed(ctx.role, Permission.VIEW_PURCHASE_AMOUNTS)
    book = await load_stock(ctx.conn, shop, day)
    catalog = await sku_catalog(ctx.conn, f.shops)
    needle = fold(q).strip() if q else ""
    chosen = [
        s
        for s in book.skus.values()
        if (status is None or s.status is status)
        and (not needle or needle in catalog[s.sku_id].haystack())
    ]
    chosen.sort(key=_order)
    offset = int((decode_cursor(cursor, 1) or [0])[0])
    page = chosen[offset : offset + limit]
    rows = []
    for s in page:
        info = catalog[s.sku_id]
        plan = None
        if s.reorder is not None:
            plan = ReorderOut(
                qty=s.reorder.qty,
                raw=s.reorder.raw,
                budget=[
                    PriceOut(amount=p.amount, currency=p.currency.value) for p in s.reorder.budget
                ]
                if amounts
                else None,
            )
        rows.append(
            StockRowOut(
                sku_id=s.sku_id,
                shop_id=s.shop_id,
                item_id=s.item_id,
                product_id=s.product_id,
                title=info.title,
                product_title=info.product_title,
                qty_active=s.qty_active,
                qty_fbs=s.qty_fbs,
                qty_defected=s.qty_defected,
                qty_pending=s.qty_pending,
                stock=s.stock,
                in_transit=s.in_transit,
                locations=LocationsOut(
                    fbo=s.qty_active,
                    fbs=s.qty_fbs,
                    defected=s.qty_defected,
                    pending=s.qty_pending,
                    china=s.china,
                    road=s.road,
                    own=s.own,
                    inbound=s.inbound,
                ),
                velocity=VelocityOut(
                    value=s.velocity.value,
                    base=s.velocity.base,
                    return_rate=s.velocity.return_rate,
                    trend_ratio=s.velocity.trend_ratio,
                    trend_factor=s.velocity.trend_factor,
                    days_counted=s.velocity.days_counted,
                ),
                days_of_stock=s.days_of_stock,
                lead_time=LeadOut(
                    total=s.lead.total, stages=dict(s.lead.stages), learned=sorted(s.lead.learned)
                )
                if s.lead
                else None,
                status=s.status,
                product_status=book.products.get(s.product_id) if s.product_id else None,
                abc=s.abc.value,
                xyz=s.xyz.value if s.xyz else None,
                liquidity=s.liquidity.value if s.liquidity else None,
                last_sale_on=s.last_sale,
                order_by=OrderByOut(day=s.order_by.day, overdue=s.order_by.overdue)
                if s.order_by
                else None,
                reorder=plan,
                unit_cost=amount(s.unit_cost) if amounts else None,
                stock_value=amount(s.stock_value) if amounts else None,
            )
        )
    counts: dict[str, int] = {}
    for s in book.skus.values():
        if s.status is not None:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
    frozen = {k: v.amount for k, v in book.frozen.items()}
    return InventoryOut(
        meta=await meta(ctx.conn, f, KINDS),
        as_of=day,
        items=rows,
        total=len(chosen),
        next_cursor=encode_cursor([offset + limit]) if offset + limit < len(chosen) else None,
        totals=StockTotalsOut(
            frozen_money=frozen if amounts else None,
            frozen_total=total(list(book.frozen.values()), UZS).amount if amounts else None,
            average_days_to_sell=book.average_days,
            uncosted=book.uncosted,
            units=book.units,
            statuses=dict(sorted(counts.items())),
        ),
    )

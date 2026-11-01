"""``/opening``: boshlang'ich holat (B4.12, ADR-033, F41).

Sotuvchi hamma eski partiyani kiritmasdan boshlaydi: **boshlash sanasi** (``orgs.cost_start_on``), har tovarga
**tarixiy tannarx** (``item_costs``, sana bo'yicha davrlar bilan) va boshlash kunidagi **qoldiq** (``opening_stock``:
Uzumda + o'z omborimda). Undan oldingi sotuvlar tarixiy narxda ("tarixiy" belgisi — taxminiy), keyingilari
partiyalardan (F21); boshlang'ich qoldiq — birinchi lot (:mod:`upcore.costing`).

- ``GET`` — jadval: tovarlar va tovarga bog'lanmagan SKU'lar, oxirgi 90 kun tushumi bo'yicha (avval eng muhimlari),
  Uzum qoldig'i taklifi (boshlash sanasi bugun yoki keyin — joriy qoldiq; o'tgan sana — oldingi kun snapshoti,
  yo'q bo'lsa ``null``), saqlangan qiymatlar, oxirgi partiya narxi (ishora) va qamrov (tushumning qancha qismida
  tannarx manbasi bor). ``?start=`` — boshqa sana uchun taklif. ``?shop=`` (bir necha marta) — tanlangan do'konlarda
  SKU'si bor tovarlar; tannarx va qoldiq tovar bo'yicha umumiy (``shared`` — boshqa do'konda ham sotiladi).
  ``product_id`` — Uzum mahsuloti (birinchi SKU'niki): sahifa turlarni (rang, model) mahsulot bo'yicha guruhlaydi.
- ``PUT`` — sana va qatorlarni saqlaydi. Tovarga bog'lanmagan SKU uchun tovar yaratiladi (SKU nomi bilan) va
  bog'lanadi. Qator narxlari to'liq almashtiriladi; narxi ham, qoldig'i ham yo'q qator — o'chiriladi. Sana
  o'zgarsa — hamma tovar, aks holda faqat o'zgargan tovarlar qayta hisoblanadi (navbat orqali, "qayta hisoblandi").

O'qish — ``view_finance`` (tannarx summasi); yozish — ``manage_settings`` (egasi, menejer); audit jurnali. Sinxron bu
jadvallarga tegmaydi (tamoyil 7).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports.common import sku_catalog, today
from upapi.routes.purchases import _kick

router = APIRouter(tags=["costing"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
REVENUE_DAYS = 90
MAX_ROWS = 5000
MAX_QTY = 10_000_000
Cost = Annotated[Decimal, Field(ge=0, le=Decimal("1e12"), max_digits=14, decimal_places=2)]
Qty = Annotated[int, Field(ge=0, le=MAX_QTY)]
Shops = Annotated[list[UUID] | None, Query(description="Do'konlar (bir necha marta)")]


class PriceOut(BaseModel):
    valid_from: date | None
    unit_cost: Decimal


class OpeningRowOut(BaseModel):
    """Bitta tovar (``item_id``) yoki tovarga bog'lanmagan SKU (``sku_id``, ``item_id`` — ``null``)."""

    item_id: UUID | None
    sku_id: UUID | None
    name: str
    skus: list[str]
    shared: bool  # tovar tanlanmagan do'konda ham sotiladi (narx va qoldiq — hamma do'kon bo'yicha)
    # Uzum mahsuloti (bir nechta SKU — rang, model ...): sahifada guruh, "hammasiga bitta narx" uchun.
    product_id: UUID | None
    product: str | None
    revenue: Decimal  # oxirgi 90 kun
    uzum_suggested: (
        int | None
    )  # boshlash sanasidagi Uzum qoldig'i (FBO + FBS); ``null`` — snapshot yo'q
    uzum_qty: int | None  # saqlangan (``null`` — hali kiritilmagan)
    own_qty: int | None
    prices: list[PriceOut]
    last_lot_cost: Decimal | None  # oxirgi tayyor partiya birlik tannarxi (ishora)
    lots_after: int  # boshlash sanasidan keyin tayyor (yoki yo'ldagi) partiyalar
    lots_before: int  # boshlashdan oldin tayyor — ishlatilmaydi (qoldiqqa kirgan)


class OpeningOut(BaseModel):
    start_on: date | None  # saqlangan sana (``null`` — o'chirilgan)
    as_of: date  # takliflar shu sana uchun (``?start=`` yoki saqlangan, bo'lmasa bugun)
    stock_source: str  # ``current`` (joriy qoldiq) | ``snapshot`` (oldingi kun) | ``none``
    coverage: Decimal | None  # tushumning tannarx manbasi bor ulushi (0–1); tushum yo'q — ``null``
    rows: list[OpeningRowOut]


class PriceIn(BaseModel):
    valid_from: date | None = None
    unit_cost: Cost


class OpeningRowIn(BaseModel):
    item_id: UUID | None = None
    sku_id: UUID | None = None
    uzum_qty: Qty = 0
    own_qty: Qty = 0
    prices: Annotated[list[PriceIn], Field(max_length=50)] = []

    @model_validator(mode="after")
    def _check(self) -> OpeningRowIn:
        if (self.item_id is None) == (self.sku_id is None):
            raise ValueError("item_id yoki sku_id — bittasi kerak")
        days = [p.valid_from for p in self.prices]
        if len(set(days)) != len(days):
            raise ValueError("bir sanada bitta narx")
        return self


class OpeningIn(BaseModel):
    start_on: date | None
    rows: Annotated[list[OpeningRowIn], Field(max_length=MAX_ROWS)] = []


async def _stock(conn: Any, as_of: date) -> tuple[dict[UUID, int], str]:
    """SKU → Uzum qoldig'i (FBO + FBS) boshlash kuni boshida."""
    k, d = m.mp_skus, m.sku_daily
    if as_of >= today():
        rows = await conn.execute(select(k.c.id, k.c.qty_active, k.c.qty_fbs))
        return {r.id: (r.qty_active or 0) + (r.qty_fbs or 0) for r in rows}, "current"
    rows = await conn.execute(
        select(d.c.sku_id, d.c.qty_active, d.c.qty_fbs).where(d.c.day == as_of - timedelta(days=1))
    )
    out = {r.sku_id: (r.qty_active or 0) + (r.qty_fbs or 0) for r in rows}
    return out, "snapshot" if out else "none"


async def _read(
    ctx: OrgContext, start: date | None, shops: frozenset[UUID] | None = None
) -> OpeningOut:
    conn = ctx.conn
    saved = await conn.scalar(select(m.orgs.c.cost_start_on).where(m.orgs.c.id == ctx.org_id))
    as_of = start or saved or today()
    catalog = await sku_catalog(conn)
    stock, source = await _stock(conn, as_of)
    dm = m.daily_sku_metrics
    revenue = {
        r.sku_id: Decimal(r.revenue)
        for r in await conn.execute(
            select(dm.c.sku_id, func.sum(dm.c.revenue).label("revenue"))
            .where(dm.c.day >= today() - timedelta(days=REVENUE_DAYS), dm.c.sku_id.is_not(None))
            .group_by(dm.c.sku_id)
        )
    }
    items = {r.id: r.name for r in await conn.execute(select(m.items.c.id, m.items.c.name))}
    prices: dict[UUID, list[PriceOut]] = {}
    ic = m.item_costs
    for r in await conn.execute(select(ic).order_by(ic.c.valid_from.nulls_first())):
        prices.setdefault(r.item_id, []).append(
            PriceOut(valid_from=r.valid_from, unit_cost=r.unit_cost)
        )
    opening = {r.item_id: r for r in await conn.execute(select(m.opening_stock))}
    lt = m.lots
    lots: dict[UUID, list[Any]] = {}
    for r in await conn.execute(
        select(lt.c.item_id, lt.c.ready_on, lt.c.unit_cost)
        .where(lt.c.item_id.is_not(None))
        .order_by(lt.c.ready_on.nulls_last(), lt.c.created_at)
    ):
        lots.setdefault(r.item_id, []).append(r)

    groups: dict[UUID, list[UUID]] = {}
    lone: list[UUID] = []
    for sku in catalog.values():
        if sku.item_id is None:
            lone.append(sku.id)
        else:
            groups.setdefault(sku.item_id, []).append(sku.id)
    for item_id in prices.keys() | opening.keys():
        groups.setdefault(item_id, [])
    if shops:  # do'kon filtri: tanlangan do'konda SKU'si bor tovarlar (tannarx va qoldiq — tovar bo'yicha umumiy)
        groups = {i: g for i, g in groups.items() if any(catalog[x].shop_id in shops for x in g)}
        lone = [x for x in lone if catalog[x].shop_id in shops]

    catalog_shops = frozenset(
        x.shop_id for x in catalog.values()
    )  # filtrsiz — hech narsa "boshqa do'kon" emas

    def stock_of(skus: list[UUID]) -> int | None:
        known = [stock[s] for s in skus if s in stock]
        return sum(known) if known else (None if source != "current" or skus else 0)

    rows: list[OpeningRowOut] = []
    for item_id, skus in groups.items():
        item_lots = lots.get(item_id, [])
        ready = [x for x in item_lots if x.ready_on is not None and x.ready_on <= today()]
        saved_row = opening.get(item_id)
        rows.append(
            OpeningRowOut(
                item_id=item_id,
                sku_id=None,
                name=items.get(item_id, "—"),
                skus=[catalog[s].title or "—" for s in skus],
                product_id=catalog[skus[0]].product_id if skus else None,
                product=catalog[skus[0]].product_title if skus else None,
                shared=any(catalog[s].shop_id not in (shops or catalog_shops) for s in skus),
                revenue=sum((revenue.get(s, Decimal(0)) for s in skus), Decimal(0)),
                uzum_suggested=stock_of(skus),
                uzum_qty=saved_row.uzum_qty if saved_row else None,
                own_qty=saved_row.own_qty if saved_row else None,
                prices=prices.get(item_id, []),
                last_lot_cost=ready[-1].unit_cost if ready else None,
                lots_after=sum(1 for x in item_lots if x.ready_on is None or x.ready_on >= as_of),
                lots_before=sum(
                    1 for x in item_lots if x.ready_on is not None and x.ready_on < as_of
                ),
            )
        )
    for sku_id in lone:
        info = catalog[sku_id]
        rows.append(
            OpeningRowOut(
                item_id=None,
                sku_id=sku_id,
                name=info.product_title or info.title or "—",
                skus=[info.title or "—"],
                product_id=info.product_id,
                product=info.product_title,
                shared=False,
                revenue=revenue.get(sku_id, Decimal(0)),
                uzum_suggested=stock.get(sku_id, 0 if source == "current" else None),
                uzum_qty=None,
                own_qty=None,
                prices=[],
                last_lot_cost=None,
                lots_after=0,
                lots_before=0,
            )
        )
    rows.sort(key=lambda r: (-r.revenue, r.name, str(r.item_id or r.sku_id)))
    total = sum((r.revenue for r in rows), Decimal(0))
    covered = sum((r.revenue for r in rows if r.prices or r.lots_after), Decimal(0))
    return OpeningOut(
        start_on=saved,
        as_of=as_of,
        stock_source=source,
        coverage=(covered / total).quantize(Decimal("0.0001")) if total else None,
        rows=rows,
    )


@router.get("/orgs/{org_id}/opening", response_model=OpeningOut)
async def get_opening(
    ctx: Viewer, start: Annotated[date | None, Query()] = None, shop: Shops = None
) -> OpeningOut:
    """Boshlang'ich holat jadvali (F41); ``start`` — boshqa boshlash sanasi uchun qoldiq taklifi."""
    if start is not None and start > today():
        raise AppError("bad_day", 422, detail="kelajak sanasi bo'lmaydi")
    return await _read(ctx, start, frozenset(shop) if shop else None)


async def _item_for(ctx: OrgContext, row: OpeningRowIn) -> UUID:
    if row.item_id is not None:
        found = await ctx.conn.scalar(select(m.items.c.id).where(m.items.c.id == row.item_id))
        if found is None:
            raise AppError("item_not_found", 404)
        return row.item_id
    k = m.mp_skus
    sku = (await ctx.conn.execute(select(k).where(k.c.id == row.sku_id))).first()
    if sku is None:
        raise AppError("sku_not_found", 404)
    if sku.item_id is not None:
        return UUID(str(sku.item_id))
    info = (await sku_catalog(ctx.conn, ids=[sku.id]))[sku.id]
    name = (info.product_title or info.title or "").strip() or "—"
    item_id: UUID = await ctx.conn.scalar(
        insert(m.items).values(org_id=ctx.org_id, name=name).returning(m.items.c.id)
    )
    await ctx.conn.execute(
        update(k).where(k.c.id == sku.id).values(item_id=item_id, updated_at=func.now())
    )
    await ctx.audit("item.create", "item", item_id, after={"name": name, "sku_id": str(sku.id)})
    await calc.request(ctx.conn, ctx.org_id, calc.Scope.SHOP, sku.shop_id)
    return item_id


@router.put("/orgs/{org_id}/opening", response_model=OpeningOut)
async def put_opening(
    body: OpeningIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
    shop: Shops = None,
) -> OpeningOut:
    """Boshlash sanasi va qatorlar (F41). ``start_on: null`` — o'chirish (kiritilgan narxlar saqlanadi)."""
    if body.start_on is not None and body.start_on > today():
        raise AppError("bad_day", 422, detail="kelajak sanasi bo'lmaydi")
    conn, o = ctx.conn, m.orgs
    before = await conn.scalar(select(o.c.cost_start_on).where(o.c.id == ctx.org_id))
    if before != body.start_on:
        await conn.execute(
            update(o)
            .where(o.c.id == ctx.org_id)
            .values(cost_start_on=body.start_on, updated_at=func.now())
        )
        await ctx.audit(
            "opening.start",
            "org",
            ctx.org_id,
            before={"start_on": None if before is None else before.isoformat()},
            after={"start_on": None if body.start_on is None else body.start_on.isoformat()},
        )
    ic, os_ = m.item_costs, m.opening_stock
    touched: set[UUID] = set()
    for row in body.rows:
        item_id = await _item_for(ctx, row)
        if item_id in touched:
            raise AppError("duplicate_item", 422, detail="tovar ikki marta berilgan")
        old_prices = [
            (r.valid_from, r.unit_cost)
            for r in await conn.execute(
                select(ic.c.valid_from, ic.c.unit_cost)
                .where(ic.c.item_id == item_id)
                .order_by(ic.c.valid_from.nulls_first())
            )
        ]
        new_prices = sorted(
            ((p.valid_from, p.unit_cost) for p in row.prices), key=lambda x: x[0] or date.min
        )
        old_stock = (await conn.execute(select(os_).where(os_.c.item_id == item_id))).first()
        old_qty = (old_stock.uzum_qty, old_stock.own_qty) if old_stock else None
        new_qty = (
            (row.uzum_qty, row.own_qty) if (row.uzum_qty or row.own_qty or row.prices) else None
        )
        same_prices = [(f, Decimal(c)) for f, c in old_prices] == [
            (f, Decimal(c)) for f, c in new_prices
        ]
        if same_prices and old_qty == new_qty:
            continue
        touched.add(item_id)
        await conn.execute(delete(ic).where(ic.c.item_id == item_id))
        if new_prices:
            await conn.execute(
                insert(ic),
                [
                    {"org_id": ctx.org_id, "item_id": item_id, "valid_from": f, "unit_cost": c}
                    for f, c in new_prices
                ],
            )
        if new_qty is None:
            await conn.execute(delete(os_).where(os_.c.item_id == item_id))
        else:
            stmt = pg_insert(os_).values(
                org_id=ctx.org_id, item_id=item_id, uzum_qty=new_qty[0], own_qty=new_qty[1]
            )
            await conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=["org_id", "item_id"],
                    set_={"uzum_qty": new_qty[0], "own_qty": new_qty[1], "updated_at": func.now()},
                )
            )
        await ctx.audit(
            "opening.item",
            "item",
            item_id,
            before={
                "prices": [[None if f is None else f.isoformat(), str(c)] for f, c in old_prices],
                "qty": old_qty,
            },
            after={
                "prices": [[None if f is None else f.isoformat(), str(c)] for f, c in new_prices],
                "qty": new_qty,
            },
        )
    if before != body.start_on:
        await calc.request(conn, ctx.org_id, calc.Scope.ITEM)  # hamma tovar
    else:
        for item_id in touched:
            await calc.request(conn, ctx.org_id, calc.Scope.ITEM, item_id)
    if before != body.start_on or touched:
        background.add_task(_kick, request, ctx.org_id)
    return await _read(ctx, None, frozenset(shop) if shop else None)

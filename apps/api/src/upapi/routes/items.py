"""``/items``, ``/skus/{id}/item``: tovar (item) ↔ SKU bog'lash (M6, 03 §5).

Bitta jismoniy tovar bir necha do'kon / marketplace SKU'siga bog'lanishi mumkin; tannarx va ombor tovar darajasida
yuritiladi. Standart — har SKU alohida tovar (yoki tovarsiz); birlashtirish qo'lda. Bog'lash tannarxga ta'sir qiladi,
shuning uchun ``manage_purchases`` ruxsati (egasi, menejer, omborchi) va audit jurnali kerak. Sinxron ``item_id`` ga
tegmaydi (tamoyil 7). O'zgargach eski va yangi tovar, SKU do'koni qayta hisoblanadi (``upapi.calc``, navbat orqali).
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports.common import fold
from upapi.routes.skus import LinkedItemOut, item_of

router = APIRouter(tags=["catalog"])
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]
MAX_ITEMS = 500


class ItemOut(BaseModel):
    id: UUID
    name: str
    image_url: str | None
    sku_count: int


class ItemsOut(BaseModel):
    items: list[ItemOut]


class ItemLinkIn(BaseModel):
    """``existing`` — mavjud tovarga (``item_id``); ``new`` — SKU nomi (yoki ``name``) bilan yangi tovar; ``none`` —
    tovardan ajratish (tovar o'zi saqlanadi)."""

    mode: Literal["existing", "new", "none"]
    item_id: UUID | None = None
    name: Annotated[str | None, Field(max_length=200)] = None


@router.get("/orgs/{org_id}/items", response_model=ItemsOut)
async def list_items(
    ctx: Manager, q: Annotated[str | None, Query(max_length=100)] = None
) -> ItemsOut:
    """Tovarlar (bog'lash tanlovi uchun): nom bo'yicha qidiruv (lotin/kirill, tutuq turidan qat'i nazar)."""
    i, k = m.items, m.mp_skus
    counts = select(k.c.item_id, func.count().label("n")).group_by(k.c.item_id).subquery()
    rows = await ctx.conn.execute(
        select(i.c.id, i.c.name, i.c.image_url, func.coalesce(counts.c.n, 0).label("n"))
        .outerjoin(counts, counts.c.item_id == i.c.id)
        .order_by(i.c.name, i.c.id)
    )
    needle = fold(q).strip() if q else ""
    found = [r for r in rows if not needle or needle in fold(r.name)]
    return ItemsOut(
        items=[
            ItemOut(id=r.id, name=r.name, image_url=r.image_url, sku_count=int(r.n))
            for r in found[:MAX_ITEMS]
        ]
    )


@router.put("/orgs/{org_id}/skus/{sku_id}/item", response_model=LinkedItemOut | None)
async def link_item(sku_id: UUID, body: ItemLinkIn, ctx: Manager) -> LinkedItemOut | None:
    k = m.mp_skus
    sku = (await ctx.conn.execute(select(k).where(k.c.id == sku_id))).first()
    if sku is None:
        raise AppError("sku_not_found", 404)
    before = sku.item_id
    target: UUID | None = None
    if body.mode == "existing":
        if body.item_id is None:
            raise AppError("bad_request", 422, detail="item_id kerak")
        found = await ctx.conn.scalar(select(m.items.c.id).where(m.items.c.id == body.item_id))
        if found is None:
            raise AppError("item_not_found", 404)
        target = found
    elif body.mode == "new":
        name = (body.name or sku.sku_code or "").strip()
        if not name:
            raise AppError("bad_request", 422, detail="Tovar nomi kerak")
        target = await ctx.conn.scalar(
            insert(m.items).values(org_id=ctx.org_id, name=name).returning(m.items.c.id)
        )
        await ctx.audit("item.create", "item", target, after={"name": name, "sku_id": str(sku_id)})
    if target != before:
        await ctx.conn.execute(
            update(k).where(k.c.id == sku_id).values(item_id=target, updated_at=func.now())
        )
        await ctx.audit(
            "sku.link_item",
            "sku",
            sku_id,
            before={"item_id": None if before is None else str(before)},
            after={"item_id": None if target is None else str(target), "mode": body.mode},
        )
        # Qayta hisob: eski va yangi tovar sotuvlari, tovarsiz qolgan sotuvlar (do'kon).
        for item in (before, target):
            if item is not None:
                await calc.request(ctx.conn, ctx.org_id, calc.Scope.ITEM, item)
        await calc.request(ctx.conn, ctx.org_id, calc.Scope.SHOP, sku.shop_id)
    return None if target is None else await item_of(ctx, target)

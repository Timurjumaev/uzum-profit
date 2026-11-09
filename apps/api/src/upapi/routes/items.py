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
from upapi.reports.common import fold, sku_catalog
from upapi.routes.skus import LinkedItemOut, item_of

router = APIRouter(tags=["catalog"])
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]
MAX_ITEMS = 500
MAX_PICKER = 5000


class ItemOut(BaseModel):
    id: UUID
    name: str
    image_url: str | None
    sku_count: int


class ItemsOut(BaseModel):
    items: list[ItemOut]
    total: int  # qidiruvga mos jami tovar (``items`` — birinchi ``limit`` tasi)


class PickerRowOut(BaseModel):
    """Xarid qatori uchun tanlov qatori: SKU (``sku_id``) yoki SKU'siz tovar (``sku_id`` — ``null``). ``item_id`` —
    SKU bog'langan tovar (``null`` — tovari yo'q: tanlanganda yaratiladi)."""

    sku_id: UUID | None
    item_id: UUID | None
    item_name: str | None
    shop_id: UUID | None
    shop: str | None  # do'kon taxallusi (yo'q bo'lsa nomi)
    product_title: str | None
    title: str | None  # SKU nomi (variant: rang, o'lcham)
    article: str | None
    image_url: str | None
    stock: int | None  # Uzum omborida (FBO + FBS)
    sold: int | None  # Uzum bo'yicha jami sotilgan
    status: str | None  # Uzum SKU holati (matn sifatida, o'zgartirilmaydi)


class PickerOut(BaseModel):
    """Hamma SKU (holatidan qat'i nazar — arxivlangan va bloklangan ham): avval qoldig'i yoki sotuvi bor, keyin
    qolganlari. ``truncated`` — ro'yxat ``MAX_PICKER`` dan oshdi."""

    rows: list[PickerRowOut]
    truncated: bool


class ItemLinkIn(BaseModel):
    """``existing`` — mavjud tovarga (``item_id``); ``new`` — SKU nomi (yoki ``name``) bilan yangi tovar; ``none`` —
    tovardan ajratish (tovar o'zi saqlanadi)."""

    mode: Literal["existing", "new", "none"]
    item_id: UUID | None = None
    name: Annotated[str | None, Field(max_length=200)] = None


@router.get("/orgs/{org_id}/items", response_model=ItemsOut)
async def list_items(
    ctx: Manager,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ITEMS)] = 50,
) -> ItemsOut:
    """Tovarlar (bog'lash tanlovi uchun): nom bo'yicha qidiruv (lotin/kirill, tutuq turidan qat'i nazar), birinchi
    ``limit`` tasi va mos kelganlar soni (``total``) — tanlov 500+ tovarda ham serverda qidiradi (B4.52)."""
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
            for r in found[:limit]
        ],
        total=len(found),
    )


async def item_of_sku(ctx: OrgContext, sku_id: UUID) -> UUID:
    """SKU'ning tovari; yo'q bo'lsa — mahsulot (yoki SKU) nomi bilan yangi tovar yaratiladi va bog'lanadi (audit,
    qayta hisob navbatiga do'kon). Tannarx tovar darajasida yuritiladi; standart — har SKU alohida tovar."""
    k = m.mp_skus
    sku = (await ctx.conn.execute(select(k).where(k.c.id == sku_id))).first()
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


@router.get("/orgs/{org_id}/sku-picker", response_model=PickerOut)
async def sku_picker(ctx: Manager) -> PickerOut:
    """Xarid qatoriga tanlanadigan hamma narsa: org'ning barcha SKU'lari (do'kon, mahsulot, variant, qoldiq, holat)
    va SKU'siz qolgan tovarlar. Hech narsa holat bo'yicha yashirilmaydi — "mening SKU'm yo'q" xatosi bo'lmasin."""
    k, p, s, i = m.mp_skus, m.mp_products, m.shops, m.items
    rows = await ctx.conn.execute(
        select(
            k.c.id,
            k.c.item_id,
            k.c.shop_id,
            k.c.sku_code,
            k.c.article,
            k.c.status,
            k.c.qty_active,
            k.c.qty_fbs,
            k.c.qty_sold,
            p.c.title.label("product_title"),
            func.coalesce(s.c.alias, s.c.name).label("shop"),
            i.c.name.label("item_name"),
            i.c.image_url,
        )
        .select_from(k)
        .outerjoin(p, p.c.id == k.c.product_id)
        .outerjoin(s, s.c.id == k.c.shop_id)
        .outerjoin(i, i.c.id == k.c.item_id)
    )
    out: list[PickerRowOut] = []
    for r in rows:
        stock = (
            None
            if r.qty_active is None and r.qty_fbs is None
            else (r.qty_active or 0) + (r.qty_fbs or 0)
        )
        out.append(
            PickerRowOut(
                sku_id=r.id,
                item_id=r.item_id,
                item_name=r.item_name,
                shop_id=r.shop_id,
                shop=r.shop,
                product_title=r.product_title,
                title=r.sku_code,
                article=r.article,
                image_url=r.image_url,
                stock=stock,
                sold=r.qty_sold,
                status=r.status,
            )
        )
    orphans = await ctx.conn.execute(
        select(i.c.id, i.c.name, i.c.image_url).where(
            ~select(k.c.id).where(k.c.item_id == i.c.id).exists()
        )
    )
    for o in orphans:
        out.append(
            PickerRowOut(
                sku_id=None,
                item_id=o.id,
                item_name=o.name,
                shop_id=None,
                shop=None,
                product_title=None,
                title=None,
                article=None,
                image_url=o.image_url,
                stock=None,
                sold=None,
                status=None,
            )
        )

    def key(r: PickerRowOut) -> tuple[int, str, str, str]:
        active = (r.stock or 0) > 0 or (r.sold or 0) > 0
        return (
            0 if active else 1,
            fold(r.product_title or r.item_name or r.title or ""),
            fold(r.title or ""),
            str(r.sku_id or r.item_id),
        )

    out.sort(key=key)
    return PickerOut(rows=out[:MAX_PICKER], truncated=len(out) > MAX_PICKER)


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

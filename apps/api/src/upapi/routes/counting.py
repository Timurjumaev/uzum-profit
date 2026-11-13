"""Sanash va "Xaridni ikkiga bo'lish" (TM4, ADR-061 §5–§6; 02 M9, F20).

- ``POST /purchases/{id}/count`` — har qatorda **kelgan son** (standart = buyurtma soni) va **brak**; sog' dona = kelgan −
  brak, xaridning hamma chiqimi sog' donaga bo'linadi (F20). Qadoq qo'shimchasi (so'm/dona) — qatorga: berilmasa
  tovardagi qiymatdan nusxa; ``remember_pack`` — tovarga ham yoziladi. **Sotuvchi qaytargan summa** (ixtiyoriy, keyin ham
  — ``PATCH /purchases/{id}``) tovar summasidan ayriladi. Sanash sanasi — qabul sanasi (holat "Omborimda").
- ``POST /purchases/{id}/split`` — kam uchraydigan holat: xarid qismlab keladi. Ko'rsatilgan donalar yangi xaridga
  ko'chadi (u "Yo'lda" qoladi), xaridning chiqimlari dona bo'yicha bo'linadi (``upcore.purchasing.split_units``; keyin
  tahrirlanadi). Faqat sanalmagan xaridda; qo'lda ulushli chiqim bo'lsa — rad (``split_manual_shares``).

Omborchi sonlarni kiritadi, summalarni (qadoq, qaytarilgan summa) — faqat ``view_purchase_amounts`` bilan.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from upcore.money import Currency, Money, to_decimal
from upcore.purchasing import PurchaseError, split_units

from upapi.calc import lots as calc_lots
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import purchases as rp
from upapi.reports.common import today
from upapi.routes.purchases import (
    MAX_BULK,
    Manager,
    _changed,
    _detail,
    _plain,
    _purchase,
    _require_amounts,
    request_shipment_members,
)

router = APIRouter(tags=["purchases"])

Qty = Annotated[int, Field(ge=0, le=10_000_000)]
Pack = Annotated[Decimal | None, Field(ge=0, max_digits=18, decimal_places=2)]


class CountLineIn(BaseModel):
    line_id: UUID
    received_qty: Qty
    defect_qty: Qty = 0
    pack_unit_cost: Pack = None  # so'm/dona; berilmasa — tovardagi qiymat (bo'lsa)


class CountIn(BaseModel):
    """Sanash: berilmagan qatorlar o'zgarmaydi (hamma qator sanalganda holat "Omborimda")."""

    lines: Annotated[list[CountLineIn], Field(min_length=1, max_length=MAX_BULK)]
    counted_on: date | None = None  # bo'lmasa — bugun (Toshkent)
    remember_pack: bool = False  # qadoq qo'shimchasini tovarga ham yozish
    refund_amount: Annotated[Decimal | None, Field(ge=0, max_digits=18, decimal_places=4)] = None
    refund_currency: Currency | None = None


class SplitLineIn(BaseModel):
    line_id: UUID
    qty: Annotated[
        int, Field(ge=1, le=10_000_000)
    ]  # yangi xaridga ko'chadigan (keyin keladigan) dona


class SplitIn(BaseModel):
    lines: Annotated[list[SplitLineIn], Field(min_length=1, max_length=MAX_BULK)]


class SplitOut(BaseModel):
    purchase: rp.PurchaseDetailOut
    new_purchase_id: UUID


async def _lines(ctx: Any, purchase_id: UUID) -> dict[UUID, Any]:
    pl = m.purchase_lines
    return {
        r.id: r
        for r in await ctx.conn.execute(
            select(pl).where(pl.c.purchase_id == purchase_id).order_by(pl.c.created_at, pl.c.id)
        )
    }


@router.post("/orgs/{org_id}/purchases/{purchase_id}/count", response_model=rp.PurchaseDetailOut)
async def count_purchase(
    purchase_id: UUID,
    body: CountIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    """Sanash (ADR-061 §6): kelgan son, brak, qadoq qo'shimchasi va sotuvchi qaytargan summa — bitta tranzaksiyada."""
    if (
        body.refund_amount is not None
        or body.remember_pack
        or any(x.pack_unit_cost is not None for x in body.lines)
    ):
        _require_amounts(ctx)
    if body.refund_amount is not None and body.refund_currency is None:
        raise AppError("bad_refund", 422, detail="qaytarilgan summa valyutasi kerak")
    row = await _purchase(ctx, purchase_id)
    lines = await _lines(ctx, purchase_id)
    ids = [x.line_id for x in body.lines]
    if len(set(ids)) != len(ids) or set(ids) - set(lines):
        raise AppError("line_not_found", 404, detail="qator shu xaridda emas")
    pl, items, p = m.purchase_lines, m.items, m.purchases
    item_ids = {lines[x].item_id for x in ids if lines[x].item_id is not None}
    item_pack: dict[UUID, Decimal | None] = {}
    if item_ids:
        item_pack = {
            r.id: r.pack_unit_cost
            for r in await ctx.conn.execute(
                select(items.c.id, items.c.pack_unit_cost).where(items.c.id.in_(item_ids))
            )
        }
    touched: set[UUID | None] = set()
    for x in body.lines:
        if x.defect_qty > x.received_qty:
            raise AppError("bad_line", 422, detail="brak kelgan donadan ko'p")
        line = lines[x.line_id]
        values: dict[str, Any] = {"received_qty": x.received_qty, "defect_qty": x.defect_qty}
        pack = x.pack_unit_cost
        if pack is None and line.pack_unit_cost is None and line.item_id is not None:
            pack = item_pack.get(line.item_id)
        if pack is not None:
            values["pack_unit_cost"] = pack
            if body.remember_pack and line.item_id is not None:
                await ctx.conn.execute(
                    update(items)
                    .where(items.c.id == line.item_id)
                    .values(pack_unit_cost=pack, updated_at=func.now())
                )
        await ctx.conn.execute(
            update(pl).where(pl.c.id == x.line_id).values(**values, updated_at=func.now())
        )
        touched.add(line.item_id)
    after = await _lines(ctx, purchase_id)
    values = {}
    if all(r.received_qty is not None for r in after.values()) and row.received_on is None:
        values["received_on"] = body.counted_on or today()
    if body.refund_amount is not None:
        values |= {
            "refund_amount": body.refund_amount if body.refund_amount > 0 else None,
            "refund_currency": body.refund_currency.value
            if body.refund_currency and body.refund_amount > 0
            else None,
            "refund_on": (body.counted_on or today()) if body.refund_amount > 0 else None,
        }
    if values:
        await ctx.conn.execute(
            update(p).where(p.c.id == purchase_id).values(**values, updated_at=func.now())
        )
    await ctx.audit(
        "purchase.count", "purchase", purchase_id, after=_plain(body.model_dump(mode="json"))
    )
    await _changed(ctx, request, background, purchase_id, touched)
    await request_shipment_members(ctx, row.shipment_id, skip=purchase_id)
    return await _detail(ctx, purchase_id)


@router.post(
    "/orgs/{org_id}/purchases/{purchase_id}/split", response_model=SplitOut, status_code=201
)
async def split_purchase(
    purchase_id: UUID,
    body: SplitIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> SplitOut:
    """Xaridni ikkiga bo'lish (ADR-061 §6): ko'rsatilgan donalar yangi xaridga ("Yo'lda"), chiqimlar dona bo'yicha."""
    row = await _purchase(ctx, purchase_id)
    lines = await _lines(ctx, purchase_id)
    moves = {x.line_id: x.qty for x in body.lines}
    if len(moves) != len(body.lines) or set(moves) - set(lines):
        raise AppError("line_not_found", 404, detail="qator shu xaridda emas")
    if row.received_on is not None or any(r.received_qty is not None for r in lines.values()):
        raise AppError("split_counted", 409, detail="sanalgan xarid bo'linmaydi")
    for lid, qty in moves.items():
        if qty > lines[lid].ordered_qty:
            raise AppError("bad_line", 422, detail="ko'chadigan dona buyurtmadan ko'p")
    kept_total = sum(r.ordered_qty for r in lines.values()) - sum(moves.values())
    if kept_total <= 0:
        raise AppError("bad_split", 422, detail="eski xaridda kamida bitta dona qolishi kerak")
    cc, p, pl = m.cost_components, m.purchases, m.purchase_lines
    comps = list(await ctx.conn.execute(select(cc).where(cc.c.purchase_id == purchase_id)))
    for comp in comps:
        _, shares = calc_lots.targets_of(comp.targets)
        if shares:
            raise AppError(
                "split_manual_shares",
                409,
                detail="qo'lda ulushli chiqim bor — avval ulushlarni olib tashlang",
            )
    new_id: UUID = await ctx.conn.scalar(
        insert(p)
        .values(
            org_id=ctx.org_id,
            title=f"{row.title or ''} (2)".strip(),
            supplier_id=row.supplier_id,
            carrier_id=row.carrier_id,
            note=row.note,
            track_no=row.track_no,
            ordered_on=row.ordered_on,
            paid_on=row.paid_on,
        )
        .returning(p.c.id)
    )
    mapping: dict[UUID, UUID] = {}  # eski qator → yangi xariddagi qator
    copy = (
        "item_id",
        "sku_id",
        "temp_name",
        "url",
        "image_url",
        "variant",
        "unit_price",
        "currency",
        "unit_weight",
        "unit_volume",
        "pack_unit_cost",
    )
    for lid, qty in moves.items():
        line = lines[lid]
        kept = line.ordered_qty - qty
        if kept == 0:  # butun qator ko'chadi — qator o'zi o'tadi (id saqlanadi)
            await ctx.conn.execute(
                update(pl).where(pl.c.id == lid).values(purchase_id=new_id, updated_at=func.now())
            )
            mapping[lid] = lid
            continue
        sums: tuple[Decimal | None, Decimal | None] = (None, None)
        if line.line_sum is not None:
            a, b = split_units(Money(to_decimal(line.line_sum), Currency.UZS), kept, qty)
            sums = (a.amount, b.amount)
        await ctx.conn.execute(
            update(pl)
            .where(pl.c.id == lid)
            .values(ordered_qty=kept, line_sum=sums[0], updated_at=func.now())
        )
        mapping[lid] = await ctx.conn.scalar(
            insert(pl)
            .values(
                org_id=ctx.org_id,
                purchase_id=new_id,
                ordered_qty=qty,
                line_sum=sums[1],
                **{k: getattr(line, k) for k in copy},
            )
            .returning(pl.c.id)
        )
    units = {lid: r.ordered_qty for lid, r in lines.items()}
    for comp in comps:
        targets, _ = calc_lots.targets_of(comp.targets)
        scope = [UUID(x) for x in targets] if targets is not None else list(lines)
        moved = sum(moves.get(lid, 0) for lid in scope if lid in units)
        kept = sum(units[lid] for lid in scope if lid in units) - moved
        if moved == 0:
            continue
        try:
            first, second = split_units(
                Money(to_decimal(comp.amount), calc_lots.currency_of(comp.currency)), kept, moved
            )
        except PurchaseError as exc:
            raise AppError("bad_split", 422, detail=str(exc)) from exc
        charged: tuple[Any, Any] = (None, None)
        if comp.charged_amount is not None:
            c1, c2 = split_units(
                Money(
                    to_decimal(comp.charged_amount), calc_lots.currency_of(comp.charged_currency)
                ),
                kept,
                moved,
            )
            charged = (c1.amount, c2.amount)
        new_targets = None
        old_targets = comp.targets
        if targets is not None:
            new_targets = {"lines": [str(mapping[lid]) for lid in scope if lid in mapping]}
            remaining = [str(lid) for lid in scope if lid not in mapping or mapping[lid] != lid]
            old_targets = {**(comp.targets or {}), "lines": remaining}
        cols = {
            k: getattr(comp, k)
            for k in (
                "kind",
                "currency",
                "paid_on",
                "rate_mode",
                "rate",
                "charged_currency",
                "allocation",
                "weight_kg",
                "cost_type_id",
                "account_id",
            )
        }
        await ctx.conn.execute(
            insert(cc).values(
                org_id=ctx.org_id,
                purchase_id=new_id,
                amount=second.amount,
                charged_amount=charged[1],
                targets=new_targets,
                **cols,
            )
        )
        if kept == 0:
            await ctx.conn.execute(cc.delete().where(cc.c.id == comp.id))
        else:
            await ctx.conn.execute(
                update(cc)
                .where(cc.c.id == comp.id)
                .values(
                    amount=first.amount,
                    charged_amount=charged[0],
                    targets=old_targets,
                    updated_at=func.now(),
                )
            )
    await ctx.audit(
        "purchase.split",
        "purchase",
        purchase_id,
        after=_plain({"new_purchase_id": new_id, "lines": {str(k): v for k, v in moves.items()}}),
    )
    await _changed(ctx, request, background, purchase_id)
    await _changed(ctx, request, background, new_id)
    await request_shipment_members(ctx, row.shipment_id, skip=purchase_id)
    return SplitOut(purchase=await _detail(ctx, purchase_id), new_purchase_id=new_id)

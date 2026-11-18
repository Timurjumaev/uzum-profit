"""``/warehouse``: Omborim — SKU bo'yicha qoldiq va "Boshqa SKU'ga o'tkazish" (TM5, ADR-061 §7, §10; 02 M10).

Qoldiq sanalgan ("Omborimda") xaridlardan: har qatorning sog' donasi (kelgan − brak) − boshqa SKU'ga o'tkazilgani;
o'tkazilgan qator o'z SKU'sida. Keyin hisobdan chiqarish va tuzatishlar (``stock_moves``, SKU ko'rsatilgan bo'lsa — o'sha
SKU'dan, bo'lmasa tovarning SKU'siz qatoridan) va qabul qilinmagan postavkalarga ajratilgan dona (ADR-034) ayiriladi.
Qiymat — qatorlarning lot birlik tannarxida (F20/F21).

**Boshqa SKU'ga o'tkazish** (do'konlar orasida ham, bir do'kon ichida ham): manba qatordan N dona shu xariddagi yangi
qatorga (``source_line_id``) — dona birlik tannarxi bilan o'tadi (``upcore.purchasing.apply_transfers``); bekor qilish —
o'tkazilgan qatorni o'chirish. Ruxsat — ``manage_purchases``; summalar — ``view_purchase_amounts`` bilan.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select
from upcore.purchasing import INFO_FLAGS, SupplyState, supply_state

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import dispatch, integrity, linking
from upapi.reports import purchases as rp
from upapi.reports.common import sku_catalog, today
from upapi.reports.stock import inbound_by_sku
from upapi.routes.items import item_of_sku
from upapi.routes.purchases import _amounts, _changed, _plain

router = APIRouter(tags=["inventory"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]


class SourceOut(BaseModel):
    """O'tkazish manbasi — sanalgan xarid qatori (qolgan sog' dona)."""

    line_id: UUID
    purchase_id: UUID
    purchase_title: str | None
    counted_on: date | None
    qty: int
    unit_cost: Decimal | None  # summalar ruxsati bilan


class TransferOut(BaseModel):
    """Shu SKU'ga o'tkazilgan qator (bekor qilish uchun)."""

    line_id: UUID
    purchase_id: UUID
    qty: int
    from_sku_id: UUID | None
    from_name: str | None


class WarehouseRow(BaseModel):
    key: str  # ``sku:<id>`` yoki ``item:<id>`` (SKU'siz qatorlar)
    sku_id: UUID | None
    item_id: UUID | None
    shop_id: UUID | None
    shop: str | None
    title: str | None  # SKU nomi / tovar nomi
    product_title: str | None
    barcode: str | None
    qty: int
    reserved: int  # qabul qilinmagan postavkalarga ajratilgan (ADR-034)
    # TM9.3 (M10): Omborimda manfiy — butunlik buzilgan (jo'natilgan / hisobdan chiqarilgan dona sanalgandan ko'p);
    # son 0 ga qisilmaydi, xato sifatida ko'rsatiladi.
    broken: bool = False
    dispatched: int = 0  # Uzumga jo'natmalarda (Jo'natilmoqda + Uzumda, TM6) — qoldiqdan ayirilgan
    unit_cost: Decimal | None
    # TM9.7 (G11): tannarx taxminiy (F22 — kargo kiritilmagan, sanalmagan ...); noma'lum — ``unit_cost`` yo'q.
    estimated: bool = False
    value: Decimal | None
    sources: list[SourceOut]
    transfers_in: list[TransferOut]


class UncountedLine(BaseModel):
    sku_id: UUID | None
    item_id: UUID | None
    title: str | None
    shop: str | None
    qty: int  # buyurtma soni (taxminiy — hali sanalmagan)


class UncountedOut(BaseModel):
    """TM9.8 (ADR-069): "Omborimda · sanalmagan" — "Keldi" belgilangan, sanalmagan xarid (dona — buyurtma soni, ``~``)."""

    purchase_id: UUID
    title: str | None
    arrived_on: date
    days: int  # kelganidan beri kun
    qty: int
    lines: list[UncountedLine]


class WarehouseOut(BaseModel):
    items: list[WarehouseRow]
    amounts: bool
    total_qty: int
    total_value: Decimal | None
    # TM9.8: sanalmagan qism alohida — sanalgan qoldiq (``items``, M10) tenglamasi o'zgarmaydi.
    uncounted: list[UncountedOut] = []
    uncounted_qty: int = 0


class TransferIn(BaseModel):
    source_line_id: UUID
    to_sku_id: UUID
    qty: Annotated[int, Field(ge=1, le=10_000_000)]


def _good(line: Any) -> int:
    arrived: int = line.received_qty if line.received_qty is not None else line.ordered_qty
    return arrived - int(line.defect_qty)


async def _book(ctx: OrgContext) -> dict[str, Any]:
    """Omborimdagi qatorlar: ``lines`` (hammasi, sanalgan xaridlarda), ``moved_out`` (manba → o'tkazilgan dona),
    ``purchases``, lot narxlari."""
    p, pl, lots = m.purchases, m.purchase_lines, m.lots
    purchases = {
        r.id: r
        for r in await ctx.conn.execute(select(p))
        if supply_state(rp.stage_dates(r)) is SupplyState.IN_STOCK
    }
    lines = list(
        await ctx.conn.execute(
            select(pl)
            .where(pl.c.purchase_id.in_(list(purchases)))
            .order_by(pl.c.created_at, pl.c.id)
        )
    )
    moved_out: dict[UUID, int] = {}
    for r in lines:
        if r.source_line_id is not None:
            moved_out[r.source_line_id] = moved_out.get(r.source_line_id, 0) + _good(r)
    unit: dict[UUID, Decimal] = {}
    rough: set[UUID] = set()  # TM9.7 (G11): taxminiy lot (F22) — jo'natma qoralamasida belgi
    info = {f.value for f in INFO_FLAGS}
    for r in await ctx.conn.execute(
        select(lots.c.purchase_line_id, lots.c.unit_cost, lots.c.flags).where(
            lots.c.purchase_line_id.in_([r.id for r in lines])
        )
    ):
        unit[r.purchase_line_id] = r.unit_cost
        if set(r.flags or ()) - info:
            rough.add(r.purchase_line_id)
    # O'tkazilgan qator manba narxi bilan o'tadi (ADR-061 §7) — qayta hisob hali yetmagan bo'lsa ham noma'lum emas.
    for r in lines:
        if r.source_line_id is not None and r.id not in unit and r.source_line_id in unit:
            unit[r.id] = unit[r.source_line_id]
            if r.source_line_id in rough:
                rough.add(r.id)
    return {
        "purchases": purchases,
        "lines": lines,
        "moved_out": moved_out,
        "unit": unit,
        "rough": rough,
    }


@router.get("/orgs/{org_id}/warehouse", response_model=WarehouseOut)
async def warehouse(ctx: Viewer) -> WarehouseOut:
    """Omborim (ADR-061 §7): SKU bo'yicha qoldiq, qiymat va o'tkazish manbalari; qoldig'i bor qatorlar."""
    return await stock(ctx, _amounts(ctx))


async def stock(ctx: OrgContext, amounts: bool) -> WarehouseOut:
    """Omborim hisobi; ``amounts`` — summalar javobga chiqadimi (jo'natma narxi uchun ichkarida doim)."""
    await linking.sync(ctx.conn, datetime.now(UTC))
    book = await _book(ctx)
    it, sh, sm = m.items, m.shops, m.stock_moves
    rows: dict[str, dict[str, Any]] = {}

    def row(sku_id: UUID | None, item_id: UUID | None) -> dict[str, Any]:
        key = f"sku:{sku_id}" if sku_id is not None else f"item:{item_id}"
        return rows.setdefault(
            key,
            {
                "key": key,
                "sku_id": sku_id,
                "item_id": item_id,
                "qty": 0,
                "lots": [],
                "sources": [],
                "transfers_in": [],
                "rough": False,
            },
        )

    # TM6: Uzumga jo'natmalar (Jo'natilmoqda + Uzumda) eng eski partiyalardan FIFO ayiriladi (ADR-050 (3)).
    sent = await dispatch.attribute(ctx.conn, book["lines"], book["purchases"], book["moved_out"])
    for line in book["lines"]:
        att = sent.get(line.id)
        out_qty = 0 if att is None else att.sending + att.linked
        qty = _good(line) - book["moved_out"].get(line.id, 0) - out_qty
        r = row(line.sku_id, line.item_id)
        r["qty"] += qty
        r["dispatched"] = r.get("dispatched", 0) + out_qty
        cost = book["unit"].get(line.id)
        if qty > 0 and cost is not None:
            r["lots"].append((qty, cost))
            r["rough"] = r["rough"] or line.id in book["rough"]
        purchase = book["purchases"][line.purchase_id]
        if qty > 0:
            r["sources"].append(
                SourceOut(
                    line_id=line.id,
                    purchase_id=line.purchase_id,
                    purchase_title=purchase.title,
                    counted_on=purchase.received_on,
                    qty=qty,
                    unit_cost=cost if amounts else None,
                )
            )
        if line.source_line_id is not None:
            r["transfers_in"].append(line)
    # Hisobdan chiqarish / tuzatish (SKU ko'rsatilgan — o'sha SKU'dan, bo'lmasa tovarning SKU'siz qatoridan).
    for mv in await ctx.conn.execute(
        select(sm.c.item_id, sm.c.sku_id, sm.c.kind, func.sum(sm.c.qty).label("qty"))
        .where(sm.c.kind.in_(("adjust", "writeoff")))
        .group_by(sm.c.item_id, sm.c.sku_id, sm.c.kind)
    ):
        key = f"sku:{mv.sku_id}" if mv.sku_id is not None else f"item:{mv.item_id}"
        if key not in rows:
            continue
        delta = int(mv.qty) if mv.kind == "adjust" else -abs(int(mv.qty))
        rows[key]["qty"] += delta
    reserved = await inbound_by_sku(ctx.conn, await dispatch.linked_invoices(ctx.conn))
    held = await dispatch.held(ctx.conn)
    sku_ids = [r["sku_id"] for r in rows.values() if r["sku_id"] is not None]
    item_ids = [r["item_id"] for r in rows.values() if r["item_id"] is not None]
    line_sku = {x.id: x.sku_id for x in book["lines"]}
    skus = await sku_catalog(
        ctx.conn, ids=list({*sku_ids, *(s for s in line_sku.values() if s is not None)})
    )
    shops = {r.id: r.name for r in await ctx.conn.execute(select(sh.c.id, sh.c.name))}
    names = {
        r.id: r.name
        for r in await ctx.conn.execute(select(it.c.id, it.c.name).where(it.c.id.in_(item_ids)))
    }
    out: list[WarehouseRow] = []
    total_qty, total_value, known = 0, Decimal(0), True
    for r in rows.values():
        sku = skus.get(r["sku_id"]) if r["sku_id"] is not None else None
        res = reserved.get(r["sku_id"], 0) if r["sku_id"] is not None else 0
        # Partiyalarga bog'lanmagan (sanalgandan ko'p) jo'natilgan dona ham ayiriladi — manfiy bo'lsa xato.
        raw = r["qty"] - (held.get(r["sku_id"], 0) - r.get("dispatched", 0) if r["sku_id"] else 0)
        broken = raw < 0
        qty = raw if broken else max(0, raw - res)
        if qty == 0 and not r["transfers_in"]:
            continue
        lot_qty = sum(q for q, _ in r["lots"])
        unit = sum((q * c for q, c in r["lots"]), Decimal(0)) / lot_qty if lot_qty else None
        value = None if unit is None or broken else (unit * qty).quantize(Decimal("0.01"))
        total_qty += max(qty, 0)
        if value is None:
            known = known and qty <= 0
        else:
            total_value += value
        out.append(
            WarehouseRow(
                key=r["key"],
                sku_id=r["sku_id"],
                item_id=r["item_id"],
                shop_id=sku.shop_id if sku else None,
                shop=shops.get(sku.shop_id) if sku else None,
                title=(sku.title if sku else None) or names.get(r["item_id"]),
                product_title=(sku.product_title if sku else None) or names.get(r["item_id"]),
                barcode=sku.barcode if sku else None,
                qty=qty,
                reserved=res,
                broken=broken,
                dispatched=r.get("dispatched", 0),
                unit_cost=unit.quantize(Decimal("0.01")) if amounts and unit is not None else None,
                estimated=r["rough"],
                value=value if amounts else None,
                sources=r["sources"],
                transfers_in=[
                    TransferOut(
                        line_id=x.id,
                        purchase_id=x.purchase_id,
                        qty=_good(x),
                        from_sku_id=line_sku.get(x.source_line_id),
                        from_name=(
                            skus[line_sku[x.source_line_id]].title
                            if line_sku.get(x.source_line_id) in skus
                            else None
                        ),
                    )
                    for x in r["transfers_in"]
                ],
            )
        )
    out.sort(key=lambda x: (x.shop or "", x.title or "", x.key))
    pending = await uncounted(ctx)
    return WarehouseOut(
        items=out,
        amounts=amounts,
        total_qty=total_qty,
        total_value=(total_value.quantize(Decimal("0.01")) if known else None) if amounts else None,
        uncounted=pending,
        uncounted_qty=sum(x.qty for x in pending),
    )


async def uncounted(ctx: OrgContext) -> list[UncountedOut]:
    """ "Keldi" belgilangan, hali sanalmagan xaridlar (eskisi birinchi) — dona buyurtma soni bilan."""
    p, pl, it, sh = m.purchases, m.purchase_lines, m.items, m.shops
    rows = [
        r
        for r in await ctx.conn.execute(
            select(p)
            .where(
                p.c.arrival_marked.is_(True),
                p.c.arrived_on.is_not(None),
                p.c.received_on.is_(None),
                p.c.sent_to_uzum_on.is_(None),
                p.c.closed_on.is_(None),
            )
            .order_by(p.c.arrived_on, p.c.created_at, p.c.id)
        )
    ]
    if not rows:
        return []
    lines = list(
        await ctx.conn.execute(
            select(pl)
            .where(pl.c.purchase_id.in_([r.id for r in rows]), pl.c.source_line_id.is_(None))
            .order_by(pl.c.created_at, pl.c.id)
        )
    )
    skus = await sku_catalog(ctx.conn, ids=list({x.sku_id for x in lines if x.sku_id}))
    names = {
        r.id: r.name
        for r in await ctx.conn.execute(
            select(it.c.id, it.c.name).where(it.c.id.in_({x.item_id for x in lines if x.item_id}))
        )
    }
    shops = {r.id: r.name for r in await ctx.conn.execute(select(sh.c.id, sh.c.name))}
    day = today()
    out = []
    for r in rows:
        mine = [x for x in lines if x.purchase_id == r.id]
        items = []
        for x in mine:
            sku = skus.get(x.sku_id) if x.sku_id else None
            items.append(
                UncountedLine(
                    sku_id=x.sku_id,
                    item_id=x.item_id,
                    title=(sku.title if sku else None) or names.get(x.item_id) or x.temp_name,
                    shop=shops.get(sku.shop_id) if sku else None,
                    qty=x.ordered_qty,
                )
            )
        out.append(
            UncountedOut(
                purchase_id=r.id,
                title=r.title,
                arrived_on=r.arrived_on,
                days=max((day - r.arrived_on).days, 0),
                qty=sum(x.qty for x in items),
                lines=items,
            )
        )
    return out


@router.post("/orgs/{org_id}/warehouse/transfer", response_model=WarehouseOut, status_code=201)
async def transfer(
    body: TransferIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> WarehouseOut:
    """Boshqa SKU'ga o'tkazish (ADR-061 §7): manba qatordan N dona yangi qatorga — birlik tannarxi bilan."""
    book = await _book(ctx)
    source = next((x for x in book["lines"] if x.id == body.source_line_id), None)
    if source is None:
        raise AppError("line_not_found", 404, detail="qator omborimda emas (xarid sanalmagan)")
    if source.sku_id == body.to_sku_id:
        raise AppError("bad_transfer", 422, detail="o'sha SKU'ning o'ziga o'tkazilmaydi")
    root = source if source.source_line_id is None else None
    if root is None:
        raise AppError(
            "bad_transfer", 422, detail="o'tkazilgan qatordan qayta o'tkazilmaydi — manbadan"
        )
    # TM9.3: jo'natilgan va hisobdan chiqarilgan dona o'tkazilmaydi (qatorning omborimdagi donasi).
    use = (await integrity.ledger(ctx.conn)).lines.get(source.id)
    available = _good(source) - (book["moved_out"].get(source.id, 0) if use is None else use.used)
    if body.qty > available:
        raise AppError("bad_transfer", 422, detail=f"qatorda {available} dona bor")
    item_id = await item_of_sku(ctx, body.to_sku_id)
    pl = m.purchase_lines
    line_id = await ctx.conn.scalar(
        insert(pl)
        .values(
            org_id=ctx.org_id,
            purchase_id=source.purchase_id,
            item_id=item_id,
            sku_id=body.to_sku_id,
            ordered_qty=body.qty,
            received_qty=body.qty,
            source_line_id=source.id,
            variant=source.variant,
        )
        .returning(pl.c.id)
    )
    await ctx.audit("warehouse.transfer", "purchase_line", line_id, after=_plain(body.model_dump()))
    await _changed(ctx, request, background, source.purchase_id, {source.item_id, item_id})
    return await warehouse(ctx)


@router.delete("/orgs/{org_id}/warehouse/transfers/{line_id}", status_code=204)
async def cancel_transfer(
    line_id: UUID, ctx: Manager, request: Request, background: BackgroundTasks
) -> Response:
    """O'tkazmani bekor qilish: donalar manba SKU'ga qaytadi (tannarx bilan)."""
    pl = m.purchase_lines
    row = (
        await ctx.conn.execute(
            select(pl).where(pl.c.id == line_id, pl.c.source_line_id.is_not(None))
        )
    ).first()
    if row is None:
        raise AppError("line_not_found", 404)
    # TM9.3: o'tkazilgan donalar jo'natilgan yoki hisobdan chiqarilgan bo'lsa bekor qilinmaydi.
    integrity.check_lines(await integrity.ledger(ctx.conn), {line_id: None})
    source_item = await ctx.conn.scalar(select(pl.c.item_id).where(pl.c.id == row.source_line_id))
    await ctx.conn.execute(delete(pl).where(pl.c.id == line_id))
    await ctx.audit(
        "warehouse.transfer_cancel",
        "purchase_line",
        line_id,
        before=_plain({"qty": row.received_qty, "sku_id": row.sku_id}),
    )
    await calc.request(ctx.conn, ctx.org_id, calc.Scope.ITEM, row.item_id)
    await _changed(ctx, request, background, row.purchase_id, {source_item, row.item_id})
    return Response(status_code=204)

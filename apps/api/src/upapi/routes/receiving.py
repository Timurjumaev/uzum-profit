"""``/receiving``: Uzum qabulidagi farq va kamomad ro'yxati (TM7, ADR-061 §8; 02 M10, F33, F52).

- **Kam qabul qilindi** — sotuvchi tanlaydi: **"Uzum yo'qotdi"** (``lost``) → kamomad ro'yxati (holat: Ochiq → Topildi /
  Kompensatsiya qilindi (summa) / Zarar deb yopildi; zarar foyda hisobida alohida qator — F52) yoki **"Men sanashda
  adashganman"** (``miscount``) → xaridning kelgan soni tuzatiladi (eng yangi bog'langan partiyadan), jo'natma soni
  qabul qilinganga tenglashadi, tannarx qayta hisoblanadi.
- **Ko'p qabul qilindi** — shu SKU'da ochiq kamomad bo'lsa ``found`` (kamomad "Topildi" bo'lib yopiladi); bo'lmasa
  ``recount`` — xarid soni oshiriladi (bir bosish).

O'qish — ``view_purchases``; qaror — ``manage_purchases``; summalar (tannarx, kompensatsiya, jarima) —
``view_purchase_amounts`` bilan.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import dispatch
from upapi.reports import receiving as rr
from upapi.reports.common import sku_catalog, today
from upapi.routes.purchases import _amounts, _kick, _plain, _require_amounts

router = APIRouter(tags=["inventory"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]


class FineOut(BaseModel):
    day: date
    amount: Decimal


class DiffOut(BaseModel):
    dispatch_id: UUID
    invoice_id: UUID
    invoice_number: int | None
    shop: str | None
    accepted_on: date
    sku_id: UUID
    title: str | None
    barcode: str | None
    shipped: int
    accepted: int
    diff: int  # manfiy — kam qabul qilindi
    unit_cost: Decimal | None
    value: Decimal | None  # farqning tannarxdagi summasi (|diff| × unit_cost)
    resolution: str | None  # lost / miscount / found / recount
    shortage_id: UUID | None
    open_shortages: (
        int  # shu SKU'dagi ochiq kamomad donasi (ortiqcha qabul uchun "Topildi" taklifi)
    )
    fines: list[FineOut]  # bog'liq C000007 jarimalari (summalar ruxsati bilan)
    fines_total: Decimal | None


class ShortageOut(BaseModel):
    id: UUID
    dispatch_id: UUID
    sku_id: UUID
    title: str | None
    shop: str | None
    qty: int  # kamomad donasi (musbat)
    status: str  # open / found / compensated / written_off
    unit_cost: Decimal | None
    amount: Decimal | None  # tannarxdagi summa
    compensation: Decimal | None
    loss: Decimal | None  # F52 (yopilganda)
    closed_on: date | None
    note: str | None
    created_on: date


class ReceivingOut(BaseModel):
    diffs: list[DiffOut]
    shortages: list[ShortageOut]
    amounts: bool


class ResolveIn(BaseModel):
    dispatch_id: UUID
    sku_id: UUID
    action: Literal["lost", "miscount", "found", "recount"]
    note: Annotated[str | None, Field(max_length=500)] = None
    # Qaysi partiyaning soni tuzatiladi (miscount / recount); bo'lmasa — jo'natmaga bog'langan eng yangi partiyadan.
    line_id: UUID | None = None


class ShortagePatch(BaseModel):
    status: Literal["open", "found", "compensated", "written_off"]
    compensation: Annotated[Decimal | None, Field(ge=0, max_digits=18, decimal_places=2)] = None
    note: Annotated[str | None, Field(max_length=500)] = None


async def _view(ctx: OrgContext) -> ReceivingOut:
    from upcore.money import Currency, Money
    from upcore.purchasing import receiving_loss

    amounts = _amounts(ctx)
    found = await rr.diffs(ctx.conn)
    rd = m.receiving_diffs
    lost = list(
        await ctx.conn.execute(
            select(rd).where(rd.c.resolution == "lost").order_by(rd.c.created_at.desc(), rd.c.id)
        )
    )
    catalog = await sku_catalog(
        ctx.conn, ids=list({x.sku_id for x in found} | {x.sku_id for x in lost})
    )
    shops = {r.id: r.name for r in await ctx.conn.execute(select(m.shops.c.id, m.shops.c.name))}
    open_by_sku: dict[UUID, int] = {}
    for x in lost:
        if x.status == "open":
            open_by_sku[x.sku_id] = open_by_sku.get(x.sku_id, 0) + abs(x.qty)

    def money(v: Decimal | None) -> Decimal | None:
        return v if amounts else None

    def loss(x: Any) -> Decimal | None:
        if x.status not in ("compensated", "written_off") or x.unit_cost is None:
            return None
        comp = Money(x.compensation, Currency.UZS) if x.compensation is not None else None
        return receiving_loss(abs(x.qty), Money(x.unit_cost, Currency.UZS), comp).amount

    def shop_of(sku_id: UUID) -> str | None:
        info = catalog.get(sku_id)
        return shops.get(info.shop_id) if info else None

    return ReceivingOut(
        diffs=[
            DiffOut(
                dispatch_id=x.dispatch_id,
                invoice_id=x.invoice_id,
                invoice_number=x.invoice_number,
                shop=shops.get(x.shop_id),
                accepted_on=x.accepted_on,
                sku_id=x.sku_id,
                title=catalog[x.sku_id].title if x.sku_id in catalog else None,
                barcode=catalog[x.sku_id].barcode if x.sku_id in catalog else None,
                shipped=x.shipped,
                accepted=x.accepted,
                diff=x.diff if x.resolution is None else x.resolution.qty,
                unit_cost=money(x.unit_cost),
                value=money(
                    None
                    if x.unit_cost is None
                    else x.unit_cost * abs(x.diff if x.resolution is None else x.resolution.qty)
                ),
                resolution=None if x.resolution is None else x.resolution.resolution,
                shortage_id=x.resolution.id
                if x.resolution is not None and x.resolution.resolution == "lost"
                else None,
                open_shortages=open_by_sku.get(x.sku_id, 0),
                fines=[FineOut(day=d, amount=a) for d, a in x.fines] if amounts else [],
                fines_total=sum((a for _, a in x.fines), Decimal("0.00"))
                if amounts and x.fines
                else None,
            )
            for x in found
        ],
        shortages=[
            ShortageOut(
                id=x.id,
                dispatch_id=x.dispatch_id,
                sku_id=x.sku_id,
                title=catalog[x.sku_id].title if x.sku_id in catalog else None,
                shop=shop_of(x.sku_id),
                qty=abs(x.qty),
                status=x.status,
                unit_cost=money(x.unit_cost),
                amount=money(None if x.unit_cost is None else x.unit_cost * abs(x.qty)),
                compensation=money(x.compensation),
                loss=money(loss(x)),
                closed_on=x.closed_on,
                note=x.note,
                created_on=x.created_at.date(),
            )
            for x in lost
        ],
        amounts=amounts,
    )


@router.get("/orgs/{org_id}/receiving", response_model=ReceivingOut)
async def receiving(ctx: Viewer) -> ReceivingOut:
    """Qabul farqlari (qarorsizlari birinchi) va kamomad ro'yxati."""
    return await _view(ctx)


async def _adjust_lines(
    ctx: OrgContext, sku_id: UUID, delta: int, line_id: UUID | None = None
) -> set[UUID | None]:
    """Xarid sonini tuzatish (ADR-061 §8): shu SKU'ning jo'natmaga bog'langan eng yangi partiyalaridan (``delta`` < 0 —
    kamaytirish, sog' donadan pastga emas; > 0 — eng yangi partiyaga qo'shish). Tegilgan xaridlar qaytadi."""
    states = await dispatch.line_states(ctx.conn)
    pl, p = m.purchase_lines, m.purchases
    # Sotuvchi partiyani tanlagan bo'lsa — o'sha (sanalgan, shu SKU); bo'lmasa jo'natmaga bog'langan partiyalar.
    scope = pl.c.id == line_id if line_id is not None else pl.c.id.in_(list(states))
    lines = list(
        await ctx.conn.execute(
            select(pl, p.c.received_on.label("counted_on"))
            .join(p, p.c.id == pl.c.purchase_id)
            .where(
                pl.c.sku_id == sku_id,
                pl.c.source_line_id.is_(None),
                p.c.received_on.is_not(None),
                scope,
            )
        )
    )
    lines.sort(key=lambda x: (x.counted_on or date.min, x.created_at), reverse=True)
    if not lines:
        raise AppError("bad_receiving", 409, detail="bog'langan partiya topilmadi")
    touched: set[UUID | None] = set()
    left = abs(delta)
    for x in lines:
        if left == 0:
            break
        received = x.received_qty if x.received_qty is not None else x.ordered_qty
        if delta > 0:
            take = left
            new = received + take
        else:
            att = states.get(x.id)
            cap = received - x.defect_qty
            if line_id is None and att is not None:
                cap = min(cap, att.linked + att.sending)
            take = min(left, cap)
            if take <= 0:
                continue
            new = received - take
        await ctx.conn.execute(
            update(pl).where(pl.c.id == x.id).values(received_qty=new, updated_at=func.now())
        )
        await calc.request(ctx.conn, ctx.org_id, calc.Scope.PURCHASE, x.purchase_id)
        touched.add(x.item_id)
        left -= take
    if left:
        raise AppError("bad_receiving", 409, detail="tuzatish uchun yetarli dona yo'q")
    return touched


async def _set_item_qty(ctx: OrgContext, dispatch_id: UUID, sku_id: UUID, delta: int) -> None:
    di = m.fbo_dispatch_items
    row = (
        await ctx.conn.execute(
            select(di).where(di.c.dispatch_id == dispatch_id, di.c.sku_id == sku_id).limit(1)
        )
    ).first()
    if row is None:
        raise AppError("bad_receiving", 409, detail="jo'natmada bu SKU yo'q")
    if row.qty + delta <= 0:
        await ctx.conn.execute(di.delete().where(di.c.id == row.id))
    else:
        await ctx.conn.execute(
            update(di).where(di.c.id == row.id).values(qty=row.qty + delta, updated_at=func.now())
        )


@router.post("/orgs/{org_id}/receiving/resolve", response_model=ReceivingOut)
async def resolve(
    body: ResolveIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> ReceivingOut:
    """Farq bo'yicha qaror (bir marta; keyin kamomad holati alohida o'zgaradi)."""
    found = next(
        (
            x
            for x in await rr.diffs(ctx.conn)
            if x.dispatch_id == body.dispatch_id and x.sku_id == body.sku_id
        ),
        None,
    )
    if found is None:
        raise AppError("not_found", 404, detail="farq topilmadi")
    if found.resolution is not None:
        raise AppError("bad_receiving", 409, detail="qaror allaqachon yozilgan")
    diff = found.diff
    if body.action in ("lost", "miscount") and diff >= 0:
        raise AppError("bad_receiving", 422, detail="bu amal faqat kam qabul qilinganda")
    if body.action in ("found", "recount") and diff <= 0:
        raise AppError("bad_receiving", 422, detail="bu amal faqat ko'p qabul qilinganda")
    rd = m.receiving_diffs
    status = "closed"
    touched: set[UUID | None] = set()
    if body.action == "lost":
        status = "open"
    elif body.action == "miscount" or body.action == "recount":
        touched = await _adjust_lines(ctx, body.sku_id, diff, body.line_id)
        await _set_item_qty(ctx, body.dispatch_id, body.sku_id, diff)
    else:  # found — ochiq kamomadlar eskisidan yopiladi
        left = diff
        for x in await ctx.conn.execute(
            select(rd)
            .where(rd.c.sku_id == body.sku_id, rd.c.resolution == "lost", rd.c.status == "open")
            .order_by(rd.c.created_at, rd.c.id)
        ):
            if left == 0:
                break
            take = min(left, abs(x.qty))
            values: dict[str, Any] = (
                {"status": "found", "closed_on": today()}
                if take == abs(x.qty)
                else {"qty": x.qty + take}
            )
            await ctx.conn.execute(
                update(rd).where(rd.c.id == x.id).values(**values, updated_at=func.now())
            )
            left -= take
        if left == diff:
            raise AppError("bad_receiving", 409, detail="shu SKU'da ochiq kamomad yo'q")
    await ctx.conn.execute(
        insert(rd).values(
            org_id=ctx.org_id,
            dispatch_id=body.dispatch_id,
            sku_id=body.sku_id,
            qty=diff,
            resolution=body.action,
            status=status,
            unit_cost=found.unit_cost,
            closed_on=None if status == "open" else today(),
            note=body.note,
        )
    )
    await ctx.audit(
        "receiving.resolve", "dispatch", body.dispatch_id, after=_plain(body.model_dump())
    )
    for item in touched:
        if item is not None:
            await calc.request(ctx.conn, ctx.org_id, calc.Scope.ITEM, item)
    if touched:
        background.add_task(_kick, request, ctx.org_id)
    return await _view(ctx)


@router.patch("/orgs/{org_id}/receiving/shortages/{shortage_id}", response_model=ReceivingOut)
async def update_shortage(shortage_id: UUID, body: ShortagePatch, ctx: Manager) -> ReceivingOut:
    """Kamomad holati: Topildi / Kompensatsiya qilindi (summa) / Zarar deb yopildi — yopilgan kun bugun; Ochiq — qayta
    ochish. Zarar (F52) foyda hisobida yopilgan kunga."""
    rd = m.receiving_diffs
    row = (
        await ctx.conn.execute(select(rd).where(rd.c.id == shortage_id, rd.c.resolution == "lost"))
    ).first()
    if row is None:
        raise AppError("not_found", 404, detail="kamomad topilmadi")
    if body.compensation is not None or body.status == "compensated":
        _require_amounts(ctx)
    if body.status == "compensated" and body.compensation is None:
        raise AppError("bad_receiving", 422, detail="kompensatsiya summasi kerak")
    values: dict[str, Any] = {
        "status": body.status,
        "compensation": body.compensation if body.status == "compensated" else None,
        "closed_on": None if body.status == "open" else today(),
    }
    if body.note is not None:
        values["note"] = body.note
    await ctx.conn.execute(
        update(rd).where(rd.c.id == shortage_id).values(**values, updated_at=func.now())
    )
    await ctx.audit(
        "receiving.shortage",
        "receiving_diff",
        shortage_id,
        before=_plain({"status": row.status}),
        after=_plain(values),
    )
    return await _view(ctx)

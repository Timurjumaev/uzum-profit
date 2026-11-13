"""``/cargo-pool``: kargo puli jadvali (TM3, ADR-061 §3) va xarajat turlari lug'ati (ADR-061 §4).

Hamma "Yo'lda" xaridlar, kargo puli hali kiritilmaganlari, bitta jadvalda. Xarid kiritilayotganda "trekli" yoki "kodli"
tanlanmaydi — kargo puli kelganda shu yerda:

- **Trekli** (``POST /cargo-pool/tracked``): bir nechta xarid qatoriga o'z summasi (kg va trek ixtiyoriy, faqat
  ma'lumot) — har xaridga "Kargo" xarajati (xaridning o'z kargo puli, xarid ichida dona bo'yicha). Bitta "Saqlash".
- **Kodli quti** (``POST /cargo-pool/box``): bir nechta xarid belgilanadi, bitta summa → **Kargo** (ADR-046
  ``shipments``) yaratiladi, xaridlar unga biriktiriladi. Ulushlar **dona bo'yicha** (``POST /cargo-pool/shares`` —
  inputlar uchun tayyor ulushlar, F20 ``box_shares``); sotuvchi o'zgartirgan ulushlar ``targets.purchase_shares`` da
  saqlanadi, qolgani hisobda kelgan dona bo'yicha (sanashda dona o'zgarsa o'zi qayta bo'linadi).

Xaridda yo o'z kargo puli, yo quti — ikkalasi birga emas (ikki marta hisoblanmasin): trekli summa kargodagi xaridga,
quti esa o'z kargo puli bor xaridga yozilmaydi (``cargo_twice``). Valyuta standarti — USD; kurs: Markaziy bank yoki
qo'lda. Tariflar (kg, m³) kiritilmaydi — faqat yakuniy summa.

Yozish — ``manage_purchases`` + ``view_purchase_amounts``; o'qish — ``view_purchases``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, insert, select, update
from upcore.money import Currency, Money, to_decimal
from upcore.purchasing import (
    AllocationBase,
    ComponentKind,
    PurchaseError,
    SupplyState,
    box_shares,
    supply_state,
)

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc import lots as calc_lots
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import purchases as rp
from upapi.routes.purchases import (
    _amounts,
    _kick,
    _plain,
    _require_amounts,
    check_component,
    request_shipment_members,
)

router = APIRouter(tags=["purchases"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]

Amount = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
Share = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
Rate = Annotated[Decimal | None, Field(gt=0, max_digits=18, decimal_places=6)]
RateMode = Annotated[str, Field(pattern="^(cbu|manual)$")]
Weight = Annotated[Decimal | None, Field(gt=0, max_digits=12, decimal_places=3)]
MAX_ROWS = 100


class PoolRow(BaseModel):
    """Kargo puli kutilayotgan xarid. ``units`` — sanalgan bo'lsa kelgan, bo'lmasa buyurtma qilingan dona (ulushlar
    shu bo'yicha)."""

    purchase_id: UUID
    title: str | None
    track_no: str | None
    supplier_name: str | None
    ordered_on: date | None
    state: SupplyState
    items: list[str]
    units: int


class PoolOut(BaseModel):
    items: list[PoolRow]
    amounts: bool


class Money4(BaseModel):
    """Kurs bilan summa: ``rate_mode`` ``cbu`` (to'lov kunidagi Markaziy bank kursi) yoki ``manual`` (``rate``)."""

    currency: Currency = Currency.USD
    rate_mode: RateMode = "cbu"
    rate: Rate = None
    paid_on: date | None = None  # bo'lmasa — xarid / kargo sanasi (hisob qoidasi, ``calc.lots``)

    @model_validator(mode="after")
    def _rate(self) -> Money4:
        check_component({"currency": self.currency, "rate_mode": self.rate_mode, "rate": self.rate})
        return self


class TrackedRow(BaseModel):
    purchase_id: UUID
    amount: Amount
    weight_kg: Weight = None
    track_no: Annotated[str | None, Field(max_length=100)] = (
        None  # bo'sh bo'lmasa — xarid treki yangilanadi
    )


class TrackedIn(Money4):
    rows: Annotated[list[TrackedRow], Field(min_length=1, max_length=MAX_ROWS)]


class TrackedOut(BaseModel):
    created: int


class SharesIn(BaseModel):
    """Kodli quti ulushlarini hisoblash: ``fixed`` — sotuvchi o'zgartirgan ulushlar (komponent valyutasida)."""

    amount: Amount
    currency: Currency = Currency.USD
    purchase_ids: Annotated[list[UUID], Field(min_length=1, max_length=MAX_ROWS)]
    fixed: dict[UUID, Share] = Field(default_factory=dict)


class SharesOut(BaseModel):
    shares: dict[UUID, Decimal]
    units: dict[UUID, int]


class BoxIn(Money4):
    """Kodli quti: bitta summa bir nechta xaridga. ``title`` — shaxsiy kod yoki quti nomi."""

    title: Annotated[str, Field(min_length=1, max_length=300)]
    carrier_id: UUID | None = None
    amount: Amount
    weight_kg: Weight = None
    purchase_ids: Annotated[list[UUID], Field(min_length=1, max_length=MAX_ROWS)]
    fixed: dict[UUID, Share] = Field(default_factory=dict)


class BoxOut(BaseModel):
    shipment_id: UUID


class BoxSharesIn(BaseModel):
    """Qutining qo'lda ulushlari (to'liq almashtiriladi; bo'sh — hammasi dona bo'yicha)."""

    fixed: dict[UUID, Share] = Field(default_factory=dict)


class CostTypeIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]


class CostTypeOut(BaseModel):
    id: UUID
    name: str


# --- Yordamchilar ---------------------------------------------------------------------------------


def _units(lines: list[Any]) -> int:
    return sum(x.ordered_qty if x.received_qty is None else x.received_qty for x in lines)


async def _members(ctx: OrgContext, ids: list[UUID]) -> dict[UUID, Any]:
    """Tanlangan xaridlar (hammasi shu tashkilotda bo'lishi shart)."""
    if len(set(ids)) != len(ids):
        raise AppError("bad_request", 422, detail="xarid takrorlangan")
    p = m.purchases
    rows = {r.id: r for r in await ctx.conn.execute(select(p).where(p.c.id.in_(ids)))}
    if len(rows) != len(ids):
        raise AppError("purchase_not_found", 404)
    return rows


async def _lines_of(ctx: OrgContext, ids: list[UUID]) -> dict[UUID, list[Any]]:
    pl = m.purchase_lines
    out: dict[UUID, list[Any]] = {pid: [] for pid in ids}
    for row in await ctx.conn.execute(select(pl).where(pl.c.purchase_id.in_(ids))):
        out[row.purchase_id].append(row)
    return out


async def _own_cargo(ctx: OrgContext, ids: list[UUID] | None = None) -> set[UUID]:
    """O'z kargo puli ("Kargo" xarajati) bor xaridlar."""
    cc = m.cost_components
    query = select(cc.c.purchase_id).where(
        cc.c.purchase_id.is_not(None), cc.c.kind == ComponentKind.CARGO.value
    )
    if ids is not None:
        query = query.where(cc.c.purchase_id.in_(ids))
    return {r.purchase_id for r in await ctx.conn.execute(query)}


def _shares(
    amount: Decimal, currency: Currency, units: dict[UUID, int], fixed: dict[UUID, Decimal]
) -> dict[UUID, Decimal]:
    try:
        out = box_shares(
            Money(to_decimal(amount), currency),
            {str(k): v for k, v in units.items()},
            {str(k): v for k, v in fixed.items()},
        )
    except PurchaseError as exc:
        raise AppError("bad_shares", 422, detail=str(exc)) from exc
    return {UUID(k): v.amount for k, v in out.items()}


async def _recalc(
    ctx: OrgContext, request: Request, background: BackgroundTasks, ids: list[UUID]
) -> None:
    for pid in ids:
        await calc.request(ctx.conn, ctx.org_id, calc.Scope.PURCHASE, pid)
    background.add_task(_kick, request, ctx.org_id)


def _component(money: Money4, amount: Decimal, weight: Decimal | None) -> dict[str, Any]:
    return {
        "kind": ComponentKind.CARGO.value,
        "amount": amount,
        "currency": money.currency.value,
        "paid_on": money.paid_on,
        "rate_mode": money.rate_mode,
        "rate": money.rate if money.rate_mode == "manual" else None,
        "allocation": AllocationBase.UNITS.value,
        "weight_kg": weight,
    }


# --- Kargo puli jadvali ---------------------------------------------------------------------------


@router.get("/orgs/{org_id}/cargo-pool", response_model=PoolOut)
async def cargo_pool(
    ctx: Viewer,
    counted: Annotated[
        bool, Query(description="Sanalgan (Omborimda), kargo puli kiritilmagan xaridlar ham")
    ] = False,
) -> PoolOut:
    """Kargo puli kutilayotgan xaridlar (eskisi birinchi): "Yo'lda" (``counted`` — "Omborimda" ham), "Tovar qo'limda"
    emas, kargo (quti) ga biriktirilmagan va o'z "Kargo" xarajati yo'q."""
    p, s = m.purchases, m.suppliers
    rows = list(
        await ctx.conn.execute(
            select(p)
            .where(p.c.shipment_id.is_(None), p.c.on_hand.is_(False))
            .order_by(p.c.ordered_on.nulls_last(), p.c.created_at, p.c.id)
        )
    )
    wanted = {SupplyState.IN_TRANSIT} | ({SupplyState.IN_STOCK} if counted else set())
    rows = [r for r in rows if supply_state(rp.stage_dates(r)) in wanted]
    own = await _own_cargo(ctx, [r.id for r in rows])
    rows = [r for r in rows if r.id not in own]
    ids = [r.id for r in rows]
    lines = await _lines_of(ctx, ids)
    suppliers = {r.id: r.name for r in await ctx.conn.execute(select(s.c.id, s.c.name))}
    item_ids = {x.item_id for rows_ in lines.values() for x in rows_ if x.item_id}
    names: dict[UUID, str] = {}
    if item_ids:
        names = {
            r.id: r.name
            for r in await ctx.conn.execute(
                select(m.items.c.id, m.items.c.name).where(m.items.c.id.in_(item_ids))
            )
        }
    out = []
    for r in rows:
        titles: list[str] = []
        for x in lines[r.id]:
            name = names.get(x.item_id) if x.item_id else x.temp_name
            if name and name not in titles:
                titles.append(name)
        out.append(
            PoolRow(
                purchase_id=r.id,
                title=r.title,
                track_no=r.track_no,
                supplier_name=suppliers.get(r.supplier_id) if r.supplier_id else None,
                ordered_on=r.ordered_on,
                state=supply_state(rp.stage_dates(r)),
                items=titles[:3],
                units=_units(lines[r.id]),
            )
        )
    return PoolOut(items=out, amounts=_amounts(ctx))


@router.post("/orgs/{org_id}/cargo-pool/tracked", response_model=TrackedOut, status_code=201)
async def save_tracked(
    body: TrackedIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> TrackedOut:
    """Trekli kargo puli: har qatorga xaridning o'z "Kargo" xarajati (xarid ichida dona bo'yicha). Hammasi yoki hech
    biri (bitta tranzaksiya)."""
    _require_amounts(ctx)
    ids = [x.purchase_id for x in body.rows]
    members = await _members(ctx, ids)
    if any(x.shipment_id is not None for x in members.values()):
        raise AppError(
            "cargo_twice", 409, detail="xarid kodli qutida — kargo puli quti orqali bo'linadi"
        )
    cc, p = m.cost_components, m.purchases
    for row in body.rows:
        values = _component(body, row.amount, row.weight_kg)
        component_id = await ctx.conn.scalar(
            insert(cc)
            .values(org_id=ctx.org_id, purchase_id=row.purchase_id, **values)
            .returning(cc.c.id)
        )
        track = (row.track_no or "").strip()
        if track:
            await ctx.conn.execute(
                update(p)
                .where(p.c.id == row.purchase_id)
                .values(track_no=track, updated_at=func.now())
            )
        await ctx.audit(
            "cost_component.create",
            "cost_component",
            component_id,
            after=_plain({**values, "purchase_id": row.purchase_id, "track_no": track or None}),
        )
    await _recalc(ctx, request, background, ids)
    return TrackedOut(created=len(body.rows))


@router.post("/orgs/{org_id}/cargo-pool/shares", response_model=SharesOut)
async def preview_shares(body: SharesIn, ctx: Viewer) -> SharesOut:
    """Kodli quti: har xaridga tushadigan ulush (F20 ``box_shares``) — inputlarda tayyor turadi. Hech narsa yozilmaydi."""
    await _members(ctx, body.purchase_ids)
    lines = await _lines_of(ctx, body.purchase_ids)
    units = {pid: _units(lines[pid]) for pid in body.purchase_ids}
    return SharesOut(
        shares=_shares(body.amount, body.currency, units, dict(body.fixed)), units=units
    )


@router.post("/orgs/{org_id}/cargo-pool/box", response_model=BoxOut, status_code=201)
async def save_box(
    body: BoxIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> BoxOut:
    """Kodli quti: Kargo yaratiladi, xaridlar biriktiriladi, bitta "Kargo" xarajati (ulushlar dona bo'yicha, qo'lda
    o'zgartirilganlari — ``targets.purchase_shares``)."""
    _require_amounts(ctx)
    members = await _members(ctx, body.purchase_ids)
    if any(x.shipment_id is not None for x in members.values()):
        raise AppError("purchase_in_shipment", 409, detail="xarid boshqa kargoda")
    if await _own_cargo(ctx, body.purchase_ids):
        raise AppError(
            "cargo_twice", 409, detail="xaridning o'z kargo puli bor — qutiga qo'shilmaydi"
        )
    if body.carrier_id is not None:
        found = await ctx.conn.scalar(
            select(m.carriers.c.id).where(m.carriers.c.id == body.carrier_id)
        )
        if found is None:
            raise AppError("carrier_not_found", 404)
    lines = await _lines_of(ctx, body.purchase_ids)
    units = {pid: _units(lines[pid]) for pid in body.purchase_ids}
    _shares(body.amount, body.currency, units, dict(body.fixed))  # tekshiruv
    sh, p, cc = m.shipments, m.purchases, m.cost_components
    shipment_id = await ctx.conn.scalar(
        insert(sh)
        .values(org_id=ctx.org_id, title=body.title.strip(), carrier_id=body.carrier_id)
        .returning(sh.c.id)
    )
    assert shipment_id is not None
    await ctx.conn.execute(
        update(p)
        .where(p.c.id.in_(body.purchase_ids))
        .values(shipment_id=shipment_id, updated_at=func.now())
    )
    values = _component(body, body.amount, body.weight_kg)
    targets = (
        {"purchase_shares": {str(k): str(v) for k, v in body.fixed.items()}} if body.fixed else None
    )
    await ctx.conn.execute(
        insert(cc).values(org_id=ctx.org_id, shipment_id=shipment_id, targets=targets, **values)
    )
    await ctx.audit(
        "shipment.create",
        "shipment",
        shipment_id,
        after=_plain({**body.model_dump(), "box": True}),
    )
    await request_shipment_members(ctx, shipment_id)
    background.add_task(_kick, request, ctx.org_id)
    return BoxOut(shipment_id=shipment_id)


@router.put(
    "/orgs/{org_id}/shipments/{shipment_id}/components/{component_id}/purchase-shares",
    response_model=SharesOut,
)
async def set_box_shares(
    shipment_id: UUID,
    component_id: UUID,
    body: BoxSharesIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> SharesOut:
    """Qutining qo'lda ulushlarini almashtirish (ADR-061 §3): yig'indi summadan oshmaydi; hamma xarid qo'lda bo'lsa —
    summaga teng. Javob — yangi ulushlar."""
    _require_amounts(ctx)
    cc, p = m.cost_components, m.purchases
    row = (
        await ctx.conn.execute(
            select(cc).where(cc.c.id == component_id, cc.c.shipment_id == shipment_id)
        )
    ).first()
    if row is None:
        raise AppError("component_not_found", 404)
    ids = list(await ctx.conn.scalars(select(p.c.id).where(p.c.shipment_id == shipment_id)))
    if set(body.fixed) - set(ids):
        raise AppError("purchase_not_found", 404, detail="xarid shu kargoda emas")
    lines = await _lines_of(ctx, ids)
    units = {pid: _units(lines[pid]) for pid in ids}
    shares = _shares(row.amount, calc_lots.currency_of(row.currency), units, dict(body.fixed))
    targets = {k: v for k, v in (row.targets or {}).items() if k != "purchase_shares"}
    if body.fixed:
        targets["purchase_shares"] = {str(k): str(v) for k, v in body.fixed.items()}
    await ctx.conn.execute(
        update(cc)
        .where(cc.c.id == component_id)
        .values(targets=targets or None, updated_at=func.now())
    )
    await ctx.audit(
        "cost_component.update",
        "cost_component",
        component_id,
        before=_plain({"targets": row.targets}),
        after=_plain({"targets": targets or None}),
    )
    await request_shipment_members(ctx, shipment_id)
    background.add_task(_kick, request, ctx.org_id)
    return SharesOut(shares=shares, units=units)


# --- Xarajat turlari lug'ati (ADR-061 §4) ---------------------------------------------------------


@router.get("/orgs/{org_id}/cost-types", response_model=list[CostTypeOut])
async def list_cost_types(ctx: Viewer) -> list[CostTypeOut]:
    """Sotuvchining o'z xarajat turlari (tayyor turlar — ``ComponentKind``, UI'da)."""
    t = m.cost_types
    rows = await ctx.conn.execute(select(t.c.id, t.c.name).order_by(t.c.name))
    return [CostTypeOut(id=r.id, name=r.name) for r in rows]


@router.post("/orgs/{org_id}/cost-types", response_model=CostTypeOut, status_code=201)
async def create_cost_type(body: CostTypeIn, ctx: Manager) -> CostTypeOut:
    t = m.cost_types
    name = " ".join(body.name.split())
    if not name:
        raise AppError("bad_request", 422, detail="nom bo'sh")
    existing = await ctx.conn.scalar(select(t.c.id).where(func.lower(t.c.name) == name.lower()))
    if existing is not None:
        return CostTypeOut(id=existing, name=name)
    type_id = await ctx.conn.scalar(
        insert(t).values(org_id=ctx.org_id, name=name).returning(t.c.id)
    )
    assert type_id is not None
    await ctx.audit("cost_type.create", "cost_type", type_id, after={"name": name})
    return CostTypeOut(id=type_id, name=name)


@router.delete("/orgs/{org_id}/cost-types/{type_id}", status_code=204)
async def delete_cost_type(type_id: UUID, ctx: Manager) -> Response:
    """Faqat ishlatilmagan tur o'chadi (aks holda xarajat turi jim yo'qolardi)."""
    t, cc = m.cost_types, m.cost_components
    row = (await ctx.conn.execute(select(t).where(t.c.id == type_id))).first()
    if row is None:
        raise AppError("cost_type_not_found", 404)
    used = await ctx.conn.scalar(
        select(func.count()).select_from(cc).where(cc.c.cost_type_id == type_id)
    )
    if used:
        raise AppError("cost_type_in_use", 409, detail="bu tur xarajatlarda ishlatilgan")
    await ctx.conn.execute(delete(t).where(t.c.id == type_id))
    await ctx.audit("cost_type.delete", "cost_type", type_id, before={"name": row.name})
    return Response(status_code=204)

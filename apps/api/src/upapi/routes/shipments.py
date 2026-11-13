"""``/shipments``: Kargo (jo'natma) — bitta kargo, ko'p xarid (B4.31, ADR-046; 02 M9, F20).

Katta sotuvchi 10 xil bazadagi tovarni bitta presslangan o'ramda olib keladi: kargo narxi bitta, tovarlar esa bir necha
xaridda (yetkazib beruvchi bo'yicha). Kargo — alohida yozuv: nomi, kargo kompaniyasi, **Xitoy omborida / yo'lda /
Toshkentga keldi sanalari** va **xarajat komponentlari** (kargo, bojxona, yorliq ...). Xarid faqat bitta kargoga tegishli
(``purchases.shipment_id``); kargo xarajatlari kargodagi **hamma xaridlarning hamma tovarlariga** bitta taqsimotda
bo'linadi (``upcore.purchasing.compute_shipment_lots``: vazn / hajm / dona / qiymat / qo'lda; yaxlitlash qoldig'i butun
kargo bo'yicha eng katta tovarga — yig'indi tiyinigacha teng). Xarid ichidagi komponentlar (tovar, agent, Xitoy ichi)
o'z xaridida qoladi. Kargosiz xarid avvalgidek ishlaydi.

Sanalar kargodan olinadi: kargo sanasi o'zgarsa — uning xaridlarining shu bosqich ustunlari yangilanadi (bo'sh sana xarid
sanasini o'chiradi, bog'langanda esa xaridning o'z sanasi yo'qolmaydi). Kargo o'zgarsa — hamma xaridlari qayta
hisoblanadi (``calc``), sotuvlar tannarxi shular bilan yangilanadi ("qayta hisoblandi").

O'qish — ``view_purchases``; yozish va xarajatlar — ``manage_purchases`` (xarajat summalari uchun ``view_purchase_amounts``).
Kargoni o'chirish — faqat xaridlari bo'lmasa (aks holda ularning tannarxi jim o'zgarar edi); xarajatlari u bilan ketadi.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Row, delete, func, insert, or_, select, update
from upcore.fx import to_uzs
from upcore.money import Currency, Money, to_decimal
from upcore.purchasing import (
    SHIPMENT_KINDS,
    ComponentKind,
    Stage,
    SupplyState,
    current_stage,
    default_base,
)

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc import lots as calc_lots
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import purchases as rp
from upapi.reports.common import today
from upapi.routes.purchases import (
    SHIPMENT_STAGES,
    ComponentIn,
    ComponentPatch,
    _amounts,
    _component_values,
    _kick,
    _plain,
    _require_amounts,
    _shipment,
    _targets,
    check_component,
    check_cost_type,
    fx_gap,
    request_shipment_members,
)

router = APIRouter(tags=["purchases"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]

Text = Annotated[str | None, Field(max_length=300)]


class ShipmentIn(BaseModel):
    title: Text = None
    carrier_id: UUID | None = None
    cn_warehouse_on: date | None = None
    shipped_on: date | None = None
    arrived_on: date | None = None
    note: Annotated[str | None, Field(max_length=2000)] = None


class ShipmentPatch(ShipmentIn):
    """Faqat berilgan maydonlar o'zgaradi; ``null`` — qiymatni (sanani) o'chirish."""


class ShipmentOut(BaseModel):
    id: UUID
    title: str | None
    carrier_id: UUID | None
    carrier_name: str | None
    cn_warehouse_on: date | None
    shipped_on: date | None
    arrived_on: date | None
    note: str | None
    purchase_count: int
    units: int  # kargodagi hamma xaridlar donasi (qabul qilingan, yo'q bo'lsa buyurtma)
    total: (
        Decimal | None
    )  # kargo xarajatlari so'mda (summalar ruxsati bilan; kursi yo'q komponent bo'lsa — ``null``)
    created_at: datetime


class ShipmentsOut(BaseModel):
    items: list[ShipmentOut]
    amounts: bool
    total: int = 0  # jami kargo
    page: int = 1  # haqiqiy sahifa (`limit` berilmasa hammasi — 1)
    pages: int = 1


class ShipmentPurchaseOut(BaseModel):
    id: UUID
    title: str | None
    supplier_name: str | None
    stage: Stage
    state: SupplyState  # ADR-061 §1
    line_count: int
    units: int
    share: Decimal | None  # shu xaridga tushgan kargo ulushi, so'mda
    total: Decimal | None  # xaridning o'z xarajatlari + kargo ulushi
    unit_cost: Decimal | None
    error: str | None


class ShipmentLineOut(BaseModel):
    id: UUID
    purchase_id: UUID
    purchase_title: str | None
    name: str | None
    qty: int
    unit_weight: Decimal | None
    unit_volume: Decimal | None
    share: Decimal | None  # shu tovarga tushgan kargo ulushi, so'mda
    share_per_unit: Decimal | None
    flags: list[str]


class ShipmentDetailOut(BaseModel):
    shipment: ShipmentOut
    amounts: bool
    purchases: list[ShipmentPurchaseOut]
    lines: list[ShipmentLineOut]
    components: list[rp.ComponentOut]  # summalar ruxsatisiz — bo'sh
    by_kind: dict[str, Decimal]  # kargo xarajatlari turlar bo'yicha, so'mda
    error: str | None  # kargoni hisoblab bo'lmadi (masalan, xaridda kurs yo'q)
    recalc_pending: bool


# --- Yordamchilar --------------------------------------------------------------------------------


async def _exists(ctx: OrgContext, table: Any, row_id: UUID | None, code: str) -> None:
    if (
        row_id is not None
        and await ctx.conn.scalar(select(table.c.id).where(table.c.id == row_id)) is None
    ):
        raise AppError(code, 404)


def _check_ship_dates(dates: dict[Stage, date | None]) -> None:
    last: tuple[Stage, date] | None = None
    for stage in SHIPMENT_STAGES:
        on = dates.get(stage)
        if on is None:
            continue
        if last is not None and on < last[1]:
            raise AppError(
                "bad_stage_dates", 422, detail=f"{stage.value} sanasi {last[0].value} dan oldin"
            )
        last = (stage, on)


def _ship_dates(row: Any) -> dict[Stage, date | None]:
    return {s: getattr(row, f"{s.value}_on") for s in SHIPMENT_STAGES}


async def _component_row(ctx: OrgContext, shipment_id: UUID, component_id: UUID) -> Any:
    cc = m.cost_components
    row = (
        await ctx.conn.execute(
            select(cc).where(cc.c.id == component_id, cc.c.shipment_id == shipment_id)
        )
    ).first()
    if row is None:
        raise AppError("component_not_found", 404)
    return row


async def _check_targets(
    ctx: OrgContext, shipment_id: UUID, lines: list[UUID] | None, shares: dict[Any, Any]
) -> None:
    """Kargo komponenti faqat shu kargodagi xaridlar qatorlariga tegishli bo'lishi mumkin."""
    p, pl = m.purchases, m.purchase_lines
    own = {
        r.id
        for r in await ctx.conn.execute(
            select(pl.c.id)
            .join(p, p.c.id == pl.c.purchase_id)
            .where(p.c.shipment_id == shipment_id)
        )
    }
    wanted = set(lines or []) | {UUID(str(k)) for k in shares}
    if wanted - own:
        raise AppError("line_not_found", 404, detail="komponent boshqa kargo tovariga tegishli")


async def _members_changed(
    ctx: OrgContext, request: Request, background: BackgroundTasks, shipment_id: UUID
) -> None:
    """Kargo o'zgardi: xaridlarning joriy bosqichi (``status``), qayta hisob so'rovlari va hisob ishi."""
    p = m.purchases
    for row in await ctx.conn.execute(select(p).where(p.c.shipment_id == shipment_id)):
        await ctx.conn.execute(
            update(p)
            .where(p.c.id == row.id)
            .values(status=current_stage(rp.stage_dates(row)).value, updated_at=func.now())
        )
    await request_shipment_members(ctx, shipment_id)
    background.add_task(_kick, request, ctx.org_id)


async def _fx_since(ctx: OrgContext, shipment: Any) -> date | None:
    cc = m.cost_components
    comps = list(await ctx.conn.execute(select(cc).where(cc.c.shipment_id == shipment.id)))
    return await fx_gap(ctx, comps, [], shipment.shipped_on or shipment.arrived_on)


async def _kick_fx(ctx: OrgContext, request: Request, shipment: Any) -> None:
    since = await _fx_since(ctx, shipment)
    if since is not None:
        try:
            await request.app.state.jobs.defer_fx(since)
        except Exception:  # navbat ishlamasa — keyingi sinxron / kunlik ish to'ldiradi
            return


async def _pending(ctx: OrgContext, shipment_id: UUID) -> bool:
    q, p = m.recalc_queue, m.purchases
    members = select(p.c.id).where(p.c.shipment_id == shipment_id)
    found = await ctx.conn.scalar(
        select(q.c.id)
        .where(q.c.kind == "purchase", or_(q.c.ref_id.in_(members), q.c.ref_id.is_(None)))
        .limit(1)
    )
    return found is not None


async def _total(
    book: rp.Book, shipment: Row[Any], comps: list[Row[Any]]
) -> tuple[Decimal | None, list[rp.ComponentOut]]:
    fallback = calc_lots.shipment_fallback(shipment)
    outs = [book._component(fallback, c) for c in comps]
    if any(o.error or o.amount_uzs is None for o in outs):
        return None, outs
    return sum((o.amount_uzs for o in outs if o.amount_uzs is not None), Decimal(0)), outs


async def _detail(ctx: OrgContext, shipment_id: UUID) -> ShipmentDetailOut:
    book = await rp.Book(ctx.conn, today()).load(shipment_id=shipment_id)
    shipment = book.shipments.get(shipment_id)
    if shipment is None:
        raise AppError("shipment_not_found", 404)
    amounts = _amounts(ctx)
    comps = book.shipment_components.get(shipment_id, [])
    total, comp_outs = await _total(book, shipment, comps)
    group = book.group(shipment_id)
    members = sorted(book.purchases, key=lambda x: (x.created_at, x.id))

    purchases: list[ShipmentPurchaseOut] = []
    lines: list[ShipmentLineOut] = []
    units_all = 0
    for purchase in members:
        ev = group.purchases[purchase.id]
        out = book.summary(purchase, ev, amounts)
        p_lines = book.lines.get(purchase.id, [])
        qty_by = {
            x.id: x.ordered_qty if x.received_qty is None else x.received_qty for x in p_lines
        }
        units = sum(qty_by.values())
        units_all += units
        shares = [group.shares.get(str(x.id)) for x in p_lines]
        share = (
            sum((s.total.amount for s in shares if s is not None), Decimal(0))
            if amounts and group.shares
            else None
        )
        purchases.append(
            ShipmentPurchaseOut(
                id=purchase.id,
                title=purchase.title,
                supplier_name=out.supplier_name,
                stage=out.stage,
                state=out.state,
                line_count=len(p_lines),
                units=units,
                share=share,
                total=out.total,
                unit_cost=out.unit_cost,
                error=ev.error,
            )
        )
        for x in p_lines:
            item = book.items.get(x.item_id) if x.item_id else None
            s = group.shares.get(str(x.id))
            qty = qty_by[x.id]
            line_share = s.total.amount if amounts and s is not None else None
            lines.append(
                ShipmentLineOut(
                    id=x.id,
                    purchase_id=purchase.id,
                    purchase_title=purchase.title,
                    name=item.name if item is not None else x.temp_name,
                    qty=qty,
                    unit_weight=x.unit_weight,
                    unit_volume=x.unit_volume,
                    share=line_share,
                    share_per_unit=None if line_share is None or qty == 0 else line_share / qty,
                    flags=sorted(f.value for f in s.flags) if s is not None else [],
                )
            )
    by_kind: dict[str, Decimal] = {}
    if amounts:
        for o in comp_outs:
            if o.amount_uzs is not None:
                by_kind[o.kind] = by_kind.get(o.kind, Decimal(0)) + o.amount_uzs
    carrier = book.carriers.get(shipment.carrier_id) if shipment.carrier_id else None
    return ShipmentDetailOut(
        shipment=ShipmentOut(
            id=shipment.id,
            title=shipment.title,
            carrier_id=shipment.carrier_id,
            carrier_name=carrier,
            cn_warehouse_on=shipment.cn_warehouse_on,
            shipped_on=shipment.shipped_on,
            arrived_on=shipment.arrived_on,
            note=shipment.note,
            purchase_count=len(members),
            units=units_all,
            total=total if amounts else None,
            created_at=shipment.created_at,
        ),
        amounts=amounts,
        purchases=purchases,
        lines=lines,
        components=comp_outs if amounts else [],
        by_kind=by_kind,
        error=group.error,
        recalc_pending=await _pending(ctx, shipment_id),
    )


# --- Kargo ---------------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/shipments", response_model=ShipmentsOut)
async def list_shipments(
    ctx: Viewer,
    limit: Annotated[
        int | None, Query(ge=1, le=100, description="Sahifa o'lchami; bo'lmasa — hammasi")
    ] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> ShipmentsOut:
    """Kargolar (yangisi birinchi): xaridlar soni, dona va (summalar ruxsati bilan) kargo xarajatlari jami.
    ``limit`` berilsa — sahifa (B5.0d, ADR-054; tanlov ro'yxatlari ``limit`` siz hammasini oladi)."""
    sh, p, pl, cc, c = m.shipments, m.purchases, m.purchase_lines, m.cost_components, m.carriers
    amounts = _amounts(ctx)
    count = int(await ctx.conn.scalar(select(func.count()).select_from(sh)) or 0)
    pages = max(1, -(-count // limit)) if limit else 1
    at = min(page, pages) if limit else 1
    query = select(sh).order_by(sh.c.created_at.desc(), sh.c.id)
    if limit:
        query = query.limit(limit).offset((at - 1) * limit)
    rows = list(await ctx.conn.execute(query))
    carriers = {r.id: r.name for r in await ctx.conn.execute(select(c.c.id, c.c.name))}
    counts = {
        r.shipment_id: r.n
        for r in await ctx.conn.execute(
            select(p.c.shipment_id, func.count().label("n"))
            .where(p.c.shipment_id.is_not(None))
            .group_by(p.c.shipment_id)
        )
    }
    units = {
        r.shipment_id: int(r.n)
        for r in await ctx.conn.execute(
            select(
                p.c.shipment_id,
                func.sum(func.coalesce(pl.c.received_qty, pl.c.ordered_qty)).label("n"),
            )
            .join(pl, pl.c.purchase_id == p.c.id)
            .where(p.c.shipment_id.is_not(None))
            .group_by(p.c.shipment_id)
        )
    }
    totals: dict[UUID, Decimal | None] = {}
    if amounts and rows:
        comps = list(
            await ctx.conn.execute(select(cc).where(cc.c.shipment_id.in_([x.id for x in rows])))
        )
        rates = calc_lots.Rates(ctx.conn, today())
        await rates.load(calc_lots.currencies_of(comps))
        by_ship = {x.id: x for x in rows}
        for comp in comps:
            ship_id = comp.shipment_id
            if ship_id in totals and totals[ship_id] is None:
                continue
            try:
                fx = calc_lots.component_rate(
                    comp, calc_lots.shipment_fallback(by_ship[ship_id]), rates
                )
                money = Money(to_decimal(comp.amount), calc_lots.currency_of(comp.currency))
                so_far = totals.get(ship_id) or Decimal(0)
                totals[ship_id] = so_far + to_uzs(money, fx).amount
            except calc_lots.CALC_ERRORS:
                totals[ship_id] = None
        for x in rows:
            totals.setdefault(x.id, Decimal(0))
    return ShipmentsOut(
        items=[
            ShipmentOut(
                id=x.id,
                title=x.title,
                carrier_id=x.carrier_id,
                carrier_name=carriers.get(x.carrier_id) if x.carrier_id else None,
                cn_warehouse_on=x.cn_warehouse_on,
                shipped_on=x.shipped_on,
                arrived_on=x.arrived_on,
                note=x.note,
                purchase_count=int(counts.get(x.id, 0)),
                units=units.get(x.id, 0),
                total=totals.get(x.id) if amounts else None,
                created_at=x.created_at,
            )
            for x in rows
        ],
        amounts=amounts,
        total=count,
        page=at,
        pages=pages,
    )


@router.get("/orgs/{org_id}/shipments/{shipment_id}", response_model=ShipmentDetailOut)
async def get_shipment(shipment_id: UUID, ctx: Viewer) -> ShipmentDetailOut:
    return await _detail(ctx, shipment_id)


@router.post("/orgs/{org_id}/shipments", response_model=ShipmentDetailOut, status_code=201)
async def create_shipment(body: ShipmentIn, ctx: Manager) -> ShipmentDetailOut:
    await _exists(ctx, m.carriers, body.carrier_id, "carrier_not_found")
    _check_ship_dates(
        {
            Stage.CN_WAREHOUSE: body.cn_warehouse_on,
            Stage.SHIPPED: body.shipped_on,
            Stage.ARRIVED: body.arrived_on,
        }
    )
    sh = m.shipments
    shipment_id = await ctx.conn.scalar(
        insert(sh).values(org_id=ctx.org_id, **body.model_dump()).returning(sh.c.id)
    )
    assert shipment_id is not None
    await ctx.audit("shipment.create", "shipment", shipment_id, after=_plain(body.model_dump()))
    return await _detail(ctx, shipment_id)


@router.patch("/orgs/{org_id}/shipments/{shipment_id}", response_model=ShipmentDetailOut)
async def update_shipment(
    shipment_id: UUID,
    body: ShipmentPatch,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> ShipmentDetailOut:
    row = await _shipment(ctx, shipment_id)
    values = body.model_dump(exclude_unset=True)
    await _exists(ctx, m.carriers, values.get("carrier_id"), "carrier_not_found")
    _check_ship_dates(
        _ship_dates(row)
        | {Stage(k.removesuffix("_on")): v for k, v in values.items() if k.endswith("_on")}
    )
    if not values:
        return await _detail(ctx, shipment_id)
    before = {k: getattr(row, k) for k in values}
    sh, p = m.shipments, m.purchases
    await ctx.conn.execute(
        update(sh).where(sh.c.id == shipment_id).values(**values, updated_at=func.now())
    )
    await ctx.audit(
        "shipment.update", "shipment", shipment_id, before=_plain(before), after=_plain(values)
    )
    dates = {k: v for k, v in values.items() if k.endswith("_on")}
    if (
        dates
    ):  # sanalar kargodan: xaridlarning shu bosqich ustunlari kargo bilan bir xil (bo'sh ham)
        await ctx.conn.execute(
            update(p).where(p.c.shipment_id == shipment_id).values(**dates, updated_at=func.now())
        )
    await _members_changed(ctx, request, background, shipment_id)
    return await _detail(ctx, shipment_id)


@router.delete("/orgs/{org_id}/shipments/{shipment_id}", status_code=204)
async def delete_shipment(shipment_id: UUID, ctx: Manager) -> Response:
    row = await _shipment(ctx, shipment_id)
    p = m.purchases
    linked = await ctx.conn.scalar(
        select(func.count()).select_from(p).where(p.c.shipment_id == shipment_id)
    )
    if linked:
        raise AppError(
            "shipment_in_use",
            409,
            detail="kargoda xaridlar bor — avval ularni kargodan ajrating",
        )
    await ctx.conn.execute(delete(m.shipments).where(m.shipments.c.id == shipment_id))
    await ctx.audit("shipment.delete", "shipment", shipment_id, before=_plain({"title": row.title}))
    return Response(status_code=204)


# --- Kargo xarajatlari ---------------------------------------------------------------------------


def _check_kind(kind: ComponentKind) -> None:
    """Tovar, Xitoy ichki yetkazish va agent komissiyasi har xaridning o'zida; kargoga tegishli emas (ADR-049)."""
    if kind not in SHIPMENT_KINDS:
        raise AppError(
            "kind_not_for_shipment",
            422,
            detail="bu xarajat turi xaridga tegishli — uni xarid sahifasida kiriting",
        )


@router.post(
    "/orgs/{org_id}/shipments/{shipment_id}/components",
    response_model=ShipmentDetailOut,
    status_code=201,
)
async def create_component(
    shipment_id: UUID,
    body: ComponentIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> ShipmentDetailOut:
    _require_amounts(ctx)
    shipment = await _shipment(ctx, shipment_id)
    _check_kind(body.kind)
    await _check_targets(ctx, shipment_id, body.lines, body.shares)
    raw = body.model_dump()
    await check_cost_type(ctx, raw)
    values = _component_values(raw)
    values["allocation"] = values["allocation"] or default_base(body.kind).value
    cc = m.cost_components
    component_id = await ctx.conn.scalar(
        insert(cc)
        .values(
            org_id=ctx.org_id,
            shipment_id=shipment_id,
            targets=_targets(body.lines, body.shares),
            **values,
        )
        .returning(cc.c.id)
    )
    await ctx.audit(
        "cost_component.create", "cost_component", component_id, after=_plain(body.model_dump())
    )
    await _members_changed(ctx, request, background, shipment_id)
    await _kick_fx(ctx, request, shipment)
    return await _detail(ctx, shipment_id)


@router.patch(
    "/orgs/{org_id}/shipments/{shipment_id}/components/{component_id}",
    response_model=ShipmentDetailOut,
)
async def update_component(
    shipment_id: UUID,
    component_id: UUID,
    body: ComponentPatch,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> ShipmentDetailOut:
    _require_amounts(ctx)
    shipment = await _shipment(ctx, shipment_id)
    row = await _component_row(ctx, shipment_id, component_id)
    values = body.model_dump(exclude_unset=True)
    for key in ("kind", "amount", "currency", "rate_mode", "allocation"):
        if key in values and values[key] is None:
            raise AppError("bad_component", 422, detail=f"{key} bo'sh bo'lmaydi")
    # Tur o'zgarsa tekshiriladi; eski yozuvning (masalan, avval yozilgan "Tovar") boshqa maydonlari tahrirlanaveradi.
    if values.get("kind") is not None:
        _check_kind(values["kind"])
    lines, shares = calc_lots.targets_of(row.targets)
    new_lines = values.pop("lines", lines)
    new_shares = values.pop("shares", shares)
    if new_shares is None:
        new_shares = {}
    merged = {
        "currency": Currency(values.get("currency", row.currency)),
        "rate_mode": values.get("rate_mode", row.rate_mode),
        "rate": values.get("rate", row.rate),
        "charged_amount": values.get("charged_amount", row.charged_amount),
        "charged_currency": values.get(
            "charged_currency",
            Currency(row.charged_currency) if row.charged_currency else None,
        ),
    }
    try:
        check_component(merged)
    except ValueError as exc:
        raise AppError("bad_component", 422, detail=str(exc)) from None
    target_lines = None if new_lines is None else [UUID(str(x)) for x in new_lines]
    await _check_targets(ctx, shipment_id, target_lines, new_shares)
    await check_cost_type(ctx, values, row.kind)
    cols = _component_values(values)
    cols["targets"] = _targets(target_lines, new_shares, row.targets)
    before = {k: getattr(row, k) for k in cols}
    cc = m.cost_components
    await ctx.conn.execute(
        update(cc).where(cc.c.id == component_id).values(**cols, updated_at=func.now())
    )
    await ctx.audit(
        "cost_component.update",
        "cost_component",
        component_id,
        before=_plain(before),
        after=_plain(cols),
    )
    await _members_changed(ctx, request, background, shipment_id)
    await _kick_fx(ctx, request, shipment)
    return await _detail(ctx, shipment_id)


@router.delete(
    "/orgs/{org_id}/shipments/{shipment_id}/components/{component_id}",
    response_model=ShipmentDetailOut,
)
async def delete_component(
    shipment_id: UUID,
    component_id: UUID,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> ShipmentDetailOut:
    _require_amounts(ctx)
    await _shipment(ctx, shipment_id)
    row = await _component_row(ctx, shipment_id, component_id)
    await ctx.conn.execute(delete(m.cost_components).where(m.cost_components.c.id == component_id))
    await ctx.audit(
        "cost_component.delete",
        "cost_component",
        component_id,
        before=_plain({"kind": row.kind, "amount": row.amount, "currency": row.currency}),
    )
    await _members_changed(ctx, request, background, shipment_id)
    return await _detail(ctx, shipment_id)

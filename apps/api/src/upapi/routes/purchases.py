"""``/purchases``: xaridlar (partiyalar, M9, B4.6) — xarid hayoti, qatorlar, xarajat komponentlari, Partiya yo'li.

O'qish — ``view_purchases`` (summalar ``view_purchase_amounts`` bilan); yozish — ``manage_purchases`` (egasi, menejer,
omborchi). Omborchi summalarni ko'rmaydi, shuning uchun narx va komponentlarni ham o'zgartira olmaydi (403). Har
o'zgarish audit jurnaliga yoziladi.

Legacy'dagi kabi bosqichma-bosqich to'ldiriladi: avval faqat sarlavha va tovar summasi, keyin qatorlar, keyin kargo.
Bosqich sanalari ixtiyoriy, lekin tartib bilan (keyingi bosqich oldingisidan oldin emas); joriy bosqich (``status``)
— sanasi bor eng oxirgisi. Birlik tannarx (F20) javobda jonli (:mod:`upapi.reports.purchases`).

**Qayta hisob (kech kiritilgan xarajat):** har yozuv shu tranzaksiyada ``recalc_queue`` ga xarid so'rovini qo'yadi
(o'chirilgan qator/xarid tovarlari uchun — ``item`` so'rovi: lotlari FK bilan o'chadi), javobdan keyin ``calc.org``
ishi navbatga qo'yiladi → lotlar (F20) → o'tgan sotuvlar tannarxi (F21) → P&L'da "qayta hisoblandi" belgisi.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, insert, select, update
from upcore.money import Currency
from upcore.purchasing import (
    DATED_STAGES,
    AllocationBase,
    ComponentKind,
    Stage,
    current_stage,
    default_base,
)

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission, allowed
from upapi.calc.lots import targets_of
from upapi.db import models as m
from upapi.errors import AppError
from upapi.logs import get_logger
from upapi.reports import purchases as rp
from upapi.reports.common import today

router = APIRouter(tags=["purchases"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str | None, Field(max_length=500)]
Url = Annotated[str | None, Field(max_length=1000)]
Qty = Annotated[int, Field(ge=0, le=10_000_000)]
Positive = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
Measure = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=6)]
_log = get_logger("upapi.purchases")


class PurchasesOut(BaseModel):
    items: list[rp.PurchaseOut]
    amounts: bool


class PurchaseIn(BaseModel):
    title: Text = None
    supplier_id: UUID | None = None
    carrier_id: UUID | None = None
    note: Text = None
    dates: dict[Stage, date | None] = Field(
        default_factory=dict
    )  # bosqich → sana (``draft`` — yo'q)


class PurchasePatch(BaseModel):
    title: Text = None
    supplier_id: UUID | None = None
    carrier_id: UUID | None = None
    note: Text = None
    dates: dict[Stage, date | None] | None = (
        None  # faqat berilgan bosqichlar o'zgaradi; ``null`` — sanani o'chirish
    )


class LineIn(BaseModel):
    """Qator: mavjud tovar (``item_id``) yoki "yangi tovar" (``temp_name``, havola, rasm)."""

    item_id: UUID | None = None
    temp_name: Annotated[str | None, Field(max_length=200)] = None
    url: Url = None
    image_url: Url = None
    variant: Annotated[str | None, Field(max_length=200)] = None
    ordered_qty: Annotated[int, Field(ge=1, le=10_000_000)]
    received_qty: Qty | None = None
    unit_price: Annotated[Decimal | None, Field(ge=0, max_digits=18, decimal_places=4)] = None
    currency: Currency | None = None
    unit_weight: Measure | None = None  # kg / dona
    unit_volume: Measure | None = None  # m³ / dona


class LinePatch(BaseModel):
    item_id: UUID | None = None
    temp_name: Annotated[str | None, Field(max_length=200)] = None
    url: Url = None
    image_url: Url = None
    variant: Annotated[str | None, Field(max_length=200)] = None
    ordered_qty: Annotated[int | None, Field(ge=1, le=10_000_000)] = None
    received_qty: Qty | None = None
    unit_price: Annotated[Decimal | None, Field(ge=0, max_digits=18, decimal_places=4)] = None
    currency: Currency | None = None
    unit_weight: Measure | None = None
    unit_volume: Measure | None = None


class ComponentIn(BaseModel):
    """Xarajat komponenti. Kurs: ``cbu`` (to'lov sanasi), ``manual`` (``rate``), ``effective`` (kartadan yechilgan
    ``charged_amount`` ``charged_currency`` da). ``allocation`` bo'lmasa — tur standarti (kargo — vazn, tovar — qiymat,
    qolganlari — dona). ``lines`` — tegishli qatorlar (``null`` — hammasi), ``shares`` — qo'lda ulushlar."""

    kind: ComponentKind
    amount: Positive
    currency: Currency
    paid_on: date | None = None
    rate_mode: Annotated[str, Field(pattern="^(cbu|manual|effective)$")] = "cbu"
    rate: Annotated[Decimal | None, Field(gt=0, max_digits=18, decimal_places=6)] = None
    charged_amount: Positive | None = None
    charged_currency: Currency | None = None
    allocation: AllocationBase | None = None
    lines: list[UUID] | None = None
    shares: dict[UUID, Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _rate(self) -> ComponentIn:
        check_component(self.model_dump())
        return self


class ComponentPatch(BaseModel):
    kind: ComponentKind | None = None
    amount: Positive | None = None
    currency: Currency | None = None
    paid_on: date | None = None
    rate_mode: Annotated[str | None, Field(pattern="^(cbu|manual|effective)$")] = None
    rate: Annotated[Decimal | None, Field(gt=0, max_digits=18, decimal_places=6)] = None
    charged_amount: Positive | None = None
    charged_currency: Currency | None = None
    allocation: AllocationBase | None = None
    lines: list[UUID] | None = None
    shares: dict[UUID, Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]] | None = (
        None
    )


class SupplierIn(BaseModel):
    name: Name
    platform: Annotated[str | None, Field(max_length=40)] = None


class CarrierIn(BaseModel):
    name: Name
    pricing: Annotated[str | None, Field(max_length=40)] = None


def check_component(c: dict[str, Any]) -> None:
    """Kurs rejimi uchun kerakli qiymatlar (so'mda kurs kerak emas)."""
    if c["currency"] is Currency.UZS:
        return
    if c["rate_mode"] == "manual" and c.get("rate") is None:
        raise ValueError("qo'lda kurs rejimida rate kerak")
    if c["rate_mode"] == "effective":
        if c.get("charged_amount") is None or c.get("charged_currency") is None:
            raise ValueError("kartadan yechilgan summa va uning valyutasi kerak")
        if c["charged_currency"] is c["currency"]:
            raise ValueError("yechilgan summa valyutasi boshqa bo'lishi kerak")


def _plain(values: dict[str, Any]) -> dict[str, Any]:
    """Audit (JSONB) uchun: sana, UUID, Decimal — satr."""

    def one(v: Any) -> Any:
        if v is None or isinstance(v, (str, bool, int)):
            return v
        if isinstance(v, list):
            return [one(x) for x in v]
        if isinstance(v, dict):
            return {str(k): one(x) for k, x in v.items()}
        return str(v)

    return {k: one(v) for k, v in values.items()}


def _check_dates(dates: dict[Stage, date | None]) -> None:
    last: tuple[Stage, date] | None = None
    for stage in DATED_STAGES:
        on = dates.get(stage)
        if on is None:
            continue
        if last is not None and on < last[1]:
            raise AppError(
                "bad_stage_dates", 422, detail=f"{stage.value} sanasi {last[0].value} dan oldin"
            )
        last = (stage, on)


def _date_columns(dates: dict[Stage, date | None]) -> dict[str, date | None]:
    if Stage.DRAFT in dates:
        raise AppError("bad_stage_dates", 422, detail="qoralama bosqichining sanasi yo'q")
    return {f"{s.value}_on": on for s, on in dates.items()}


async def _exists(ctx: OrgContext, table: Any, row_id: UUID | None, code: str) -> None:
    if (
        row_id is not None
        and await ctx.conn.scalar(select(table.c.id).where(table.c.id == row_id)) is None
    ):
        raise AppError(code, 404)


async def _purchase(ctx: OrgContext, purchase_id: UUID) -> Any:
    p = m.purchases
    row = (await ctx.conn.execute(select(p).where(p.c.id == purchase_id))).first()
    if row is None:
        raise AppError("purchase_not_found", 404)
    return row


async def _line(ctx: OrgContext, purchase_id: UUID, line_id: UUID) -> Any:
    pl = m.purchase_lines
    row = (
        await ctx.conn.execute(
            select(pl).where(pl.c.id == line_id, pl.c.purchase_id == purchase_id)
        )
    ).first()
    if row is None:
        raise AppError("line_not_found", 404)
    return row


async def _component(ctx: OrgContext, purchase_id: UUID, component_id: UUID) -> Any:
    cc = m.cost_components
    row = (
        await ctx.conn.execute(
            select(cc).where(cc.c.id == component_id, cc.c.purchase_id == purchase_id)
        )
    ).first()
    if row is None:
        raise AppError("component_not_found", 404)
    return row


def _amounts(ctx: OrgContext) -> bool:
    return allowed(ctx.role, Permission.VIEW_PURCHASE_AMOUNTS)


def _require_amounts(ctx: OrgContext) -> None:
    if not _amounts(ctx):
        raise AppError("forbidden", 403, detail=Permission.VIEW_PURCHASE_AMOUNTS.value)


async def _detail(ctx: OrgContext, purchase_id: UUID) -> rp.PurchaseDetailOut:
    book = await rp.Book(ctx.conn, today()).load(purchase_id)
    if not book.purchases:
        raise AppError("purchase_not_found", 404)
    pending = await rp.recalc_pending(ctx.conn, purchase_id)
    return book.detail(book.purchases[0], _amounts(ctx), pending)


async def _changed(
    ctx: OrgContext,
    request: Request,
    background: BackgroundTasks,
    purchase_id: UUID,
    items: Iterable[UUID | None] = (),
) -> None:
    """Xarid o'zgardi: joriy bosqich (``status``), qayta hisob so'rovlari va (commitdan keyin) hisob ishi."""
    p = m.purchases
    row = (await ctx.conn.execute(select(p).where(p.c.id == purchase_id))).first()
    if row is not None:
        await ctx.conn.execute(
            update(p)
            .where(p.c.id == purchase_id)
            .values(status=current_stage(rp.stage_dates(row)).value, updated_at=func.now())
        )
        await calc.request(ctx.conn, ctx.org_id, calc.Scope.PURCHASE, purchase_id)
    for item in items:
        if item is not None:
            await calc.request(ctx.conn, ctx.org_id, calc.Scope.ITEM, item)
    background.add_task(_kick, request, ctx.org_id)


async def _kick(request: Request, org_id: UUID) -> None:
    """Hisob ishini navbatga qo'yish; bo'lmasa — tungi to'liq qayta qurish yoki keyingi sinxron oladi."""
    try:
        await request.app.state.jobs.defer_calc(org_id)
    except Exception as exc:
        _log.warning("calc_defer_failed", org_id=str(org_id), error_code=type(exc).__name__)


# --- O'qish -----------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/purchases", response_model=PurchasesOut)
async def list_purchases(
    ctx: Viewer, stage: Annotated[list[Stage] | None, Query()] = None
) -> PurchasesOut:
    """Xaridlar (yangisi birinchi), joriy bosqich filtri bilan; har birida Partiya yo'li va jonli tannarx."""
    book = await rp.Book(ctx.conn, today()).load()
    amounts = _amounts(ctx)
    items = []
    for purchase in book.purchases:
        out = book.summary(purchase, book.evaluate(purchase), amounts)
        if rp.matches(out.stage, stage):
            items.append(out)
    return PurchasesOut(items=items, amounts=amounts)


@router.get("/orgs/{org_id}/purchases/{purchase_id}", response_model=rp.PurchaseDetailOut)
async def get_purchase(purchase_id: UUID, ctx: Viewer) -> rp.PurchaseDetailOut:
    return await _detail(ctx, purchase_id)


@router.get("/orgs/{org_id}/suppliers", response_model=list[rp.SupplierOut])
async def list_suppliers(ctx: Viewer) -> list[rp.SupplierOut]:
    s = m.suppliers
    rows = await ctx.conn.execute(select(s).order_by(s.c.name, s.c.id))
    return [rp.SupplierOut(id=r.id, name=r.name, platform=r.platform) for r in rows]


@router.get("/orgs/{org_id}/carriers", response_model=list[rp.CarrierOut])
async def list_carriers(ctx: Viewer) -> list[rp.CarrierOut]:
    c = m.carriers
    rows = await ctx.conn.execute(select(c).order_by(c.c.name, c.c.id))
    return [rp.CarrierOut(id=r.id, name=r.name, pricing=r.pricing) for r in rows]


# --- Yetkazib beruvchi va kargo (to'liq — B5.1) -----------------------------------------------


@router.post("/orgs/{org_id}/suppliers", response_model=rp.SupplierOut, status_code=201)
async def create_supplier(body: SupplierIn, ctx: Manager) -> rp.SupplierOut:
    s = m.suppliers
    row = (
        await ctx.conn.execute(
            insert(s)
            .values(org_id=ctx.org_id, name=body.name.strip(), platform=body.platform)
            .returning(s)
        )
    ).one()
    await ctx.audit("supplier.create", "supplier", row.id, after=_plain(body.model_dump()))
    return rp.SupplierOut(id=row.id, name=row.name, platform=row.platform)


@router.post("/orgs/{org_id}/carriers", response_model=rp.CarrierOut, status_code=201)
async def create_carrier(body: CarrierIn, ctx: Manager) -> rp.CarrierOut:
    c = m.carriers
    row = (
        await ctx.conn.execute(
            insert(c)
            .values(org_id=ctx.org_id, name=body.name.strip(), pricing=body.pricing)
            .returning(c)
        )
    ).one()
    await ctx.audit("carrier.create", "carrier", row.id, after=_plain(body.model_dump()))
    return rp.CarrierOut(id=row.id, name=row.name, pricing=row.pricing)


# --- Xarid ------------------------------------------------------------------------------------


@router.post("/orgs/{org_id}/purchases", response_model=rp.PurchaseDetailOut, status_code=201)
async def create_purchase(
    body: PurchaseIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> rp.PurchaseDetailOut:
    await _exists(ctx, m.suppliers, body.supplier_id, "supplier_not_found")
    await _exists(ctx, m.carriers, body.carrier_id, "carrier_not_found")
    _check_dates(body.dates)
    p = m.purchases
    purchase_id = await ctx.conn.scalar(
        insert(p)
        .values(
            org_id=ctx.org_id,
            title=body.title,
            supplier_id=body.supplier_id,
            carrier_id=body.carrier_id,
            note=body.note,
            **_date_columns(body.dates),
        )
        .returning(p.c.id)
    )
    assert purchase_id is not None
    await ctx.audit("purchase.create", "purchase", purchase_id, after=_plain(body.model_dump()))
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)


@router.patch("/orgs/{org_id}/purchases/{purchase_id}", response_model=rp.PurchaseDetailOut)
async def update_purchase(
    purchase_id: UUID,
    body: PurchasePatch,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    row = await _purchase(ctx, purchase_id)
    values = body.model_dump(exclude_unset=True)
    dates = values.pop("dates", None) or {}
    await _exists(ctx, m.suppliers, values.get("supplier_id"), "supplier_not_found")
    await _exists(ctx, m.carriers, values.get("carrier_id"), "carrier_not_found")
    _check_dates({**rp.stage_dates(row), **dates})
    values |= _date_columns(dates)
    if not values:
        return await _detail(ctx, purchase_id)
    before = {k: getattr(row, k) for k in values}
    p = m.purchases
    await ctx.conn.execute(update(p).where(p.c.id == purchase_id).values(**values))
    await ctx.audit(
        "purchase.update", "purchase", purchase_id, before=_plain(before), after=_plain(values)
    )
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)


@router.delete("/orgs/{org_id}/purchases/{purchase_id}", status_code=204)
async def delete_purchase(
    purchase_id: UUID, ctx: Manager, request: Request, background: BackgroundTasks
) -> Response:
    row = await _purchase(ctx, purchase_id)
    pl = m.purchase_lines
    items = {
        r.item_id
        for r in await ctx.conn.execute(select(pl.c.item_id).where(pl.c.purchase_id == purchase_id))
    }
    await ctx.conn.execute(delete(m.purchases).where(m.purchases.c.id == purchase_id))
    await ctx.audit(
        "purchase.delete",
        "purchase",
        purchase_id,
        before=_plain({"title": row.title, "status": row.status, "lines": len(items)}),
    )
    await _changed(ctx, request, background, purchase_id, items)
    return Response(status_code=204)


@router.post(
    "/orgs/{org_id}/purchases/{purchase_id}/copy",
    response_model=rp.PurchaseDetailOut,
    status_code=201,
)
async def copy_purchase(
    purchase_id: UUID, ctx: Manager, request: Request, background: BackgroundTasks
) -> rp.PurchaseDetailOut:
    """ "Qayta buyurtma" (M9): sarlavha, yetkazib beruvchi, kargo va qatorlar (buyurtma donasi, narx, vazn, hajm)
    yangi qoralamaga nusxalanadi; sanalar, qabul donasi va xarajat komponentlari — yo'q (har partiyada boshqa)."""
    row = await _purchase(ctx, purchase_id)
    p, pl = m.purchases, m.purchase_lines
    new_id = await ctx.conn.scalar(
        insert(p)
        .values(
            org_id=ctx.org_id,
            title=row.title,
            supplier_id=row.supplier_id,
            carrier_id=row.carrier_id,
            note=row.note,
        )
        .returning(p.c.id)
    )
    assert new_id is not None
    keep = (
        "item_id",
        "temp_name",
        "url",
        "image_url",
        "variant",
        "ordered_qty",
        "unit_price",
        "currency",
        "unit_weight",
        "unit_volume",
    )
    lines = list(
        await ctx.conn.execute(
            select(pl).where(pl.c.purchase_id == purchase_id).order_by(pl.c.created_at, pl.c.id)
        )
    )
    if lines:
        # created_at tartibi saqlansin: bitta INSERT'da hamma qatorga bir xil vaqt tushadi — id bo'yicha emas.
        for line in lines:
            await ctx.conn.execute(
                insert(pl).values(
                    org_id=ctx.org_id,
                    purchase_id=new_id,
                    **{k: getattr(line, k) for k in keep},
                    created_at=func.clock_timestamp(),
                )
            )
    await ctx.audit(
        "purchase.copy",
        "purchase",
        new_id,
        after={"from": str(purchase_id), "lines": len(lines)},
    )
    await _changed(ctx, request, background, new_id)
    return await _detail(ctx, new_id)


# --- Qatorlar ---------------------------------------------------------------------------------


def _check_line(values: dict[str, Any]) -> None:
    if not (values.get("item_id") or (values.get("temp_name") or "").strip()):
        raise AppError("bad_line", 422, detail="tovar (item_id) yoki yangi tovar nomi kerak")
    if values.get("unit_price") is not None and values.get("currency") is None:
        raise AppError("bad_line", 422, detail="narx valyutasi kerak")


async def _check_shares_targets(
    ctx: OrgContext, purchase_id: UUID, lines: list[UUID] | None, shares: dict[Any, Any]
) -> None:
    pl = m.purchase_lines
    own = {
        r.id for r in await ctx.conn.execute(select(pl.c.id).where(pl.c.purchase_id == purchase_id))
    }
    wanted = set(lines or []) | {UUID(str(k)) for k in shares}
    if wanted - own:
        raise AppError("line_not_found", 404, detail="komponent boshqa xarid qatoriga tegishli")


@router.post(
    "/orgs/{org_id}/purchases/{purchase_id}/lines",
    response_model=rp.PurchaseDetailOut,
    status_code=201,
)
async def create_line(
    purchase_id: UUID,
    body: LineIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    await _purchase(ctx, purchase_id)
    values = body.model_dump()
    if values["unit_price"] is not None:
        _require_amounts(ctx)
    _check_line(values)
    await _exists(ctx, m.items, body.item_id, "item_not_found")
    pl = m.purchase_lines
    line_id = await ctx.conn.scalar(
        insert(pl).values(org_id=ctx.org_id, purchase_id=purchase_id, **values).returning(pl.c.id)
    )
    await ctx.audit("purchase_line.create", "purchase_line", line_id, after=_plain(values))
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)


@router.patch(
    "/orgs/{org_id}/purchases/{purchase_id}/lines/{line_id}",
    response_model=rp.PurchaseDetailOut,
)
async def update_line(
    purchase_id: UUID,
    line_id: UUID,
    body: LinePatch,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    row = await _line(ctx, purchase_id, line_id)
    values = body.model_dump(exclude_unset=True)
    if "ordered_qty" in values and values["ordered_qty"] is None:
        raise AppError("bad_line", 422, detail="ordered_qty bo'sh bo'lmaydi")
    if {"unit_price", "currency"} & set(values):
        _require_amounts(ctx)
    merged = {**row._asdict(), **values}
    _check_line(merged)
    await _exists(ctx, m.items, values.get("item_id"), "item_not_found")
    if not values:
        return await _detail(ctx, purchase_id)
    before = {k: getattr(row, k) for k in values}
    pl = m.purchase_lines
    await ctx.conn.execute(
        update(pl).where(pl.c.id == line_id).values(**values, updated_at=func.now())
    )
    await ctx.audit(
        "purchase_line.update",
        "purchase_line",
        line_id,
        before=_plain(before),
        after=_plain(values),
    )
    # Eski tovar loti qayta qurishda o'chadi va qayta hisoblanadi (``rebuild_lots``) — alohida so'rov shart emas.
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)


@router.delete(
    "/orgs/{org_id}/purchases/{purchase_id}/lines/{line_id}",
    response_model=rp.PurchaseDetailOut,
)
async def delete_line(
    purchase_id: UUID,
    line_id: UUID,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    """Qator komponentlarda alohida tanlangan bo'lsa — 409 (sotuvchi kiritgani jim o'zgartirilmaydi)."""
    row = await _line(ctx, purchase_id, line_id)
    cc = m.cost_components
    for comp in await ctx.conn.execute(select(cc).where(cc.c.purchase_id == purchase_id)):
        lines, shares = targets_of(comp.targets)
        if str(line_id) in (lines or ()) or str(line_id) in shares:
            raise AppError(
                "line_in_use",
                409,
                detail="qator xarajat komponentida tanlangan — avval o'zgartiring",
            )
    await ctx.conn.execute(delete(m.purchase_lines).where(m.purchase_lines.c.id == line_id))
    await ctx.audit(
        "purchase_line.delete",
        "purchase_line",
        line_id,
        before=_plain(
            {k: getattr(row, k) for k in ("item_id", "temp_name", "ordered_qty", "received_qty")}
        ),
    )
    await _changed(ctx, request, background, purchase_id, {row.item_id})
    return await _detail(ctx, purchase_id)


# --- Xarajat komponentlari --------------------------------------------------------------------


def _component_values(values: dict[str, Any]) -> dict[str, Any]:
    """API maydonlari → ustunlar: ``lines``/``shares`` → ``targets`` (jsonb)."""
    out = {k: v for k, v in values.items() if k not in ("lines", "shares")}
    for key in ("kind", "currency", "charged_currency", "allocation"):
        if out.get(key) is not None:
            out[key] = str(out[key].value)
    return out


def _targets(lines: list[UUID] | None, shares: dict[Any, Decimal]) -> dict[str, Any] | None:
    if lines is None and not shares:
        return None
    out: dict[str, Any] = {}
    if lines is not None:
        out["lines"] = [str(x) for x in lines]
    if shares:
        out["shares"] = {str(k): str(v) for k, v in shares.items()}
    return out


@router.post(
    "/orgs/{org_id}/purchases/{purchase_id}/components",
    response_model=rp.PurchaseDetailOut,
    status_code=201,
)
async def create_component(
    purchase_id: UUID,
    body: ComponentIn,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    _require_amounts(ctx)
    await _purchase(ctx, purchase_id)
    await _check_shares_targets(ctx, purchase_id, body.lines, body.shares)
    values = _component_values(body.model_dump())
    values["allocation"] = values["allocation"] or default_base(body.kind).value
    cc = m.cost_components
    component_id = await ctx.conn.scalar(
        insert(cc)
        .values(
            org_id=ctx.org_id,
            purchase_id=purchase_id,
            targets=_targets(body.lines, body.shares),
            **values,
        )
        .returning(cc.c.id)
    )
    await ctx.audit(
        "cost_component.create", "cost_component", component_id, after=_plain(body.model_dump())
    )
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)


@router.patch(
    "/orgs/{org_id}/purchases/{purchase_id}/components/{component_id}",
    response_model=rp.PurchaseDetailOut,
)
async def update_component(
    purchase_id: UUID,
    component_id: UUID,
    body: ComponentPatch,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    _require_amounts(ctx)
    row = await _component(ctx, purchase_id, component_id)
    values = body.model_dump(exclude_unset=True)
    for key in ("kind", "amount", "currency", "rate_mode", "allocation"):
        if key in values and values[key] is None:
            raise AppError("bad_component", 422, detail=f"{key} bo'sh bo'lmaydi")
    lines, shares = targets_of(row.targets)
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
    await _check_shares_targets(ctx, purchase_id, target_lines, new_shares)
    cols = _component_values(values)
    cols["targets"] = _targets(target_lines, new_shares)
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
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)


@router.delete(
    "/orgs/{org_id}/purchases/{purchase_id}/components/{component_id}",
    response_model=rp.PurchaseDetailOut,
)
async def delete_component(
    purchase_id: UUID,
    component_id: UUID,
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
) -> rp.PurchaseDetailOut:
    _require_amounts(ctx)
    row = await _component(ctx, purchase_id, component_id)
    await ctx.conn.execute(delete(m.cost_components).where(m.cost_components.c.id == component_id))
    await ctx.audit(
        "cost_component.delete",
        "cost_component",
        component_id,
        before=_plain({"kind": row.kind, "amount": row.amount, "currency": row.currency}),
    )
    await _changed(ctx, request, background, purchase_id)
    return await _detail(ctx, purchase_id)

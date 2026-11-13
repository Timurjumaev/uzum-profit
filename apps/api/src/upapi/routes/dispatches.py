"""``/dispatches``: Uzumga jo'natish (TM6, ADR-061 §7, ADR-050 (2)–(3); 02 M10).

Do'kon tanlanadi → shu do'konning Omborimdagi hamma SKU'lari **to'liq soni bilan** (``GET /dispatches/draft``; qatorni
olib tashlash va sonni kamaytirish mumkin) → jo'natma saqlanadi (``POST /dispatches``) va Excel Uzum kabineti
shablonida yuklab olinadi (``GET /dispatches/{id}/excel``: varaq "Товары на отправку", ustunlar ``Штрихкод товара*``,
``Себестоимость (сум)*``, ``Количество (шт)*``). Saqlangan zahoti donalar **Jo'natilmoqda** — Omborimdan band (keyingi
Excel'da chiqmaydi). Postavka Open API'da ko'ringanda o'zi bog'lanadi ("Uzumda"); bir nechta nomzod bo'lsa sotuvchi
tanlaydi (``POST /dispatches/{id}/link``). Bekor qilish — donalar Omborimga qaytadi. Postavka dasturdan yaratilmaydi
(ADR-009). Shtrix-kodi yo'q SKU Excel'ga kirmaydi — ro'yxatda alohida ko'rsatiladi.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import dispatch
from upapi.reports.xlsx import XLSX_TYPE
from upapi.routes.purchases import _amounts, _plain
from upapi.routes.warehouse import stock

router = APIRouter(tags=["inventory"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]

SHEET = "Товары на отправку"
HEADERS = ("Штрихкод товара*", "Себестоимость (сум)*", "Количество (шт)*")
INSTRUCTION = (
    "Заполните лист «Товары на отправку»: штрихкод товара, себестоимость в сумах и количество в штуках.",
    "Файл подготовлен в SellerMax — загрузите его в кабинете Uzum при создании поставки.",  # noqa: RUF001
)


class DraftRow(BaseModel):
    sku_id: UUID
    title: str | None
    product_title: str | None
    barcode: str | None
    qty: int  # Omborimdagi to'liq son
    unit_cost: Decimal | None  # F21 lot narxi (summalar ruxsati bilan)


class DraftOut(BaseModel):
    shop_id: UUID
    rows: list[DraftRow]  # shtrix-kodi bor
    no_barcode: list[DraftRow]  # Excel'ga kirmaydi


class DispatchItemIn(BaseModel):
    sku_id: UUID
    qty: Annotated[int, Field(ge=1, le=10_000_000)]


class DispatchIn(BaseModel):
    shop_id: UUID
    items: Annotated[list[DispatchItemIn], Field(min_length=1, max_length=500)]
    note: Annotated[str | None, Field(max_length=500)] = None


class DispatchItemOut(BaseModel):
    sku_id: UUID
    title: str | None
    barcode: str | None
    qty: int
    unit_cost: Decimal | None


class InvoiceOut(BaseModel):
    id: UUID
    number: int | None
    status: str | None
    created_on: datetime | None
    accepted: int | None


class DispatchOut(BaseModel):
    id: UUID
    shop_id: UUID
    shop: str | None
    status: str  # sending / linked / canceled
    exported_at: datetime
    linked_at: datetime | None
    canceled_at: datetime | None
    note: str | None
    units: int
    items: list[DispatchItemOut]
    invoice: InvoiceOut | None
    candidates: list[InvoiceOut]  # bir nechta mos postavka — sotuvchi tanlaydi


class DispatchesOut(BaseModel):
    items: list[DispatchOut]


class LinkIn(BaseModel):
    invoice_id: UUID | None  # ``null`` — bog'lanishni olib tashlash (yana Jo'natilmoqda)


def _invoice(r: Any) -> InvoiceOut:
    return InvoiceOut(
        id=r.id, number=r.number, status=r.status, created_on=r.created_on, accepted=r.accepted
    )


async def _dispatches(ctx: OrgContext, only: UUID | None = None) -> list[DispatchOut]:
    d, di, v, sh = m.fbo_dispatches, m.fbo_dispatch_items, m.fbo_invoices, m.shops
    amounts = _amounts(ctx)
    query = select(d).order_by(d.c.exported_at.desc(), d.c.id)
    if only is not None:
        query = query.where(d.c.id == only)
    rows = list(await ctx.conn.execute(query))
    if not rows:
        return []
    ids = [r.id for r in rows]
    items: dict[UUID, list[Any]] = {}
    for r in await ctx.conn.execute(
        select(di).where(di.c.dispatch_id.in_(ids)).order_by(di.c.created_at, di.c.id)
    ):
        items.setdefault(r.dispatch_id, []).append(r)
    from upapi.reports.common import sku_catalog

    catalog = await sku_catalog(ctx.conn, ids=list({x.sku_id for xs in items.values() for x in xs}))
    shops = {r.id: r.name for r in await ctx.conn.execute(select(sh.c.id, sh.c.name))}
    invoices = {
        r.id: r
        for r in await ctx.conn.execute(
            select(v).where(v.c.id.in_([r.invoice_id for r in rows if r.invoice_id]))
        )
    }
    found = await dispatch.candidates(ctx.conn)
    return [
        DispatchOut(
            id=r.id,
            shop_id=r.shop_id,
            shop=shops.get(r.shop_id),
            status=r.status,
            exported_at=r.exported_at,
            linked_at=r.linked_at,
            canceled_at=r.canceled_at,
            note=r.note,
            units=sum(x.qty for x in items.get(r.id, [])),
            items=[
                DispatchItemOut(
                    sku_id=x.sku_id,
                    title=catalog[x.sku_id].title if x.sku_id in catalog else None,
                    barcode=x.barcode,
                    qty=x.qty,
                    unit_cost=x.unit_cost if amounts else None,
                )
                for x in items.get(r.id, [])
            ],
            invoice=_invoice(invoices[r.invoice_id]) if r.invoice_id in invoices else None,
            candidates=[_invoice(x) for x in found.get(r.id, [])] if r.status == "sending" else [],
        )
        for r in rows
    ]


async def _shop(ctx: OrgContext, shop_id: UUID) -> None:
    if await ctx.conn.scalar(select(m.shops.c.id).where(m.shops.c.id == shop_id)) is None:
        raise AppError("shop_not_found", 404)


async def _draft(ctx: OrgContext, shop_id: UUID, amounts: bool) -> DraftOut:
    current = await stock(ctx, amounts)
    rows: list[DraftRow] = []
    missing: list[DraftRow] = []
    for r in current.items:
        if r.sku_id is None or r.shop_id != shop_id or r.qty <= 0:
            continue
        row = DraftRow(
            sku_id=r.sku_id,
            title=r.title,
            product_title=r.product_title,
            barcode=r.barcode,
            qty=r.qty,
            unit_cost=r.unit_cost,
        )
        (rows if r.barcode else missing).append(row)
    return DraftOut(shop_id=shop_id, rows=rows, no_barcode=missing)


@router.get("/orgs/{org_id}/dispatches/draft", response_model=DraftOut)
async def dispatch_draft(ctx: Manager, shop_id: Annotated[UUID, Query()]) -> DraftOut:
    """Yangi jo'natma: do'konning Omborimdagi hamma SKU'lari to'liq soni bilan (jo'natmalarda band donalar — ayirilgan)."""
    await _shop(ctx, shop_id)
    return await _draft(ctx, shop_id, _amounts(ctx))


@router.post("/orgs/{org_id}/dispatches", response_model=DispatchOut, status_code=201)
async def create_dispatch(body: DispatchIn, ctx: Manager) -> DispatchOut:
    """Jo'natma: donalar darhol "Jo'natilmoqda" — Omborimdan band (keyingi Excel'da chiqmaydi)."""
    await _shop(ctx, body.shop_id)
    draft = await _draft(
        ctx, body.shop_id, True
    )  # Excel'dagi tannarx — summalar ruxsatisiz rolda ham
    available = {r.sku_id: r for r in draft.rows}
    missing = {r.sku_id for r in draft.no_barcode}
    seen: set[UUID] = set()
    for x in body.items:
        if x.sku_id in seen:
            raise AppError("bad_dispatch", 422, detail="SKU takrorlangan")
        seen.add(x.sku_id)
        if x.sku_id in missing:
            raise AppError("no_barcode", 422, detail="SKU'da shtrix-kod yo'q — Excel'ga kirmaydi")
        if x.sku_id not in available:
            raise AppError("bad_dispatch", 422, detail="SKU shu do'konning Omborimida yo'q")
        if x.qty > available[x.sku_id].qty:
            raise AppError(
                "bad_dispatch", 422, detail=f"Omborimda {available[x.sku_id].qty} dona bor"
            )
    d, di = m.fbo_dispatches, m.fbo_dispatch_items
    costs = {r.sku_id: r.unit_cost for r in draft.rows}
    dispatch_id = await ctx.conn.scalar(
        insert(d).values(org_id=ctx.org_id, shop_id=body.shop_id, note=body.note).returning(d.c.id)
    )
    for x in body.items:
        await ctx.conn.execute(
            insert(di).values(
                org_id=ctx.org_id,
                dispatch_id=dispatch_id,
                sku_id=x.sku_id,
                qty=x.qty,
                unit_cost=costs.get(x.sku_id),
                barcode=available[x.sku_id].barcode,
            )
        )
    await ctx.audit("dispatch.create", "dispatch", dispatch_id, after=_plain(body.model_dump()))
    return (await _dispatches(ctx, dispatch_id))[0]


@router.get("/orgs/{org_id}/dispatches", response_model=DispatchesOut)
async def list_dispatches(ctx: Viewer) -> DispatchesOut:
    """Jo'natmalar (yangisi birinchi): holat, tarkib, bog'langan postavka va nomzodlar. O'qishdan oldin postavkalar bilan
    solishtiriladi (bog'lash, bekor qilingan postavka)."""
    await dispatch.reconcile(ctx.conn, datetime.now(UTC))
    return DispatchesOut(items=await _dispatches(ctx))


async def _row(ctx: OrgContext, dispatch_id: UUID) -> Any:
    d = m.fbo_dispatches
    row = (await ctx.conn.execute(select(d).where(d.c.id == dispatch_id))).first()
    if row is None:
        raise AppError("dispatch_not_found", 404)
    return row


@router.get("/orgs/{org_id}/dispatches/{dispatch_id}/excel")
async def dispatch_excel(dispatch_id: UUID, ctx: Manager) -> Response:
    """Excel Uzum kabineti shablonida (ADR-050 (2)): "Инструкция" va "Товары на отправку"."""
    row = await _row(ctx, dispatch_id)
    di = m.fbo_dispatch_items
    items = list(
        await ctx.conn.execute(
            select(di).where(di.c.dispatch_id == dispatch_id).order_by(di.c.created_at, di.c.id)
        )
    )
    wb = Workbook()
    info = wb.active
    assert info is not None
    info.title = "Инструкция"
    for i, text in enumerate(INSTRUCTION, start=1):
        info.cell(row=i, column=1, value=text)
    sheet = wb.create_sheet(SHEET)
    for col, title in enumerate(HEADERS, start=1):
        sheet.cell(row=1, column=col, value=title).font = Font(bold=True)
    for i, x in enumerate(items, start=2):
        sheet.cell(row=i, column=1, value=x.barcode)
        sheet.cell(
            row=i,
            column=2,
            value=int(x.unit_cost.to_integral_value()) if x.unit_cost is not None else 0,
        )
        sheet.cell(row=i, column=3, value=x.qty)
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 22
    sheet.column_dimensions["C"].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    day = row.exported_at.astimezone(UTC).date().isoformat()
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="uzum-jonatma-{day}.xlsx"'},
    )


@router.post("/orgs/{org_id}/dispatches/{dispatch_id}/cancel", response_model=DispatchOut)
async def cancel_dispatch(dispatch_id: UUID, ctx: Manager) -> DispatchOut:
    """Bekor qilish (Jo'natilmoqda yoki bog'langan — postavka bekor bo'lganda): donalar Omborimga qaytadi."""
    row = await _row(ctx, dispatch_id)
    if row.status == "canceled":
        return (await _dispatches(ctx, dispatch_id))[0]
    d = m.fbo_dispatches
    await ctx.conn.execute(
        update(d)
        .where(d.c.id == dispatch_id)
        .values(status="canceled", canceled_at=datetime.now(UTC), updated_at=func.now())
    )
    await ctx.audit("dispatch.cancel", "dispatch", dispatch_id, before={"status": row.status})
    return (await _dispatches(ctx, dispatch_id))[0]


@router.post("/orgs/{org_id}/dispatches/{dispatch_id}/link", response_model=DispatchOut)
async def link_dispatch(dispatch_id: UUID, body: LinkIn, ctx: Manager) -> DispatchOut:
    """Postavkani qo'lda tanlash (bir nechta nomzod bo'lganda) yoki bog'lanishni olib tashlash. Postavka shu do'konniki va
    boshqa faol jo'natmaga bog'lanmagan bo'lishi shart."""
    row = await _row(ctx, dispatch_id)
    if row.status == "canceled":
        raise AppError("bad_dispatch", 409, detail="bekor qilingan jo'natma")
    d, v = m.fbo_dispatches, m.fbo_invoices
    values: dict[str, Any]
    if body.invoice_id is None:
        values = {"status": "sending", "invoice_id": None, "linked_at": None}
    else:
        inv = (await ctx.conn.execute(select(v).where(v.c.id == body.invoice_id))).first()
        if inv is None or inv.shop_id != row.shop_id:
            raise AppError("invoice_not_found", 404)
        taken = await ctx.conn.scalar(
            select(d.c.id).where(
                d.c.invoice_id == body.invoice_id, d.c.status == "linked", d.c.id != dispatch_id
            )
        )
        if taken is not None:
            raise AppError("bad_dispatch", 409, detail="postavka boshqa jo'natmaga bog'langan")
        values = {"status": "linked", "invoice_id": inv.id, "linked_at": datetime.now(UTC)}
    await ctx.conn.execute(
        update(d).where(d.c.id == dispatch_id).values(**values, updated_at=func.now())
    )
    await ctx.audit(
        "dispatch.link", "dispatch", dispatch_id, after=_plain({"invoice_id": body.invoice_id})
    )
    return (await _dispatches(ctx, dispatch_id))[0]

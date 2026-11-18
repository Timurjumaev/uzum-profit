"""Postavka ↔ jo'natma har qanday yo'lda (TM9.1, ADR-068 (1); 02 M10).

- **Tenglashtirish** (:func:`equalize`): bog'langan jo'natma tarkibi postavkada **e'lon qilingan** songa
  (``quantityToStock``) tenglashadi — kabinetda son kamaytirilgan bo'lsa ortig'i Omborimga qaytadi, postavkada bor,
  jo'natmada yo'q SKU qo'shiladi (Omborimda bo'lsa, bor qadar). Postavka qabul qilingunga qadar har solishtirishda
  (kabinetda keyin o'zgartirilsa ham); qabul qilingach — qotadi (farq — TM9.2). O'zgarishlar ``adjustments`` da
  sotuvchiga ko'rsatiladi.
- **Jo'natmasiz postavka** (:func:`orphans`): dasturdagi Excel'siz, kabinetda to'g'ridan-to'g'ri yaratilgan postavka —
  Omborimdagi SKU'lari bor, hech bir jo'natmaga bog'lanmagan va sotuvchi "Omborimdan emas" demagan. "Diqqat"da chiqadi;
  bir bosishda "Omborimdan ketgan" (:func:`from_invoice` — postavka tarkibidan jo'natma) yoki "Omborimdan emas".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from upapi.calc.costs import arrival_day
from upapi.db import models as m
from upapi.reports import dispatch, integrity


async def sync(conn: AsyncConnection, now: datetime) -> None:
    """Jo'natmalar va postavkalarni solishtirish: bog'lash / bekor (``dispatch.reconcile``), keyin tenglashtirish."""
    await dispatch.reconcile(conn, now)
    await equalize(conn)


async def declared(conn: AsyncConnection, invoice_ids: list[UUID]) -> dict[UUID, dict[UUID, int]]:
    """Postavka → SKU → e'lon qilingan dona (``quantity_to_stock``; SKU'ga bog'lanmagan qatorlar — yo'q)."""
    vi = m.fbo_invoice_items
    out: dict[UUID, dict[UUID, int]] = {}
    if not invoice_ids:
        return out
    for r in await conn.execute(
        select(vi.c.invoice_id, vi.c.sku_id, func.sum(vi.c.quantity_to_stock).label("qty"))
        .where(vi.c.invoice_id.in_(invoice_ids), vi.c.sku_id.is_not(None))
        .group_by(vi.c.invoice_id, vi.c.sku_id)
    ):
        out.setdefault(r.invoice_id, {})[r.sku_id] = int(r.qty or 0)
    return out


async def unit_costs(conn: AsyncConnection, book: integrity.Ledger) -> dict[UUID, Decimal]:
    """SKU → Omborimdagi donalarning o'rtacha lot tannarxi (F21; jo'natma qatorining tannarxi, F52 uchun ham)."""
    lots = m.lots
    ids = list(book.lines)
    if not ids:
        return {}
    cost = {
        r.purchase_line_id: r.unit_cost
        for r in await conn.execute(
            select(lots.c.purchase_line_id, lots.c.unit_cost).where(
                lots.c.purchase_line_id.in_(ids)
            )
        )
    }
    acc: dict[UUID, tuple[int, Decimal]] = {}
    for lid, use in book.lines.items():
        sku = use.line.sku_id
        left = use.good - use.used
        if sku is None or left <= 0 or cost.get(lid) is None:
            continue
        qty, total = acc.get(sku, (0, Decimal(0)))
        acc[sku] = (qty + left, total + left * cost[lid])
    return {
        sku: (total / qty).quantize(Decimal("0.01")) for sku, (qty, total) in acc.items() if qty
    }


def _available(book: integrity.Ledger, sku_id: UUID) -> int:
    b = book.balances.get(integrity.key_of(sku_id, None))
    return max(b.on_hand, 0) if b is not None else 0


async def equalize(conn: AsyncConnection) -> None:
    """Bog'langan, postavkasi hali qabul qilinmagan jo'natmalar tarkibini e'lon qilingan songa tenglashtirish
    (idempotent)."""
    d, di, v = m.fbo_dispatches, m.fbo_dispatch_items, m.fbo_invoices
    rows = [
        r
        for r in await conn.execute(
            select(d, v.c.status.label("inv_status"), v.c.created_on, v.c.raw)
            .join(v, v.c.id == d.c.invoice_id)
            .where(d.c.status == "linked")
        )
        if arrival_day(r.inv_status, r.created_on, r.raw) is None
    ]
    if not rows:
        return
    want = await declared(conn, [r.invoice_id for r in rows])
    items: dict[UUID, dict[UUID, Any]] = {}
    for x in await conn.execute(select(di).where(di.c.dispatch_id.in_([r.id for r in rows]))):
        items.setdefault(x.dispatch_id, {})[x.sku_id] = x
    book: integrity.Ledger | None = None
    costs: dict[UUID, Decimal] = {}
    for r in rows:
        declared_qty = want.get(r.invoice_id, {})
        if not declared_qty:
            continue  # postavka tarkibi hali yuklanmagan — tegilmaydi
        have = items.get(r.id, {})
        changes = []
        for sku in sorted({*have, *declared_qty}, key=str):
            target = declared_qty.get(sku, 0)
            current = have[sku].qty if sku in have else 0
            if target == current:
                continue
            new = target
            if target > current:
                if book is None:
                    book = await integrity.ledger(conn)
                    costs = await unit_costs(conn, book)
                new = current + min(target - current, _available(book, sku))
                if new == current:
                    continue
            changes.append((sku, current, new, target))
        if not changes:
            continue
        log = {str(a["sku_id"]): a for a in (r.adjustments or [])}
        for sku, current, new, target in changes:
            if sku in have and new == 0:
                await conn.execute(di.delete().where(di.c.id == have[sku].id))
            elif sku in have:
                await conn.execute(
                    update(di).where(di.c.id == have[sku].id).values(qty=new, updated_at=func.now())
                )
            else:
                await conn.execute(
                    insert(di).values(
                        org_id=r.org_id,
                        dispatch_id=r.id,
                        sku_id=sku,
                        qty=new,
                        unit_cost=costs.get(sku),
                    )
                )
            first = log.get(str(sku), {}).get("before", current)
            log[str(sku)] = {"sku_id": str(sku), "before": first, "after": new, "declared": target}
        await conn.execute(
            update(d)
            .where(d.c.id == r.id)
            .values(adjustments=list(log.values()), updated_at=func.now())
        )
        if book is not None:
            book = await integrity.ledger(conn)  # keyingi jo'natma yangilangan qoldiq bilan


@dataclass
class Orphan:
    """Jo'natmasiz postavka: SKU → e'lon qilingan dona va Omborimdagi bor dona."""

    invoice: Any
    accepted_on: Any
    items: dict[UUID, int] = field(default_factory=dict)
    available: dict[UUID, int] = field(default_factory=dict)


async def orphans(conn: AsyncConnection) -> list[Orphan]:
    """Dasturdan tashqari postavkalar (TM9.1 (a)): bekor emas, faol jo'natmaga bog'lanmagan, "Omborimdan emas" deb
    belgilanmagan, kutilayotgan jo'natmaning nomzodi emas; Omborim davridan keyin (eng birinchi sanash kunidan) yaratilgan
    va kamida bitta SKU'si Omborimda sanalgan. Qabul qilinganlari ham (Omborim ortiqcha ko'rinmasin)."""
    book = await integrity.ledger(conn)
    counted = [p.received_on for p in book.purchases.values() if p.received_on is not None]
    if not counted:
        return []
    start = min(counted)
    skus = {b.sku_id for b in book.balances.values() if b.sku_id is not None}
    v = m.fbo_invoices
    skip = await dispatch.linked_invoices(conn)
    for found in (await dispatch.candidates(conn)).values():
        skip |= {c.id for c in found}
    rows = [
        r
        for r in await conn.execute(select(v).order_by(v.c.created_on.desc().nulls_last()))
        if r.id not in skip
        and not dispatch._is_canceled(r.status)
        and r.created_on is not None
        and r.created_on.date() >= start
    ]
    if not rows:
        return []
    want = await declared(conn, [r.id for r in rows])
    out = []
    for r in rows:
        items = want.get(r.id, {})
        if not set(items) & skus:
            continue
        out.append(
            Orphan(
                invoice=r,
                accepted_on=arrival_day(r.status, r.created_on, r.raw),
                items=items,
                available={sku: _available(book, sku) for sku in items},
            )
        )
    return out


async def from_invoice(conn: AsyncConnection, org_id: UUID, invoice: Any, now: datetime) -> UUID:
    """ "Bu postavka Omborimdan ketgan" (TM9.1 (a)): postavka tarkibidan bog'langan jo'natma — e'lon qilingan dona Omborimdan
    chiqadi (bor qadar; yetmagani ``adjustments`` da ko'rsatiladi)."""
    book = await integrity.ledger(conn)
    costs = await unit_costs(conn, book)
    want = (await declared(conn, [invoice.id])).get(invoice.id, {})
    d, di = m.fbo_dispatches, m.fbo_dispatch_items
    dispatch_id: UUID = await conn.scalar(
        insert(d)
        .values(
            org_id=org_id,
            shop_id=invoice.shop_id,
            status="linked",
            invoice_id=invoice.id,
            exported_at=invoice.created_on or now,
            linked_at=now,
            origin="invoice",
        )
        .returning(d.c.id)
    )
    log = []
    for sku, target in sorted(want.items(), key=lambda x: str(x[0])):
        qty = min(target, _available(book, sku))
        if qty > 0:
            k = m.mp_skus
            barcode = await conn.scalar(select(k.c.barcode).where(k.c.id == sku))
            await conn.execute(
                insert(di).values(
                    org_id=org_id,
                    dispatch_id=dispatch_id,
                    sku_id=sku,
                    qty=qty,
                    unit_cost=costs.get(sku),
                    barcode=barcode,
                )
            )
        if qty != target:
            log.append({"sku_id": str(sku), "before": target, "after": qty, "declared": target})
    if log:
        await conn.execute(update(d).where(d.c.id == dispatch_id).values(adjustments=log))
    return dispatch_id

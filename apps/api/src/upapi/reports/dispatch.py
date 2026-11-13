"""Uzumga jo'natma: band qilish, postavka bilan bog'lash va partiyalarga bog'lash (TM6, ADR-061 §7, ADR-050 (3)).

- **Band qilish:** ``sending`` (Excel chiqarilgan, postavka hali API'da yo'q) va ``linked`` (postavka bilan bog'langan)
  jo'natmalar tarkibi Omborimdan ayiriladi; bekor qilingani qaytadi.
- **Bog'lash (``reconcile``):** postavka Open API'da ko'ringanda (o'sha do'kon, Excel'dan keyin yaratilgan, SKU to'plami bir
  xil, boshqa jo'natmaga bog'lanmagan, bekor emas) — yagona nomzod bo'lsa o'zi bog'lanadi; bir nechta bo'lsa sotuvchi
  tanlaydi. Bog'langan postavka bekor qilinsa — jo'natma bekor, donalar Omborimga qaytadi.
- **Partiyalarga bog'lash (``attribute``):** jo'natilgan donalar SKU bo'yicha eng eski sanalgan qatorlardan yeyiladi (FIFO,
  ``upcore.purchasing.fifo_attribute``) — xaridda "60 Uzumda · 40 Omborimda", hammasi bog'langanda holat "Uzumda".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import TASHKENT
from upcore.purchasing import SupplyState, fifo_attribute, supply_state

from upapi.db import models as m

ACTIVE = ("sending", "linked")
CANCELED_INVOICES = frozenset({"CANCELED", "CANCELLED", "REJECTED", "DELETED"})
MATCH_SLACK = timedelta(
    days=1
)  # postavka Excel'dan biroz oldin yaratilgan bo'lishi mumkin (soat mintaqasi, qo'lda)


@dataclass
class LineDispatch:
    """Qatorning jo'natma bo'yicha holati: ``sending`` — Jo'natilmoqda, ``linked`` — Uzumda (``linked_on`` — eng oxirgi
    bog'langan kun)."""

    sending: int = 0
    linked: int = 0
    linked_on: date | None = None


def _is_canceled(status: str | None) -> bool:
    return (status or "").upper() in CANCELED_INVOICES


async def candidates(conn: AsyncConnection) -> dict[UUID, list[Any]]:
    """``sending`` jo'natma → mos postavkalar (yangisi birinchi)."""
    d, di, v, vi = m.fbo_dispatches, m.fbo_dispatch_items, m.fbo_invoices, m.fbo_invoice_items
    pending = list(await conn.execute(select(d).where(d.c.status == "sending")))
    if not pending:
        return {}
    taken = {
        r.invoice_id
        for r in await conn.execute(
            select(d.c.invoice_id).where(d.c.status == "linked", d.c.invoice_id.is_not(None))
        )
    }
    skus: dict[UUID, set[UUID]] = {}
    for r in await conn.execute(
        select(di.c.dispatch_id, di.c.sku_id).where(di.c.dispatch_id.in_([x.id for x in pending]))
    ):
        skus.setdefault(r.dispatch_id, set()).add(r.sku_id)
    shops = {x.shop_id for x in pending}
    invoices = [
        r
        for r in await conn.execute(
            select(v).where(v.c.shop_id.in_(shops)).order_by(v.c.created_on.desc().nulls_last())
        )
        if r.id not in taken and not _is_canceled(r.status)
    ]
    inv_skus: dict[UUID, set[UUID]] = {}
    if invoices:
        for r in await conn.execute(
            select(vi.c.invoice_id, vi.c.sku_id).where(
                vi.c.invoice_id.in_([x.id for x in invoices]), vi.c.sku_id.is_not(None)
            )
        ):
            inv_skus.setdefault(r.invoice_id, set()).add(r.sku_id)
    out: dict[UUID, list[Any]] = {}
    for x in pending:
        want = skus.get(x.id, set())
        out[x.id] = [
            inv
            for inv in invoices
            if inv.shop_id == x.shop_id
            and (inv.created_on is None or inv.created_on >= x.exported_at - MATCH_SLACK)
            and want
            and inv_skus.get(inv.id, set()) == want
        ]
    return out


async def reconcile(conn: AsyncConnection, now: datetime) -> None:
    """Postavka holatiga qarab jo'natmalarni yangilash (idempotent): bekor qilingan postavka — jo'natma bekor; yagona mos
    postavka — bog'lanadi (bir postavka bitta jo'natmaga)."""
    d, v = m.fbo_dispatches, m.fbo_invoices
    for r in await conn.execute(
        select(d.c.id, v.c.status).join(v, v.c.id == d.c.invoice_id).where(d.c.status == "linked")
    ):
        if _is_canceled(r.status):
            await conn.execute(
                update(d)
                .where(d.c.id == r.id)
                .values(status="canceled", canceled_at=now, updated_at=func.now())
            )
    used: set[UUID] = set()
    for dispatch_id, found in (await candidates(conn)).items():
        free = [x for x in found if x.id not in used]
        if len(free) == 1:
            used.add(free[0].id)
            await conn.execute(
                update(d)
                .where(d.c.id == dispatch_id, d.c.status == "sending")
                .values(
                    status="linked", invoice_id=free[0].id, linked_at=now, updated_at=func.now()
                )
            )


async def held(conn: AsyncConnection) -> dict[UUID, int]:
    """SKU → faol jo'natmalardagi (Jo'natilmoqda + Uzumda) dona — Omborimdan ayiriladi."""
    d, di = m.fbo_dispatches, m.fbo_dispatch_items
    rows = await conn.execute(
        select(di.c.sku_id, func.sum(di.c.qty).label("qty"))
        .join(d, d.c.id == di.c.dispatch_id)
        .where(d.c.status.in_(ACTIVE))
        .group_by(di.c.sku_id)
    )
    return {r.sku_id: int(r.qty) for r in rows}


async def linked_invoices(conn: AsyncConnection) -> set[UUID]:
    """Faol jo'natmaga bog'langan postavkalar — ADR-034 "postavkada" ajratmasi ular uchun ikki marta ayirilmaydi."""
    d = m.fbo_dispatches
    return {
        r.invoice_id
        for r in await conn.execute(
            select(d.c.invoice_id).where(d.c.status.in_(ACTIVE), d.c.invoice_id.is_not(None))
        )
    }


async def attribute(
    conn: AsyncConnection,
    lines: Iterable[Any],
    counted: Mapping[UUID, Any],
    moved_out: Mapping[UUID, int],
) -> dict[UUID, LineDispatch]:
    """Jo'natilgan donalarni sanalgan qatorlarga FIFO bog'lash: ``lines`` — sanalgan xaridlar qatorlari (``sku_id`` bor),
    ``counted`` — xarid id → xarid qatori (``received_on`` — tartib uchun), ``moved_out`` — qatordan boshqa SKU'ga
    o'tkazilgan dona. Avval bog'langan (Uzumda), keyin Jo'natilmoqda donalar."""
    d, di = m.fbo_dispatches, m.fbo_dispatch_items
    demand: dict[UUID, dict[str, int]] = {}
    linked_on: dict[UUID, date] = {}
    for r in await conn.execute(
        select(di.c.sku_id, d.c.status, d.c.linked_at, di.c.qty)
        .join(d, d.c.id == di.c.dispatch_id)
        .where(d.c.status.in_(ACTIVE))
    ):
        bucket = demand.setdefault(r.sku_id, {"linked": 0, "sending": 0})
        bucket[r.status] += int(r.qty)
        if r.status == "linked" and r.linked_at is not None:
            day = r.linked_at.astimezone(TASHKENT).date()
            linked_on[r.sku_id] = max(linked_on.get(r.sku_id, day), day)
    if not demand:
        return {}
    by_sku: dict[UUID, list[Any]] = {}
    for line in lines:
        if line.sku_id is not None and line.sku_id in demand:
            by_sku.setdefault(line.sku_id, []).append(line)
    out: dict[UUID, LineDispatch] = {}
    for sku_id, rows in by_sku.items():
        rows.sort(
            key=lambda x: (counted[x.purchase_id].received_on or date.max, x.created_at, str(x.id))
        )
        stock = [(str(x.id), available(x, moved_out.get(x.id, 0))) for x in rows]
        linked = fifo_attribute(stock, demand[sku_id]["linked"])
        rest = [(lid, qty - linked.get(lid, 0)) for lid, qty in stock]
        sending = fifo_attribute(rest, demand[sku_id]["sending"])
        for lid in {*linked, *sending}:
            out[UUID(lid)] = LineDispatch(
                sending=sending.get(lid, 0),
                linked=linked.get(lid, 0),
                linked_on=linked_on.get(sku_id) if lid in linked else None,
            )
    return out


def available(line: Any, moved_out: int = 0) -> int:
    """Qatorning omborimdagi donasi: sog' dona (kelgan − brak) − boshqa SKU'ga o'tkazilgani."""
    arrived: int = line.received_qty if line.received_qty is not None else line.ordered_qty
    return arrived - int(line.defect_qty) - moved_out


async def line_states(conn: AsyncConnection) -> dict[UUID, LineDispatch]:
    """Hamma sanalgan ("Omborimda") xaridlar qatorlari bo'yicha jo'natma holati (FIFO, :func:`attribute`)."""
    from upapi.reports.purchases import stage_dates

    d = m.fbo_dispatches
    if await conn.scalar(select(d.c.id).where(d.c.status.in_(ACTIVE)).limit(1)) is None:
        return {}
    p, pl = m.purchases, m.purchase_lines
    counted = {
        r.id: r
        for r in await conn.execute(select(p).where(p.c.received_on.is_not(None)))
        if supply_state(stage_dates(r)) is SupplyState.IN_STOCK
    }
    if not counted:
        return {}
    lines = list(await conn.execute(select(pl).where(pl.c.purchase_id.in_(list(counted)))))
    moved_out: dict[UUID, int] = {}
    for r in lines:
        if r.source_line_id is not None:
            moved_out[r.source_line_id] = moved_out.get(r.source_line_id, 0) + available(r)
    return await attribute(conn, lines, counted, moved_out)

"""Uzum qabulidagi farq (TM7, ADR-061 §8; 02 M10, F33, F52).

Postavka yakuniy qabul qilinganda (``ACCEPTED``, ADR-055/056 — ``arrival_day``) jo'natilgan (``fbo_dispatch_items``) va
qabul qilingan (``fbo_invoice_items.quantity_accepted``) dona SKU bo'yicha solishtiriladi. Farq bo'lsa sotuvchi qaror
qiladi (``receiving_diffs``); qarorsiz farqlar va ochiq kamomadlar bosh sahifa "Diqqat" blokida sanaladi. Bog'liq
``C000007`` (qabul kamomadi jarimasi) xarajatlari postavka qabul qilingan kun atrofidan ko'rsatiladi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from upapi.calc.costs import arrival_day
from upapi.db import models as m

FINE_CODE = "C000007"
FINE_WINDOW = (timedelta(days=-3), timedelta(days=45))


@dataclass
class Diff:
    dispatch_id: UUID
    shop_id: UUID
    invoice_id: UUID
    invoice_number: int | None
    accepted_on: date
    sku_id: UUID
    shipped: int
    accepted: int
    unit_cost: Decimal | None
    resolution: Any = None  # ``receiving_diffs`` qatori
    fines: list[tuple[date, Decimal]] = field(default_factory=list)

    @property
    def diff(self) -> int:
        return self.accepted - self.shipped


async def diffs(conn: AsyncConnection) -> list[Diff]:
    """Qabul qilingan postavkaga bog'langan jo'natmalar bo'yicha farqlar (farq bor yoki qaror yozilgan)."""
    d, di, v, vi, rd = (
        m.fbo_dispatches,
        m.fbo_dispatch_items,
        m.fbo_invoices,
        m.fbo_invoice_items,
        m.receiving_diffs,
    )
    rows = list(
        await conn.execute(
            select(
                d.c.id,
                d.c.shop_id,
                v.c.id.label("invoice_id"),
                v.c.number,
                v.c.status,
                v.c.created_on,
                v.c.raw,
            )
            .join(v, v.c.id == d.c.invoice_id)
            .where(d.c.status == "linked")
        )
    )
    accepted_rows: list[tuple[Any, date]] = []
    for r in rows:
        day = arrival_day(r.status, r.created_on, r.raw)
        if day is not None:
            accepted_rows.append((r, day))
    if not accepted_rows:
        return []
    ids = [r.id for r, _ in accepted_rows]
    shipped: dict[tuple[UUID, UUID], tuple[int, Decimal | None]] = {}
    for x in await conn.execute(select(di).where(di.c.dispatch_id.in_(ids))):
        qty, cost = shipped.get((x.dispatch_id, x.sku_id), (0, x.unit_cost))
        shipped[(x.dispatch_id, x.sku_id)] = (qty + x.qty, cost)
    accepted: dict[tuple[UUID, UUID], int] = {}
    for x in await conn.execute(
        select(vi.c.invoice_id, vi.c.sku_id, func.sum(vi.c.quantity_accepted).label("qty"))
        .where(
            vi.c.invoice_id.in_([r.invoice_id for r, _ in accepted_rows]), vi.c.sku_id.is_not(None)
        )
        .group_by(vi.c.invoice_id, vi.c.sku_id)
    ):
        accepted[(x.invoice_id, x.sku_id)] = int(x.qty or 0)
    decided = {
        (x.dispatch_id, x.sku_id): x
        for x in await conn.execute(select(rd).where(rd.c.dispatch_id.in_(ids)))
    }
    fines = await _fines(conn, {r.shop_id for r, _ in accepted_rows})
    out: list[Diff] = []
    for r, day in accepted_rows:
        skus = {s for (did, s) in shipped if did == r.id} | {
            s for (inv, s) in accepted if inv == r.invoice_id
        }
        near = [
            (f_day, amount)
            for shop, f_day, amount in fines
            if shop == r.shop_id and day + FINE_WINDOW[0] <= f_day <= day + FINE_WINDOW[1]
        ]
        for sku in skus:
            qty, cost = shipped.get((r.id, sku), (0, None))
            got = accepted.get((r.invoice_id, sku), 0)
            row = decided.get((r.id, sku))
            if got == qty and row is None:
                continue
            out.append(
                Diff(
                    dispatch_id=r.id,
                    shop_id=r.shop_id,
                    invoice_id=r.invoice_id,
                    invoice_number=r.number,
                    accepted_on=day,
                    sku_id=sku,
                    shipped=qty,
                    accepted=got,
                    unit_cost=cost,
                    resolution=row,
                    fines=near,
                )
            )
    out.sort(key=lambda x: (x.resolution is not None, x.accepted_on, str(x.sku_id)))
    return out


async def _fines(conn: AsyncConnection, shops: set[UUID]) -> list[tuple[UUID, date, Decimal]]:
    from upcore.metrics import business_date

    e = m.mp_expenses
    rows = await conn.execute(
        select(e.c.shop_id, e.c.created_on, e.c.amount).where(
            e.c.shop_id.in_(shops), e.c.code == FINE_CODE
        )
    )
    return [(r.shop_id, business_date(r.created_on), r.amount) for r in rows]


async def attention(conn: AsyncConnection) -> int:
    """ "Diqqat" bloki: qarorsiz farqlar + ochiq kamomadlar ("Uzum yo'qotdi", hali yopilmagan)."""
    rd = m.receiving_diffs
    open_lost = int(
        await conn.scalar(
            select(func.count())
            .select_from(rd)
            .where(rd.c.resolution == "lost", rd.c.status == "open")
        )
        or 0
    )
    pending = sum(1 for x in await diffs(conn) if x.resolution is None)
    return open_lost + pending

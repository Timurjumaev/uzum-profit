"""Uzum qabulidagi farq (TM7, ADR-061 §8; TM9.2, ADR-068 (2); 02 M10, F33, F52).

Farq = postavkada **e'lon qilingan** (``fbo_invoice_items.quantity_to_stock``) − **qabul qilingan**
(``quantity_accepted``), SKU bo'yicha (F33) — Excel'dagi son emas: kabinetda son o'zgartirilgan bo'lsa ham to'g'ri.
Postavkada e'lon yo'q SKU uchun — jo'natma soni. Farq **qabul tugagach** chiqadi (``upcore.inventory.receiving_done``:
``ACCEPTED`` dan 7 kun yoki son e'longa yetdi); undan oldin — "qabul davom etmoqda" (:func:`progress`). Farq bo'lsa sotuvchi
qaror qiladi (``receiving_diffs``); qarorsiz farqlar va ochiq kamomadlar bosh sahifa "Diqqat" blokida sanaladi. Bog'liq
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
from upcore.inventory import receiving_done

from upapi.calc.costs import arrival_day
from upapi.db import models as m

FINE_CODE = "C000007"
FINE_WINDOW = (timedelta(days=-3), timedelta(days=45))


@dataclass
class Progress:
    """Qabul davom etmoqda (TM9.2): postavka ``ACCEPTED``, lekin 7 kun o'tmagan va son e'longa yetmagan."""

    dispatch_id: UUID
    invoice_id: UUID
    invoice_number: int | None
    accepted_on: date
    accepted: int
    declared: int


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
    sent: int | None = None  # dasturdagi jo'natma soni (ma'lumot; ``shipped`` — e'lon qilingan)

    @property
    def diff(self) -> int:
        return self.accepted - self.shipped


async def _accepted_rows(conn: AsyncConnection) -> list[tuple[Any, date]]:
    d, v = m.fbo_dispatches, m.fbo_invoices
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
    out = []
    for r in rows:
        day = arrival_day(r.status, r.created_on, r.raw)
        if day is not None:
            out.append((r, day))
    return out


async def _invoice_qty(
    conn: AsyncConnection, invoice_ids: list[UUID]
) -> tuple[dict[tuple[UUID, UUID], int], dict[tuple[UUID, UUID], int]]:
    """(postavka, SKU) → e'lon qilingan va qabul qilingan dona."""
    vi = m.fbo_invoice_items
    declared: dict[tuple[UUID, UUID], int] = {}
    accepted: dict[tuple[UUID, UUID], int] = {}
    for x in await conn.execute(
        select(
            vi.c.invoice_id,
            vi.c.sku_id,
            func.sum(vi.c.quantity_to_stock).label("declared"),
            func.sum(vi.c.quantity_accepted).label("accepted"),
        )
        .where(vi.c.invoice_id.in_(invoice_ids), vi.c.sku_id.is_not(None))
        .group_by(vi.c.invoice_id, vi.c.sku_id)
    ):
        declared[(x.invoice_id, x.sku_id)] = int(x.declared or 0)
        accepted[(x.invoice_id, x.sku_id)] = int(x.accepted or 0)
    return declared, accepted


async def _state(
    conn: AsyncConnection, today: date | None
) -> tuple[list[tuple[Any, date, bool]], dict[str, Any]]:
    from upapi.reports.common import today as current

    rows = await _accepted_rows(conn)
    if not rows:
        return [], {}
    day = today or current()
    di = m.fbo_dispatch_items
    sent: dict[tuple[UUID, UUID], tuple[int, Decimal | None]] = {}
    for x in await conn.execute(select(di).where(di.c.dispatch_id.in_([r.id for r, _ in rows]))):
        qty, cost = sent.get((x.dispatch_id, x.sku_id), (0, x.unit_cost))
        sent[(x.dispatch_id, x.sku_id)] = (qty + x.qty, cost)
    declared, accepted = await _invoice_qty(conn, [r.invoice_id for r, _ in rows])
    out = []
    for r, accepted_on in rows:
        skus = {s for (did, s) in sent if did == r.id} | {
            s for (inv, s) in declared if inv == r.invoice_id
        }
        want = sum(declared.get((r.invoice_id, s), sent.get((r.id, s), (0, None))[0]) for s in skus)
        got = sum(accepted.get((r.invoice_id, s), 0) for s in skus)
        done = receiving_done(accepted_on, day, want, got)
        out.append((r, accepted_on, done))
    return out, {"sent": sent, "declared": declared, "accepted": accepted}


async def progress(conn: AsyncConnection, today: date | None = None) -> list[Progress]:
    """Qabul davom etayotgan postavkalar (TM9.2): "qabul davom etmoqda: 719 / 744"."""
    rows, data = await _state(conn, today)
    out = []
    for r, accepted_on, done in rows:
        if done:
            continue
        keys = {s for (did, s) in data["sent"] if did == r.id} | {
            s for (inv, s) in data["declared"] if inv == r.invoice_id
        }
        out.append(
            Progress(
                dispatch_id=r.id,
                invoice_id=r.invoice_id,
                invoice_number=r.number,
                accepted_on=accepted_on,
                accepted=sum(data["accepted"].get((r.invoice_id, s), 0) for s in keys),
                declared=sum(
                    data["declared"].get((r.invoice_id, s), data["sent"].get((r.id, s), (0,))[0])
                    for s in keys
                ),
            )
        )
    return out


async def diffs(conn: AsyncConnection, today: date | None = None) -> list[Diff]:
    """Qabul tugagan (yoki qaror yozilgan) postavkalar bo'yicha farqlar: e'lon qilingan − qabul qilingan (F33)."""
    rd = m.receiving_diffs
    rows, data = await _state(conn, today)
    if not rows:
        return []
    ids = [r.id for r, _, _ in rows]
    decided = {
        (x.dispatch_id, x.sku_id): x
        for x in await conn.execute(select(rd).where(rd.c.dispatch_id.in_(ids)))
    }
    fines = await _fines(conn, {r.shop_id for r, _, _ in rows})
    out: list[Diff] = []
    sent, declared, accepted = data["sent"], data["declared"], data["accepted"]
    for r, day, done in rows:
        skus = {s for (did, s) in sent if did == r.id} | {
            s for (inv, s) in declared if inv == r.invoice_id
        }
        near = [
            (f_day, amount)
            for shop, f_day, amount in fines
            if shop == r.shop_id and day + FINE_WINDOW[0] <= f_day <= day + FINE_WINDOW[1]
        ]
        for sku in skus:
            qty, cost = sent.get((r.id, sku), (0, None))
            want = declared.get((r.invoice_id, sku), qty)
            got = accepted.get((r.invoice_id, sku), 0)
            row = decided.get((r.id, sku))
            if row is None and (not done or got == want):
                continue
            out.append(
                Diff(
                    dispatch_id=r.id,
                    shop_id=r.shop_id,
                    invoice_id=r.invoice_id,
                    invoice_number=r.number,
                    accepted_on=day,
                    sku_id=sku,
                    shipped=want,
                    accepted=got,
                    unit_cost=cost,
                    resolution=row,
                    fines=near,
                    sent=qty,
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

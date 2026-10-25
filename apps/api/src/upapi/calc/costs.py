"""Sotuv tannarxi (F21, F22): lotlar va hodisalar → ``sale_costs`` (03 §7).

Tovar (``items``) bo'yicha hodisalar:

- **lot kirimi** — ``lots`` (F20), tayyor sanasi ``ready_on``; yo'ldagi lotlar tartibi — xarid buyurtma sanasi;
- **sotuv** — SKU'si shu tovarga bog'langan ``sale_items`` (Yakunlangan va Jarayonda, F2), kun — F1, dona —
  ``amount``. ``amount`` qaytganlarsiz (F18: qaytgan alohida, ``amountReturns``) — qaytgan dona lotdan olinmaydi,
  shuning uchun alohida qaytish hodisasi yo'q. Semantika B2.11 da real ma'lumotda tasdiqlanadi;
- **hisobdan chiqarish** — ``stock_moves``: ``writeoff`` va manfiy ``adjust`` (brak, yo'qotish, kamomad).

Hisob faqat ``upcore.costing.compute_costs`` da (tashkilot usuli: FIFO / o'rtacha). Tovar ichida doim to'liq
hisoblanadi (natija to'liq qayta qurish bilan bir xil bo'lishi shart), lekin bazaga faqat o'zgargan qatorlar
yoziladi. COGS o'zgarsa ``changed_at`` va ``previous_cogs`` — "qayta hisoblandi" belgisi (P&L, 7 kun).

SKU'si tovarga bog'lanmagan sotuv — tannarxsiz, ``no_item`` belgisi bilan (F15 "tannarxsiz qism"); bekor yoki
noma'lum holatdagi sotuvning ``sale_costs`` qatori o'chiriladi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Row, delete, or_, select, true
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.costing import CostFlag, CostMethod, Event, Lot, Outflow, Sale, WriteOff, compute_costs
from upcore.metrics import TASHKENT as TASHKENT
from upcore.metrics import StatusGroup, business_date, status_group
from upcore.money import Currency, Money, quantize, round_rate
from upcore.purchasing import Flag

from upapi.db import models as m

COSTED = frozenset({StatusGroup.COMPLETED, StatusGroup.PROCESSING})


def day_start(day: date) -> datetime:
    """Toshkent kunining boshi (F1) — ``ordered_at`` (UTC) bilan solishtirish uchun."""
    return datetime.combine(day, time.min, TASHKENT)


def merge_day(target: dict[UUID, date | None], shop_id: UUID, day: date | None) -> None:
    """Do'kon → eng erta o'zgargan kun; ``None`` (butun tarix) ustun."""
    if shop_id in target and target[shop_id] is None:
        return
    current = target.get(shop_id)
    target[shop_id] = None if day is None else min(day, current) if current else day


@dataclass(frozen=True, slots=True)
class SaleRef:
    shop_id: UUID
    day: date
    status: str
    amount: int


@dataclass
class Changes:
    written: int = 0
    deleted: int = 0
    days: dict[UUID, date | None] = field(default_factory=dict)  # do'kon → eng erta o'zgargan kun

    def add(self, other: Changes) -> None:
        self.written += other.written
        self.deleted += other.deleted
        for shop, day in other.days.items():
            merge_day(self.days, shop, day)


def _ref(row: Any) -> SaleRef:
    return SaleRef(row.shop_id, business_date(row.ordered_at), row.status, row.amount)


def _costed(ref: SaleRef) -> bool:
    return status_group(ref.status) in COSTED and ref.amount > 0


def _row(method: CostMethod, out: Outflow) -> dict[str, Any]:
    return {
        "method": method.value,
        "unit_cost": None if out.cost is None else round_rate(out.cost.amount / out.qty),
        "cogs": None if out.cost is None else out.cost.amount,
        "flags": sorted(f.value for f in out.flags),
        "allocations": [
            {"lot": a.lot_id, "qty": a.qty, "unit": str(quantize(a.unit, 6))}
            for a in out.allocations
        ],
    }


def _same(old: Row[Any], new: dict[str, Any]) -> bool:
    return bool(
        old.method == new["method"]
        and old.unit_cost == new["unit_cost"]
        and old.cogs == new["cogs"]
        and sorted(old.flags or []) == new["flags"]
        and (old.allocations or []) == new["allocations"]
    )


async def _apply(
    conn: AsyncConnection,
    org_id: UUID,
    sales: dict[UUID, SaleRef],
    desired: dict[UUID, dict[str, Any]],
    existing: dict[UUID, Row[Any]],
    now: datetime,
) -> Changes:
    """Kerakli va mavjud qatorlar farqi: yangi/o'zgargan — upsert, keragi yo'q — o'chiriladi."""
    changes = Changes()
    rows = []
    for sale_id, new in desired.items():
        old = existing.get(sale_id)
        if old is not None and _same(old, new):
            continue
        recalculated = old is not None and old.cogs != new["cogs"]
        before = old.cogs if old is not None else None
        rows.append(
            {
                "org_id": org_id,
                "sale_item_id": sale_id,
                **new,
                "computed_at": now,
                "changed_at": now if recalculated else (old.changed_at if old else None),
                "previous_cogs": before if recalculated else (old.previous_cogs if old else None),
            }
        )
        merge_day(changes.days, sales[sale_id].shop_id, sales[sale_id].day)
    if rows:
        # executemany: so'rov bir marta kompilyatsiya qilinadi (katta VALUES ro'yxatidan ancha tez).
        stmt = pg_insert(m.sale_costs)
        columns = [k for k in rows[0] if k not in ("org_id", "sale_item_id")]
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["org_id", "sale_item_id"],
                set_={**{c: stmt.excluded[c] for c in columns}, "updated_at": now},
            ),
            rows,
        )
    changes.written = len(rows)
    stale = [sale_id for sale_id in existing if sale_id not in desired]
    if stale:
        await conn.execute(delete(m.sale_costs).where(m.sale_costs.c.sale_item_id.in_(stale)))
        for sale_id in stale:
            merge_day(changes.days, sales[sale_id].shop_id, sales[sale_id].day)
    changes.deleted = len(stale)
    return changes


async def _existing(conn: AsyncConnection, scope: ColumnElement[bool]) -> dict[UUID, Row[Any]]:
    s, k, c = m.sale_items, m.mp_skus, m.sale_costs
    query = (
        select(c)
        .join(s, s.c.id == c.c.sale_item_id)
        .outerjoin(k, k.c.id == s.c.sku_id)
        .where(scope)
    )
    return {r.sale_item_id: r for r in await conn.execute(query)}


async def method_of(conn: AsyncConnection, org_id: UUID) -> CostMethod:
    value = await conn.scalar(select(m.orgs.c.cost_method).where(m.orgs.c.id == org_id))
    return CostMethod(value or CostMethod.FIFO.value)


async def items_with_sales(conn: AsyncConnection, shop_id: UUID, since: date | None) -> set[UUID]:
    """Do'konda ``since`` kunidan sotuvi bor tovarlar (sotuvlar o'zgargan oraliq)."""
    s, k = m.sale_items, m.mp_skus
    query = (
        select(k.c.item_id)
        .distinct()
        .join(s, s.c.sku_id == k.c.id)
        .where(s.c.shop_id == shop_id, k.c.item_id.is_not(None))
    )
    if since is not None:
        query = query.where(s.c.ordered_at >= day_start(since))
    return {r.item_id for r in await conn.execute(query)}


def _lot(row: Any) -> Lot:
    return Lot(
        id=str(row.purchase_line_id),
        ready=row.ready_on,
        qty=row.qty,
        total=Money(row.total, Currency.UZS),
        flags=frozenset(Flag(f) for f in row.flags or ()),
        seq=row.ordered_on.toordinal() if row.ordered_on else 0,
    )


async def recompute_items(
    conn: AsyncConnection,
    org_id: UUID,
    items: set[UUID] | None,
    method: CostMethod,
    now: datetime,
) -> Changes:
    """F21: tovarlar (``None`` — hammasi) bo'yicha sotuv tannarxi, faqat farqlar yoziladi."""
    s, k, lots, pl, p, sm = (
        m.sale_items,
        m.mp_skus,
        m.lots,
        m.purchase_lines,
        m.purchases,
        m.stock_moves,
    )

    def only(column: Any) -> ColumnElement[bool]:
        clause: ColumnElement[bool] = column.is_not(None) if items is None else column.in_(items)
        return clause

    sales: dict[UUID, SaleRef] = {}
    by_item: dict[UUID, list[Event]] = {}
    for r in await conn.execute(
        select(s.c.id, s.c.shop_id, s.c.ordered_at, s.c.status, s.c.amount, k.c.item_id)
        .join(k, k.c.id == s.c.sku_id)
        .where(only(k.c.item_id))
    ):
        ref = sales[r.id] = _ref(r)
        if _costed(ref):
            by_item.setdefault(r.item_id, []).append(Sale(str(r.id), ref.day, ref.amount))
    for w in await conn.execute(
        select(sm.c.id, sm.c.item_id, sm.c.day, sm.c.qty).where(
            only(sm.c.item_id),
            or_(sm.c.kind == "writeoff", (sm.c.kind == "adjust") & (sm.c.qty < 0)),
            sm.c.qty != 0,
        )
    ):
        by_item.setdefault(w.item_id, []).append(WriteOff(f"w:{w.id}", w.day, abs(w.qty)))
    lots_by: dict[UUID, list[Lot]] = {}
    for lot in await conn.execute(
        select(lots, p.c.ordered_on)
        .join(pl, pl.c.id == lots.c.purchase_line_id)
        .join(p, p.c.id == pl.c.purchase_id)
        .where(only(lots.c.item_id))
    ):
        lots_by.setdefault(lot.item_id, []).append(_lot(lot))

    desired: dict[UUID, dict[str, Any]] = {}
    for item_id, events in by_item.items():
        result = compute_costs(lots_by.get(item_id, ()), events, method)
        for sale_id, out in result.sales.items():
            desired[UUID(sale_id)] = _row(method, out)
    existing = await _existing(conn, only(k.c.item_id))
    return await _apply(conn, org_id, sales, desired, existing, now)


async def recompute_unlinked(
    conn: AsyncConnection,
    org_id: UUID,
    shop_id: UUID | None,
    since: date | None,
    method: CostMethod,
    now: datetime,
) -> Changes:
    """Tovarga bog'lanmagan sotuvlar (SKU yo'q yoki SKU'da tovar yo'q): tannarxsiz, ``no_item`` belgisi."""
    s, k = m.sale_items, m.mp_skus
    scope: ColumnElement[bool] = or_(s.c.sku_id.is_(None), k.c.item_id.is_(None))
    scope = scope & (true() if shop_id is None else s.c.shop_id == shop_id)
    if since is not None:
        scope = scope & (s.c.ordered_at >= day_start(since))
    rows = await conn.execute(
        select(s.c.id, s.c.shop_id, s.c.ordered_at, s.c.status, s.c.amount)
        .outerjoin(k, k.c.id == s.c.sku_id)
        .where(scope)
    )
    sales = {r.id: _ref(r) for r in rows}
    unknown = {
        "method": method.value,
        "unit_cost": None,
        "cogs": None,
        "flags": [CostFlag.NO_ITEM.value],
        "allocations": [],
    }
    desired = {sale_id: dict(unknown) for sale_id, ref in sales.items() if _costed(ref)}
    return await _apply(conn, org_id, sales, desired, await _existing(conn, scope), now)

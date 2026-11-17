"""Ta'minot butunligi (TM9.3, ADR-068 (3); 02 M10 qabul mezoni).

Omborim daftari — sanalgan ("Omborimda") xaridlar qatorlari va ularning donasi qayerga ketgani:

- **qator** bo'yicha: Uzumga jo'natilgan (Jo'natilmoqda + Uzumda, FIFO — :func:`upapi.reports.dispatch.attribute`),
  boshqa SKU'ga o'tkazilgan, hisobdan chiqarilgan (``stock_moves`` shu qatorga yozilgan);
- **SKU** (yoki SKU'siz tovar) bo'yicha M10 tenglamasi: Omborimda + Jo'natilmoqda + Uzumda + o'tkazilgan + hisobdan
  chiqarilgan = sanalgan sog' dona (+ inventarizatsiya tuzatishi). Omborimda manfiy chiqsa — bu **xato** (0 ga
  qisilmaydi): masalan jo'natilgandan keyin sanalgan son kamaytirilgan.

Himoya (:func:`check_lines`): ishlatilgan donasi bor qator o'chirilmaydi va SKU'si almashtirilmaydi; sog' donasi
ishlatilganidan kamga tushmaydi; SKU qoldig'i manfiyga tushadigan o'zgarish rad etiladi. Sabab — alohida kod (web
matni shu kod bo'yicha, yo'l ko'rsatadi).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.purchasing import SupplyState, supply_state

from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import dispatch


def key_of(sku_id: UUID | None, item_id: UUID | None) -> str:
    """Omborim kaliti: SKU bo'lsa ``sku:<id>``, bo'lmasa tovarning SKU'siz qatori ``item:<id>``."""
    return f"sku:{sku_id}" if sku_id is not None else f"item:{item_id}"


def good_of(line: Any) -> int:
    """Sog' dona: kelgan (sanalmagan qatorda — buyurtma soni) − sanashdagi brak."""
    arrived: int = line.received_qty if line.received_qty is not None else line.ordered_qty
    return arrived - int(line.defect_qty)


@dataclass
class LineUse:
    """Sanalgan qator donasi qayerga ketgan."""

    line: Any
    good: int
    dispatched: int = 0  # Jo'natilmoqda + Uzumda (FIFO)
    transferred: int = 0  # boshqa SKU'ga o'tkazilgan
    written_off: int = 0  # shu qatorga yozilgan hisobdan chiqarish (va manfiy tuzatish)

    @property
    def used(self) -> int:
        return self.dispatched + self.transferred + self.written_off


@dataclass
class Balance:
    """SKU (yoki SKU'siz tovar) bo'yicha M10 tenglamasi."""

    key: str
    sku_id: UUID | None
    item_id: UUID | None
    good: int = 0  # sanalgan sog' dona (o'tkazilib kelgan qatorlar ham)
    transferred: int = 0  # shu kalitdan boshqa SKU'ga o'tkazilgan
    dispatched: int = 0  # faol jo'natmalardagi dona (talab)
    attributed: int = 0  # shundan partiyalarga bog'langani (qolgani — ortiqcha jo'natilgan, xato)
    written_off: int = 0  # hisobdan chiqarish (musbat)
    adjusted: int = 0  # inventarizatsiya tuzatishi (ishorali)
    lines: list[UUID] = field(default_factory=list)

    @property
    def on_hand(self) -> int:
        """Omborimda (xom, 0 ga qisilmaydi)."""
        return self.good - self.transferred - self.dispatched - self.written_off + self.adjusted


@dataclass
class Ledger:
    purchases: dict[UUID, Any]  # sanalgan xaridlar
    lines: dict[UUID, LineUse]
    balances: dict[str, Balance]

    def problems(self) -> list[Balance]:
        """M10 buzilgan kalitlar: Omborimda manfiy yoki jo'natilgan dona partiyalardan ko'p."""
        return [b for b in self.balances.values() if b.on_hand < 0 or b.dispatched > b.attributed]


async def ledger(conn: AsyncConnection) -> Ledger:
    """Omborim daftari (o'qish): sanalgan xaridlar, qatorlar ishlatilishi va kalitlar balansi."""
    from upapi.reports.purchases import stage_dates

    p, pl, sm = m.purchases, m.purchase_lines, m.stock_moves
    purchases = {
        r.id: r
        for r in await conn.execute(select(p))
        if supply_state(stage_dates(r)) is SupplyState.IN_STOCK
    }
    rows = list(
        await conn.execute(
            select(pl)
            .where(pl.c.purchase_id.in_(list(purchases)))
            .order_by(pl.c.created_at, pl.c.id)
        )
    )
    moved_out: dict[UUID, int] = {}
    for r in rows:
        if r.source_line_id is not None:
            moved_out[r.source_line_id] = moved_out.get(r.source_line_id, 0) + good_of(r)
    sent = await dispatch.attribute(conn, rows, purchases, moved_out)
    lines: dict[UUID, LineUse] = {}
    balances: dict[str, Balance] = {}

    def balance(sku_id: UUID | None, item_id: UUID | None) -> Balance:
        key = key_of(sku_id, item_id)
        return balances.setdefault(key, Balance(key=key, sku_id=sku_id, item_id=item_id))

    for r in rows:
        att = sent.get(r.id)
        use = LineUse(
            line=r,
            good=good_of(r),
            dispatched=0 if att is None else att.sending + att.linked,
            transferred=moved_out.get(r.id, 0),
        )
        lines[r.id] = use
        b = balance(r.sku_id, r.item_id)
        b.good += use.good
        b.transferred += use.transferred
        b.attributed += use.dispatched
        b.lines.append(r.id)
    held = await dispatch.held(conn)
    if held:
        k = m.mp_skus
        item_of = {
            r.id: r.item_id
            for r in await conn.execute(select(k.c.id, k.c.item_id).where(k.c.id.in_(list(held))))
        }
        for sku_id, qty in held.items():
            balance(sku_id, item_of.get(sku_id)).dispatched += qty
    for mv in await conn.execute(
        select(
            sm.c.item_id,
            sm.c.sku_id,
            sm.c.kind,
            sm.c.purchase_line_id,
            func.sum(sm.c.qty).label("qty"),
        )
        .where(sm.c.kind.in_(("adjust", "writeoff")))
        .group_by(sm.c.item_id, sm.c.sku_id, sm.c.kind, sm.c.purchase_line_id)
    ):
        key = key_of(mv.sku_id, mv.item_id)
        qty = int(mv.qty)
        out = abs(qty) if mv.kind == "writeoff" else max(0, -qty)
        if mv.purchase_line_id in lines:
            lines[mv.purchase_line_id].written_off += out
        found = balances.get(key)
        if (
            found is None
        ):  # Omborimda qatori yo'q tovar (masalan, boshlang'ich holat) — M10 ga tegishli emas
            continue
        if mv.kind == "writeoff":
            found.written_off += abs(qty)
        else:
            found.adjusted += qty
    return Ledger(purchases=purchases, lines=lines, balances=balances)


def _reason(use: LineUse) -> tuple[str, str]:
    if use.dispatched:
        return (
            "units_dispatched",
            f"{use.dispatched} dona Uzumga jo'natilgan — avval jo'natmani bekor qiling",
        )
    if use.transferred:
        return (
            "units_transferred",
            f"{use.transferred} dona boshqa SKU'ga o'tkazilgan — avval o'tkazmani bekor qiling",
        )
    return (
        "units_written_off",
        f"{use.written_off} dona hisobdan chiqarilgan — avval o'sha yozuvni o'chiring",
    )


def check_lines(
    book: Ledger,
    new_good: Mapping[UUID, int | None],
    rekeyed: set[UUID] | frozenset[UUID] = frozenset(),
) -> None:
    """O'zgarish butunlikni buzmaydimi (bo'lmasa ``AppError`` 409). ``new_good`` — qator → yangi sog' dona (``None`` —
    qator Omborimdan ketadi: o'chirish yoki xarid "Omborimda"dan chiqadi); ``rekeyed`` — SKU (tovar) almashtirilgan
    qatorlar. Omborimda bo'lmagan (sanalmagan) qatorlar tekshirilmaydi — ularda ishlatilgan dona yo'q."""
    drop: dict[str, int] = {}
    for line_id, good in new_good.items():
        use = book.lines.get(line_id)
        if use is None:
            continue
        leaves = good is None or line_id in rekeyed
        if leaves and use.used > 0:
            code, detail = _reason(use)
            raise AppError(code, 409, detail=detail)
        if good is not None and good < use.used:
            code, detail = _reason(use)
            raise AppError(code, 409, detail=f"sog' dona {use.used} dan kam bo'lmaydi: {detail}")
        lost = use.good if leaves else use.good - (good or 0)
        if lost > 0:
            key = key_of(use.line.sku_id, use.line.item_id)
            drop[key] = drop.get(key, 0) + lost
    for key, lost in drop.items():
        b = book.balances[key]
        if b.on_hand - lost < 0:
            code = "units_written_off" if b.written_off or b.adjusted < 0 else "units_dispatched"
            raise AppError(
                code,
                409,
                detail=f"Omborimda {max(b.on_hand, 0)} dona qoladi — {lost} dona kamaytirib bo'lmaydi "
                "(qolgani jo'natilgan yoki hisobdan chiqarilgan)",
            )

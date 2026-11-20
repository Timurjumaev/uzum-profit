"""B5.4 / B5.0a: Bosh sahifa "Yo'qotishlar va imkoniyat" bloki (ADR-043 (5), AI'siz, formula bilan).

Yo'qotishlar (davr bo'yicha, so'mda): qaytarish xarajati (Uzum "qaytim saqlash"), jarimalar, brak zarari (F51), Uzum
qabulidagi yo'qotish (F52), nelikvid tovar saqlash haqi (F30 × F43), tugab qolishdan yo'qotilgan foyda (F34).
Imkoniyat — nelikvid tovarda muzlagan pul (F30, F29). "Diqqat" va "Zarar 5 SKU" dagi raqamlar takrorlanmaydi; bekor
summasi yo'qotish emas (F17).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory
from upcore.inventory import STOCKOUT_MAX_DAYS, DayStat, Liquidity, stockout_loss
from upcore.metrics import Period
from upcore.money import Currency, Money
from upcore.pnl import DEFECT_LOSS, RECEIVING_LOSS, Statement

from upapi.db import models as m
from upapi.reports import cells as rc
from upapi.reports.common import Filters
from upapi.reports.stock import StockBook

UZS = Currency.UZS
PROFIT_DAYS = 90  # F34: o'rtacha foyda/dona — oxirgi 90 kun
VELOCITY_DAYS = 60  # F23 oynasi tugashdan oldin shuncha kungacha orqaga cho'ziladi


@dataclass(frozen=True, slots=True)
class Losses:
    return_cost: Money
    fines: Money
    defect_loss: Money  # F51
    receiving_loss: Money  # F52
    illiquid_storage: Money  # F30 × F43
    illiquid_skus: int
    stockout_loss: Money | None  # F34; ``None`` — hisoblab bo'lmadi (ma'lumot yo'q)
    stockout_skus: int
    illiquid_money: Money  # imkoniyat: nelikvid tovarda muzlagan pul

    @property
    def total(self) -> Money:
        parts = [
            self.return_cost,
            self.fines,
            self.defect_loss,
            self.receiving_loss,
            self.illiquid_storage,
        ]
        if self.stockout_loss is not None:
            parts.append(self.stockout_loss)
        return Money(sum((p.amount for p in parts), Decimal(0)), UZS)


def _positive(value: Money | None) -> Money:
    return Money(max(value.amount, Decimal(0)), UZS) if value is not None else Money.zero(UZS)


def statement_losses(s: Statement) -> tuple[Money, Money, Money, Money]:
    """Davr hisobidan to'rtta qator: qaytarish xarajati, jarimalar, F51, F52 (manfiy bo'lmaydi)."""
    zero = Money.zero(UZS)
    return (
        _positive(s.uzum_expenses.get(ExpenseCategory.RETURN_STORAGE, zero)),
        _positive(s.uzum_expenses.get(ExpenseCategory.FINE, zero)),
        _positive(s.own_expenses.get(DEFECT_LOSS, zero)),
        _positive(s.own_expenses.get(RECEIVING_LOSS, zero)),
    )


async def _zero_candidates(conn: AsyncConnection, sku_ids: list[UUID], period: Period) -> set[UUID]:
    """Davrda (yoki undan 90 kun oldin boshlangan tugashda) snapshot bo'yicha qoldig'i 0 bo'lgan SKU'lar."""
    if not sku_ids:
        return set()
    sd = m.sku_daily
    start = period.start - timedelta(days=STOCKOUT_MAX_DAYS)
    rows = await conn.execute(
        select(sd.c.sku_id)
        .where(
            sd.c.sku_id.in_(sku_ids),
            sd.c.day >= start,
            sd.c.day <= period.end,
            (sd.c.qty_active + sd.c.qty_fbs) <= 0,
        )
        .distinct()
    )
    return {r.sku_id for r in rows}


async def _series(
    conn: AsyncConnection, sku_ids: set[UUID], since: date, until: date
) -> dict[UUID, list[DayStat]]:
    d, sd = m.daily_sku_metrics, m.sku_daily
    sold: dict[UUID, dict[date, tuple[int, int, int]]] = {}
    for r in await conn.execute(
        select(d.c.sku_id, d.c.day, d.c.units, d.c.returns, d.c.units_processing).where(
            d.c.sku_id.in_(sku_ids), d.c.day >= since, d.c.day <= until
        )
    ):
        sold.setdefault(r.sku_id, {})[r.day] = (r.units, r.returns, r.units_processing)
    snaps: dict[UUID, dict[date, bool]] = {}
    for sr in await conn.execute(
        select(sd.c.sku_id, sd.c.day, sd.c.qty_active, sd.c.qty_fbs).where(
            sd.c.sku_id.in_(sku_ids), sd.c.day >= since, sd.c.day <= until
        )
    ):
        snaps.setdefault(sr.sku_id, {})[sr.day] = (sr.qty_active or 0) + (sr.qty_fbs or 0) > 0
    out: dict[UUID, list[DayStat]] = {}
    for sku in sku_ids:
        days = []
        for i in range((until - since).days + 1):
            day = since + timedelta(days=i)
            units, returned, processing = sold.get(sku, {}).get(day, (0, 0, 0))
            days.append(DayStat(day, units, returned, snaps.get(sku, {}).get(day), processing))
        out[sku] = days
    return out


async def stockout_losses(
    conn: AsyncConnection, f: Filters, stock: StockBook, today: date
) -> tuple[Money, int]:
    """F34 butun tanlov bo'yicha: (yo'qotilgan foyda, tugab qolgan SKU'lar soni).

    O'rtacha foyda/dona — SKU'ning oxirgi 90 kunlik sof foydasi / sotilgan dona (F12 / F3 donasi); sotuvi yoki foydasi
    yo'q SKU'da hisoblab bo'lmaydi — o'tkazib yuboriladi (raqam o'ylab topilmaydi)."""
    period = f.period
    candidates = await _zero_candidates(conn, sorted(stock.skus), period)
    if not candidates:
        return Money.zero(UZS), 0
    p90 = Period(today - timedelta(days=PROFIT_DAYS), today - timedelta(days=1))
    book = await rc.load_book(conn, p90, today)
    by_sku = book.scoped(f, p90).by_sku()
    series = await _series(
        conn,
        candidates,
        period.start - timedelta(days=STOCKOUT_MAX_DAYS + VELOCITY_DAYS),
        min(period.end, today),
    )
    lost = Money.zero(UZS)
    skus = 0
    for sku, days in series.items():
        st = by_sku.get(str(sku))
        if st is None or st.units <= 0:
            continue
        per_unit = Money(st.net_profit.amount / st.units, UZS)
        item = stock.skus[sku]
        replenishing = item.in_transit + item.own + item.inbound > 0
        loss = stockout_loss(
            days, period.start, min(period.end, today), per_unit, replenishing=replenishing
        )
        if loss.zero_days:
            skus += 1
            lost = lost + loss.lost
    return lost, skus


def illiquid(stock: StockBook, by_sku: dict[Any, Statement]) -> tuple[Money, int, Money]:
    """F30: nelikvid SKU'larning davrdagi saqlash haqi (F43), soni va ulardagi muzlagan pul (lot narxida, F29)."""
    storage = Money.zero(UZS)
    money = Money.zero(UZS)
    count = 0
    for sku, item in stock.skus.items():
        if item.liquidity is not Liquidity.ILLIQUID:
            continue
        count += 1
        if item.stock_value is not None:
            money = money + item.stock_value
        st = by_sku.get(str(sku))
        if st is not None:
            storage = storage + _positive(st.uzum_expenses.get(ExpenseCategory.STORAGE))
    return storage, count, money


async def losses(
    conn: AsyncConnection,
    f: Filters,
    s: Statement,
    by_sku: dict[Any, Statement],
    stock: StockBook,
    today: date,
) -> Losses:
    ret, fines, defect, receiving = statement_losses(s)
    storage, illiquid_count, frozen = illiquid(stock, by_sku)
    lost, lost_skus = await stockout_losses(conn, f, stock, today)
    return Losses(
        return_cost=ret,
        fines=fines,
        defect_loss=defect,
        receiving_loss=receiving,
        illiquid_storage=storage,
        illiquid_skus=illiquid_count,
        stockout_loss=lost,
        stockout_skus=lost_skus,
        illiquid_money=frozen,
    )

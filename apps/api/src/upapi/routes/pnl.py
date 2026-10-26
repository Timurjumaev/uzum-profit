"""``/pnl``: foyda va zarar (M5, F3–F16; ADR-026). Ruxsat — ``view_finance`` (egasi, menejer, buxgalter).

Hisob varag'i tanlangan davr va oldingi xuddi shu uzunlikdagi davr bilan solishtiriladi (``rows``: joriy, tushumga
nisbatan, oldingi, farq). Ko'rinishlar (``view``): oylar, kunlar, do'konlar, SKU bo'yicha ustunlar — kataklar
yig'indisi (ustunlar yig'indisi = jami). SKU ko'rinishida ``unlinked`` — SKU'ga bog'lanmagan sotuvlar, ``null`` —
taqsimlanmagan (sotuvsiz kun) xarajatlar. Kutilayotgan foyda (F16) va "qayta hisoblandi" soni alohida. Bepul logistika kunlari (``free_periods``, Uzum bonusi —
ADR-031) haqiqiy foydaga ta'sir qilmaydi, faqat belgilash uchun; SKU ko'rinishida ustun nomi.
Drill-down: sotuvlar — ``/sales``, xarajatlar — ``/expenses`` (shu filtrlar bilan).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from upcore.pnl import CellKey, Cells, Statement, compare

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.reports import cells as rc
from upapi.reports import free
from upapi.reports.common import (
    Filters,
    Heavy,
    Meta,
    PeriodOut,
    db_now,
    filters,
    meta,
    sku_catalog,
)
from upapi.reports.schemas import PendingOut, RowOut, StatementOut

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders", "expenses"]


class View(StrEnum):
    TOTAL = "total"
    MONTH = "month"
    DAY = "day"
    SHOP = "shop"
    SKU = "sku"


class ColumnOut(BaseModel):
    key: str | None  # oy/kun (ISO), do'kon yoki SKU id, ``unlinked``; ``null`` — taqsimlanmagan
    statement: StatementOut
    title: str | None = None  # SKU ko'rinishida: SKU nomi (``skuFullTitle``)
    shop_id: UUID | None = None  # SKU ko'rinishida: SKU do'koni


class PendingShopOut(PendingOut):
    shop_id: UUID


class PnlOut(BaseModel):
    meta: Meta
    statement: StatementOut
    previous: StatementOut
    rows: list[RowOut]
    columns: list[ColumnOut]
    pending: PendingOut
    pending_shops: list[PendingShopOut]
    recalculated: int  # davr sotuvlaridan oxirgi 7 kunda tannarxi o'zgarganlari (03 §7)
    free_periods: list[
        PeriodOut
    ]  # Uzum bonusi — bepul logistika kunlari (ADR-031; tanlangan davr ichida)


def columns(cells: Cells, view: View) -> tuple[list[ColumnOut], Statement]:
    """Ko'rinish ustunlari va jami (bir o'tishda)."""
    views: dict[View, Callable[[CellKey], Any]] = {
        View.MONTH: lambda k: k.day.replace(day=1),
        View.DAY: lambda k: k.day,
        View.SHOP: lambda k: k.shop,
        View.SKU: lambda k: k.sku,
    }
    if view is View.TOTAL:
        return [], cells.statement()
    groups, whole = cells.by_and_total(views[view])
    out = [
        ColumnOut(key=None if k is None or k == "" else str(k), statement=StatementOut.of(s))
        for k, s in groups.items()
    ]
    return out, whole


@router.get("/orgs/{org_id}/pnl", response_model=PnlOut)
async def pnl(ctx: Finance, f: Filter, _: Heavy, view: View = View.TOTAL) -> PnlOut:
    previous = f.period.previous()
    book = await rc.load_book(ctx.conn, rc.span(previous, f.period))
    cur, before = book.scoped(f, f.period), book.scoped(f, previous)
    cols, s = columns(cur, view)
    if view is View.SKU:
        await _titles(ctx, cols)
    p = before.statement()
    days = await free.free_days(ctx.conn, f)
    pend = await rc.pending(ctx.conn, f)
    now = await db_now(ctx.conn)
    return PnlOut(
        meta=await meta(ctx.conn, f, KINDS, previous),
        statement=StatementOut.of(s),
        previous=StatementOut.of(p),
        rows=[RowOut.of(r) for r in compare(s, p)],
        columns=cols,
        pending=PendingOut.of(pend.total),
        pending_shops=[
            PendingShopOut(shop_id=shop, **PendingOut.of(e).model_dump())
            for shop, e in sorted(pend.shops.items(), key=lambda kv: str(kv[0]))
        ],
        recalculated=await rc.recalculated(ctx.conn, f, now),
        free_periods=[PeriodOut.of(x) for x in days.periods()],
    )


async def _titles(ctx: OrgContext, cols: list[ColumnOut]) -> None:
    ids = []
    for c in cols:
        if c.key is not None and c.key != rc.UNLINKED:
            ids.append(UUID(c.key))
    catalog = await sku_catalog(ctx.conn, ids=ids) if ids else {}
    for c in cols:
        info = catalog.get(UUID(c.key)) if c.key is not None and c.key != rc.UNLINKED else None
        if info is not None:
            c.title, c.shop_id = info.title, info.shop_id

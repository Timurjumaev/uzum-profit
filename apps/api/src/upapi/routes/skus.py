"""``/skus``: mahsulotlar jadvali (M6, unit-iqtisod). Ruxsat — ``view_finance``.

Har SKU (tanlangan do'konlar katalogi, sotuvsizlari ham): davr kesimi (``Cells.by_sku`` — P&L bilan bitta hisob),
unit-iqtisod (``upcore.pnl.unit_economics``), holat belgisi (M6), qaytish/bekor ulushi (F17, F18), qoldiq, zaxira
kunlari (F24), ABC (F28, bizniki) va Uzum ``rank``. SKU'ga bog'lanmagan sotuvlar va taqsimlanmagan xarajatlar
alohida (``unlinked``, ``unallocated``): qatorlar + ikkalasi = P&L jami (M5 qabul mezoni).

Qidiruv (``q``) — SKU nomi, mahsulot nomi, artikul, shtrix-kod; lotin/kirill va tutuq turidan qat'i nazar.
Saralash ``sort`` (``-`` — kamayish), sahifalash ``cursor`` bilan. Ustun tanlash va saqlangan ko'rinishlar — B4 (UI).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from upcore.metrics import ProfitLabel, cancel_rate, profit_label, return_share
from upcore.pnl import Cells, Statement, unit_economics

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.errors import AppError
from upapi.reports import cells as rc
from upapi.reports.common import (
    Cursor,
    Filters,
    Heavy,
    Limit,
    Meta,
    decode_cursor,
    encode_cursor,
    filters,
    fold,
    meta,
    sku_catalog,
)
from upapi.reports.schemas import StatementOut, amount
from upapi.reports.stock import load_stock

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders", "expenses", "products", "snapshot"]


class SkuSort(StrEnum):
    REVENUE = "revenue"
    NET_PROFIT = "net_profit"
    UNITS = "units"
    MARGIN = "margin"
    TITLE = "title"
    STOCK = "stock"
    DAYS_OF_STOCK = "days_of_stock"


class SkuRowOut(BaseModel):
    sku_id: UUID
    shop_id: UUID
    item_id: UUID | None
    product_id: UUID | None
    title: str | None
    product_title: str | None
    article: str | None
    barcode: str | None
    image_url: str | None
    price: Decimal | None
    units: int
    revenue: Decimal  # F3
    avg_price: Decimal | None
    commission_share: Decimal | None
    logistics_per_unit: Decimal | None
    cogs_per_unit: Decimal | None
    ads_per_unit: Decimal | None
    acos: Decimal | None  # F19
    profit_per_unit: Decimal | None
    net_profit: Decimal  # F12
    margin: Decimal | None  # F13
    uncovered_share: Decimal  # 1 − F15
    uncovered_lines: int
    roi: Decimal | None  # F14
    return_share: Decimal | None  # F18
    cancel_share: Decimal | None  # F17
    label: ProfitLabel  # M6 holat belgisi
    stock: int  # FBO + FBS
    days_of_stock: Decimal | None  # F24
    abc: str  # F28 (bizniki, oxirgi 30 kun)
    rank: str | None  # Uzum ``rankInfo``
    status: str | None  # Uzum SKU holati


class SkusOut(BaseModel):
    meta: Meta
    items: list[SkuRowOut]
    total: int  # filtr (``q``) bo'yicha jami SKU
    next_cursor: str | None
    unlinked: StatementOut  # SKU'ga bog'lanmagan sotuvlar
    unallocated: StatementOut  # sotuvsiz kun xarajatlari (taqsimlanmagan)


def _value(row: SkuRowOut, sort: SkuSort) -> Any:
    return getattr(row, sort.value)


@router.get("/orgs/{org_id}/skus", response_model=SkusOut)
async def skus(
    ctx: Finance,
    f: Filter,
    _: Heavy,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Annotated[str, Query(pattern=r"^-?[a-z_]+$")] = "-revenue",
    limit: Limit = 100,
    cursor: Cursor = None,
) -> SkusOut:
    desc = sort.startswith("-")
    try:
        key = SkuSort(sort.lstrip("-"))
    except ValueError:
        raise AppError("bad_sort", 422, detail=sort) from None
    offset = int((decode_cursor(cursor, 1) or [0])[0])
    book = await rc.load_book(ctx.conn, f.period)
    cells = book.scoped(f)
    by_sku = cells.by_sku()
    sums = await rc.sale_sums(ctx.conn, f, by_sku=True)
    catalog = await sku_catalog(ctx.conn, f.shops)
    stock = await load_stock(ctx.conn, sorted(f.shops, key=str) if f.shops else None, f.today)
    empty = Cells(f.period, {}).statement()
    needle = fold(q).strip() if q else ""

    rows = []
    for info in catalog.values():
        if needle and needle not in info.haystack():
            continue
        s: Statement = by_sku.get(str(info.id), empty)
        u = unit_economics(s)
        st = stock.skus.get(info.id)
        n = sums.get(str(info.id), rc.SaleSums())
        rows.append(
            SkuRowOut(
                sku_id=info.id,
                shop_id=info.shop_id,
                item_id=info.item_id,
                product_id=info.product_id,
                title=info.title,
                product_title=info.product_title,
                article=info.article,
                barcode=info.barcode,
                image_url=info.image_url,
                price=info.price,
                units=s.units,
                revenue=s.revenue.amount,
                avg_price=amount(u.avg_price),
                commission_share=u.commission_share,
                logistics_per_unit=amount(u.logistics_per_unit),
                cogs_per_unit=amount(u.cogs_per_unit),
                ads_per_unit=amount(u.ads_per_unit),
                acos=u.acos,
                profit_per_unit=amount(u.profit_per_unit),
                net_profit=s.net_profit.amount,
                margin=s.margin,
                uncovered_share=s.uncovered_share,
                uncovered_lines=s.uncovered_lines,
                roi=s.roi,
                return_share=return_share(n.units, n.returns),
                cancel_share=cancel_rate(n.units, n.canceled),
                label=profit_label(s.net_profit, s.margin),
                stock=st.stock if st else 0,
                days_of_stock=st.days_of_stock if st else None,
                abc=st.abc.value if st else "C",
                rank=info.rank,
                status=info.status,
            )
        )
    present = sorted(rows, key=lambda r: (r.title or "", str(r.sku_id)))  # barqaror ikkinchi tartib
    nones = [r for r in present if _value(r, key) is None]
    known = sorted(
        (r for r in present if _value(r, key) is not None),
        key=lambda r: _value(r, key),
        reverse=desc,
    )
    ordered = known + nones  # qiymatsizlar doim oxirida
    page = ordered[offset : offset + limit]
    more = offset + limit < len(ordered)
    return SkusOut(
        meta=await meta(ctx.conn, f, KINDS),
        items=page,
        total=len(ordered),
        next_cursor=encode_cursor([offset + limit]) if more else None,
        unlinked=StatementOut.of(by_sku.get(rc.UNLINKED, empty)),
        unallocated=StatementOut.of(by_sku.get(None, empty)),
    )

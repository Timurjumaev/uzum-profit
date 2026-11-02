"""``/skus``: mahsulotlar jadvali (M6, unit-iqtisod). Ruxsat — ``view_finance``.

Har SKU (tanlangan do'konlar katalogi, sotuvsizlari ham): davr kesimi (``Cells.by_sku`` — P&L bilan bitta hisob),
unit-iqtisod (``upcore.pnl.unit_economics``), holat belgisi (M6), qaytish/bekor ulushi (F17, F18), qoldiq, zaxira
kunlari (F24), ABC (F28, bizniki) va Uzum ``rank``. SKU'ga bog'lanmagan sotuvlar va taqsimlanmagan xarajatlar
alohida (``unlinked``, ``unallocated``): qatorlar + ikkalasi = P&L jami (M5 qabul mezoni).

Xarajatlar ikki ustunda: ``expenses_direct`` (SKU'ga bog'langan) va ``expenses_allocated`` (do'kon / tashkilot
xarajatining tushum ulushi, ADR-026); sotuvsiz kun xarajati — ``unallocated`` alohida. Uzum xarajatlari
API bergandek olinadi (ADR-035).

Qidiruv (``q``) — SKU nomi, mahsulot nomi, artikul, shtrix-kod; lotin/kirill va tutuq turidan qat'i nazar.
Filtrlar: ``label`` (holat belgisi), ``abc``, ``shop``. Saralash ``sort`` (``-`` — kamayish), sahifalash ``cursor`` bilan.

``/skus/{id}`` — SKU sahifasi: KPI'lar (shu davr hisobi), kunlik tarix (sotuv, foyda, narx, qoldiq snapshotlari),
tannarx tarixi (tovar lotlari), qaytish sabablari, bog'langan tovar va unit kalkulyator boshlang'ich qiymatlari
(``calc``, manbasi bilan). ``/unit-calc`` — F35/F36: kalkulyator hisobi (UI qayta hisoblamaydi, tamoyil 4).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from upcore.metrics import (
    ProfitLabel,
    StatusGroup,
    cancel_rate,
    profit_label,
    return_share,
    statuses,
)
from upcore.money import Currency, Money, quantize
from upcore.pnl import Cells, Statement, unit_economics
from upcore.tax import effective_rate
from upcore.unit import unit_calc

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import cells as rc
from upapi.reports import products as rp
from upapi.reports.common import (
    Cursor,
    Filters,
    Heavy,
    Limit,
    Meta,
    SkuInfo,
    decode_cursor,
    encode_cursor,
    filters,
    fold,
    meta,
    sku_catalog,
)
from upapi.reports.schemas import StatementOut, amount
from upapi.reports.stock import SkuStock, load_stock

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders", "expenses", "products", "snapshot"]
UZS = Currency.UZS
HUNDRED = Decimal(100)


class SkuSort(StrEnum):
    REVENUE = "revenue"
    NET_PROFIT = "net_profit"
    UNITS = "units"
    MARGIN = "margin"
    TITLE = "title"
    STOCK = "stock"
    DAYS_OF_STOCK = "days_of_stock"
    AVG_PRICE = "avg_price"
    PROFIT_PER_UNIT = "profit_per_unit"
    ROI = "roi"
    RETURN_SHARE = "return_share"
    CANCEL_SHARE = "cancel_share"
    EXPENSES_DIRECT = "expenses_direct"
    EXPENSES_ALLOCATED = "expenses_allocated"


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
    expenses_direct: Decimal  # F9 + F10 to'g'ridan-to'g'ri qismi (ADR-026)
    expenses_allocated: Decimal  # F9 + F10 tushum ulushida taqsimlangan qismi (ADR-026)
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
    total: int  # filtr (``q``, ``label``, ``abc``) bo'yicha jami SKU
    next_cursor: str | None
    unlinked: StatementOut  # SKU'ga bog'lanmagan sotuvlar
    unallocated: StatementOut  # sotuvsiz kun xarajatlari (taqsimlanmagan)


def _value(row: SkuRowOut, sort: SkuSort) -> Any:
    return getattr(row, sort.value)


def _row(
    info: SkuInfo,
    s: Statement,
    n: rc.SaleSums,
    st: SkuStock | None,
) -> SkuRowOut:
    u = unit_economics(s)
    return SkuRowOut(
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
        expenses_direct=s.direct_total.amount,
        expenses_allocated=s.allocated_total.amount,
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


@router.get("/orgs/{org_id}/skus", response_model=SkusOut)
async def skus(
    ctx: Finance,
    f: Filter,
    _: Heavy,
    q: Annotated[str | None, Query(max_length=100)] = None,
    label: Annotated[ProfitLabel | None, Query(description="Holat belgisi bo'yicha")] = None,
    abc: Annotated[Literal["A", "B", "C"] | None, Query(description="ABC (F28)")] = None,
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
        row = _row(
            info,
            by_sku.get(str(info.id), empty),
            sums.get(str(info.id), rc.SaleSums()),
            stock.skus.get(info.id),
        )
        if (label is None or row.label is label) and (abc is None or row.abc == abc):
            rows.append(row)
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


# --- SKU sahifasi -----------------------------------------------------------------------------


class SkuDayOut(BaseModel):
    """Kun kesimi: sotuv (``daily_sku_metrics`` kataklari) va snapshot (narx, komissiya, qoldiq); ikkalasidan biri
    bo'lmasligi mumkin."""

    day: date
    units: int
    revenue: Decimal
    net_profit: Decimal  # F12 (shu kun kataklari)
    profit_per_unit: Decimal | None
    price: Decimal | None  # snapshot
    commission_pct: Decimal | None  # snapshot
    stock: int | None  # snapshot: FBO + FBS


class LotOut(BaseModel):
    """Tannarx tarixi: tovarning bitta lot'i (F20) — tayyor sanasi, soni va tannarxi/dona."""

    id: UUID
    ready_on: date | None  # ``null`` — yo'lda (tayyor emas)
    qty: int
    unit_cost: Decimal
    total: Decimal
    flags: list[str]


class ReturnCauseOut(BaseModel):
    cause: str | None  # Uzum ``returnCause``; ``null`` — sabab ko'rsatilmagan
    units: int


class LinkedSkuOut(BaseModel):
    sku_id: UUID
    shop_id: UUID
    title: str | None


class LinkedItemOut(BaseModel):
    """Tovar (item) va u bilan bog'langan SKU'lar (M6: bitta jismoniy tovar — bir necha SKU)."""

    item_id: UUID
    name: str
    skus: list[LinkedSkuOut]


class StockDetailOut(BaseModel):
    active: int  # FBO ``quantityActive``
    fbs: int
    defected: int
    pending: int
    in_transit: int  # yo'ldagi (tayyor bo'lmagan) lotlar
    status: str | None  # F26 holati


class CalcDefaultsOut(BaseModel):
    """Unit kalkulyator boshlang'ich qiymatlari (F35, F36) va ularning manbasi; ``null`` — qiymat yo'q (UI so'raydi).

    Manbalar: ``price`` — ``period`` (davr o'rtachasi) | ``catalog``; ``unit_cost`` — ``last_lot`` | ``period``;
    ``logistics`` — ``last_paid`` | ``shop_typical`` (standart tarif — F40); ``commission_pct`` — ``period`` |
    ``snapshot`` | ``catalog``; ``tax_pct`` va ``ads_pct`` — ``period``."""

    price: Decimal | None
    unit_cost: Decimal | None
    logistics: Decimal | None
    packaging: Decimal
    commission_pct: Decimal | None
    tax_pct: Decimal | None
    ads_pct: Decimal | None
    sources: dict[str, str]


class SkuDetailOut(BaseModel):
    meta: Meta
    sku: SkuRowOut
    statement: StatementOut
    uzum_url: str | None
    history: list[SkuDayOut]
    lots: list[LotOut]
    returns: list[ReturnCauseOut]
    stock_detail: StockDetailOut | None
    linked: LinkedItemOut | None
    calc: CalcDefaultsOut


def _pct(value: Decimal | None) -> Decimal | None:
    return None if value is None else quantize(value * HUNDRED, 2)


@router.get("/orgs/{org_id}/skus/{sku_id}", response_model=SkuDetailOut)
async def sku_detail(
    sku_id: UUID, ctx: Finance, f: Filter, _: Heavy, request: Request
) -> SkuDetailOut:
    catalog = await sku_catalog(ctx.conn, ids=[sku_id])
    info = catalog.get(sku_id)
    if info is None:
        raise AppError("sku_not_found", 404)
    conn = ctx.conn
    book = await rc.load_book(conn, f.period)
    key = str(sku_id)
    mine = book.cells.within(f.period, lambda k: k.sku == key)
    s, daily = mine.statement(), mine.by(lambda k: k.day)
    n = (await rc.sale_sums(conn, f, sku=sku_id)).get(None, rc.SaleSums())
    stock = await load_stock(conn, [info.shop_id], f.today, {sku_id})
    st = stock.skus.get(sku_id)
    row = _row(info, s, n, st)

    d = m.sku_daily
    snaps = {
        r.day: r
        for r in await conn.execute(
            select(d.c.day, d.c.qty_active, d.c.qty_fbs, d.c.price, d.c.commission_pct).where(
                d.c.sku_id == sku_id, d.c.day >= f.period.start, d.c.day <= f.period.end
            )
        )
    }
    history = []
    for day in sorted(set(daily) | set(snaps)):
        ds, snap = daily.get(day), snaps.get(day)
        covered = ds.covered_units if ds else 0
        history.append(
            SkuDayOut(
                day=day,
                units=ds.units if ds else 0,
                revenue=ds.revenue.amount if ds else Decimal(0),
                net_profit=ds.net_profit.amount if ds else Decimal(0),
                profit_per_unit=(
                    quantize(ds.net_profit.amount / covered, 2) if ds and covered else None
                ),
                price=snap.price if snap else None,
                commission_pct=snap.commission_pct if snap else None,
                stock=(snap.qty_active or 0) + (snap.qty_fbs or 0) if snap else None,
            )
        )

    lots: list[LotOut] = []
    linked = None
    if info.item_id is not None:
        l_ = m.lots
        lots = [
            LotOut(
                id=r.id,
                ready_on=r.ready_on,
                qty=r.qty,
                unit_cost=r.unit_cost,
                total=r.total,
                flags=list(r.flags),
            )
            for r in await conn.execute(
                select(l_)
                .where(l_.c.item_id == info.item_id)
                .order_by(l_.c.ready_on.nulls_last(), l_.c.created_at, l_.c.id)
            )
        ]
        linked = await item_of(ctx, info.item_id)

    t = m.sale_items
    causes: dict[str | None, int] = defaultdict(int)
    for cause, units in await conn.execute(
        select(t.c.return_cause, func.sum(t.c.amount_returns))
        .where(
            t.c.sku_id == sku_id,
            t.c.amount_returns > 0,
            t.c.ordered_at >= day_start(f.period.start),
            t.c.ordered_at < day_start(f.period.end + timedelta(days=1)),
            func.upper(func.trim(t.c.status)).in_(statuses(StatusGroup.COMPLETED)),
        )
        .group_by(t.c.return_cause)
    ):
        causes[cause] += int(units)

    fees = await rp.load_fees(conn, f.period.end, {sku_id: info.shop_id})
    fee, fee_source = fees.of(info.shop_id, sku_id)
    u = unit_economics(s)
    org = book.cells.within(f.period).statement()
    last_lot = next((x for x in reversed(lots) if x.ready_on is not None), None)
    last_snap = next((x for x in reversed(history) if x.commission_pct is not None), None)
    sources: dict[str, str] = {}

    def pick(name: str, *options: tuple[str, Any]) -> Any:
        for source, value in options:
            if value is not None:
                sources[name] = source
                return value
        return None

    calc = CalcDefaultsOut(
        price=pick("price", ("period", amount(u.avg_price)), ("catalog", info.price)),
        # Narx qo'yish uchun — oxirgi partiya (keyingi donalar shu narxda keladi, ADR-033); bo'lmasa davr o'rtachasi.
        unit_cost=pick(
            "unit_cost",
            ("last_lot", None if last_lot is None else last_lot.unit_cost),
            ("period", amount(u.cogs_per_unit)),
        ),
        logistics=pick("logistics", (fee_source or "", amount(fee))) if fee_source else None,
        packaging=Decimal(0),
        commission_pct=pick(
            "commission_pct",
            ("period", _pct(u.commission_share)),
            ("snapshot", None if last_snap is None else last_snap.commission_pct),
            ("catalog", info.commission_pct),
        ),
        tax_pct=pick("tax_pct", ("period", _pct(effective_rate(org.tax, org.revenue)))),
        ads_pct=pick("ads_pct", ("period", _pct(u.acos))),
        sources=sources,
    )
    url = None
    if info.product_external_id is not None:
        url = request.app.state.settings.uzum_product_url.format(id=info.product_external_id)
    return SkuDetailOut(
        meta=await meta(conn, f, KINDS),
        sku=row,
        statement=StatementOut.of(s),
        uzum_url=url,
        history=history,
        lots=lots,
        returns=[
            ReturnCauseOut(cause=c, units=v)
            for c, v in sorted(causes.items(), key=lambda kv: (-kv[1], kv[0] or ""))
        ],
        stock_detail=(
            None
            if st is None
            else StockDetailOut(
                active=st.qty_active,
                fbs=st.qty_fbs,
                defected=st.qty_defected,
                pending=st.qty_pending,
                in_transit=st.in_transit,
                status=None if st.status is None else st.status.value,
            )
        ),
        linked=linked,
        calc=calc,
    )


async def item_of(ctx: OrgContext, item_id: UUID) -> LinkedItemOut | None:
    """Tovar va unga bog'langan SKU'lar (RLS ichida)."""
    name = await ctx.conn.scalar(select(m.items.c.name).where(m.items.c.id == item_id))
    if name is None:
        return None
    k = m.mp_skus
    return LinkedItemOut(
        item_id=item_id,
        name=name,
        skus=[
            LinkedSkuOut(sku_id=r.id, shop_id=r.shop_id, title=r.sku_code)
            for r in await ctx.conn.execute(
                select(k.c.id, k.c.shop_id, k.c.sku_code)
                .where(k.c.item_id == item_id)
                .order_by(k.c.shop_id, k.c.external_id)
            )
        ],
    )


# --- Unit kalkulyator (F35, F36) --------------------------------------------------------------

Sum = Annotated[Decimal, Query(ge=0, le=Decimal("1e12"))]
Percent = Annotated[Decimal, Query(ge=0, le=100)]


class UnitCalcOut(BaseModel):
    """Bir dona iqtisodi berilgan narxda; ``breakeven`` (F35) va ``target_price`` (F36) — ``null`` bo'lsa ulush
    100% dan oshgan: hech qanday narx foyda bermaydi."""

    price: Decimal
    fixed: Decimal  # F35: tannarx + logistika + qadoq
    share_pct: Decimal  # komissiya% + soliq% + reklama%
    commission: Decimal
    tax: Decimal
    ads: Decimal
    profit: Decimal
    margin: Decimal | None
    roi: Decimal | None
    breakeven: Decimal | None
    target_price: Decimal | None


@router.get("/orgs/{org_id}/unit-calc", response_model=UnitCalcOut)
async def unit_calculator(
    ctx: Finance,
    price: Sum,
    unit_cost: Sum,
    commission_pct: Percent,
    logistics: Sum = Decimal(0),
    packaging: Sum = Decimal(0),
    tax_pct: Percent = Decimal(0),
    ads_pct: Percent = Decimal(0),
    target_margin_pct: Annotated[Decimal | None, Query(ge=0, le=100)] = None,
) -> UnitCalcOut:
    del ctx  # faqat ruxsat: hisob tashkilot ma'lumotiga tayanmaydi
    c = unit_calc(
        Money(price, UZS),
        Money(unit_cost, UZS),
        Money(logistics, UZS),
        Money(packaging, UZS),
        commission_pct,
        tax_pct,
        ads_pct,
        target_margin_pct,
    )
    return UnitCalcOut(
        price=c.price.amount,
        fixed=c.fixed.amount,
        share_pct=c.share_pct,
        commission=c.commission.amount,
        tax=c.tax.amount,
        ads=c.ads.amount,
        profit=c.profit.amount,
        margin=c.margin,
        roi=c.roi,
        breakeven=amount(c.breakeven),
        target_price=amount(c.target_price),
    )

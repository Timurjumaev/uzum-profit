"""``/exports/*.xlsx``: jadvallarni Excel'ga eksport (B4.10, M14 asosi; 03 §8).

Eksport ro'yxat endpoint'ining o'zini chaqiradi (hamma sahifasini kursor bo'yicha yig'adi) — shuning uchun filtr, tartib,
rol bo'yicha yashirish (omborchi summasiz) va hisob ro'yxat bilan bir xil bo'ladi: "bitta formula — bitta joy".
Ruxsat: ``export`` (moliya jadvallari) yoki ``export_inventory`` (ombor, xaridlar) + ro'yxatning o'z ruxsati.
Yo'l ``/skus/{id}`` kabi yo'llar bilan to'qnashmasligi uchun ``/orgs/{org_id}/exports/<jadval>.xlsx``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from upcore.inventory import StockStatus
from upcore.metrics import ProfitLabel, StatusGroup
from upcore.purchasing import Stage

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission, allowed
from upapi.errors import AppError
from upapi.reports import xlsx
from upapi.reports.common import MAX_LIMIT, Filters, filters
from upapi.routes import expenses as expenses_routes
from upapi.routes import inventory as inventory_routes
from upapi.routes import purchases as purchases_routes
from upapi.routes import sales as sales_routes
from upapi.routes import skus as skus_routes

router = APIRouter(tags=["exports"])
Exporter = Annotated[OrgContext, Depends(require(Permission.EXPORT))]
StockExporter = Annotated[OrgContext, Depends(require(Permission.EXPORT_INVENTORY))]
Filter = Annotated[Filters, Depends(filters)]
MAX_PAGES = 200  # 100 000 qator: xato so'rov xotirani bosmaydi


def _need(ctx: OrgContext, permission: Permission) -> None:
    if not allowed(ctx.role, permission):
        raise AppError("forbidden", 403, detail=permission.value)


async def _all(fetch: Callable[[str | None], Awaitable[Any]]) -> list[Any]:
    """Ro'yxat endpoint'ining hamma sahifasi (``next_cursor`` bo'yicha)."""
    items: list[Any] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        page = await fetch(cursor)
        items.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return items
    raise AppError("export_too_large", 422)


def _file(name: str, data: bytes) -> Response:
    return Response(
        data,
        media_type=xlsx.XLSX_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{name}.xlsx"',
            "Cache-Control": "no-store",
        },
    )


def _period(f: Filters) -> str:
    return f"{f.period.start:%d.%m.%Y} – {f.period.end:%d.%m.%Y}"


def _span(f: Filters) -> str:
    return f"{f.period.start:%Y%m%d}-{f.period.end:%Y%m%d}"


def _shops(f: Filters) -> list[str]:
    return [f"Doʼkonlar: {len(f.shops)} ta"] if f.shops else []


def _flags(row: Any) -> str:
    return ", ".join(row.cost_flags)


SALES = [
    xlsx.Col("Sana", lambda r: r.day, "date"),
    xlsx.Col("Buyurtma", lambda r: r.order_id, "int"),
    xlsx.Col("Mahsulot (SKU)", lambda r: r.sku_title),
    xlsx.Col("Holat", lambda r: r.status),
    xlsx.Col("Guruh", lambda r: r.group.value),
    xlsx.Col("Dona", lambda r: r.amount, "int", total=True),
    xlsx.Col("Qaytgan dona", lambda r: r.amount_returns, "int", total=True),
    xlsx.Col("Narx", lambda r: r.sell_price, "money"),
    xlsx.Col("Tushum (F3)", lambda r: r.revenue, "money", total=True),
    xlsx.Col("Komissiya", lambda r: r.commission, "money", total=True),
    xlsx.Col("Logistika", lambda r: r.logistics, "money", total=True),
    xlsx.Col("Uzum toʼlovi (F6)", lambda r: r.payout, "money", total=True),
    xlsx.Col("Tannarx (F7)", lambda r: r.cogs, "money", total=True),
    xlsx.Col("Yalpi foyda (F8)", lambda r: r.gross_profit, "money", total=True),
    xlsx.Col("Tannarx belgilari", _flags),
]


@router.get("/orgs/{org_id}/exports/sales.xlsx")
async def export_sales(
    ctx: Exporter,
    f: Filter,
    group: StatusGroup | None = None,
    sku: Annotated[UUID | None, Query(description="SKU id")] = None,
    unlinked: bool = False,
) -> Response:
    _need(ctx, Permission.VIEW_FINANCE)

    async def fetch(cursor: str | None) -> Any:
        return await sales_routes.sales(ctx, f, group, sku, unlinked, MAX_LIMIT, cursor)

    rows = await _all(fetch)
    note = [_period(f), *_shops(f)]
    return _file(f"sotuvlar-{_span(f)}", xlsx.build("Sotuvlar", SALES, rows, note))


SKUS = [
    xlsx.Col("SKU", lambda r: r.title),
    xlsx.Col("Tovar", lambda r: r.product_title),
    xlsx.Col("Artikul", lambda r: r.article),
    xlsx.Col("Shtrixkod", lambda r: r.barcode),
    xlsx.Col("Narx", lambda r: r.price, "money"),
    xlsx.Col("Dona", lambda r: r.units, "int", total=True),
    xlsx.Col("Tushum (F3)", lambda r: r.revenue, "money", total=True),
    xlsx.Col("Oʼrtacha narx", lambda r: r.avg_price, "money"),
    xlsx.Col("Komissiya ulushi", lambda r: r.commission_share, "ratio"),
    xlsx.Col("Logistika/dona", lambda r: r.logistics_per_unit, "money"),
    xlsx.Col("Tannarx/dona", lambda r: r.cogs_per_unit, "money"),
    xlsx.Col("Reklama/dona", lambda r: r.ads_per_unit, "money"),
    xlsx.Col("Foyda/dona", lambda r: r.profit_per_unit, "money"),
    xlsx.Col("Sof foyda (F12)", lambda r: r.net_profit, "money", total=True),
    xlsx.Col("Bevosita xarajat", lambda r: r.expenses_direct, "money", total=True),
    xlsx.Col("Taqsimlangan xarajat", lambda r: r.expenses_allocated, "money", total=True),
    xlsx.Col("Marja (F13)", lambda r: r.margin, "ratio"),
    xlsx.Col("Tannarxsiz ulush", lambda r: r.uncovered_share, "ratio"),
    xlsx.Col("ROI (F14)", lambda r: r.roi, "ratio"),
    xlsx.Col("ACOS (F19)", lambda r: r.acos, "ratio"),
    xlsx.Col("Qaytish (F18)", lambda r: r.return_share, "ratio"),
    xlsx.Col("Bekor (F17)", lambda r: r.cancel_share, "ratio"),
    xlsx.Col("Holat", lambda r: r.label.value),
    xlsx.Col("Qoldiq", lambda r: r.stock, "int", total=True),
    xlsx.Col("Zaxira kunlari (F24)", lambda r: r.days_of_stock, "money"),
    xlsx.Col("ABC (F28)", lambda r: r.abc),
]


@router.get("/orgs/{org_id}/exports/skus.xlsx")
async def export_skus(
    ctx: Exporter,
    f: Filter,
    q: Annotated[str | None, Query(max_length=100)] = None,
    label: ProfitLabel | None = None,
    abc: Literal["A", "B", "C"] | None = None,
    sort: Annotated[str, Query(pattern=r"^-?[a-z_]+$")] = "-revenue",
) -> Response:
    _need(ctx, Permission.VIEW_FINANCE)

    async def fetch(cursor: str | None) -> Any:
        return await skus_routes.skus(ctx, f, None, q, label, abc, sort, MAX_LIMIT, cursor)

    rows = await _all(fetch)
    note = [_period(f), *_shops(f)]
    return _file(f"mahsulotlar-{_span(f)}", xlsx.build("Mahsulotlar", SKUS, rows, note))


UZUM_EXPENSES = [
    xlsx.Col("Sana", lambda r: r.day, "date"),
    xlsx.Col("Toifa", lambda r: r.category),
    xlsx.Col("Nomi", lambda r: r.name),
    xlsx.Col("Turi", lambda r: r.type),
    xlsx.Col("Summa (F9, ishorali)", lambda r: r.amount, "money", total=True),
    xlsx.Col("Holat", lambda r: r.status),
    xlsx.Col("P&Lʼga kirdi", lambda r: r.in_pnl, "bool"),
    xlsx.Col("Kirmagan sababi", lambda r: r.excluded),
    xlsx.Col("Buyurtma", lambda r: r.order_id, "int"),
]
OWN_EXPENSES = [
    xlsx.Col("Toifa", lambda r: r.category),
    xlsx.Col("Qamrov", lambda r: r.scope),
    xlsx.Col("Boshlanishi", lambda r: r.start_on, "date"),
    xlsx.Col("Tugashi", lambda r: r.end_on, "date"),
    xlsx.Col("Summa", lambda r: r.amount, "money", total=True),
    xlsx.Col("Davrga toʼgʼri keladigani (F10)", lambda r: r.in_period, "money", total=True),
    xlsx.Col("Takrorlanish", lambda r: r.recurrence),
    xlsx.Col("Izoh", lambda r: r.note),
]


@router.get("/orgs/{org_id}/exports/expenses.xlsx")
async def export_expenses(
    ctx: Exporter,
    f: Filter,
    kind: Literal["uzum", "own"] = "uzum",
    category: Annotated[str | None, Query(description="Uzum toifasi")] = None,
    include_excluded: bool = False,
) -> Response:
    _need(ctx, Permission.VIEW_SETTINGS)
    note = [_period(f), *_shops(f)]
    if kind == "own":
        # O'z xarajatlari bitta javobda keladi (sahifalanmaydi) — bitta chaqiruv yetadi.
        page = await expenses_routes.expenses(ctx, f, None, False, 1, None)
        data = xlsx.build("Oʼz xarajatlarim", OWN_EXPENSES, page.own_items, note)
        return _file(f"oz-xarajatlar-{_span(f)}", data)

    async def fetch(cursor: str | None) -> Any:
        return await expenses_routes.expenses(ctx, f, category, include_excluded, MAX_LIMIT, cursor)

    rows = await _all(fetch)
    data = xlsx.build("Uzum xarajatlari", UZUM_EXPENSES, rows, note)
    return _file(f"uzum-xarajatlari-{_span(f)}", data)


def _purchase_cols(amounts: bool) -> list[xlsx.Col]:
    cols = [
        xlsx.Col("Xarid", lambda r: r.title),
        xlsx.Col("Bosqich", lambda r: r.stage.value),
        xlsx.Col("Yetkazib beruvchi", lambda r: r.supplier_name),
        xlsx.Col("Kargo", lambda r: r.carrier_name),
        xlsx.Col("Tovarlar", lambda r: r.items),
        xlsx.Col("Qatorlar", lambda r: r.line_count, "int", total=True),
        xlsx.Col("Buyurtma (dona)", lambda r: r.units_ordered, "int", total=True),
        xlsx.Col("Qabul (dona)", lambda r: r.units_received, "int", total=True),
    ]
    if amounts:  # omborchi summasiz (03 §10)
        cols += [
            xlsx.Col("Jami (F20)", lambda r: r.total, "money", total=True),
            xlsx.Col("Dona tannarxi", lambda r: r.unit_cost, "money"),
        ]
    cols += [
        xlsx.Col("Belgilar", lambda r: r.flags),
        xlsx.Col("Izoh", lambda r: r.note),
        xlsx.Col("Yaratildi", lambda r: r.created_at, "datetime"),
    ]
    return cols


@router.get("/orgs/{org_id}/exports/purchases.xlsx")
async def export_purchases(
    ctx: StockExporter, stage: Annotated[list[Stage] | None, Query()] = None
) -> Response:
    _need(ctx, Permission.VIEW_PURCHASES)
    page = await purchases_routes.list_purchases(ctx, stage)
    data = xlsx.build("Xaridlar", _purchase_cols(page.amounts), page.items)
    return _file("xaridlar", data)


def _stock_cols(amounts: bool) -> list[xlsx.Col]:
    cols = [
        xlsx.Col("SKU", lambda r: r.title),
        xlsx.Col("Tovar", lambda r: r.product_title),
        xlsx.Col("FBO", lambda r: r.locations.fbo, "int", total=True),
        xlsx.Col("FBS", lambda r: r.locations.fbs, "int", total=True),
        xlsx.Col("Brak", lambda r: r.locations.defected, "int", total=True),
        xlsx.Col("Kutilayotgan", lambda r: r.locations.pending, "int", total=True),
        xlsx.Col("Xitoyda", lambda r: r.locations.china, "int", total=True),
        xlsx.Col("Yoʼlda", lambda r: r.locations.road, "int", total=True),
        xlsx.Col("Oʼz omborimda", lambda r: r.locations.own, "int", total=True),
        xlsx.Col("Postavkada", lambda r: r.locations.inbound, "int", total=True),
        xlsx.Col("Sotuv tezligi (F23, dona/kun)", lambda r: r.velocity.value, "money"),
        xlsx.Col("Zaxira kunlari (F24)", lambda r: r.days_of_stock, "money"),
        xlsx.Col("Holat (F26)", lambda r: r.status.value if r.status else None),
        xlsx.Col("ABC (F28)", lambda r: r.abc),
        xlsx.Col("Nelikvid (F30)", lambda r: r.liquidity),
        xlsx.Col("Buyurtma sanasi (F27)", lambda r: r.order_by.day if r.order_by else None, "date"),
        xlsx.Col("Tavsiya miqdor (F27)", lambda r: r.reorder.qty if r.reorder else None, "int"),
    ]
    if amounts:
        cols += [
            xlsx.Col("Lot narxi", lambda r: r.unit_cost, "money"),
            xlsx.Col("Qoldiq qiymati", lambda r: r.stock_value, "money", total=True),
        ]
    return cols


@router.get("/orgs/{org_id}/exports/inventory.xlsx")
async def export_inventory(
    ctx: StockExporter,
    shop: Annotated[list[UUID] | None, Query(description="Do'konlar")] = None,
    as_of: Annotated[date | None, Query(description="Qaysi kun holatiga")] = None,
    status: StockStatus | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    _need(ctx, Permission.VIEW_PURCHASES)
    amounts = allowed(ctx.role, Permission.VIEW_PURCHASE_AMOUNTS)
    day: date | None = None

    async def fetch(cursor: str | None) -> Any:
        nonlocal day
        page = await inventory_routes.inventory(
            ctx, None, shop, as_of, status, q, MAX_LIMIT, cursor
        )
        day = page.as_of
        return page

    rows = await _all(fetch)
    note = [f"Holat: {day:%d.%m.%Y}"] if day else []
    data = xlsx.build("Ombor", _stock_cols(amounts), rows, note)
    return _file(f"ombor-{day:%Y%m%d}" if day else "ombor", data)

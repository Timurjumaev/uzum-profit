"""``/opening/costs``: tannarxni Excel orqali kiritish (B7.1, M2 5-qadam (b); ADR-065). Yagona import.

Aylanma: Boshlang'ich holat jadvali Excel'ga yuklab olinadi (``GET …/costs.xlsx`` — ID, do'kon, SKU, shtrix-kod, nom, qoldiq,
hozirgi tannarx va to'ldiriladigan "Tannarx, so'm" ustuni) → sotuvchi faqat shu ustunni yozadi → ``POST …/preview`` faylni
o'qib **nima o'zgarishini** ko'rsatadi (yangi / o'zgaradi eski → yangi / xato — qator va sabab; hech narsa yozilmaydi) →
``POST …/apply`` tasdiqlangan o'zgarishlarni bitta tranzaksiyada saqlaydi. Bo'sh katak tegilmaydi; o'sha faylni qayta yuklash
hech narsani o'zgartirmaydi (``same``). "Tannarx" — tovarning **boshidan** amal qiladigan narxi (``item_costs.valid_from`` bo'sh);
davrli narxlar (sana bilan) tegilmaydi.

Qator kaliti — fayldagi ID (``item:<uuid>`` yoki tovarga bog'lanmagan ``sku:<uuid>``); ID bo'sh bo'lsa zaxira — shtrix-kod
(do'kon nomi bilan toraytirilib), bir ma'noli bo'lmasa — xato (taxmin bilan bog'lanmaydi).

Xavfsizlik (ilovadagi birinchi fayl yuklash): faqat ``.xlsx`` (zip imzosi), ≤ 5 MB, ≤ 20 000 qator, zip ichi hajmi va yozuvlari
cheklangan (zip-bomba), ``read_only`` va ``data_only`` o'qish (formulalar hisoblanmaydi — faqat saqlangan qiymat), fayl diskka
yozilmaydi (xotirada), daqiqasiga cheklov, audit jurnali; ruxsat — ``manage_settings``. Fayl multipart emas, to'g'ridan-to'g'ri
tana (``Content-Type`` — xlsx).
"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports.xlsx import XLSX_TYPE, safe_text
from upapi.routes.items import item_of_sku
from upapi.routes.opening import Cost, _read
from upapi.routes.purchases import _kick

router = APIRouter(tags=["costing"])
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
MAX_ZIP_ENTRIES = 200
MAX_ZIP_UNPACKED = 80 * 1024 * 1024  # ochilgandagi umumiy hajm (zip-bomba)
LIMIT_PER_MINUTE = 10
HEADERS = ("ID", "Doʻkon", "SKU", "Shtrix-kod", "Nom", "Qoldiq", "Hozirgi tannarx", "Tannarx, soʻm")
ID_COL, BARCODE_COL, COST_COL = 0, 3, 7
MAX_ERRORS = 200


class CostChangeOut(BaseModel):
    key: str
    row: int  # fayldagi qator raqami
    name: str
    old: Decimal | None  # hozirgi tannarx (yo'q — yangi)
    new: Decimal


class CostRowErrorOut(BaseModel):
    row: int
    reason: str


class CostPreviewOut(BaseModel):
    new: int
    changed: int  # mavjud narx ustidan yoziladi (ko'rib chiqishda alohida ko'rsatiladi, tamoyil 7)
    same: int  # o'zgarmaydi
    empty: int  # bo'sh katak — tegilmaydi
    errors: list[CostRowErrorOut]
    error_count: int
    changes: list[CostChangeOut]


class CostChangeIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    unit_cost: Cost


class CostApplyIn(BaseModel):
    changes: Annotated[list[CostChangeIn], Field(min_length=1, max_length=MAX_ROWS)]


class CostApplyOut(BaseModel):
    saved: int
    unchanged: int


def parse_cost(raw: Any) -> Decimal | None:
    """Katak → tannarx: bo'sh — ``None`` (tegilmaydi); ``12 500``, ``12500,50``, ``12 500.5`` bir xil o'qiladi; manfiy, matn,
    formula xatosi (``#REF!``) — ``ValueError`` (sabab matni bilan)."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("son emas")
    if isinstance(raw, (int, float, Decimal)):
        text = format(Decimal(str(raw)), "f")
    else:
        text = "".join(str(raw).split())  # hamma bo'shliq (NBSP, ingichka ham)
        if text == "":
            return None
        if text.startswith("#"):
            raise ValueError(f"formula xatosi ({text})")
        if "," in text and "." in text:
            raise ValueError("vergul va nuqta birga — noaniq")
        text = text.replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("son emas") from None
    if not value.is_finite():
        raise ValueError("son emas")
    if value < 0:
        raise ValueError("manfiy bo'lmaydi")
    if value > Decimal("1e12"):
        raise ValueError("juda katta")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("kasr — ko'pi bilan 2 xona")
    return value.quantize(Decimal("0.01"))


def check_zip(data: bytes) -> None:
    """Fayl haqiqiy ``.xlsx`` (zip) va ochilganda hajmi chegarada (zip-bomba)."""
    if data[:2] != b"PK":
        raise AppError("bad_file", 422, detail="faqat .xlsx fayl")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_UNPACKED:
                raise AppError("bad_file", 422, detail="fayl juda katta (ochilganda)")
            if not any(i.filename == "xl/workbook.xml" for i in infos):
                raise AppError("bad_file", 422, detail="faqat .xlsx fayl")
    except zipfile.BadZipFile:
        raise AppError("bad_file", 422, detail="fayl buzilgan yoki .xlsx emas") from None


def read_sheet(data: bytes) -> list[tuple[int, list[Any]]]:
    """Birinchi varaq qatorlari ``(raqam, katakchalar)``; sarlavha tekshiriladi. Formulalar hisoblanmaydi (``data_only``)."""
    check_zip(data)
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise AppError("bad_file", 422, detail="fayl o'qilmadi") from None
    try:
        ws = wb.worksheets[0]
        rows: list[tuple[int, list[Any]]] = []
        for n, values in enumerate(ws.iter_rows(max_row=MAX_ROWS + 2, values_only=True), 1):
            if n > MAX_ROWS + 1:
                raise AppError("bad_file", 422, detail=f"qator {MAX_ROWS} dan oshmasin")
            rows.append((n, list(values)))
    finally:
        wb.close()
    if not rows:
        raise AppError("bad_template", 422, detail="fayl bo'sh")
    head = [str(c).strip() if c is not None else "" for c in rows[0][1]]
    if head[: len(HEADERS)] != list(HEADERS):
        raise AppError("bad_template", 422, detail="shablon emas — jadvalni ilovadan yuklab oling")
    return rows[1:]


async def _targets(ctx: OrgContext) -> dict[str, dict[str, Any]]:
    """Fayldagi kalitlar: ``item:<id>`` va tovarsiz ``sku:<id>`` — nom va hozirgi (boshidan) tannarx."""
    conn = ctx.conn
    out: dict[str, dict[str, Any]] = {}
    base: dict[UUID, Decimal] = {
        r.item_id: r.unit_cost
        for r in await conn.execute(
            select(m.item_costs.c.item_id, m.item_costs.c.unit_cost).where(
                m.item_costs.c.valid_from.is_(None)
            )
        )
    }
    for r in await conn.execute(select(m.items.c.id, m.items.c.name)):
        out[f"item:{r.id}"] = {"name": r.name, "old": base.get(r.id)}
    for sku in await conn.execute(
        select(m.mp_skus.c.id, m.mp_skus.c.sku_code, m.mp_skus.c.item_id)
    ):
        if sku.item_id is None:
            out[f"sku:{sku.id}"] = {
                "name": sku.sku_code or "—",
                "old": None,
                "canon": f"sku:{sku.id}",
            }
        elif f"item:{sku.item_id}" in out:
            # Tovarga bog'langan SKU: eski fayldagi ``sku:`` kaliti (tovar keyin yaratilgan) shu tovarga olib boradi.
            out[f"sku:{sku.id}"] = {**out[f"item:{sku.item_id}"], "canon": f"item:{sku.item_id}"}
    for key, value in list(out.items()):
        value.setdefault("canon", key)
    return out


async def _by_barcode(ctx: OrgContext) -> dict[str, list[tuple[str, str]]]:
    """Shtrix-kod → [(kalit, do'kon nomi)] — ID bo'sh qatorlar uchun zaxira."""
    shops = {r.id: (r.alias or r.name) for r in await ctx.conn.execute(select(m.shops))}
    k = m.mp_skus
    out: dict[str, list[tuple[str, str]]] = {}
    for r in await ctx.conn.execute(select(k.c.id, k.c.item_id, k.c.barcode, k.c.shop_id)):
        if not r.barcode:
            continue
        key = f"item:{r.item_id}" if r.item_id else f"sku:{r.id}"
        out.setdefault(str(r.barcode).strip(), []).append((key, shops.get(r.shop_id, "")))
    return out


@router.get("/orgs/{org_id}/opening/costs.xlsx")
async def costs_template(ctx: Manager) -> Response:
    """Boshlang'ich holat jadvali Excel'da: faqat "Tannarx, so'm" to'ldiriladi (hozirgi narx oldindan yozilgan)."""
    opening = await _read(ctx, None, None)
    k = m.mp_skus
    sku_rows: dict[str, list[Any]] = {}
    shops = {r.id: (r.alias or r.name) for r in await ctx.conn.execute(select(m.shops))}
    for r in await ctx.conn.execute(
        select(k.c.id, k.c.item_id, k.c.sku_code, k.c.barcode, k.c.shop_id).order_by(k.c.sku_code)
    ):
        key = f"item:{r.item_id}" if r.item_id else f"sku:{r.id}"
        sku_rows.setdefault(key, []).append(r)
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tannarx"
    ws.append(list(HEADERS))
    for n in range(1, len(HEADERS) + 1):
        c = ws.cell(1, n)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="FFE9C2" if n == len(HEADERS) else "E7ECEA")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for row in opening.rows:
        key = f"item:{row.item_id}" if row.item_id else f"sku:{row.sku_id}"
        items = sku_rows.get(key, [])
        shop_names = sorted({shops.get(i.shop_id, "") for i in items} - {""})
        base = next((p.unit_cost for p in row.prices if p.valid_from is None), None)
        qty = (row.uzum_qty or 0) + (row.own_qty or 0) if row.uzum_qty is not None else None
        ws.append(
            [
                key,
                safe_text(", ".join(shop_names)),
                safe_text(", ".join(row.skus)),
                safe_text(", ".join(str(i.barcode) for i in items if i.barcode)),
                safe_text(row.name),
                qty,
                float(base) if base is not None else None,
                float(base) if base is not None else None,
            ]
        )
    ws.column_dimensions["A"].hidden = True  # yashirin ichki id — qator kaliti
    for n, w in {2: 18, 3: 28, 4: 18, 5: 36, 6: 10, 7: 16, 8: 18}.items():
        ws.column_dimensions[get_column_letter(n)].width = w
    for line in range(2, ws.max_row + 1):
        for col in (7, 8):
            ws.cell(line, col).number_format = "#,##0.##"
    ws.freeze_panes = "B2"
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": 'attachment; filename="tannarx.xlsx"'},
    )


async def _upload(ctx: OrgContext, request: Request) -> bytes:
    """So'rov tanasi (xlsx), ``MAX_BYTES`` dan oshsa o'qish to'xtaydi; daqiqasiga cheklov."""
    limiter = request.app.state.import_limiter
    if not limiter.hit(f"{ctx.org_id}:{ctx.user.user_id}"):
        raise AppError("too_many_requests", 429, detail="bir daqiqada juda ko'p yuklash — kuting")
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BYTES:
        raise AppError("file_too_large", 413, detail="fayl 5 MB dan katta")
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise AppError("file_too_large", 413, detail="fayl 5 MB dan katta")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise AppError("bad_file", 422, detail="fayl bo'sh")
    return data


@router.post("/orgs/{org_id}/opening/costs/preview", response_model=CostPreviewOut)
async def costs_preview(ctx: Manager, request: Request) -> CostPreviewOut:
    """Faylni o'qib, nima o'zgarishini ko'rsatadi (hech narsa yozilmaydi)."""
    data = await _upload(ctx, request)
    sheet = read_sheet(data)
    targets = await _targets(ctx)
    barcodes = await _by_barcode(ctx)
    errors: list[CostRowErrorOut] = []
    error_count = 0
    changes: list[CostChangeOut] = []
    seen: dict[str, int] = {}
    new = changed = same = empty = 0

    def fail(row: int, reason: str) -> None:
        nonlocal error_count
        error_count += 1
        if len(errors) < MAX_ERRORS:
            errors.append(CostRowErrorOut(row=row, reason=reason))

    for n, cells in sheet:
        cells = cells + [None] * (len(HEADERS) - len(cells))
        if all(c is None or str(c).strip() == "" for c in cells):
            continue
        try:
            cost = parse_cost(cells[COST_COL])
        except ValueError as e:
            fail(n, f"Tannarx: {e}")
            continue
        if cost is None:
            empty += 1
            continue
        key = str(cells[ID_COL]).strip() if cells[ID_COL] is not None else ""
        if key == "":
            code = str(cells[BARCODE_COL]).strip() if cells[BARCODE_COL] is not None else ""
            found = barcodes.get(code, []) if code else []
            shop = str(cells[1]).strip() if cells[1] is not None else ""
            if shop:
                found = [f for f in found if f[1] == shop] or found
            keys = {f[0] for f in found}
            if len(keys) != 1:
                fail(n, "ID yo'q va shtrix-kod bo'yicha bir ma'noli topilmadi")
                continue
            key = next(iter(keys))
        target = targets.get(key)
        if target is None:
            fail(n, "tovar topilmadi (ID eskirgan yoki boshqa tashkilotniki)")
            continue
        key = target["canon"]
        if key in seen:
            fail(n, f"tovar ikki marta berilgan (qator {seen[key]})")
            continue
        seen[key] = n
        old: Decimal | None = target["old"]
        if old is not None and Decimal(old) == cost:
            same += 1
            continue
        if old is None:
            new += 1
        else:
            changed += 1
        changes.append(CostChangeOut(key=key, row=n, name=target["name"], old=old, new=cost))
    return CostPreviewOut(
        new=new,
        changed=changed,
        same=same,
        empty=empty,
        errors=errors,
        error_count=error_count,
        changes=changes,
    )


@router.post("/orgs/{org_id}/opening/costs/apply", response_model=CostApplyOut)
async def costs_apply(
    body: CostApplyIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> CostApplyOut:
    """Ko'rib chiqilgan o'zgarishlarni bitta tranzaksiyada saqlaydi; tovarsiz SKU uchun tovar yaratiladi. Takror — jim."""
    conn, ic = ctx.conn, m.item_costs
    targets = await _targets(ctx)
    unknown = [c.key for c in body.changes if c.key not in targets]
    if unknown:
        raise AppError("item_not_found", 404, detail="tovar topilmadi")
    keys = [targets[c.key]["canon"] for c in body.changes]
    if len(set(keys)) != len(keys):
        raise AppError("duplicate_item", 422, detail="tovar ikki marta berilgan")
    saved = unchanged = 0
    touched: list[UUID] = []
    for change, canon in zip(body.changes, keys, strict=True):
        old = targets[change.key]["old"]
        if old is not None and Decimal(old) == change.unit_cost:
            unchanged += 1
            continue
        kind, _, raw = canon.partition(":")
        item_id = UUID(raw) if kind == "item" else await item_of_sku(ctx, UUID(raw))
        stmt = pg_insert(ic).values(
            org_id=ctx.org_id, item_id=item_id, valid_from=None, unit_cost=change.unit_cost
        )
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["org_id", "item_id", "valid_from"],
                set_={"unit_cost": change.unit_cost},
            )
        )
        await ctx.audit(
            "opening.import",
            "item",
            item_id,
            before={"unit_cost": None if old is None else str(old)},
            after={"unit_cost": str(change.unit_cost)},
        )
        touched.append(item_id)
        saved += 1
    for item_id in touched:
        await calc.request(conn, ctx.org_id, calc.Scope.ITEM, item_id)
    if touched:
        background.add_task(_kick, request, ctx.org_id)
    return CostApplyOut(saved=saved, unchanged=unchanged)

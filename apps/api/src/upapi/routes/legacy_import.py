"""``/imports/legacy``: legacy ``uzum.db`` → xaridlar (B4.9, 03 §16) va solishtirma hisobot.

Sotuvchi faylni Sozlamalar → "Legacy import" da tanlaydi; brauzer uni xom bayt sifatida yuboradi
(``application/octet-stream``). Avval ``dry_run=true`` — hech narsa yozilmaydi, lekin hisobot haqiqiy yo'l bilan
olinadi: xaridlar savepoint ichida yaratiladi, birlik tannarx (F20) xarid sahifasidagi kabi bazadan hisoblanadi, keyin
savepoint bekor qilinadi. Tasdiqlansa — xuddi shu narsa yoziladi va hisob ishi navbatga qo'yiladi (lotlar → sotuvlar).

Ko'chirish qoidasi — :mod:`upcore.legacy` (``batches`` → ``purchases``, ``batch_lines`` → ``purchase_lines``,
tovar/kargo/qo'shimcha → ``cost_components``, kurslar qo'lda kurs sifatida saqlanadi). Qatorning SKU kodi shu do'kon
(``shops.external_id`` = legacy ``shop_id``) SKU'si bilan (``sku_code``, katta-kichik harfsiz) bog'lanadi: SKU tovarga
bog'langan bo'lsa — o'sha tovar, bog'lanmagan bo'lsa — SKU nomi bilan yangi tovar yaratilib bog'lanadi; SKU topilmasa
qator "yangi tovar" (vaqtinchalik nom) bo'lib qoladi va hisobotda ko'rsatiladi.

Bosqich sanalari: buyurtma va to'lov — partiya sanasi; kargo kiritilgan partiya — "Uzumga yuborildi" (kargo sanasi):
legacy faqat Uzum qoldig'ini yuritgan, aks holda eski partiya o'z omborimda turib qolardi (B4.7 qarori). Kargo
kiritilmagan partiya — "To'landi" (yo'lda). Qo'shimcha chiqim nomlari xarid izohiga yoziladi.

Qayta yuklash xavfsiz: ``legacy_batch_id`` bo'yicha bor partiya qayta yaratilmaydi va o'zgartirilmaydi (tamoyil 7) —
hisobotda joriy xarid bilan solishtiriladi. Ruxsat: ``manage_settings`` va summalar (egasi, menejer); audit.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, insert, select, text, update
from upcore.legacy import LegacyBatch, legacy_unit_costs, to_purchase, tolerance, worst_difference
from upcore.money import round_rate
from upcore.purchasing import Stage, current_stage

from upapi import calc, legacyfile
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission, allowed
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import purchases as rp
from upapi.reports.common import today
from upapi.routes.purchases import _kick, _plain

router = APIRouter(tags=["settings"])
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
CENT = Decimal("0.01")


class LegacyShopOut(BaseModel):
    legacy_id: int
    name: str
    connected: bool  # shu Uzum do'koni tashkilotga ulanganmi (SKU'lar shu do'kondan qidiriladi)


class LegacyLineOut(BaseModel):
    name: str  # SKU kodi yoki vaqtinchalik nom
    qty: int
    item_name: str | None  # bog'langan tovar; ``null`` — "yangi tovar" bo'lib qoldi
    legacy_unit_cost: Decimal | None
    new_unit_cost: Decimal | None
    difference: Decimal | None


class LegacyBatchOut(BaseModel):
    """Bitta partiya: ``status`` — ``created`` (yaratildi / yaratiladi), ``exists`` (oldin ko'chirilgan — tegilmadi),
    ``error`` (o'qib yoki hisoblab bo'lmadi). ``match`` — hamma qator birlik tannarxi 1 tiyingacha bir xil
    (``null`` — solishtiradigan dona yo'q)."""

    legacy_id: int
    title: str
    day: date | None
    shop: str | None
    status: str
    purchase_id: UUID | None
    stage: str | None
    units: int
    total_legacy: Decimal | None
    total_new: Decimal | None
    worst_difference: Decimal | None
    match: bool | None
    new_items: int  # SKU bog'lanmagan edi — yangi tovar yaratildi
    unmatched: list[str]  # SKU topilmadi — "yangi tovar" bo'lib qoldi
    warnings: list[str]
    lines: list[LegacyLineOut]


class LegacyImportOut(BaseModel):
    dry_run: bool
    shops: list[LegacyShopOut]
    created: int
    existing: int
    errors: int
    mismatched: int  # birlik tannarxi legacy'dan farq qilgan partiyalar
    batches: list[LegacyBatchOut]


@dataclass
class _Sku:
    id: UUID
    shop_id: UUID
    sku_code: str
    item_id: UUID | None


@dataclass
class _Created:
    purchase_id: UUID
    new_items: int
    unmatched: list[str]
    item_names: list[str | None]


def _title(batch: LegacyBatch) -> str:
    return batch.title or f"Legacy #{batch.id}"


def _note(batch: LegacyBatch) -> str | None:
    parts = [batch.note] if batch.note else []
    extras = [f"{e.name}: {e.amount.quantize(CENT):f} so'm" for e in batch.extras if e.amount]
    if extras:
        parts.append("Qo'shimcha chiqimlar: " + "; ".join(extras))
    parts.append(f"Legacy partiya #{batch.id} dan ko'chirildi")
    return "\n".join(parts)


async def _skus(ctx: OrgContext, shop_external: dict[int, UUID]) -> dict[tuple[int, str], _Sku]:
    k = m.mp_skus
    by_shop = {v: e for e, v in shop_external.items()}
    out: dict[tuple[int, str], _Sku] = {}
    if not by_shop:
        return out
    for r in await ctx.conn.execute(
        select(k.c.id, k.c.shop_id, k.c.sku_code, k.c.item_id)
        .where(k.c.shop_id.in_(list(by_shop)), k.c.sku_code.is_not(None))
        .order_by(k.c.external_id)
    ):
        key = (by_shop[r.shop_id], r.sku_code.strip().lower())
        out.setdefault(key, _Sku(r.id, r.shop_id, r.sku_code, r.item_id))
    return out


async def _create(
    ctx: OrgContext, batch: LegacyBatch, skus: dict[tuple[int, str], _Sku]
) -> _Created:
    """Bitta partiyani yozadi (``to_purchase`` qoidasi bilan)."""
    migration = to_purchase(batch)
    model = migration.purchase
    ready = model.cargo_paid_date
    p, pl, cc, k = m.purchases, m.purchase_lines, m.cost_components, m.mp_skus
    dates = {Stage.ORDERED: batch.day, Stage.PAID: batch.day, Stage.SENT_TO_UZUM: ready}
    purchase_id = await ctx.conn.scalar(
        insert(p)
        .values(
            org_id=ctx.org_id,
            title=_title(batch)[:200],
            note=_note(batch),
            legacy_batch_id=batch.id,
            ordered_on=batch.day,
            paid_on=batch.day,
            sent_to_uzum_on=ready,
            status=current_stage(dates).value,
        )
        .returning(p.c.id)
    )
    assert purchase_id is not None
    created = _Created(purchase_id, 0, [], [])
    line_ids: dict[str, UUID] = {}
    for legacy, line in zip(batch.lines, model.lines, strict=True):
        item_id = None
        temp_name: str | None = legacy.label or legacy.sku or "Nomsiz tovar"
        sku = (
            skus.get((batch.shop_id, legacy.sku.strip().lower()))
            if legacy.sku and batch.shop_id is not None
            else None
        )
        if sku is not None:
            item_id = sku.item_id
            if item_id is None:
                item_id = await ctx.conn.scalar(
                    insert(m.items)
                    .values(org_id=ctx.org_id, name=sku.sku_code)
                    .returning(m.items.c.id)
                )
                await ctx.conn.execute(
                    update(k).where(k.c.id == sku.id).values(item_id=item_id, updated_at=func.now())
                )
                await ctx.audit(
                    "sku.link_item",
                    "sku",
                    sku.id,
                    before={"item_id": None},
                    after={"item_id": str(item_id), "mode": "legacy_import"},
                )
                sku.item_id = item_id  # shu fayldagi keyingi partiyalar o'sha tovarni oladi
                await calc.request(ctx.conn, ctx.org_id, calc.Scope.SHOP, sku.shop_id)
                created.new_items += 1
            temp_name = None
        elif legacy.sku:
            created.unmatched.append(legacy.sku)
        created.item_names.append(sku.sku_code if sku is not None else None)
        line_id = await ctx.conn.scalar(
            insert(pl)
            .values(
                org_id=ctx.org_id,
                purchase_id=purchase_id,
                item_id=item_id,
                temp_name=None if temp_name is None else temp_name[:200],
                variant=legacy.label if item_id is not None else None,
                ordered_qty=line.ordered_qty,
                received_qty=line.received_qty,
                unit_price=None if line.unit_price is None else line.unit_price.amount,
                currency=None if line.unit_price is None else line.unit_price.currency.value,
                created_at=func.clock_timestamp(),  # qatorlar tartibi legacy bilan bir xil qolsin
            )
            .returning(pl.c.id)
        )
        assert line_id is not None
        line_ids[line.id] = line_id
    for comp in model.components:
        manual = comp.rate is not None
        await ctx.conn.execute(
            insert(cc).values(
                org_id=ctx.org_id,
                purchase_id=purchase_id,
                kind=comp.kind.value,
                amount=comp.amount.amount,
                currency=comp.amount.currency.value,
                paid_on=comp.rate.day if comp.rate is not None else batch.day,
                rate_mode="manual" if manual else "cbu",
                rate=round_rate(comp.rate.rate) if comp.rate is not None else None,
                allocation=comp.base.value,
                targets=(
                    None
                    if comp.line_ids is None
                    else {"lines": [str(line_ids[x]) for x in comp.line_ids]}
                ),
                created_at=func.clock_timestamp(),
            )
        )
    await ctx.audit(
        "purchase.import_legacy",
        "purchase",
        purchase_id,
        after=_plain(
            {
                "legacy_batch_id": batch.id,
                "lines": len(batch.lines),
                "components": len(model.components),
                "new_items": created.new_items,
                "unmatched": created.unmatched,
            }
        ),
    )
    await calc.request(ctx.conn, ctx.org_id, calc.Scope.PURCHASE, purchase_id)
    return created


async def _report(
    ctx: OrgContext,
    batch: LegacyBatch,
    purchase_id: UUID,
    status: str,
    shop: str | None,
    created: _Created | None,
    warnings: list[str],
) -> LegacyBatchOut:
    """Legacy formulasi ↔ bazadagi xaridning jonli hisobi (xarid sahifasidagi bilan bir xil yo'l, F20)."""
    book = await rp.Book(ctx.conn, today()).load(purchase_id)
    row = book.purchases[0]
    lines = book.lines.get(purchase_id, [])
    ev = book.evaluate(row)
    if ev.error:
        warnings = [*warnings, f"yangi hisob: {ev.error}"]
    new_cost = {lot.line_id: lot.unit_cost.amount if lot.unit_cost else None for lot in ev.lots}
    legacy = legacy_unit_costs(batch)
    comparable = len(lines) == len(batch.lines) and not ev.error
    if not comparable and status == "exists":
        warnings = [*warnings, "xarid qatorlari o'zgartirilgan — qatorma-qator solishtirilmadi"]
    out_lines = []
    pairs: list[tuple[Decimal, Decimal | None]] = []
    good = True
    priced_lines = sum(x.qty > 0 for x in batch.lines)
    components = len(book.components.get(purchase_id, []))
    for i, x in enumerate(batch.lines):
        old = legacy[i] if legacy else None
        new = new_cost.get(str(lines[i].id)) if comparable else None
        if comparable and x.qty > 0 and old is not None:
            pairs.append((old, new))
            limit = tolerance(x.qty, priced_lines, components)
            good &= new is not None and abs(new - old) <= limit
        name = created.item_names[i] if created else None
        if name is None and comparable and lines[i].item_id is not None:
            item = book.items.get(lines[i].item_id)
            name = item.name if item else None
        out_lines.append(
            LegacyLineOut(
                name=x.sku or x.label or "—",
                qty=x.qty,
                item_name=name,
                legacy_unit_cost=None if old is None else old.quantize(CENT),
                new_unit_cost=None if new is None else new.quantize(CENT),
                difference=None if old is None or new is None else (new - old).quantize(CENT),
            )
        )
    worst = worst_difference([a for a, _ in pairs], [b for _, b in pairs]) if pairs else None
    units = sum(x.qty for x in batch.lines)
    total_legacy = sum((a * x.qty for a, x in zip(legacy, batch.lines, strict=True)), Decimal(0))
    total_new = sum((lot.total.amount for lot in ev.lots), Decimal(0)) if not ev.error else None
    return LegacyBatchOut(
        legacy_id=batch.id,
        title=_title(batch),
        day=batch.day,
        shop=shop,
        status=status,
        purchase_id=purchase_id,
        stage=row.status,
        units=units,
        total_legacy=total_legacy.quantize(CENT) if legacy else None,
        total_new=None if total_new is None else total_new.quantize(CENT),
        worst_difference=None if worst is None else worst.quantize(CENT),
        match=None if worst is None else good,
        new_items=created.new_items if created else 0,
        unmatched=created.unmatched if created else [],
        warnings=warnings,
        lines=out_lines,
    )


@router.post(
    "/orgs/{org_id}/imports/legacy",
    response_model=LegacyImportOut,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def import_legacy(
    ctx: Manager,
    request: Request,
    background: BackgroundTasks,
    dry_run: Annotated[bool, Query()] = True,
) -> LegacyImportOut:
    """Legacy ``uzum.db`` ni o'qib partiyalarni xarid qiladi (``dry_run`` — faqat hisobot) va solishtiradi."""
    if not allowed(
        ctx.role, Permission.VIEW_PURCHASE_AMOUNTS
    ):  # pragma: no cover - matritsada doim bor
        raise AppError("forbidden", 403, detail=Permission.VIEW_PURCHASE_AMOUNTS.value)
    data = await request.body()
    try:
        parsed = await asyncio.to_thread(legacyfile.read, data)
    except legacyfile.LegacyFileError as exc:
        raise AppError("bad_legacy_file", 422, detail=str(exc)) from None

    s = m.shops
    shop_ids = {
        r.external_id: r.id for r in await ctx.conn.execute(select(s.c.id, s.c.external_id))
    }
    names = dict(parsed.shops)
    # Bir vaqtda ikki import bir partiyani ikki marta yaratmasin.
    await ctx.conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"legacy-import:{ctx.org_id}"},
    )
    p = m.purchases
    existing = {
        r.legacy_batch_id: r.id
        for r in await ctx.conn.execute(
            select(p.c.legacy_batch_id, p.c.id)
            .where(p.c.legacy_batch_id.is_not(None))
            .order_by(p.c.created_at)
        )
    }
    savepoint = await ctx.conn.begin_nested()
    reports: list[LegacyBatchOut] = []
    try:
        skus = await _skus(ctx, shop_ids)
        for batch in parsed.batches:
            shop = names.get(batch.shop_id) if batch.shop_id is not None else None
            warnings = list(to_purchase(batch).warnings)
            if batch.shop_id is not None and batch.shop_id not in shop_ids:
                warnings.append("do'kon ulanmagan — SKU'lar bog'lanmadi")
            if batch.id in existing:
                reports.append(
                    await _report(ctx, batch, existing[batch.id], "exists", shop, None, warnings)
                )
                continue
            created = await _create(ctx, batch, skus)
            reports.append(
                await _report(ctx, batch, created.purchase_id, "created", shop, created, warnings)
            )
    except BaseException:
        await savepoint.rollback()
        raise
    if dry_run:
        await savepoint.rollback()
    else:
        await savepoint.commit()
    for legacy_id, reason in sorted(parsed.errors.items()):
        reports.append(
            LegacyBatchOut(
                legacy_id=legacy_id,
                title=f"Legacy #{legacy_id}",
                day=None,
                shop=None,
                status="error",
                purchase_id=None,
                stage=None,
                units=0,
                total_legacy=None,
                total_new=None,
                worst_difference=None,
                match=None,
                new_items=0,
                unmatched=[],
                warnings=[reason],
                lines=[],
            )
        )
    for r in reports:
        if dry_run and r.status == "created":
            r.purchase_id = None
    created_n = sum(r.status == "created" for r in reports)
    if not dry_run:
        await ctx.audit(
            "legacy.import",
            "org",
            ctx.org_id,
            after={"batches": len(parsed.batches), "created": created_n},
        )
        if created_n:
            background.add_task(_kick, request, ctx.org_id)
    return LegacyImportOut(
        dry_run=dry_run,
        shops=[
            LegacyShopOut(legacy_id=i, name=n, connected=i in shop_ids)
            for i, n in sorted(names.items())
        ],
        created=created_n,
        existing=sum(r.status == "exists" for r in reports),
        errors=sum(r.status == "error" for r in reports),
        mismatched=sum(r.match is False for r in reports),
        batches=reports,
    )

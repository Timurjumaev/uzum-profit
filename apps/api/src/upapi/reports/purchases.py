"""Xaridlar (M9, B4.6) bazadan → javob: ro'yxat va xarid sahifasi.

Birlik tannarx (F20) **jonli** hisoblanadi — lotlarni quradigan yo'l bilan bir xil (:func:`upapi.calc.lots.evaluate`):
xarid sahifasida tahrirdan keyin (yoki kurs o'zgarsa) raqam darhol yangi, sotuvlar tannarxi esa qayta hisob navbati
orqali (``recalc_pending``). Hisoblab bo'lmaydigan xarid (qo'lda kurs yo'q, ulush yetishmaydi ...) — summasiz,
sababi bilan (``error``): raqam o'ylab topilmaydi.

Partiya yo'li — :func:`upcore.purchasing.timeline`; kutilgan sana — tashkilot xaridlari tarixidan F25 bosqich
medianasi (``upcore.inventory.lead_time``); tarix yo'q bosqichda — sozlamadagi standart muddat (``orgs.settings``, B4.8). Summalar (narx, komponentlar,
tannarx) faqat ``view_purchase_amounts`` bilan (omborchi — summasiz, 03 §10).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Row, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.fx import to_uzs
from upcore.inventory import lead_time
from upcore.money import Money, to_decimal
from upcore.purchasing import (
    DATED_STAGES,
    LotCost,
    Stage,
    average_unit_cost,
    current_stage,
    purchase_total,
    stage_days,
    timeline,
)

from upapi import orgsettings
from upapi.calc import lots as calc_lots
from upapi.db import models as m

MAX_PURCHASES = 500


def stage_dates(row: Any) -> dict[Stage, date | None]:
    """Xarid qatori → bosqich sanalari (ustun ``<bosqich>_on``)."""
    return {s: getattr(row, f"{s.value}_on") for s in DATED_STAGES}


class StageOut(BaseModel):
    """Partiya yo'li nuqtasi (04 §6.2): ``done`` / ``current`` / ``upcoming``."""

    stage: Stage
    state: str
    on: date | None
    days: int | None  # joriy bosqichda necha kun o'tdi
    expected: date | None  # keyingi bosqich kutilgan sanasi (F25)
    delayed: bool


class LineCostOut(BaseModel):
    """Qator (lot) tannarxi, F20: komponentlar bo'yicha tarkib. ``unit_cost`` — dona 0 bo'lsa ``null``."""

    total: Decimal
    unit_cost: Decimal | None
    breakdown: dict[str, Decimal]


class LineOut(BaseModel):
    id: UUID
    item_id: UUID | None
    item_name: str | None
    item_image: str | None
    temp_name: str | None  # "yangi tovar" (hali tovar/SKU yo'q)
    url: str | None
    image_url: str | None
    variant: str | None
    ordered_qty: int
    received_qty: int | None  # ``null`` — qabul qilinmagan
    shortage: int  # buyurtma − qabul (kamomad; qabul qilinmagan — 0)
    unit_price: Decimal | None  # valyutada (summalar ruxsati bilan)
    currency: str | None
    unit_weight: Decimal | None  # kg / dona
    unit_volume: Decimal | None  # m³ / dona
    flags: list[str]  # F22
    cost: LineCostOut | None  # summalar ruxsati yo'q yoki hisoblab bo'lmadi — ``null``


class ComponentOut(BaseModel):
    """Xarajat komponenti. ``applied_rate`` — hisobda ishlatilgan kurs (so'mda ``null``), ``rate_day`` — uning sanasi
    (CBU dam olish kunida — oxirgi ish kuni); kursni aniqlab bo'lmasa ``error``."""

    id: UUID
    kind: str
    amount: Decimal
    currency: str
    paid_on: date | None
    rate_mode: str
    rate: Decimal | None  # qo'lda kiritilgan
    charged_amount: Decimal | None
    charged_currency: str | None
    allocation: str
    lines: list[UUID] | None  # ``null`` — hamma qatorlar
    shares: dict[str, Decimal]
    applied_rate: Decimal | None
    rate_day: date | None
    amount_uzs: Decimal | None
    error: str | None


class PurchaseOut(BaseModel):
    """Ro'yxat qatori. ``total`` / ``unit_cost`` — so'mda (F20; summalar ruxsati va hisob bo'lsa)."""

    id: UUID
    title: str | None
    stage: Stage
    supplier_id: UUID | None
    supplier_name: str | None
    carrier_id: UUID | None
    carrier_name: str | None
    dates: dict[Stage, date | None]
    timeline: list[StageOut]
    line_count: int
    items: list[str]  # birinchi 3 ta tovar nomi
    units_ordered: int
    units_received: int | None  # hech bir qator qabul qilinmagan — ``null``
    total: Decimal | None
    unit_cost: Decimal | None  # o'rtacha (jami / dona)
    flags: list[str]  # qatorlar F22 belgilari yig'indisi
    error: str | None
    note: str | None
    created_at: datetime


class PurchaseDetailOut(BaseModel):
    purchase: PurchaseOut
    amounts: bool  # summalar ko'rinadimi (``view_purchase_amounts``)
    lines: list[LineOut]
    components: list[ComponentOut]  # summalar ruxsatisiz — bo'sh
    by_kind: dict[str, Decimal]  # komponent turlari bo'yicha so'mda
    recalc_pending: bool  # sotuvlar tannarxi hali qayta hisoblanmoqda


class SupplierOut(BaseModel):
    id: UUID
    name: str
    platform: str | None


class CarrierOut(BaseModel):
    id: UUID
    name: str
    pricing: str | None


async def org_lead(conn: AsyncConnection) -> dict[str, Decimal]:
    """F25 bosqich kunlari tashkilot xaridlari tarixidan (oxirgi 5 xarid medianasi)."""
    p = m.purchases
    history: dict[str, list[int]] = {}
    for row in await conn.execute(select(p).order_by(p.c.ordered_on.nulls_first(), p.c.created_at)):
        for stage, days in stage_days(stage_dates(row)).items():
            history.setdefault(stage, []).append(days)
    return dict(lead_time(history, (await orgsettings.load(conn)).lead_days).stages)


def _timeline(row: Any, today: date, lead: dict[str, Decimal]) -> list[StageOut]:
    return [
        StageOut(
            stage=x.stage,
            state=x.state,
            on=x.on,
            days=x.days,
            expected=x.expected,
            delayed=x.delayed,
        )
        for x in timeline(stage_dates(row), today, lead)
    ]


class Book:
    """Tanlangan xaridlar: qatorlar, komponentlar, tovar va yetkazib beruvchi nomlari, kurslar (bir marta o'qiladi)."""

    def __init__(self, conn: AsyncConnection, today: date) -> None:
        self.conn, self.today = conn, today
        self.purchases: list[Row[Any]] = []
        self.lines: dict[UUID, list[Row[Any]]] = {}
        self.components: dict[UUID, list[Row[Any]]] = {}
        self.items: dict[UUID, Any] = {}
        self.suppliers: dict[UUID, str] = {}
        self.carriers: dict[UUID, str] = {}
        self.rates = calc_lots.Rates(conn, today)
        self.lead: dict[str, Decimal] = {}

    async def load(self, purchase_id: UUID | None = None) -> Book:
        p, pl, cc = m.purchases, m.purchase_lines, m.cost_components
        query = select(p).order_by(p.c.created_at.desc(), p.c.id).limit(MAX_PURCHASES)
        if purchase_id is not None:
            query = query.where(p.c.id == purchase_id)
        self.purchases = list(await self.conn.execute(query))
        ids = [x.id for x in self.purchases]
        for row in await self.conn.execute(
            select(pl).where(pl.c.purchase_id.in_(ids)).order_by(pl.c.created_at, pl.c.id)
        ):
            self.lines.setdefault(row.purchase_id, []).append(row)
        for row in await self.conn.execute(
            select(cc).where(cc.c.purchase_id.in_(ids)).order_by(cc.c.created_at, cc.c.id)
        ):
            self.components.setdefault(row.purchase_id, []).append(row)
        item_ids = {x.item_id for rows in self.lines.values() for x in rows if x.item_id}
        if item_ids:
            i = m.items
            self.items = {
                r.id: r
                for r in await self.conn.execute(
                    select(i.c.id, i.c.name, i.c.image_url).where(i.c.id.in_(item_ids))
                )
            }
        s, c = m.suppliers, m.carriers
        self.suppliers = {r.id: r.name for r in await self.conn.execute(select(s.c.id, s.c.name))}
        self.carriers = {r.id: r.name for r in await self.conn.execute(select(c.c.id, c.c.name))}
        await self.rates.load(
            calc_lots.currencies_of(
                [r for rows in (*self.lines.values(), *self.components.values()) for r in rows]
            )
        )
        self.lead = await org_lead(self.conn)
        return self

    def evaluate(self, purchase: Row[Any]) -> calc_lots.Evaluation:
        return calc_lots.evaluate(
            purchase,
            self.lines.get(purchase.id, []),
            self.components.get(purchase.id, []),
            self.rates,
        )

    def summary(self, purchase: Row[Any], ev: calc_lots.Evaluation, amounts: bool) -> PurchaseOut:
        lines = self.lines.get(purchase.id, [])
        names = []
        for x in lines:
            item = self.items.get(x.item_id) if x.item_id else None
            name = item.name if item is not None else x.temp_name
            if name and name not in names:
                names.append(name)
        received = [x.received_qty for x in lines if x.received_qty is not None]
        flags = sorted({f.value for lot in ev.lots for f in lot.flags})
        total = unit = None
        if amounts and ev.model is not None and ev.error is None:
            total = purchase_total(ev.model).amount
            avg = average_unit_cost(ev.lots)
            unit = None if avg is None else avg.amount
        return PurchaseOut(
            id=purchase.id,
            title=purchase.title,
            stage=current_stage(stage_dates(purchase)),
            supplier_id=purchase.supplier_id,
            supplier_name=self.suppliers.get(purchase.supplier_id)
            if purchase.supplier_id
            else None,
            carrier_id=purchase.carrier_id,
            carrier_name=self.carriers.get(purchase.carrier_id) if purchase.carrier_id else None,
            dates=stage_dates(purchase),
            timeline=_timeline(purchase, self.today, self.lead),
            line_count=len(lines),
            items=names[:3],
            units_ordered=sum(x.ordered_qty for x in lines),
            units_received=sum(received) if received else None,
            total=total,
            unit_cost=unit,
            flags=flags,
            error=ev.error,
            note=purchase.note,
            created_at=purchase.created_at,
        )

    def _line(self, row: Row[Any], lot: LotCost | None, amounts: bool) -> LineOut:
        item = self.items.get(row.item_id) if row.item_id else None
        cost = None
        if amounts and lot is not None:
            cost = LineCostOut(
                total=lot.total.amount,
                unit_cost=None if lot.unit_cost is None else lot.unit_cost.amount,
                breakdown={k.value: v.amount for k, v in lot.breakdown.items()},
            )
        return LineOut(
            id=row.id,
            item_id=row.item_id,
            item_name=None if item is None else item.name,
            item_image=None if item is None else item.image_url,
            temp_name=row.temp_name,
            url=row.url,
            image_url=row.image_url,
            variant=row.variant,
            ordered_qty=row.ordered_qty,
            received_qty=row.received_qty,
            shortage=0 if row.received_qty is None else max(row.ordered_qty - row.received_qty, 0),
            unit_price=row.unit_price if amounts else None,
            currency=row.currency,
            unit_weight=row.unit_weight,
            unit_volume=row.unit_volume,
            flags=sorted(f.value for f in lot.flags) if lot is not None else [],
            cost=cost,
        )

    def _component(self, purchase: Row[Any], row: Row[Any]) -> ComponentOut:
        rate = error = uzs = None
        try:
            fx = calc_lots.component_rate(row, purchase, self.rates)
            money = Money(to_decimal(row.amount), calc_lots.currency_of(row.currency))
            uzs = to_uzs(money, fx).amount
            rate = fx
        except calc_lots.CALC_ERRORS as exc:
            error = str(exc) or type(exc).__name__
        lines, shares = calc_lots.targets_of(row.targets)
        return ComponentOut(
            id=row.id,
            kind=row.kind,
            amount=row.amount,
            currency=row.currency,
            paid_on=row.paid_on,
            rate_mode=row.rate_mode,
            rate=row.rate,
            charged_amount=row.charged_amount,
            charged_currency=row.charged_currency,
            allocation=row.allocation,
            lines=None if lines is None else [UUID(x) for x in lines],
            shares=shares,
            applied_rate=None if rate is None else rate.rate,
            rate_day=None if rate is None else rate.day,
            amount_uzs=uzs,
            error=error,
        )

    def detail(self, purchase: Row[Any], amounts: bool, pending: bool) -> PurchaseDetailOut:
        ev = self.evaluate(purchase)
        lots = {lot.line_id: lot for lot in ev.lots}
        by_kind: dict[str, Decimal] = {}
        if amounts and ev.error is None:
            for lot in ev.lots:
                for kind, money in lot.breakdown.items():
                    by_kind[kind.value] = by_kind.get(kind.value, Decimal(0)) + money.amount
        return PurchaseDetailOut(
            purchase=self.summary(purchase, ev, amounts),
            amounts=amounts,
            lines=[
                self._line(x, lots.get(str(x.id)), amounts) for x in self.lines.get(purchase.id, [])
            ],
            components=[self._component(purchase, c) for c in self.components.get(purchase.id, [])]
            if amounts
            else [],
            by_kind=by_kind,
            recalc_pending=pending,
        )


async def recalc_pending(conn: AsyncConnection, purchase_id: UUID) -> bool:
    """Xarid (yoki hamma xaridlar) qayta hisob navbatida turibdimi."""
    q = m.recalc_queue
    found = await conn.scalar(
        select(q.c.id)
        .where(q.c.kind == "purchase", or_(q.c.ref_id == purchase_id, q.c.ref_id.is_(None)))
        .limit(1)
    )
    return found is not None


def matches(stage: Stage, wanted: Sequence[Stage] | None) -> bool:
    return not wanted or stage in wanted

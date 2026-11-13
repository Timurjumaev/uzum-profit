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
    SupplyState,
    average_unit_cost,
    current_stage,
    purchase_total,
    stage_days,
    supply_path,
    supply_state,
    timeline,
    transit_days,
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


class PathOut(BaseModel):
    """Partiya yo'li nuqtasi (ADR-061 §1, 04 §6.2): Yo'lda → Omborimda → Uzumda. ``mark``: ``done`` / ``current`` /
    ``upcoming``; "Yo'lda" joriy bo'lsa — ``days`` o'tdi, sanash ``expected`` da kutiladi (F25)."""

    state: SupplyState
    mark: str
    on: date | None
    days: int | None
    expected: date | None
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
    sku_id: UUID | None  # qator qaysi SKU uchun (ADR-061; eski qatorlarda ``null``)
    line_sum: Decimal | None  # qator summasi, xarid valyutasida (summalar ruxsati bilan)
    defect_qty: int  # sanashdagi brak (kelganning ichida)
    good_qty: int  # tannarx bo'linadigan sog' dona: kelgan − brak (sanalmagan — buyurtma qilingan)
    pack_unit_cost: Decimal | None  # qadoq qo'shimchasi, so'm/dona (summalar ruxsati bilan)
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
    rate_source: (
        str | None
    )  # ``cbu`` / ``market`` (zaxira, rasmiy emas) / ``manual`` / ``effective``
    amount_uzs: Decimal | None
    error: str | None


class PurchaseOut(BaseModel):
    """Ro'yxat qatori. ``total`` / ``unit_cost`` — so'mda (F20; summalar ruxsati va hisob bo'lsa)."""

    id: UUID
    title: str | None
    stage: Stage
    state: SupplyState  # ADR-061 §1: Yo'lda / Omborimda / Uzumda (hosila)
    path: list[PathOut]  # uch nuqtali Partiya yo'li
    track_no: str | None
    on_hand: bool  # "Tovar qo'limda" — kargo kutilmaydi
    refund_amount: Decimal | None  # sotuvchi qaytargan summa (summalar ruxsati bilan)
    refund_currency: str | None
    supplier_id: UUID | None
    supplier_name: str | None
    carrier_id: UUID | None
    carrier_name: str | None
    shipment_id: UUID | None  # kargo (ADR-046): xarid faqat bitta kargoga tegishli
    shipment_name: str | None
    dates: dict[
        Stage, date | None
    ]  # kargoga bog'langan xaridda Xitoy omborida / yo'lda / keldi — kargodan
    timeline: list[StageOut]
    line_count: int
    items: list[str]  # birinchi 3 ta tovar nomi
    units_ordered: int
    units_received: int | None  # hech bir qator qabul qilinmagan — ``null``
    units_defect: int  # sanashdagi brak
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
    shipment_components: list[
        ComponentOut
    ]  # kargo xarajatlari (faqat o'qish; summalar ruxsatisiz — bo'sh)
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
    shipments = {r.id: r for r in await conn.execute(select(m.shipments))}
    for row in await conn.execute(select(p).order_by(p.c.ordered_on.nulls_first(), p.c.created_at)):
        row = calc_lots.effective_purchase(row, shipments.get(row.shipment_id))
        for stage, days in stage_days(stage_dates(row)).items():
            history.setdefault(stage, []).append(days)
        transit = transit_days(stage_dates(row))
        if transit is not None:
            history.setdefault(TRANSIT, []).append(transit)
    stages = dict(lead_time(history, (await orgsettings.load(conn)).lead_days).stages)
    if TRANSIT not in stages and all(x in stages for x in TRANSIT_PARTS):
        # Tarix yo'q: buyurtma → sanash standarti — sanashgacha bo'lgan eski bosqich muddatlari yig'indisi.
        stages[TRANSIT] = sum((stages[x] for x in TRANSIT_PARTS), Decimal(0))
    return stages


# F25 (ADR-061): "Yo'lda" muddati — buyurtma → sanash; tarix bo'lmasa eski to'rt bosqich standartlari yig'indisi.
TRANSIT = "transit"
TRANSIT_PARTS = ("prep", "china", "cargo", "receive")


def _path(row: Any, today: date, lead: dict[str, Decimal], created: datetime) -> list[PathOut]:
    return [
        PathOut(
            state=x.state, mark=x.mark, on=x.on, days=x.days, expected=x.expected, delayed=x.delayed
        )
        for x in supply_path(stage_dates(row), today, lead.get(TRANSIT), created.date())
    ]


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
        self.shipments: dict[UUID, Row[Any]] = {}
        self.shipment_components: dict[UUID, list[Row[Any]]] = {}
        self.siblings: dict[
            UUID, Row[Any]
        ] = {}  # kargodagi hamma xaridlar (ro'yxatdan tashqaridagilar ham)
        self._groups: dict[UUID, calc_lots.ShipmentEvaluation] = {}
        self.rates = calc_lots.Rates(conn, today)
        self.lead: dict[str, Decimal] = {}

    async def load(self, purchase_id: UUID | None = None, shipment_id: UUID | None = None) -> Book:
        """``purchase_id`` — bitta xarid; ``shipment_id`` — shu kargoning xaridlari (kargo xaridsiz bo'lsa ham o'qiladi)."""
        p, pl, cc = m.purchases, m.purchase_lines, m.cost_components
        query = select(p).order_by(p.c.created_at.desc(), p.c.id).limit(MAX_PURCHASES)
        if purchase_id is not None:
            query = query.where(p.c.id == purchase_id)
        if shipment_id is not None:
            query = query.where(p.c.shipment_id == shipment_id)
        self.purchases = list(await self.conn.execute(query))
        shipment_ids = {x.shipment_id for x in self.purchases if x.shipment_id is not None}
        if shipment_id is not None:
            shipment_ids.add(shipment_id)
        self.siblings = {x.id: x for x in self.purchases}
        if (
            shipment_ids
        ):  # kargo xarajati ular orasida bo'linadi: ro'yxatda bo'lmasa ham hammasi kerak
            for x in await self.conn.execute(select(p).where(p.c.shipment_id.in_(shipment_ids))):
                self.siblings.setdefault(x.id, x)
            sh = m.shipments
            self.shipments = {
                r.id: r
                for r in await self.conn.execute(select(sh).where(sh.c.id.in_(shipment_ids)))
            }
            for row in await self.conn.execute(
                select(cc)
                .where(cc.c.shipment_id.in_(shipment_ids))
                .order_by(cc.c.created_at, cc.c.id)
            ):
                self.shipment_components.setdefault(row.shipment_id, []).append(row)
        ids = list(self.siblings)
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
                [
                    r
                    for rows in (
                        self.siblings.values(),  # sotuvchi qaytargan summa valyutasi (ADR-061)
                        *self.lines.values(),
                        *self.components.values(),
                        *self.shipment_components.values(),
                    )
                    for r in rows
                ]
            )
        )
        self.lead = await org_lead(self.conn)
        return self

    def effective(self, purchase: Row[Any]) -> Any:
        """Kargoga bog'langan xarid: sanalar kargodan (``stage_dates``, Partiya yo'li uchun)."""
        shipment = self.shipments.get(purchase.shipment_id) if purchase.shipment_id else None
        return calc_lots.effective_purchase(purchase, shipment)

    def group(self, shipment_id: UUID) -> calc_lots.ShipmentEvaluation:
        """Kargo hisobi (bir marta): hamma xaridlari birga, kargo xarajatlari ular orasida bo'lingan."""
        if shipment_id not in self._groups:
            members = [x for x in self.siblings.values() if x.shipment_id == shipment_id]
            self._groups[shipment_id] = calc_lots.evaluate_shipment(
                self.shipments[shipment_id],
                members,
                self.lines,
                self.components,
                self.shipment_components.get(shipment_id, []),
                self.rates,
            )
        return self._groups[shipment_id]

    def evaluate(self, purchase: Row[Any]) -> calc_lots.Evaluation:
        shipment_id = purchase.shipment_id
        if shipment_id is not None and shipment_id in self.shipments:
            return self.group(shipment_id).purchases[purchase.id]
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
            # Kargoli xarid: o'z komponentlari + kargo ulushi (lotlar yig'indisi); kargosiz — komponentlar yig'indisi.
            total = (
                sum((lot.total.amount for lot in ev.lots), Decimal(0))
                if purchase.shipment_id is not None
                else purchase_total(ev.model).amount
            )
            avg = average_unit_cost(ev.lots)
            unit = None if avg is None else avg.amount
        eff = self.effective(purchase)
        shipment = self.shipments.get(purchase.shipment_id) if purchase.shipment_id else None
        return PurchaseOut(
            id=purchase.id,
            title=purchase.title,
            stage=current_stage(stage_dates(eff)),
            state=supply_state(stage_dates(eff)),
            path=_path(eff, self.today, self.lead, purchase.created_at),
            track_no=purchase.track_no,
            on_hand=purchase.on_hand,
            refund_amount=purchase.refund_amount if amounts else None,
            refund_currency=purchase.refund_currency if amounts else None,
            supplier_id=purchase.supplier_id,
            supplier_name=self.suppliers.get(purchase.supplier_id)
            if purchase.supplier_id
            else None,
            carrier_id=purchase.carrier_id,
            carrier_name=self.carriers.get(purchase.carrier_id) if purchase.carrier_id else None,
            shipment_id=purchase.shipment_id,
            shipment_name=None if shipment is None else (shipment.title or ""),
            dates=stage_dates(eff),
            timeline=_timeline(eff, self.today, self.lead),
            line_count=len(lines),
            items=names[:3],
            units_ordered=sum(x.ordered_qty for x in lines),
            units_received=sum(received) if received else None,
            units_defect=sum(x.defect_qty for x in lines),
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
            sku_id=row.sku_id,
            line_sum=row.line_sum if amounts else None,
            defect_qty=row.defect_qty,
            good_qty=(row.ordered_qty if row.received_qty is None else row.received_qty)
            - row.defect_qty,
            pack_unit_cost=row.pack_unit_cost if amounts else None,
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
            rate_source=None if rate is None else rate.source.value,
            amount_uzs=uzs,
            error=error,
        )

    def shipment_component_outs(self, purchase: Row[Any]) -> list[ComponentOut]:
        shipment = self.shipments.get(purchase.shipment_id) if purchase.shipment_id else None
        if shipment is None:
            return []
        fallback = calc_lots.shipment_fallback(shipment)
        return [self._component(fallback, c) for c in self.shipment_components.get(shipment.id, [])]

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
            shipment_components=self.shipment_component_outs(purchase) if amounts else [],
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


def matches(
    out: PurchaseOut, stages: Sequence[Stage] | None, states: Sequence[SupplyState] | None = None
) -> bool:
    """Ro'yxat filtri: eski bosqich (``stage``) va / yoki holat (``state``, ADR-061)."""
    return (not stages or out.stage in stages) and (not states or out.state in states)

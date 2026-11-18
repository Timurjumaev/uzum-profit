"""Xaridlar (M9, B4.6) bazadan → javob: ro'yxat va xarid sahifasi.

Birlik tannarx (F20) **jonli** hisoblanadi — lotlarni quradigan yo'l bilan bir xil (:func:`upapi.calc.lots.evaluate`):
xarid sahifasida tahrirdan keyin (yoki kurs o'zgarsa) raqam darhol yangi, sotuvlar tannarxi esa qayta hisob navbati
orqali (``recalc_pending``). Hisoblab bo'lmaydigan xarid (qo'lda kurs yo'q, ulush yetishmaydi ...) — summasiz,
sababi bilan (``error``): raqam o'ylab topilmaydi.

Partiya yo'li — :func:`upcore.purchasing.supply_path`; kutilgan sana — F25 "yo'l" muddati (:func:`lead_history`:
tashkilot xaridlari tarixidan oxirgi 5 ta mediana); tarix yo'q bo'lsa — sozlamadagi standart muddat (``orgs.settings``, B4.8). Summalar (narx, komponentlar,
tannarx) faqat ``view_purchase_amounts`` bilan (omborchi — summasiz, 03 §10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Row, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.fx import to_uzs
from upcore.inventory import LeadTime, learn_lead
from upcore.metrics import business_date
from upcore.money import Money, to_decimal
from upcore.purchasing import (
    DATED_STAGES,
    HANDOVER,
    TRANSIT,
    Flag,
    LotCost,
    Stage,
    SupplyState,
    average_unit_cost,
    defect_cost,
    handover_days,
    purchase_total,
    supply_path,
    supply_state,
    transit_days,
)

from upapi import orgsettings
from upapi.calc import lots as calc_lots
from upapi.calc.costs import arrival_day
from upapi.db import models as m
from upapi.reports import dispatch

MAX_PURCHASES = 500


def stage_dates(row: Any) -> dict[Stage, date | None]:
    """Xarid qatori → bosqich sanalari (ustun ``<bosqich>_on``)."""
    return {s: getattr(row, f"{s.value}_on") for s in DATED_STAGES}


def arrival(row: Any) -> date | None:
    """TM9.8 (ADR-069): "Keldi" sanasi — faqat yangi qoida bo'yicha belgilangan bo'lsa (``arrival_marked``); eski
    "Toshkentga keldi" bosqich sanasi holatga ta'sir qilmaydi."""
    return row.arrived_on if getattr(row, "arrival_marked", None) else None


class HistoryOut(BaseModel):
    """Eski bosqich sanasi (ADR-061 §11): xarid sahifasidagi "Tarix" — faqat o'qish."""

    stage: Stage
    on: date


class PathOut(BaseModel):
    """Partiya yo'li nuqtasi (ADR-061 §1, 04 §6.2): Yo'lda → Omborimda → Uzumda. ``mark``: ``done`` / ``current`` /
    ``upcoming``; "Yo'lda" joriy bo'lsa — ``days`` o'tdi, sanash ``expected`` da kutiladi (F25)."""

    state: SupplyState
    mark: str
    on: date | None
    days: int | None
    expected: date | None
    delayed: bool
    uncounted: bool = False  # TM9.8: "Omborimda · sanalmagan"


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
    # Sanashdagi brak tannarxga qancha qo'shdi (F20, so'm; summalar ruxsati bilan).
    defect_cost: Decimal | None = None
    source_line_id: UUID | None = None  # boshqa SKU'ga o'tkazilgan qator: manba qator (ADR-061 §7)
    # TM9.6: qatorga yozilgan qaytarilgan summa (xarid ``refund_currency`` da) va F55 — kelmagan qator zarari (so'm).
    refund_amount: Decimal | None = None
    missing_loss: Decimal | None = None
    # Jadvalda nom tagida: SKU kodi (``skuFullTitle``) va Uzum SKU ID (qator SKU'ga bog'langan bo'lsa).
    sku_code: str | None = None
    sku_external_id: int | None = None


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
    cost_type_id: UUID | None = None  # sotuvchining o'z turi (ADR-061 §4; ``kind`` — ``other``)
    type_name: str | None = None
    weight_kg: Decimal | None = None  # kargo vazni — faqat ma'lumot (ADR-061 §3)
    purchase_shares: dict[str, Decimal] = {}  # kodli quti: qo'lda o'zgartirilgan xarid ulushlari


class PurchaseOut(BaseModel):
    """Ro'yxat qatori. ``total`` / ``unit_cost`` — so'mda (F20; summalar ruxsati va hisob bo'lsa)."""

    id: UUID
    title: str | None
    state: SupplyState  # ADR-061 §1: Yo'lda / Omborimda / Uzumda (hosila)
    path: list[PathOut]  # uch nuqtali Partiya yo'li
    # TM9.8 (ADR-069): "Keldi" sanasi (yangi qoida) va sanalganmi — Omborimda, ``counted`` yo'q: "Omborimda · sanalmagan".
    arrived_on: date | None = None
    counted: bool = False
    # TM9.6 F55: kelmagan (sog' donasi 0) tovarlar soni va zarari (so'm; summalar ruxsati bilan).
    missing_lines: int = 0
    missing_loss: Decimal | None = None
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
    ordered_on: date | None  # buyurtma sanasi (sarlavha shaklida tahrirlanadi)
    history: list[
        HistoryOut
    ]  # eski bosqich sanalari ("Tarix", faqat o'qish; kargodagi xaridda — kargodan)
    line_count: int
    items: list[str]  # birinchi 3 ta tovar nomi
    units_ordered: int
    units_received: int | None  # hech bir qator qabul qilinmagan — ``null``
    units_defect: int  # sanashdagi brak
    units_sending: int = 0  # Uzumga jo'natmada, postavka hali yo'q (Jo'natilmoqda, TM6)
    units_at_uzum: int = 0  # postavkaga bog'langan (Uzumda, TM6)
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


@dataclass
class LeadHistory:
    """F25 tarixi (B5.1): har bo'lak ("transit", "handover") uchun kunlar ro'yxati (eng eskisidan yangisiga) — tovar,
    yetkazib beruvchi va butun tashkilot bo'yicha. ``item_supplier`` — tovarning oxirgi (yetkazib beruvchisi ko'rsatilgan)
    xaridi yetkazib beruvchisi."""

    item: dict[UUID, dict[str, list[int]]] = field(default_factory=dict)
    supplier: dict[UUID, dict[str, list[int]]] = field(default_factory=dict)
    org: dict[str, list[int]] = field(default_factory=dict)
    item_supplier: dict[UUID, UUID] = field(default_factory=dict)

    def learn(self, item_id: UUID | None, defaults: dict[str, int]) -> LeadTime:
        """Tovar uchun F25: tovar → yetkazib beruvchi → tashkilot → standart."""
        mine = self.item.get(item_id, {}) if item_id is not None else {}
        sup = self.item_supplier.get(item_id) if item_id is not None else None
        return learn_lead(mine, self.supplier.get(sup, {}) if sup else {}, self.org, defaults)


async def lead_history(conn: AsyncConnection) -> LeadHistory:
    """F25 tarixi xaridlardan: **yo'l** — buyurtma → keldi (``transit_days``; eski xaridlarda sanash), **topshirish** —
    jo'natma (``fbo_dispatches`` → postavka savdoga chiqqan kun, ADR-056) yoki eski xaridlarda qabul → "Uzumga yuborildi"."""
    out = LeadHistory()
    p, pl = m.purchases, m.purchase_lines
    shipments = {r.id: r for r in await conn.execute(select(m.shipments))}
    seen: set[UUID] = set()
    rows = await conn.execute(
        select(p, pl.c.item_id)
        .join(pl, pl.c.purchase_id == p.c.id)
        .order_by(p.c.ordered_on.nulls_first(), p.c.created_at, p.c.id)
    )
    for r in rows:
        eff = calc_lots.effective_purchase(r, shipments.get(r.shipment_id))
        dates = stage_dates(eff)
        parts = {
            TRANSIT: transit_days(dates, arrival(eff)),
            HANDOVER: handover_days(dates),
        }
        for part, days in parts.items():
            if days is None:
                continue
            if r.item_id is not None:
                out.item.setdefault(r.item_id, {}).setdefault(part, []).append(days)
            if r.id not in seen and r.supplier_id is not None:
                out.supplier.setdefault(r.supplier_id, {}).setdefault(part, []).append(days)
            if r.id not in seen:
                out.org.setdefault(part, []).append(days)
        seen.add(r.id)
        if r.item_id is not None and r.supplier_id is not None:
            out.item_supplier[r.item_id] = r.supplier_id
    # Jo'natma: Excel chiqarilgan kun → postavka savdoga chiqqan kun (har jo'natma tashkilotga bir marta, tovarga — o'z qatori).
    d, di, v, k = m.fbo_dispatches, m.fbo_dispatch_items, m.fbo_invoices, m.mp_skus
    done: set[UUID] = set()
    for r in await conn.execute(
        select(d.c.id, d.c.exported_at, v.c.status, v.c.created_on, v.c.raw, k.c.item_id)
        .select_from(
            d.join(v, v.c.id == d.c.invoice_id)
            .join(di, di.c.dispatch_id == d.c.id)
            .join(k, k.c.id == di.c.sku_id)
        )
        .where(d.c.status == "linked")
        .order_by(d.c.exported_at, d.c.id)
    ):
        accepted = arrival_day(r.status, r.created_on, r.raw)
        if accepted is None:
            continue
        days = (accepted - business_date(r.exported_at)).days
        if days < 0:
            continue
        if r.item_id is not None:
            out.item.setdefault(r.item_id, {}).setdefault(HANDOVER, []).append(days)
        if r.id not in done:
            out.org.setdefault(HANDOVER, []).append(days)
            done.add(r.id)
    return out


async def org_lead(conn: AsyncConnection) -> dict[str, Decimal]:
    """F25 tashkilot darajasi: har bo'lak — tashkilot xaridlari tarixining oxirgi 5 ta medianasi, tarix yo'q bo'lsa
    Sozlamalardagi standart (partiya yo'li va kutilgan sana uchun)."""
    history = await lead_history(conn)
    return dict(learn_lead({}, {}, history.org, (await orgsettings.load(conn)).lead_days).stages)


def _path(
    dates: dict[Stage, date | None],
    today: date,
    lead: dict[str, Decimal],
    created: datetime,
    arrived: date | None = None,
) -> list[PathOut]:
    return [
        PathOut(
            state=x.state,
            mark=x.mark,
            on=x.on,
            days=x.days,
            expected=x.expected,
            delayed=x.delayed,
            uncounted=x.uncounted,
        )
        for x in supply_path(dates, today, lead.get(TRANSIT), created.date(), arrived)
    ]


def _defect_cost(row: Any, lot: LotCost | None) -> Decimal | None:
    if lot is None:
        return None
    cost = defect_cost(lot, calc_lots.line_model(row))
    return None if cost is None else cost.amount.quantize(Decimal("0.01"))


class Book:
    """Tanlangan xaridlar: qatorlar, komponentlar, tovar va yetkazib beruvchi nomlari, kurslar (bir marta o'qiladi)."""

    def __init__(self, conn: AsyncConnection, today: date) -> None:
        self.conn, self.today = conn, today
        self.purchases: list[Row[Any]] = []
        self.lines: dict[UUID, list[Row[Any]]] = {}
        self.components: dict[UUID, list[Row[Any]]] = {}
        self.items: dict[UUID, Any] = {}
        self.skus: dict[UUID, Any] = {}
        self.skus_by_item: dict[UUID, Any] = {}
        self.suppliers: dict[UUID, str] = {}
        self.carriers: dict[UUID, str] = {}
        self.cost_types: dict[UUID, str] = {}
        self.shipments: dict[UUID, Row[Any]] = {}
        self.shipment_components: dict[UUID, list[Row[Any]]] = {}
        self.siblings: dict[
            UUID, Row[Any]
        ] = {}  # kargodagi hamma xaridlar (ro'yxatdan tashqaridagilar ham)
        self._groups: dict[UUID, calc_lots.ShipmentEvaluation] = {}
        self.rates = calc_lots.Rates(conn, today)
        self.lead: dict[str, Decimal] = {}
        self.dispatch: dict[UUID, dispatch.LineDispatch] = {}

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
        # SKU kodi/ID nom tagida uchun. Qatorda ``sku_id`` bo'lsa — o'sha SKU; eski qatorlarda (``sku_id`` saqlanmagan)
        # tovarning yagona SKU'si (standart — har SKU alohida tovar); tovarda bir nechta SKU bo'lsa — taxmin qilinmaydi.
        all_lines = [x for rows in self.lines.values() for x in rows]
        sku_ids = {x.sku_id for x in all_lines if x.sku_id}
        legacy_items = {x.item_id for x in all_lines if x.sku_id is None and x.item_id}
        if sku_ids or legacy_items:
            k = m.mp_skus
            cond = []
            if sku_ids:
                cond.append(k.c.id.in_(sku_ids))
            if legacy_items:
                cond.append(k.c.item_id.in_(legacy_items))
            found = list(
                await self.conn.execute(
                    select(k.c.id, k.c.item_id, k.c.sku_code, k.c.external_id).where(or_(*cond))
                )
            )
            self.skus = {r.id: r for r in found}
            per_item: dict[UUID, list[Any]] = {}
            for r in found:
                if r.item_id in legacy_items:
                    per_item.setdefault(r.item_id, []).append(r)
            self.skus_by_item = {i: rows[0] for i, rows in per_item.items() if len(rows) == 1}
        s, c = m.suppliers, m.carriers
        self.suppliers = {r.id: r.name for r in await self.conn.execute(select(s.c.id, s.c.name))}
        self.carriers = {r.id: r.name for r in await self.conn.execute(select(c.c.id, c.c.name))}
        t = m.cost_types
        self.cost_types = {r.id: r.name for r in await self.conn.execute(select(t.c.id, t.c.name))}
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
        self.dispatch = await dispatch.line_states(self.conn)
        return self

    def dispatch_dates(
        self, purchase: Row[Any], eff: Any
    ) -> tuple[dict[Stage, date | None], int, int]:
        """TM6 (ADR-061 §1, §7): jo'natmalar bo'yicha qatorlar holati — Jo'natilmoqda va Uzumdagi dona; xaridning hamma
        donasi postavkaga bog'langan bo'lsa holat "Uzumda" (sana — oxirgi bog'langan kun)."""
        dates = dict(stage_dates(eff))
        lines = self.lines.get(purchase.id, [])
        states = [self.dispatch[x.id] for x in lines if x.id in self.dispatch]
        sending = sum(x.sending for x in states)
        linked = sum(x.linked for x in states)
        if linked and dates.get(Stage.SENT_TO_UZUM) is None:
            moved: dict[UUID, int] = {}
            for x in lines:
                if x.source_line_id is not None:
                    moved[x.source_line_id] = moved.get(x.source_line_id, 0) + dispatch.available(x)
            whole = sum(dispatch.available(x, moved.get(x.id, 0)) for x in lines)
            if whole > 0 and linked >= whole:
                days = [x.linked_on for x in states if x.linked_on is not None]
                dates[Stage.SENT_TO_UZUM] = max(days) if days else self.today
        return dates, sending, linked

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
        own = [
            x for x in lines if x.source_line_id is None
        ]  # o'tkazilgan qatorlar donasi ikki marta sanalmaydi
        received = [x.received_qty for x in own if x.received_qty is not None]
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
        dates, sending, linked = self.dispatch_dates(purchase, eff)
        shipment = self.shipments.get(purchase.shipment_id) if purchase.shipment_id else None
        return PurchaseOut(
            id=purchase.id,
            title=purchase.title,
            state=supply_state(dates, arrival(eff)),
            path=_path(dates, self.today, self.lead, purchase.created_at, arrival(eff)),
            arrived_on=arrival(eff),
            counted=eff.received_on is not None,
            missing_lines=sum(1 for lot in ev.lots if lot.missing is not None),
            missing_loss=(
                sum(
                    (lot.missing.amount for lot in ev.lots if lot.missing is not None), Decimal(0)
                ).quantize(Decimal("0.01"))
                if amounts and any(lot.missing is not None for lot in ev.lots)
                else None
            ),
            units_sending=sending,
            units_at_uzum=linked,
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
            ordered_on=eff.ordered_on,
            history=[
                HistoryOut(stage=k, on=v) for k, v in stage_dates(eff).items() if v is not None
            ],
            line_count=len(lines),
            items=names[:3],
            units_ordered=sum(x.ordered_qty for x in own),
            units_received=sum(received) if received else None,
            units_defect=sum(x.defect_qty for x in own),
            total=total,
            unit_cost=unit,
            flags=flags,
            error=ev.error,
            note=purchase.note,
            created_at=purchase.created_at,
        )

    def _line(self, row: Row[Any], lot: LotCost | None, amounts: bool) -> LineOut:
        item = self.items.get(row.item_id) if row.item_id else None
        sku = (
            self.skus.get(row.sku_id)
            if row.sku_id
            else (self.skus_by_item.get(row.item_id) if row.item_id else None)
        )
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
            sku_code=None if sku is None else sku.sku_code,
            sku_external_id=None if sku is None else sku.external_id,
            line_sum=row.line_sum if amounts else None,
            defect_qty=row.defect_qty,
            good_qty=(row.ordered_qty if row.received_qty is None else row.received_qty)
            - row.defect_qty,
            pack_unit_cost=row.pack_unit_cost if amounts else None,
            defect_cost=_defect_cost(row, lot) if amounts else None,
            source_line_id=row.source_line_id,
            flags=sorted(f.value for f in lot.flags) if lot is not None else [],
            cost=cost,
            refund_amount=row.refund_amount if amounts else None,
            missing_loss=(
                lot.missing.amount.quantize(Decimal("0.01"))
                if amounts and lot is not None and lot.missing is not None
                else None
            ),
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
            cost_type_id=row.cost_type_id,
            type_name=self.cost_types.get(row.cost_type_id) if row.cost_type_id else None,
            weight_kg=row.weight_kg,
            purchase_shares=calc_lots.purchase_shares_of(row.targets),
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


def matches(out: PurchaseOut, states: Sequence[SupplyState] | None) -> bool:
    """Ro'yxat filtri: holat (``state``, ADR-061 §1)."""
    return not states or out.state in states


async def goods_missing(conn: AsyncConnection) -> int:
    """TM9.5 "Diqqat": tovar summasi kiritilmagan (F22 ``goods_missing``) xaridlar soni — lot belgilaridan."""
    lots, pl = m.lots, m.purchase_lines
    found = await conn.scalar(
        select(func.count(func.distinct(pl.c.purchase_id)))
        .select_from(lots.join(pl, pl.c.id == lots.c.purchase_line_id))
        .where(lots.c.flags.contains([Flag.GOODS_MISSING.value]))
    )
    return int(found or 0)


async def uncounted(conn: AsyncConnection) -> int:
    """TM9.8 "Diqqat": "Keldi" belgilangan, hali sanalmagan xaridlar soni."""
    p = m.purchases
    found = await conn.scalar(
        select(func.count())
        .select_from(p)
        .where(
            p.c.arrival_marked.is_(True),
            p.c.received_on.is_(None),
            p.c.sent_to_uzum_on.is_(None),
            p.c.closed_on.is_(None),
        )
    )
    return int(found or 0)

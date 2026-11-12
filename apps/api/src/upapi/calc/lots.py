"""Lotlar (F20): xarid + qatorlar + komponentlar (sotuvchi kiritgan) → ``lots`` (har qator — bitta lot).

Bazadagi qiymatlar ``upcore.purchasing`` tiplariga o'giriladi; hisob — faqat ``compute_lots`` (formula shu yerda
qayta yozilmaydi). Kurs (``upcore.fx``):

- ``cbu`` — to'lov sanasidagi CBU kursi (dam olish kuni — oxirgi ish kuni, ``rate_on``). Sana: komponentning
  ``paid_on``, yo'q bo'lsa xaridning to'lov, keyin buyurtma sanasi, hech biri yo'q bo'lsa bugungi kun (taxminiy —
  lotda doim "kurs CBU" belgisi bor).
- ``manual`` — ``rate`` ustuni; ``effective`` — ``charged_amount``/``charged_currency`` dan (karta valyutasi so'mdan
  boshqa bo'lsa uning CBU kursi bilan).

``targets`` (jsonb): ``{"lines": [qator id, ...], "shares": {qator id: ulush}}`` — ``lines`` yo'q bo'lsa hamma
qatorlar, ``shares`` — qo'lda taqsimot (``manual``). Qatorlardagi narx (``value`` asosi) so'mga tovar komponentining
kursi bilan, u yo'q bo'lsa CBU bilan o'tkaziladi.

Hisoblab bo'lmaydigan xarid (kurs yo'q, qo'lda ulush yetishmaydi, valyutasi yo'q narx ...) — lotsiz qoladi va xato
natijada qaytadi: raqam o'ylab topilmaydi, sotuvlari esa "lot yetmadi" / "lot yo'q" belgisini oladi.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import Row, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.fx import FxError, FxRate, RateSource, effective_fx_rate, manual_rate, rate_on
from upcore.money import Currency, Money, MoneyError, round_rate, to_decimal
from upcore.purchasing import (
    AllocationBase,
    ComponentKind,
    CostComponent,
    LotCost,
    Purchase,
    PurchaseError,
    PurchaseLine,
    compute_lots,
    compute_shipment_lots,
    compute_shipment_shares,
    split_by_purchase,
)

from upapi.db import models as m
from upapi.logs import get_logger

_log = get_logger("upapi.calc")
CALC_ERRORS = (PurchaseError, FxError, MoneyError, ValueError, TypeError, KeyError)


class Rates:
    """CBU kurslari (global ``fx_rates``): valyuta bo'yicha bir marta o'qiladi."""

    def __init__(self, conn: AsyncConnection, today: date) -> None:
        self.conn, self.today = conn, today
        self._cache: dict[Currency, list[FxRate]] = {}

    async def load(self, currencies: Iterable[Currency]) -> None:
        wanted = sorted({c for c in currencies if c is not Currency.UZS} - set(self._cache))
        if not wanted:
            return
        for ccy in wanted:
            self._cache[ccy] = []
        rows = await self.conn.execute(
            select(
                m.fx_rates.c.day, m.fx_rates.c.currency, m.fx_rates.c.rate, m.fx_rates.c.source
            ).where(
                m.fx_rates.c.source.in_([RateSource.CBU.value, RateSource.MARKET.value]),
                m.fx_rates.c.currency.in_([c.value for c in wanted]),
            )
        )
        for r in (
            rows
        ):  # bir kunda CBU bor bo'lsa — u ustun (``rate_on``); bozor kursi faqat bo'shliqni yopadi
            self._cache[Currency(r.currency)].append(
                FxRate(r.day, Currency(r.currency), r.rate, RateSource(r.source))
            )

    def cbu(self, currency: Currency, day: date | None) -> FxRate:
        return rate_on(self._cache.get(currency, ()), currency, day or self.today).rate


@dataclass
class LotsResult:
    items: set[UUID] = field(default_factory=set)  # lotlari o'zgargan (eski yoki yangi) tovarlar
    written: int = 0
    errors: dict[UUID, str] = field(default_factory=dict)  # xarid → sabab


def currency_of(value: str | None) -> Currency:
    if not value:
        raise PurchaseError("valyuta ko'rsatilmagan")
    return Currency(value.strip().upper())


def _line(row: Row[Any]) -> PurchaseLine:
    price = None
    if row.unit_price is not None:
        price = Money(to_decimal(row.unit_price), currency_of(row.currency))
    return PurchaseLine(
        id=str(row.id),
        ordered_qty=row.ordered_qty,
        received_qty=row.received_qty,
        unit_price=price,
        unit_weight=row.unit_weight,
        unit_volume=row.unit_volume,
        defect_qty=row.defect_qty,
        line_sum=row.line_sum,
        pack_unit_cost=(
            None
            if row.pack_unit_cost is None
            else Money(to_decimal(row.pack_unit_cost), Currency.UZS)
        ),
    )


def component_rate(row: Row[Any], purchase: Row[Any], rates: Rates) -> FxRate | None:
    """Komponent kursi (so'mda — ``None``); kiritilmagan qo'lda kurs va h.k. — ``PurchaseError``."""
    currency = currency_of(row.currency)
    if currency is Currency.UZS:
        return None
    day = row.paid_on or purchase.paid_on or purchase.ordered_on
    if row.rate_mode == "manual":
        if row.rate is None:
            raise PurchaseError(f"{row.kind}: qo'lda kurs kiritilmagan")
        return manual_rate(day or rates.today, currency, row.rate)
    if row.rate_mode == "effective":
        if row.charged_amount is None:
            raise PurchaseError(f"{row.kind}: kartadan yechilgan summa kiritilmagan")
        charged = Money(to_decimal(row.charged_amount), currency_of(row.charged_currency))
        charged_rate = (
            None if charged.currency is Currency.UZS else rates.cbu(charged.currency, day)
        )
        return effective_fx_rate(
            day or rates.today, Money(to_decimal(row.amount), currency), charged, charged_rate
        )
    return rates.cbu(currency, day)


def targets_of(raw: Mapping[str, Any] | None) -> tuple[tuple[str, ...] | None, dict[str, Decimal]]:
    raw = raw or {}
    lines = raw.get("lines")
    shares = {str(k): to_decimal(str(v)) for k, v in (raw.get("shares") or {}).items()}
    return (tuple(str(x) for x in lines) if lines is not None else None), shares


def purchase_shares_of(raw: Mapping[str, Any] | None) -> dict[str, Decimal]:
    """Kodli quti (ADR-061 §3): ``targets.purchase_shares`` — xarid id → sotuvchi qo'lda yozgan summa (komponent
    valyutasida). Bo'sh — hammasi dona bo'yicha."""
    return {
        str(k): to_decimal(str(v)) for k, v in ((raw or {}).get("purchase_shares") or {}).items()
    }


def refund_of(
    purchase: Any, components: Sequence[CostComponent], rates: Rates
) -> tuple[Money | None, FxRate | None]:
    """Sotuvchi qaytargan summa (ADR-061 §6) va kursi: tovar komponenti shu valyutada bo'lsa — o'sha kurs (pul qaysi
    kursda ketgan bo'lsa shunda qaytadi), bo'lmasa qaytgan (yo'q bo'lsa to'lov / buyurtma) kunidagi CBU kursi."""
    if getattr(purchase, "refund_amount", None) is None:
        return None, None
    refund = Money(to_decimal(purchase.refund_amount), currency_of(purchase.refund_currency))
    if refund.currency is Currency.UZS:
        return refund, None
    goods = next(
        (
            c.rate
            for c in components
            if c.kind is ComponentKind.GOODS
            and c.rate is not None
            and c.rate.currency is refund.currency
        ),
        None,
    )
    day = purchase.refund_on or purchase.paid_on or purchase.ordered_on
    return refund, goods or rates.cbu(refund.currency, day)


class Effective:
    """Qator + ustidan yoziladigan qiymatlar (``Row`` o'zgarmas): kargoga bog'langan xaridning Xitoy omborida / yo'lda /
    Toshkentga keldi sanalari kargodan olinadi (ADR-046); kargoda sana yo'q bo'lsa — xaridning o'zinikи."""

    def __init__(self, row: Row[Any], **over: Any) -> None:
        self._row, self._over = row, over

    def __getattr__(self, name: str) -> Any:
        if name in self._over:
            return self._over[name]
        return getattr(self._row, name)


SHIPMENT_DATES = ("cn_warehouse_on", "shipped_on", "arrived_on")


def effective_purchase(purchase: Row[Any], shipment: Row[Any] | None) -> Any:
    """Kargoga bog'langan xarid: kargo sanalari ustun (bo'sh bo'lsa — xaridniki); kargosiz — o'zi."""
    if shipment is None:
        return purchase
    over = {
        name: getattr(shipment, name)
        for name in SHIPMENT_DATES
        if getattr(shipment, name) is not None
    }
    return Effective(purchase, **over)


def shipment_fallback(shipment: Row[Any]) -> Any:
    """Kargo komponenti sanasiz bo'lsa kurs sanasi: yo'lga chiqqan, yo'q bo'lsa kelgan kun (``component_rate`` uchun)."""
    return SimpleNamespace(
        paid_on=shipment.shipped_on or shipment.arrived_on, ordered_on=shipment.cn_warehouse_on
    )


def build_components(
    components: Sequence[Row[Any]], purchase: Any, rates: Rates
) -> tuple[CostComponent, ...]:
    """Baza komponentlari → ``upcore`` komponentlari (kurslar shu yerda tanlanadi)."""
    parsed = []
    for c in components:
        line_ids, shares = targets_of(c.targets)
        parsed.append(
            CostComponent(
                kind=ComponentKind(c.kind),
                amount=Money(to_decimal(c.amount), currency_of(c.currency)),
                rate=component_rate(c, purchase, rates),
                base=AllocationBase(c.allocation),
                line_ids=line_ids,
                manual_shares=shares,
            )
        )
    return tuple(parsed)


def shipment_components(
    rows: Sequence[Row[Any]], fallback: Any, rates: Rates, purchases: Sequence[Purchase]
) -> tuple[CostComponent, ...]:
    """Kargo komponentlari; ``purchase_shares`` bor komponent (kodli quti, ADR-061 §3) xaridlar bo'yicha bo'linadi:
    qo'lda yozilgan summalar o'zgarmaydi, qolgani kelgan dona bo'yicha (:func:`upcore.purchasing.split_by_purchase`).
    Kargodan chiqarilgan xaridning ulushi e'tiborga olinmaydi (qolganlarga dona bo'yicha qaytadi)."""
    out: list[CostComponent] = []
    known = {p.id for p in purchases}
    for row, component in zip(rows, build_components(rows, fallback, rates), strict=True):
        fixed = {k: v for k, v in purchase_shares_of(row.targets).items() if k in known}
        if fixed:
            out.extend(split_by_purchase(component, purchases, fixed))
        else:
            out.append(component)
    return tuple(out)


def build_purchase(
    purchase: Row[Any],
    lines: Sequence[Row[Any]],
    components: Sequence[Row[Any]],
    rates: Rates,
    shipment_components: Sequence[Row[Any]] = (),
) -> Purchase:
    """Baza qatorlari → ``upcore`` xaridi (kurslar shu yerda tanlanadi). ``shipment_components`` — faqat kargo to'langan
    sanasi uchun (lot sotuvga tayyor sanasi, F21); ularning taqsimoti :func:`evaluate_shipment` da."""
    parsed = build_components(components, purchase, rates)
    line_currencies = {currency_of(x.currency) for x in lines if x.unit_price is not None}
    goods_rate = None
    ccy = line_currencies.pop() if len(line_currencies) == 1 else Currency.UZS
    if ccy is not Currency.UZS:
        goods = next(
            (
                p.rate
                for p in parsed
                if p.kind is ComponentKind.GOODS and p.rate is not None and p.rate.currency is ccy
            ),
            None,
        )
        goods_rate = goods or rates.cbu(ccy, purchase.paid_on or purchase.ordered_on)
    cargo_paid = [
        c.paid_on
        for c in (*components, *shipment_components)
        if c.kind == "cargo" and c.paid_on is not None
    ]
    refund, refund_rate = refund_of(purchase, parsed, rates)
    return Purchase(
        id=str(purchase.id),
        lines=tuple(_line(x) for x in lines),
        components=tuple(parsed),
        refund=refund,
        refund_rate=refund_rate,
        on_hand=bool(getattr(purchase, "on_hand", False)),
        goods_rate=goods_rate,
        order_date=purchase.ordered_on,
        # Kargo bir necha marta to'lansa — oxirgisi (tovar to'liq qo'lga olingan kun).
        cargo_paid_date=max(cargo_paid) if cargo_paid else None,
        received_date=purchase.received_on,
        # ADR-057 Q6: qabul ham, kargo to'lovi ham belgilanmagan, lekin keyingi bosqich bor — tovar qo'lda bo'lgan.
        later_date=min(
            (d for d in (purchase.sent_to_uzum_on, purchase.closed_on) if d is not None),
            default=None,
        ),
    )


@dataclass
class Evaluation:
    """Bitta xaridning jonli hisobi (xarid sahifasi, M9): model, lotlar yoki hisoblab bo'lmagan sabab."""

    model: Purchase | None = None
    lots: list[LotCost] = field(default_factory=list)
    error: str | None = None


def evaluate(
    purchase: Row[Any], lines: Sequence[Row[Any]], components: Sequence[Row[Any]], rates: Rates
) -> Evaluation:
    """F20 — ``rebuild_lots`` bilan bir xil yo'l (kurslar :class:`Rates` ga oldindan yuklangan bo'lishi kerak).
    Kargosiz xarid; kargoga bog'langanlar — :func:`evaluate_shipment`."""
    if not lines:
        return Evaluation()
    try:
        model = build_purchase(purchase, lines, components, rates)
        return Evaluation(model, compute_lots(model))
    except CALC_ERRORS as exc:
        return Evaluation(error=str(exc) or type(exc).__name__)


@dataclass
class ShipmentEvaluation:
    """Kargo hisobi: xaridlar natijasi, kargo komponentlarining har qatorga ulushi (qator id → ulush; xarid ichidagi
    komponentlarsiz) va umumiy xato (hisoblab bo'lmasa)."""

    purchases: dict[UUID, Evaluation] = field(default_factory=dict)
    shares: dict[str, LotCost] = field(default_factory=dict)
    error: str | None = None


def evaluate_shipment(
    shipment: Row[Any],
    purchases: Sequence[Row[Any]],
    lines_by: Mapping[UUID, Sequence[Row[Any]]],
    comps_by: Mapping[UUID, Sequence[Row[Any]]],
    shipment_comps: Sequence[Row[Any]],
    rates: Rates,
) -> ShipmentEvaluation:
    """F20, kargo bilan (ADR-046): kargoga tegishli HAMMA xaridlar birga hisoblanadi — kargo xarajatlari butun
    kargo tovarlariga bir taqsimotda bo'linadi. Biror xarid hisoblanmasa (kurs yo'q ...) — hammasi xato bilan
    qaytadi: qolganlarining ulushi unsiz hisoblansa, kargo noto'g'ri bo'linar edi (raqam o'ylab topilmaydi)."""
    out: dict[UUID, Evaluation] = {}
    active = [p for p in purchases if lines_by.get(p.id)]
    for p in purchases:
        if not lines_by.get(p.id):
            out[p.id] = Evaluation()
    if (
        not active
    ):  # tovarsiz kargo: xarajatni bo'ladigan qator yo'q (komponentlar alohida ko'rsatiladi)
        return ShipmentEvaluation(out)
    try:
        models = {
            p.id: build_purchase(
                effective_purchase(p, shipment),
                lines_by[p.id],
                comps_by.get(p.id, []),
                rates,
                shipment_comps,
            )
            for p in active
        }
        components = shipment_components(
            shipment_comps, shipment_fallback(shipment), rates, list(models.values())
        )
        lots = compute_shipment_lots(list(models.values()), components)
        shares = compute_shipment_shares(list(models.values()), components) if components else {}
    except CALC_ERRORS as exc:
        reason = str(exc) or type(exc).__name__
        error = f"kargo hisoblanmadi: {reason}"
        for p in active:
            out[p.id] = Evaluation(error=error)
        return ShipmentEvaluation(out, {}, error)
    for p in active:
        out[p.id] = Evaluation(models[p.id], lots[str(p.id)])
    return ShipmentEvaluation(out, shares)


def currencies_of(rows: Iterable[Row[Any]]) -> set[Currency]:
    """Qator va komponentlardagi valyutalar (kurslarni oldindan yuklash uchun); noto'g'ri qiymat o'tkaziladi."""
    out: set[Currency] = set()
    for r in rows:
        for value in (
            getattr(r, "currency", None),
            getattr(r, "charged_currency", None),
            getattr(r, "refund_currency", None),  # xarid qatori: sotuvchi qaytargan summa (ADR-061)
        ):
            with contextlib.suppress(PurchaseError, ValueError):
                out.add(currency_of(value))
    return out


async def rebuild_lots(
    conn: AsyncConnection, org_id: UUID, purchase_ids: set[UUID] | None, today: date
) -> LotsResult:
    """Xaridlar lotlarini qayta quradi (``None`` — tashkilotning hamma xaridlari). Qaytadi: lotlari o'zgargan
    tovarlar (sotuv tannarxi shular uchun qayta hisoblanadi). Kargoga bog'langan xarid o'zgarsa — kargoning
    hamma xaridlari qayta quriladi (kargo xarajati ular orasida bo'linadi, ADR-046)."""
    result = LotsResult()
    p, pl, cc, lots, sh = m.purchases, m.purchase_lines, m.cost_components, m.lots, m.shipments
    query = select(p)
    if purchase_ids is not None:
        query = query.where(p.c.id.in_(purchase_ids))
    purchases = list(await conn.execute(query))
    shipment_ids = {x.shipment_id for x in purchases if x.shipment_id is not None}
    if shipment_ids and purchase_ids is not None:
        have = {x.id for x in purchases}
        purchases += [
            x
            for x in await conn.execute(select(p).where(p.c.shipment_id.in_(shipment_ids)))
            if x.id not in have
        ]
    ids = [x.id for x in purchases]
    shipments = {x.id: x for x in await conn.execute(select(sh).where(sh.c.id.in_(shipment_ids)))}
    ship_comps: dict[UUID, list[Row[Any]]] = {}
    for row in await conn.execute(
        select(cc).where(cc.c.shipment_id.in_(shipment_ids)).order_by(cc.c.created_at, cc.c.id)
    ):
        ship_comps.setdefault(row.shipment_id, []).append(row)

    lines_by: dict[UUID, list[Row[Any]]] = {}
    for row in await conn.execute(
        select(pl).where(pl.c.purchase_id.in_(ids)).order_by(pl.c.created_at, pl.c.id)
    ):
        lines_by.setdefault(row.purchase_id, []).append(row)
    comps_by: dict[UUID, list[Row[Any]]] = {}
    for row in await conn.execute(
        select(cc).where(cc.c.purchase_id.in_(ids)).order_by(cc.c.created_at, cc.c.id)
    ):
        comps_by.setdefault(row.purchase_id, []).append(row)

    # Eski lotlar: ularning tovarlari ham qayta hisoblanadi (lot yo'qolsa yoki boshqa tovarga o'tsa).
    old = delete(lots).where(
        lots.c.purchase_line_id.in_(select(pl.c.id).where(pl.c.purchase_id.in_(ids)))
    )
    result.items |= {
        r.item_id for r in await conn.execute(old.returning(lots.c.item_id)) if r.item_id
    }

    rates = Rates(conn, today)
    await rates.load(
        currencies_of(
            [
                r
                for rows in (
                    purchases,
                    *lines_by.values(),
                    *comps_by.values(),
                    *ship_comps.values(),
                )
                for r in rows
            ]
        )
    )

    evaluations: dict[UUID, Evaluation] = {}
    for purchase in purchases:
        if purchase.shipment_id is None:
            evaluations[purchase.id] = evaluate(
                purchase, lines_by.get(purchase.id, []), comps_by.get(purchase.id, []), rates
            )
    for shipment_id, shipment in shipments.items():
        members = [x for x in purchases if x.shipment_id == shipment_id]
        evaluations |= evaluate_shipment(
            shipment, members, lines_by, comps_by, ship_comps.get(shipment_id, []), rates
        ).purchases

    new_rows: list[dict[str, Any]] = []
    for purchase in purchases:
        lines = lines_by.get(purchase.id, [])
        ev = evaluations[purchase.id]
        if ev.error is not None:
            result.errors[purchase.id] = ev.error
            _log.warning("calc_purchase_failed", purchase_id=str(purchase.id), reason=ev.error)
            continue
        if ev.model is None:
            continue
        model = ev.model
        item_of = {str(x.id): x.item_id for x in lines}
        for cost in ev.lots:
            if cost.qty == 0:
                continue
            new_rows.append(
                {
                    "org_id": org_id,
                    "purchase_line_id": UUID(cost.line_id),
                    "item_id": item_of[cost.line_id],
                    "ready_on": model.ready_date,
                    "qty": cost.qty,
                    "total": cost.total.amount,
                    "unit_cost": round_rate(cost.total.amount / cost.qty),
                    "flags": sorted(f.value for f in cost.flags),
                }
            )
    if new_rows:
        await conn.execute(insert(lots), new_rows)
    result.items |= {r["item_id"] for r in new_rows if r["item_id"] is not None}
    result.written = len(new_rows)
    return result

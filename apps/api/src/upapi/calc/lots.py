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
from typing import Any
from uuid import UUID

from sqlalchemy import Row, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.fx import FxError, FxRate, effective_fx_rate, manual_rate, rate_on
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
            select(m.fx_rates.c.day, m.fx_rates.c.currency, m.fx_rates.c.rate).where(
                m.fx_rates.c.source == "cbu", m.fx_rates.c.currency.in_([c.value for c in wanted])
            )
        )
        for r in rows:
            self._cache[Currency(r.currency)].append(FxRate(r.day, Currency(r.currency), r.rate))

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


def build_purchase(
    purchase: Row[Any], lines: Sequence[Row[Any]], components: Sequence[Row[Any]], rates: Rates
) -> Purchase:
    """Baza qatorlari → ``upcore`` xaridi (kurslar shu yerda tanlanadi)."""
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
    cargo_paid = [c.paid_on for c in components if c.kind == "cargo" and c.paid_on is not None]
    return Purchase(
        id=str(purchase.id),
        lines=tuple(_line(x) for x in lines),
        components=tuple(parsed),
        goods_rate=goods_rate,
        order_date=purchase.ordered_on,
        # Kargo bir necha marta to'lansa — oxirgisi (tovar to'liq qo'lga olingan kun).
        cargo_paid_date=max(cargo_paid) if cargo_paid else None,
        received_date=purchase.received_on,
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
    """F20 — ``rebuild_lots`` bilan bir xil yo'l (kurslar :class:`Rates` ga oldindan yuklangan bo'lishi kerak)."""
    if not lines:
        return Evaluation()
    try:
        model = build_purchase(purchase, lines, components, rates)
        return Evaluation(model, compute_lots(model))
    except CALC_ERRORS as exc:
        return Evaluation(error=str(exc) or type(exc).__name__)


def currencies_of(rows: Iterable[Row[Any]]) -> set[Currency]:
    """Qator va komponentlardagi valyutalar (kurslarni oldindan yuklash uchun); noto'g'ri qiymat o'tkaziladi."""
    out: set[Currency] = set()
    for r in rows:
        for value in (getattr(r, "currency", None), getattr(r, "charged_currency", None)):
            with contextlib.suppress(PurchaseError, ValueError):
                out.add(currency_of(value))
    return out


async def rebuild_lots(
    conn: AsyncConnection, org_id: UUID, purchase_ids: set[UUID] | None, today: date
) -> LotsResult:
    """Xaridlar lotlarini qayta quradi (``None`` — tashkilotning hamma xaridlari). Qaytadi: lotlari o'zgargan
    tovarlar (sotuv tannarxi shular uchun qayta hisoblanadi)."""
    result = LotsResult()
    p, pl, cc, lots = m.purchases, m.purchase_lines, m.cost_components, m.lots
    query = select(p)
    if purchase_ids is not None:
        query = query.where(p.c.id.in_(purchase_ids))
    purchases = list(await conn.execute(query))
    ids = [x.id for x in purchases]

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
        currencies_of([r for rows in (*lines_by.values(), *comps_by.values()) for r in rows])
    )

    new_rows: list[dict[str, Any]] = []
    for purchase in purchases:
        lines = lines_by.get(purchase.id, [])
        ev = evaluate(purchase, lines, comps_by.get(purchase.id, []), rates)
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

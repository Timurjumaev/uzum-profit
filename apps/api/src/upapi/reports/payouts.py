"""F38 to'lov prognozi (B5.7): Uzum sotuvchiga qaysi kuni qancha to'laydi.

Qoidalar kodga qotirilmaydi: to'lov jadvali — Sozlamalarda (akkauntga bitta, ``payout_schedules``), shartlari (oy kunlari,
yechish foizi, "10 kun" kechikishi, kechikish ish kunlari) — sanasi bilan ma'lumotnomada (``ref_payout_terms``,
``ref_amounts`` ``payout_*``; yo'q bo'lsa boshlang'ich). Uzum API to'lov sanasini bermaydi — hisob qatorlardan:

- **Yechilgan** qator (``withdrawnProfit`` > 0) prognozga kirmaydi;
- Yakunlangan, hali yechilmagan qator — yechishga tayyor: bugundan, keyingi jadval sanasida to'lanadi;
- Jarayondagi, topshirilgan (``dateIssued`` — mijoz BBP'dan olgan kun) qator — topshirilgan kun + kechikish (10 kun)
  kuni yakunlanadi; summa × F16 R (yakunlanish ulushi) — **taxminiy**;
- Topshirilmagan Jarayondagi qator — sana noma'lum, alohida jamida ("sana noma'lum").

Dam olish kunlari: shanba, yakshanba (bayram ma'lumotnomasi keyin). Ushlanmalar (xarajatlar) hali ayirilmaydi — natija
"ushlanmalarsiz": prognoz haqiqiy to'lov bilan solishtirilib tekshiriladi (``withdrawn_seen_at``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.cash import (
    PayoutRules,
    ScheduleKind,
    ScheduleTerms,
    forecast_payouts,
    payout_rules,
    schedule_terms,
)
from upcore.money import Currency, Money

from upapi.db import models as m
from upapi.reports.stock import completion_by_shop

UZS = Currency.UZS


@dataclass(frozen=True)
class PayoutEventOut:
    expected: date
    latest: date
    gross: Decimal
    fee: Decimal
    net: Decimal
    estimated: bool  # Jarayondagi sotuvlar hisobga olingan (R bilan) — taxminiy


@dataclass(frozen=True)
class PayoutForecast:
    kind: ScheduleKind | None  # jadval kiritilmagan — ``None`` (prognoz yo'q)
    fee_pct: Decimal | None
    rules: PayoutRules
    available: Decimal  # yechishga tayyor (Yakunlangan, yechilmagan) — ushlanmalarsiz
    unknown_date: Decimal  # topshirilmagan Jarayondagi qatorlar summasi (sana noma'lum)
    events: list[PayoutEventOut]


async def _terms(conn: AsyncConnection, kind: ScheduleKind, today: date) -> ScheduleTerms:
    stored = [
        ScheduleTerms(
            ScheduleKind(r.kind),
            None if r.days_of_month is None else tuple(r.days_of_month),
            r.fee_pct,
            r.valid_from,
        )
        for r in await conn.execute(select(m.ref_payout_terms))
    ]
    return schedule_terms(kind, today, stored)


async def load_forecast(conn: AsyncConnection, today: date) -> PayoutForecast:
    ra = m.ref_amounts
    rules = payout_rules(
        [
            (r.code, r.valid_from, r.amount)
            for r in await conn.execute(select(ra).where(ra.c.code.like("payout\\_%")))
        ],
        today,
    )
    ps = m.payout_schedules
    schedule = (
        await conn.execute(
            select(ps.c.kind)
            .where(ps.c.valid_from <= today)
            .order_by(ps.c.valid_from.desc())
            .limit(1)
        )
    ).first()
    if schedule is None:
        return PayoutForecast(None, None, rules, Decimal(0), Decimal(0), [])
    terms = await _terms(conn, ScheduleKind(schedule.kind), today)
    s = m.sale_items
    withdrawn = func.coalesce(func.nullif(s.c.raw["withdrawnProfit"].astext, "").cast(Numeric), 0)
    lines = (
        await conn.execute(
            select(
                s.c.shop_id,
                func.upper(func.trim(s.c.status)).label("status"),
                s.c.issued_at,
                func.coalesce(s.c.seller_profit, 0).label("profit"),
            ).where(
                func.upper(func.trim(s.c.status)).in_(("TO_WITHDRAW", "PROCESSING")),
                withdrawn <= 0,
            )
        )
    ).all()
    rate = await completion_by_shop(conn, {r.shop_id for r in lines}, today)
    ready: dict[date, Money] = {}
    expected: dict[date, Money] = {}
    unknown = Decimal(0)
    for r in lines:
        profit = Decimal(r.profit)
        if r.status == "TO_WITHDRAW":
            ready[today] = ready.get(today, Money.zero(UZS)) + Money(profit, UZS)
            continue
        share = rate.get(r.shop_id)
        if r.issued_at is None or share is None:
            unknown += profit
            continue
        day = max(r.issued_at.date() + timedelta(days=rules.lag_days), today)
        expected[day] = expected.get(day, Money.zero(UZS)) + Money(profit * share, UZS)
    both: dict[date, Money] = dict(ready)
    for day, amount in expected.items():
        both[day] = both.get(day, Money.zero(UZS)) + amount
    sure = {
        e.expected: e.gross.amount
        for e in forecast_payouts(ready, terms, delay_workdays=rules.delay_workdays)
    }
    events = [
        PayoutEventOut(
            e.expected,
            e.latest,
            e.gross.amount,
            e.fee.amount,
            e.net.amount,
            estimated=e.gross.amount > sure.get(e.expected, Decimal(0)),
        )
        for e in forecast_payouts(both, terms, delay_workdays=rules.delay_workdays)
    ]
    available = sum((a.amount for a in ready.values()), Decimal(0))
    return PayoutForecast(terms.kind, terms.fee_pct, rules, available, unknown, events)

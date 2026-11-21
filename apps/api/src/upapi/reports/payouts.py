"""F38 to'lov prognozi (B5.7): Uzum sotuvchiga qaysi kuni qancha to'laydi.

Qoidalar kodga qotirilmaydi: to'lov jadvali — Sozlamalarda (akkauntga bitta, ``payout_schedules``), shartlari (oy kunlari,
yechish foizi, "10 kun" kechikishi, kechikish ish kunlari) — sanasi bilan ma'lumotnomada (``ref_payout_terms``,
``ref_amounts`` ``payout_*``; yo'q bo'lsa boshlang'ich). Uzum API to'lov sanasini bermaydi — hisob qatorlardan.

**Qoida (Temur, 2026-11-22; real to'lovlar bilan tasdiqlangan — ``upcore.cash.payout_date``):** mijoz tovarni olib ketgan kundan
(``dateIssued``) 10 kun o'tgach pul yechishga beriladi va keyingi jadval sanasi 00:00 da avtomatik yechiladi — to'lov sanasi D ga
olib ketilgan kuni ≤ D − 11 bo'lgan qatorlar kiradi. ``withdrawnProfit`` **ishlatilmaydi**: u to'langan qatorlarning aksariyatida
ham 0 (real o'lchov, 2026-11-21) — "yechilmagan" belgisi emas. Qator allaqachon to'langan hisoblanadi, agar uning to'lov sanasi
(``payout_date``) bugun yoki undan oldin bo'lsa (to'lov o'sha kuni yaratiladi).

- Yakunlangan (``TO_WITHDRAW``) qator — 10 kun o'tgan, to'lov sanasi kelajakda: **yechishga tayyor** (``available``, "Ertaroq yechib
  olish" bilan shu summa olinadi) va o'z to'lovida to'liq hisoblanadi;
- Jarayondagi, olib ketilgan qator — olib ketilgan kun + kechikish kuni yakunlanadi; summa × F16 R (yakunlanish ulushi) — **taxminiy**;
- Olib ketilmagan Jarayondagi qator — sana noma'lum, alohida jamida.

**Ushlanmalar:** Uzum to'lovdan xizmat to'lovlarini (reklama, saqlash, qaytarilgan tovar saqlash, jarima) ayiradi (real: jadval to'lovlari
oynadagi foydadan 7–13% kam). Prognoz oxirgi 30 kundagi shu xarajatlarning kunlik o'rtachasini to'lov davri uzunligiga ko'paytirib
ayiradi — natija har doim **taxminiy**. Dam olish kunlari: shanba, yakshanba (bayram ma'lumotnomasi keyin)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.cash import (
    PayoutEvent,
    PayoutRules,
    ScheduleKind,
    ScheduleTerms,
    forecast_payouts,
    payout_date,
    payout_rules,
    schedule_gap_days,
    schedule_terms,
)
from upcore.metrics import TASHKENT
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
    lines = (
        await conn.execute(
            select(
                s.c.shop_id,
                func.upper(func.trim(s.c.status)).label("status"),
                s.c.issued_at,
                func.coalesce(s.c.seller_profit, 0).label("profit"),
            ).where(func.upper(func.trim(s.c.status)).in_(("TO_WITHDRAW", "PROCESSING")))
        )
    ).all()
    rate = await completion_by_shop(
        conn, {r.shop_id for r in lines if r.status == "PROCESSING"}, today
    )
    daily: dict[date, Money] = {}
    sure: dict[date, Money] = {}
    available = Decimal(0)
    unknown = Decimal(0)
    for r in lines:
        profit = Decimal(r.profit)
        if r.issued_at is None:
            if r.status == "PROCESSING":
                unknown += profit
            continue
        picked = r.issued_at.astimezone(TASHKENT).date()
        matured = picked + timedelta(days=rules.lag_days)
        if payout_date(picked, terms, rules.lag_days) <= today:
            continue  # to'lov allaqachon yaratilgan (to'langan yoki yo'lda)
        if r.status == "TO_WITHDRAW":
            sure[matured] = sure.get(matured, Money.zero(UZS)) + Money(profit, UZS)
            daily[matured] = daily.get(matured, Money.zero(UZS)) + Money(profit, UZS)
            if matured <= today:
                available += profit
            continue
        share = rate.get(r.shop_id)
        if share is None:
            unknown += profit
            continue
        daily[matured] = daily.get(matured, Money.zero(UZS)) + Money(profit * share, UZS)
    services = await _services_per_day(conn, today)
    sure_gross = {
        e.expected: e.gross.amount
        for e in forecast_payouts(sure, terms, delay_workdays=rules.delay_workdays)
    }
    events = []
    for e in forecast_payouts(daily, terms, delay_workdays=rules.delay_workdays):
        held = services * schedule_gap_days(e.expected, terms)
        gross = e.gross.amount - held
        if gross <= 0:
            continue  # ushlanma to'lovdan katta — to'lov bo'lmaydi
        adjusted = PayoutEvent(
            e.expected, e.latest, Money(gross, UZS), Money(gross, UZS) * (terms.fee_pct / 100)
        )
        events.append(
            PayoutEventOut(
                adjusted.expected,
                adjusted.latest,
                adjusted.gross.amount,
                adjusted.fee.amount,
                adjusted.net.amount,
                estimated=held > 0 or e.gross.amount > sure_gross.get(e.expected, Decimal(0)),
            )
        )
    return PayoutForecast(terms.kind, terms.fee_pct, rules, available, unknown, events)


SERVICE_CATEGORIES = ("advertising", "storage", "return_storage", "fine")
SERVICES_DAYS = 30


async def _services_per_day(conn: AsyncConnection, today: date) -> Decimal:
    """Uzum to'lovdan ayiradigan xizmat to'lovlarining oxirgi ``SERVICES_DAYS`` kundagi kunlik o'rtachasi (yechish haqi — alohida,
    har to'lovga bitta, bu yerga kirmaydi). Hisobga olinmagan (``excluded``) va daromad turidagi yozuvlar tashqarida."""
    e = m.mp_expenses
    total = await conn.scalar(
        select(func.coalesce(func.sum(e.c.amount), 0)).where(
            e.c.type == "OUTCOME",
            e.c.excluded.is_(None),
            e.c.category.in_(SERVICE_CATEGORIES),
            func.date(func.timezone("Asia/Tashkent", e.c.created_on))
            > today - timedelta(days=SERVICES_DAYS),
            func.date(func.timezone("Asia/Tashkent", e.c.created_on)) <= today,
        )
    )
    return Decimal(total or 0) / SERVICES_DAYS

"""Oylik maqsadlar (M12, B5.8; F59): fakt, oy oxiri prognozi (Bosh sahifa bilan bitta hisob), bajarilish va holat.
``/goals`` sahifasi va "Reja orqada" hodisasi (``upapi.notify``) shu hisobdan foydalanadi."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import GoalStatus, Period, goal_progress, run_rate

from upapi.db import models as m
from upapi.reports import cells as rc
from upapi.reports.common import Filters
from upapi.reports.forecast import basis_values, forecast_basis

type Metric = Literal["revenue", "net_profit", "units"]
METRICS: tuple[Metric, ...] = ("revenue", "net_profit", "units")


class GoalShopOut(BaseModel):
    id: UUID
    name: str


class GoalOut(BaseModel):
    id: UUID
    shop_id: UUID | None  # None — butun tashkilot
    metric: Metric
    target: Decimal
    fact: Decimal
    forecast: Decimal | None  # oy oxiri; kelgusi oyda yo'q
    percent: Decimal  # bajarilish, F59
    forecast_percent: Decimal | None
    deviation_pct: Decimal | None
    status: GoalStatus


class GoalsOut(BaseModel):
    month: date  # oyning 1-kuni
    days_in_month: int
    elapsed_days: int  # prognoz asosidagi to'liq o'tgan kunlar (0 — prognoz yo'q)
    shops: list[GoalShopOut]
    goals: list[GoalOut]


def bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    return first, first.replace(day=calendar.monthrange(day.year, day.month)[1])


def _pick(metric: str, revenue: Decimal, profit: Decimal, units: Decimal | int) -> Decimal:
    return {"revenue": revenue, "net_profit": profit, "units": Decimal(units)}[metric]


async def month_goals(conn: AsyncConnection, month: date | None, now: date) -> GoalsOut:
    first, last = bounds(month or now)
    t = m.goals
    rows = list(
        await conn.execute(
            select(t)
            .where(t.c.period_start == first, t.c.item_id.is_(None))
            .order_by(t.c.shop_id.nulls_first(), t.c.metric)
        )
    )
    shops = [
        GoalShopOut(id=r.id, name=r.alias or r.name)
        for r in await conn.execute(
            select(m.shops).where(m.shops.c.active.is_(True)).order_by(m.shops.c.name)
        )
    ]
    days = last.day
    if now < first:
        period, basis, elapsed = None, None, 0  # kelgusi oy
    elif now > last:
        period, basis, elapsed = Period(first, last), None, days  # o'tgan oy — tugagan
    else:
        period, basis = Period(first, now), forecast_basis(now)
        elapsed = basis.days if basis is not None else 0
    book = None
    if period is not None:
        book = await rc.load_book(conn, period, now)
    out: list[GoalOut] = []
    for g in rows:
        if g.metric not in METRICS:  # bazada qo'lda yozilgan noma'lum ko'rsatkich
            continue
        fact = Decimal(0)
        forecast: Decimal | None = None
        if book is not None and period is not None:
            f = Filters(period, frozenset({g.shop_id}) if g.shop_id else None, now)
            statement = book.scoped(f, period).statement()
            fact = _pick(
                g.metric, statement.revenue.amount, statement.net_profit.amount, statement.units
            )
            if now > last:
                forecast = fact
            elif basis is not None:
                done = book.scoped(f, basis).statement()
                r = (await rc.realization(conn, f)).total
                value = _pick(g.metric, *basis_values(done, r))
                forecast = run_rate(value, elapsed, days)
        p = goal_progress(g.target, fact, forecast)
        out.append(
            GoalOut(
                id=g.id,
                shop_id=g.shop_id,
                metric=g.metric,
                target=g.target,
                fact=fact,
                forecast=forecast,
                percent=p.percent,
                forecast_percent=p.forecast_percent,
                deviation_pct=p.deviation_pct,
                status=p.status,
            )
        )
    return GoalsOut(month=first, days_in_month=days, elapsed_days=elapsed, shops=shops, goals=out)

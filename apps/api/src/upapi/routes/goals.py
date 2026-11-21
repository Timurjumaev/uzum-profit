"""``/goals``: oylik reja-fakt (M12, B5.8; F59). O'qish — ``view_finance``, belgilash — ``manage_settings``.

Maqsad: kalendar oyi, ko'rsatkich (tushum, sof foyda, dona), butun tashkilot yoki bitta do'kon bo'yicha. Fakt — oy boshidan
bugungacha (Bosh sahifadagi bilan bir hisob), oy oxiri prognozi — to'liq o'tgan kunlar run-rate'i (``upapi.reports.forecast``,
Bosh sahifa bilan bitta); o'tgan oy uchun prognoz = fakt, kelgusi oy — fakt 0, prognoz yo'q. Bajarilish %, og'ish va holat — F59
(``upcore.metrics.goal_progress``). Tovar bo'yicha maqsad yo'q (ADR-063).
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from upcore.metrics import GoalStatus, Period, goal_progress, run_rate

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import cells as rc
from upapi.reports.common import Filters, today
from upapi.reports.forecast import basis_values, forecast_basis

router = APIRouter(tags=["goals"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Settings = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]

type Metric = Literal["revenue", "net_profit", "units"]
METRICS: tuple[Metric, ...] = ("revenue", "net_profit", "units")
MAX_TARGET = Decimal("1e13")


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


class GoalIn(BaseModel):
    month: date  # oyning istalgan kuni
    shop_id: UUID | None = None
    metric: Metric
    target: Annotated[Decimal, Field(gt=0)]


def _bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    return first, first.replace(day=calendar.monthrange(day.year, day.month)[1])


@router.get("/orgs/{org_id}/goals", response_model=GoalsOut)
async def list_goals(ctx: Finance, month: date | None = None) -> GoalsOut:
    conn, now = ctx.conn, today()
    first, last = _bounds(month or now)
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


def _pick(metric: str, revenue: Decimal, profit: Decimal, units: Decimal | int) -> Decimal:
    return {"revenue": revenue, "net_profit": profit, "units": Decimal(units)}[metric]


@router.put("/orgs/{org_id}/goals", response_model=GoalOut)
async def set_goal(body: GoalIn, ctx: Settings) -> GoalOut:
    """Maqsadni belgilash yoki yangilash (oy + do'kon + ko'rsatkich bo'yicha bitta)."""
    if body.target > MAX_TARGET:
        raise AppError("goal_invalid", 422, detail="maqsad juda katta")
    if body.shop_id is not None:
        found = await ctx.conn.scalar(select(m.shops.c.id).where(m.shops.c.id == body.shop_id))
        if found is None:
            raise AppError("shop_not_found", 404, detail="do'kon topilmadi")
    first, last = _bounds(body.month)
    t = m.goals
    stmt = pg_insert(t).values(
        org_id=ctx.org_id,
        shop_id=body.shop_id,
        metric=body.metric,
        period_start=first,
        period_end=last,
        target=body.target,
    )
    row = (
        await ctx.conn.execute(
            stmt.on_conflict_do_update(
                constraint="uq_goals_org_id_shop_id_item_id_metric_period_start",
                set_={"target": stmt.excluded.target},
            ).returning(t)
        )
    ).one()
    await ctx.audit(
        "goal.set",
        "goal",
        row.id,
        after={"month": first.isoformat(), "metric": body.metric, "target": str(body.target)},
    )
    # Javob — ro'yxatdagi bilan bir xil shaklda (fakt/prognoz bilan).
    listed = await list_goals(ctx, first)
    return next(x for x in listed.goals if x.id == row.id)


@router.delete("/orgs/{org_id}/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: UUID, ctx: Settings) -> None:
    t = m.goals
    row = (await ctx.conn.execute(delete(t).where(t.c.id == goal_id).returning(t.c.id))).first()
    if row is None:
        raise AppError("goal_not_found", 404, detail="maqsad topilmadi")
    await ctx.audit("goal.delete", "goal", goal_id)

"""``/goals``: oylik reja-fakt (M12, B5.8; F59). O'qish — ``view_finance``, belgilash — ``manage_settings``.

Maqsad: kalendar oyi, ko'rsatkich (tushum, sof foyda, dona), butun tashkilot yoki bitta do'kon bo'yicha. Fakt — oy boshidan
bugungacha (Bosh sahifadagi bilan bir hisob), oy oxiri prognozi — to'liq o'tgan kunlar run-rate'i (``upapi.reports.forecast``,
Bosh sahifa bilan bitta); o'tgan oy uchun prognoz = fakt, kelgusi oy — fakt 0, prognoz yo'q. Bajarilish %, og'ish va holat — F59
(``upcore.metrics.goal_progress``). Tovar bo'yicha maqsad yo'q (ADR-063).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports.common import today
from upapi.reports.goals import GoalOut, GoalsOut, Metric, bounds, month_goals

router = APIRouter(tags=["goals"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Settings = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
MAX_TARGET = Decimal("1e13")


class GoalIn(BaseModel):
    month: date  # oyning istalgan kuni
    shop_id: UUID | None = None
    metric: Metric
    target: Annotated[Decimal, Field(gt=0)]


@router.get("/orgs/{org_id}/goals", response_model=GoalsOut)
async def list_goals(ctx: Finance, month: date | None = None) -> GoalsOut:
    return await month_goals(ctx.conn, month, today())


@router.put("/orgs/{org_id}/goals", response_model=GoalOut)
async def set_goal(body: GoalIn, ctx: Settings) -> GoalOut:
    """Maqsadni belgilash yoki yangilash (oy + do'kon + ko'rsatkich bo'yicha bitta)."""
    if body.target > MAX_TARGET:
        raise AppError("goal_invalid", 422, detail="maqsad juda katta")
    if body.shop_id is not None:
        found = await ctx.conn.scalar(select(m.shops.c.id).where(m.shops.c.id == body.shop_id))
        if found is None:
            raise AppError("shop_not_found", 404, detail="do'kon topilmadi")
    first, last = bounds(body.month)
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
    listed = await month_goals(ctx.conn, first, today())
    return next(x for x in listed.goals if x.id == row.id)


@router.delete("/orgs/{org_id}/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: UUID, ctx: Settings) -> None:
    t = m.goals
    row = (await ctx.conn.execute(delete(t).where(t.c.id == goal_id).returning(t.c.id))).first()
    if row is None:
        raise AppError("goal_not_found", 404, detail="maqsad topilmadi")
    await ctx.audit("goal.delete", "goal", goal_id)

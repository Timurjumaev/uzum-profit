"""``/reports/monthly``: oylik hisobot (M14, B7.3; ADR-065). Ruxsat — ``view_finance``.

Hamma raqam mavjud hisobdan (``dashboard`` / ``upcore.pnl``) — yangi formula yo'q: hisob varag'i (F3 → F12) oldingi **kalendar oy**
bilan, "Buyurtmadan sof foydagacha" (F49), eng foydali va zarardagi SKU'lar, Uzum va o'z xarajatlari toifalar bo'yicha (hisob
varag'ida), tovardagi pul (F29 — hozirgi holat). Foyda sahifasi bilan bir xil davr uchun tiyinigacha teng (test).

**Oyning yopilishi:** oy tugamagan yoki unda Jarayondagi buyurtma qolgan bo'lsa — hisobot **dastlabki** (nechta buyurtma va qancha
summa hali jarayonda — ``processing_lines`` / ``processing_revenue``); oy tugagan va hammasi yakuniy holatga yetgan — **yakuniy**.
Chop etish va PDF — brauzerdan (chop etish uslubi); server tomonda PDF yasalmaydi.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from upcore.metrics import Period

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.errors import AppError
from upapi.reports.common import Filters, Heavy, PeriodOut, today
from upapi.reports.goals import bounds
from upapi.reports.schemas import RowOut, StatementOut
from upapi.routes import dashboard as dashboard_routes
from upapi.routes.dashboard import FlowStepOut, SkuBriefOut

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]


class MonthlyReportOut(BaseModel):
    month: date  # oyning 1-kuni
    period: PeriodOut  # hisobot davri: oy boshidan oy oxirigacha (oy tugamagan bo'lsa — bugungacha)
    previous: PeriodOut  # oldingi kalendar oy
    month_over: bool  # oy oxiri o'tib ketdi
    status: Literal["preliminary", "final"]
    processing_lines: int  # shu oyda hali Jarayondagi buyurtma qatorlari
    processing_revenue: Decimal  # ularning tushumi
    statement: StatementOut  # F3 → F12
    rows: list[RowOut]  # hisob varag'i: joriy, tushumga nisbatan, oldingi oy, farq
    flow: list[FlowStepOut]  # F49
    top: list[SkuBriefOut]
    bottom: list[SkuBriefOut]
    frozen_money: Decimal  # F29: tovardagi pul (hozirgi holat)
    in_transit_value: Decimal  # F29: yo'lda


def previous_month(first: date) -> Period:
    end = first - timedelta(days=1)
    return Period(end.replace(day=1), end)


@router.get("/orgs/{org_id}/reports/monthly", response_model=MonthlyReportOut)
async def monthly_report(ctx: Finance, _: Heavy, month: date | None = None) -> MonthlyReportOut:
    now = today()
    first, last = bounds(month or now)
    if first > now:
        raise AppError("bad_day", 422, detail="kelajak oyi uchun hisobot yo'q")
    period = Period(first, min(last, now))
    prev = previous_month(first)
    f = Filters(period, None, now, previous=prev)
    out = await dashboard_routes.dashboard(ctx, f, None)
    s = out.statement
    over = last < now
    return MonthlyReportOut(
        month=first,
        period=PeriodOut.of(period),
        previous=PeriodOut.of(prev),
        month_over=over,
        status="final" if over and s.lines_processing == 0 else "preliminary",
        processing_lines=s.lines_processing,
        processing_revenue=s.revenue_processing,
        statement=s,
        rows=out.rows,
        flow=out.summary.flow,
        top=out.top,
        bottom=out.bottom,
        frozen_money=out.kpis.frozen_money,
        in_transit_value=out.kpis.in_transit_value,
    )

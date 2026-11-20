"""``/payouts/forecast``: Uzum to'lov prognozi (B5.7, F38). Ruxsat — ``view_finance`` (egasi, menejer, buxgalter).

Jadval Sozlamalarda kiritilmagan bo'lsa ``schedule`` — ``null`` va prognoz bo'sh (jadval o'ylab topilmaydi). Summalar
ushlanmalarsiz; Jarayondagi sotuvlar F16 R bilan va ``estimated`` belgisi bilan (09 §? ; reports/payouts.py)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.reports.common import today
from upapi.reports.payouts import load_forecast

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]


class PayoutEventSchema(BaseModel):
    expected: date  # kutilgan to'lov sanasi (jadval; dam olish kuni → keyingi ish kuni)
    latest: date  # eng kech sana (+ kechikish ish kunlari)
    gross: Decimal  # to'lov summasi (yechish haqigacha, ushlanmalarsiz)
    fee: Decimal  # pul yechish haqi (jadval foizi)
    net: Decimal
    estimated: bool  # Jarayondagi sotuvlar R bilan hisobga olingan — taxminiy


class PayoutRulesSchema(BaseModel):
    lag_days: int
    urgent_fee_pct: Decimal
    delay_workdays: int


class PayoutForecastOut(BaseModel):
    schedule: str | None  # jadval turi; kiritilmagan — ``null``
    fee_pct: Decimal | None
    rules: PayoutRulesSchema
    available: Decimal  # yechishga tayyor (Yakunlangan, yechilmagan), ushlanmalarsiz
    unknown_date: Decimal  # topshirilmagan Jarayondagi qatorlar (sana noma'lum)
    events: list[PayoutEventSchema]


@router.get("/orgs/{org_id}/payouts/forecast", response_model=PayoutForecastOut)
async def payout_forecast(ctx: Finance) -> PayoutForecastOut:
    f = await load_forecast(ctx.conn, today())
    return PayoutForecastOut(
        schedule=f.kind.value if f.kind else None,
        fee_pct=f.fee_pct,
        rules=PayoutRulesSchema(
            lag_days=f.rules.lag_days,
            urgent_fee_pct=f.rules.urgent_fee_pct,
            delay_workdays=f.rules.delay_workdays,
        ),
        available=f.available,
        unknown_date=f.unknown_date,
        events=[PayoutEventSchema(**e.__dict__) for e in f.events],
    )

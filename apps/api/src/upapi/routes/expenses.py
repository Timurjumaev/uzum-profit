"""``/expenses``: xarajatlar (M8; P&L xarajat qatorlari drill-down'i). Ruxsat — ``view_settings`` (egasi, menejer,
buxgalter — 03 §10 "xarajat ... ko'rish").

- **Uzum xarajatlari** (F9): toifalar bo'yicha ishorali yig'indi (OUTCOME +, INCOME − — kompensatsiya), oylar trendi,
  eng katta jarimalar; yig'indi = P&L dagi F9 (bir xil qoidalar: ``excluded`` bo'sh, toifa P&L'ga kiradi). Ro'yxat —
  hamma qatorlar (``include_excluded`` bilan chiqarilganlari ham, sababi bilan), kursor bilan.
- **O'z xarajatlari** (F10): davrga to'g'ri keladigan qismi (kunlik amortizatsiya, ``own_expense_in_period``),
  toifalar bo'yicha. Do'kon filtri bo'lsa — shu do'konlar va tashkilot darajasidagilari (``scope``) to'liq summasi;
  P&L'da esa tashkilot xarajati do'konlarga tushum ulushida taqsimlanadi (ADR-026).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from upcore.expenses import Direction, ExpenseCategory, signed_amount
from upcore.metrics import ManualExpense, business_date, own_expense_in_period
from upcore.money import Currency, Money

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports.cells import in_pnl, month_start
from upapi.reports.common import (
    Cursor,
    Filters,
    Limit,
    Meta,
    decode_cursor,
    encode_cursor,
    filters,
    meta,
)

router = APIRouter(tags=["reports"])
Settings_ = Annotated[OrgContext, Depends(require(Permission.VIEW_SETTINGS))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["expenses"]
UZS = Currency.UZS
FINES = 10


class CategoryOut(BaseModel):
    category: str
    amount: Decimal


class MonthOut(BaseModel):
    month: date
    categories: dict[str, Decimal]


class ExpenseOut(BaseModel):
    id: UUID
    shop_id: UUID
    external_id: int
    created_on: datetime
    day: date  # F1
    code: str | None
    raw_code: str | None
    category: str
    type: str  # OUTCOME / INCOME
    amount: Decimal  # P&L ta'siri, ishora bilan (F9)
    name: str | None
    status: str | None
    excluded: str | None  # nega P&L'ga kirmadi
    in_pnl: bool
    order_id: int | None
    sale_item_id: UUID | None


class OwnExpenseOut(BaseModel):
    id: UUID
    category: str
    scope: str  # org / shop / item
    shop_id: UUID | None
    item_id: UUID | None
    start_on: date
    end_on: date
    amount: Decimal  # to'liq summa
    in_period: Decimal  # F10: davrga to'g'ri keladigan qismi
    recurrence: str | None
    note: str | None


class ExpensesOut(BaseModel):
    meta: Meta
    uzum: list[CategoryOut]  # F9 turlari
    uzum_total: Decimal
    by_month: list[MonthOut]
    fines: list[ExpenseOut]  # eng katta jarimalar
    own: list[CategoryOut]  # F10 toifalari
    own_total: Decimal
    own_items: list[OwnExpenseOut]
    items: list[ExpenseOut]
    next_cursor: str | None


def _row(r: Any) -> ExpenseOut:
    return ExpenseOut(
        id=r.id,
        shop_id=r.shop_id,
        external_id=r.external_id,
        created_on=r.created_on,
        day=business_date(r.created_on),
        code=r.code,
        raw_code=r.raw_code,
        category=r.category,
        type=r.type,
        amount=signed_amount(Money(r.amount, UZS), r.type).amount,
        name=r.name,
        status=r.status,
        excluded=r.excluded,
        in_pnl=r.excluded is None and in_pnl(r.category),
        order_id=r.order_external_id,
        sale_item_id=r.sale_item_id,
    )


def _categories(totals: dict[str, Money]) -> list[CategoryOut]:
    return [CategoryOut(category=c, amount=a.amount) for c, a in sorted(totals.items())]


@router.get("/orgs/{org_id}/expenses", response_model=ExpensesOut)
async def expenses(
    ctx: Settings_,
    f: Filter,
    category: Annotated[str | None, Query(description="Uzum toifasi (ro'yxat uchun)")] = None,
    include_excluded: Annotated[bool, Query(description="P&L'ga kirmaganlari ham")] = False,
    limit: Limit = 100,
    cursor: Cursor = None,
) -> ExpensesOut:
    e = m.mp_expenses
    zero = Money.zero(UZS)
    where = [
        e.c.created_on >= day_start(f.period.start),
        e.c.created_on < day_start(f.period.end + timedelta(days=1)),
    ]
    if f.shops:
        where.append(e.c.shop_id.in_(f.shops))

    # F9 yig'indilari va trend — P&L bilan bir xil qatorlar.
    totals: dict[str, Money] = {}
    months: dict[date, dict[str, Money]] = {}
    fines = []
    for r in await ctx.conn.execute(select(e).where(*where, e.c.excluded.is_(None))):
        if not in_pnl(r.category):
            continue
        signed = signed_amount(Money(r.amount, UZS), r.type)
        totals[r.category] = totals.get(r.category, zero) + signed
        month = months.setdefault(month_start(business_date(r.created_on)), {})
        month[r.category] = month.get(r.category, zero) + signed
        if r.category == ExpenseCategory.FINE.value and r.type == Direction.OUTCOME.value:
            fines.append(r)
    fines.sort(key=lambda r: (-r.amount, r.created_on, r.id))

    query = select(e).where(*where).order_by(e.c.created_on.desc(), e.c.id.desc()).limit(limit + 1)
    if not include_excluded:
        query = query.where(e.c.excluded.is_(None))
    if category is not None:
        query = query.where(e.c.category == category)
    after = decode_cursor(cursor, 2)
    if after is not None:
        at, last = datetime.fromisoformat(after[0]), UUID(after[1])
        query = query.where(or_(e.c.created_on < at, and_(e.c.created_on == at, e.c.id < last)))
    rows = list(await ctx.conn.execute(query))
    more = len(rows) > limit
    rows = rows[:limit]

    x, c = m.manual_expenses, m.expense_categories
    own_query = (
        select(x, c.c.name.label("category"))
        .join(c, c.c.id == x.c.category_id)
        .where(x.c.start_on <= f.period.end, x.c.end_on >= f.period.start)
        .order_by(x.c.start_on, x.c.created_at, x.c.id)
    )
    own_rows = list(await ctx.conn.execute(own_query))
    item_shops: dict[UUID, set[UUID]] = {}
    items = {r.item_id for r in own_rows if r.item_id is not None}
    if items:
        k = m.mp_skus
        for r in await ctx.conn.execute(
            select(k.c.item_id, k.c.shop_id).where(k.c.item_id.in_(items))
        ):
            item_shops.setdefault(r.item_id, set()).add(r.shop_id)
    own_totals: dict[str, Money] = {}
    own_items = []
    for r in own_rows:
        scope = "item" if r.item_id is not None else "shop" if r.shop_id is not None else "org"
        if f.shops is not None:
            shops = {r.shop_id} if r.shop_id is not None else item_shops.get(r.item_id, set())
            if scope != "org" and not shops & f.shops:
                continue
        part = own_expense_in_period(
            ManualExpense(Money(r.amount, UZS), r.start_on, r.end_on), f.period
        )
        own_totals[r.category] = own_totals.get(r.category, zero) + part
        own_items.append(
            OwnExpenseOut(
                id=r.id,
                category=r.category,
                scope=scope,
                shop_id=r.shop_id,
                item_id=r.item_id,
                start_on=r.start_on,
                end_on=r.end_on,
                amount=r.amount,
                in_period=part.amount,
                recurrence=r.recurrence,
                note=r.note,
            )
        )

    last_row = rows[-1] if rows else None
    return ExpensesOut(
        meta=await meta(ctx.conn, f, KINDS),
        uzum=_categories(totals),
        uzum_total=sum(totals.values(), zero).amount,
        by_month=[
            MonthOut(month=mo, categories={k: v.amount for k, v in sorted(cats.items())})
            for mo, cats in sorted(months.items())
        ],
        fines=[_row(r) for r in fines[:FINES]],
        own=_categories(own_totals),
        own_total=sum(own_totals.values(), zero).amount,
        own_items=own_items,
        items=[_row(r) for r in rows],
        next_cursor=encode_cursor([last_row.created_on.isoformat(), str(last_row.id)])
        if more and last_row is not None
        else None,
    )

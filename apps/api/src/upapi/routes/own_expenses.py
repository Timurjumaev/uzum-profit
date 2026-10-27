"""``/own-expenses``: o'z xarajatlarim (M8, F10) — qo'shish, tahrirlash, o'chirish. O'qish (``GET /expenses``) —
``view_settings``; yozish — ``manage_settings`` (egasi, menejer), har o'zgarish audit jurnaliga yoziladi.

Xarajat — summa ``[start_on; end_on]`` kunlariga teng taqsimlanadi (F10): bir martalik — ``start_on = end_on``,
amortizatsiya (masalan, printer 12 oyga) — davr oxirigacha. Takroriy (har oy shu kuni): ``repeat_months`` ≥ 2 bo'lsa har
oy uchun alohida bir kunlik yozuv yaratiladi (``recurrence = monthly``, oy kunida kun yo'q bo'lsa oy oxirgi kuni);
cheksiz takrorlash va seriyani birga tahrirlash — keyin. Toifa — nom bilan (yo'q bo'lsa yaratiladi); tavsiya etilgan
boshlang'ich toifalar ro'yxatda. P&L bu jadvalni to'g'ridan-to'g'ri o'qiydi — qayta hisob navbati kerak emas.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, insert, select, update

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError

router = APIRouter(tags=["settings"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_SETTINGS))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
DEFAULT_CATEGORIES = ["ish haqi", "ijara", "qadoq", "internet", "bank", "transport", "boshqa"]
MAX_REPEAT = 24
Name = Annotated[str, Field(min_length=1, max_length=60)]
Note = Annotated[str | None, Field(max_length=300)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=16, decimal_places=2)]


class CategoriesOut(BaseModel):
    items: list[str]  # mavjud toifalar + tavsiya etilgan boshlang'ichlar


class OwnRowOut(BaseModel):
    id: UUID
    category: str
    shop_id: UUID | None
    item_id: UUID | None
    start_on: date
    end_on: date
    amount: Decimal
    recurrence: str | None
    note: str | None


class OwnExpenseIn(BaseModel):
    category: Name
    amount: Amount
    start_on: date
    end_on: date | None = None  # bo'sh — bir martalik
    shop_id: UUID | None = None
    item_id: UUID | None = None
    note: Note = None
    repeat_months: Annotated[int, Field(ge=1, le=MAX_REPEAT)] = 1

    @model_validator(mode="after")
    def _period(self) -> OwnExpenseIn:
        if self.end_on is not None and self.end_on < self.start_on:
            raise ValueError("end_on start_on dan oldin")
        if self.repeat_months > 1 and self.end_on not in (None, self.start_on):
            raise ValueError("takroriy xarajatda davr (amortizatsiya) bo'lmaydi")
        return self


class OwnExpensePatch(BaseModel):
    category: Name | None = None
    amount: Amount | None = None
    start_on: date | None = None
    end_on: date | None = None
    shop_id: UUID | None = None
    item_id: UUID | None = None
    note: Note = None


def _audit(values: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v if isinstance(v, (str, bool, list)) or v is None else str(v) for k, v in values.items()
    }


def _add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


async def _category_id(ctx: OrgContext, name: str) -> UUID:
    c = m.expense_categories
    name = name.strip()
    found = await ctx.conn.scalar(select(c.c.id).where(c.c.name == name))
    if found is not None:
        return found  # type: ignore[no-any-return]
    return (  # type: ignore[no-any-return]
        await ctx.conn.scalar(insert(c).values(org_id=ctx.org_id, name=name).returning(c.c.id))
    )


async def _links_exist(ctx: OrgContext, shop_id: UUID | None, item_id: UUID | None) -> None:
    if (
        shop_id is not None
        and await ctx.conn.scalar(select(m.shops.c.id).where(m.shops.c.id == shop_id)) is None
    ):
        raise AppError("shop_not_found", 404)
    if (
        item_id is not None
        and await ctx.conn.scalar(select(m.items.c.id).where(m.items.c.id == item_id)) is None
    ):
        raise AppError("item_not_found", 404)


def _out(row: Any, category: str) -> OwnRowOut:
    return OwnRowOut(
        id=row.id,
        category=category,
        shop_id=row.shop_id,
        item_id=row.item_id,
        start_on=row.start_on,
        end_on=row.end_on,
        amount=row.amount,
        recurrence=row.recurrence,
        note=row.note,
    )


async def _one(ctx: OrgContext, expense_id: UUID) -> Any:
    x, c = m.manual_expenses, m.expense_categories
    row = (
        await ctx.conn.execute(
            select(x, c.c.name.label("category"))
            .join(c, c.c.id == x.c.category_id)
            .where(x.c.id == expense_id)
        )
    ).first()
    if row is None:
        raise AppError("expense_not_found", 404)
    return row


@router.get("/orgs/{org_id}/own-expense-categories", response_model=CategoriesOut)
async def categories(ctx: Viewer) -> CategoriesOut:
    c = m.expense_categories
    names = [r for (r,) in await ctx.conn.execute(select(c.c.name).order_by(c.c.name))]
    return CategoriesOut(items=names + [d for d in DEFAULT_CATEGORIES if d not in names])


@router.post("/orgs/{org_id}/own-expenses", response_model=list[OwnRowOut], status_code=201)
async def create(body: OwnExpenseIn, ctx: Manager) -> list[OwnRowOut]:
    await _links_exist(ctx, body.shop_id, body.item_id)
    category_id = await _category_id(ctx, body.category)
    t = m.manual_expenses
    out = []
    for i in range(body.repeat_months):
        if body.repeat_months > 1:
            day = _add_months(body.start_on, i)
            start, end, recurrence = day, day, "monthly"
        else:
            start, end, recurrence = body.start_on, body.end_on or body.start_on, None
        row = (
            await ctx.conn.execute(
                insert(t)
                .values(
                    org_id=ctx.org_id,
                    category_id=category_id,
                    shop_id=body.shop_id,
                    item_id=body.item_id,
                    amount=body.amount,
                    start_on=start,
                    end_on=end,
                    recurrence=recurrence,
                    note=body.note,
                )
                .returning(t)
            )
        ).one()
        await ctx.audit(
            "own_expense.create",
            "manual_expense",
            row.id,
            after=_audit(
                {**body.model_dump(exclude={"repeat_months"}), "start_on": start, "end_on": end}
            ),
        )
        out.append(_out(row, body.category.strip()))
    return out


@router.patch("/orgs/{org_id}/own-expenses/{expense_id}", response_model=OwnRowOut)
async def update_expense(expense_id: UUID, body: OwnExpensePatch, ctx: Manager) -> OwnRowOut:
    row = await _one(ctx, expense_id)
    values = body.model_dump(exclude_unset=True)
    for key in ("category", "amount", "start_on", "end_on"):
        if key in values and values[key] is None:
            raise AppError("bad_request", 422, detail=f"{key} bo'sh bo'lmaydi")
    start, end = values.get("start_on", row.start_on), values.get("end_on", row.end_on)
    if end < start:
        raise AppError("bad_period", 422, detail="Davr oxiri boshidan oldin")
    await _links_exist(ctx, values.get("shop_id"), values.get("item_id"))
    category = row.category
    if "category" in values:
        category = values.pop("category").strip()
        values["category_id"] = await _category_id(ctx, category)
    if not values:
        return _out(row, category)
    before = {k: getattr(row, k) for k in values if hasattr(row, k)}
    t = m.manual_expenses
    updated = (
        await ctx.conn.execute(
            update(t)
            .where(t.c.id == expense_id)
            .values(**values, updated_at=func.now())
            .returning(t)
        )
    ).one()
    await ctx.audit(
        "own_expense.update",
        "manual_expense",
        expense_id,
        before=_audit(before),
        after=_audit({**values, "category_id": values.get("category_id")}),
    )
    return _out(updated, category)


@router.delete("/orgs/{org_id}/own-expenses/{expense_id}", status_code=204)
async def delete_expense(expense_id: UUID, ctx: Manager) -> Response:
    row = await _one(ctx, expense_id)
    await ctx.conn.execute(delete(m.manual_expenses).where(m.manual_expenses.c.id == expense_id))
    before = {
        k: getattr(row, k)
        for k in ("category", "amount", "start_on", "end_on", "shop_id", "item_id", "note")
    }
    await ctx.audit("own_expense.delete", "manual_expense", expense_id, before=_audit(before))
    return Response(status_code=204)

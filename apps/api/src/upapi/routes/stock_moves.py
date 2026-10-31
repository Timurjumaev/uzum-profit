"""``/stock-moves``: o'z omborim bo'yicha hisobdan chiqarish va inventarizatsiya tuzatishi (M10, B4.7).

- ``writeoff`` — brak, yo'qotish, kamomad (musbat dona): tovar hisobdan chiqadi. Tannarx dvigatelida (F21) lotdan
  chiqim sifatida yeydi (``upapi.calc.costs``), o'z omborim qoldig'ini kamaytiradi.
- ``adjust`` — inventarizatsiya tuzatishi (ishorali dona, 0 emas): manfiysi hisobdan chiqarish kabi lotdan chiqim,
  musbati faqat o'z omborim sonini oshiradi (lot yaratmaydi — tannarx faqat xariddan).

Ruxsat — ``manage_purchases`` (egasi, menejer, omborchi); omborchi summani ko'rmaydi, shuning uchun bu yerda summa
yo'q. Har yozuv audit jurnaliga yoziladi va shu tranzaksiyada tovar bo'yicha qayta hisob so'rovi qo'yiladi
(``calc.org`` commitdan keyin) → o'tgan sotuvlar tannarxi va P&L "qayta hisoblandi". Sinxron ``stock_moves`` ga
tegmaydi (tamoyil 7).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, insert, select

from upapi import calc
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports.common import today
from upapi.routes.purchases import _kick

router = APIRouter(tags=["inventory"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_PURCHASES))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_PURCHASES))]
KINDS = ("writeoff", "adjust")
MAX_QTY = 10_000_000


class StockMoveIn(BaseModel):
    item_id: UUID
    kind: Literal["writeoff", "adjust"]
    qty: Annotated[int, Field(ge=-MAX_QTY, le=MAX_QTY)]  # writeoff — musbat, adjust — ishorali
    day: date
    note: Annotated[str | None, Field(max_length=500)] = None
    purchase_line_id: UUID | None = None

    @model_validator(mode="after")
    def _check(self) -> StockMoveIn:
        if self.kind == "writeoff" and self.qty <= 0:
            raise ValueError("hisobdan chiqarish donasi musbat bo'lishi kerak")
        if self.kind == "adjust" and self.qty == 0:
            raise ValueError("tuzatish donasi 0 bo'lmasligi kerak")
        return self


class StockMoveOut(BaseModel):
    id: UUID
    item_id: UUID
    kind: str
    qty: int
    day: date
    note: str | None
    purchase_line_id: UUID | None
    created_at: datetime


class StockMovesOut(BaseModel):
    items: list[StockMoveOut]


def _out(row: Any) -> StockMoveOut:
    return StockMoveOut(
        id=row.id,
        item_id=row.item_id,
        kind=row.kind,
        qty=row.qty,
        day=row.day,
        note=row.note,
        purchase_line_id=row.purchase_line_id,
        created_at=row.created_at,
    )


@router.get("/orgs/{org_id}/items/{item_id}/stock-moves", response_model=StockMovesOut)
async def list_stock_moves(item_id: UUID, ctx: Viewer) -> StockMovesOut:
    """Tovarning hisobdan chiqarish va tuzatish yozuvlari (yangisi birinchi)."""
    sm = m.stock_moves
    rows = await ctx.conn.execute(
        select(sm)
        .where(sm.c.item_id == item_id, sm.c.kind.in_(KINDS))
        .order_by(sm.c.day.desc(), sm.c.created_at.desc())
    )
    return StockMovesOut(items=[_out(r) for r in rows])


@router.post("/orgs/{org_id}/stock-moves", response_model=StockMoveOut, status_code=201)
async def create_stock_move(
    body: StockMoveIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> StockMoveOut:
    if body.day > today():
        raise AppError("bad_day", 422, detail="kelajak sanasi bo'lmaydi")
    if await ctx.conn.scalar(select(m.items.c.id).where(m.items.c.id == body.item_id)) is None:
        raise AppError("item_not_found", 404)
    if body.purchase_line_id is not None:
        pl = m.purchase_lines
        line = await ctx.conn.scalar(select(pl.c.item_id).where(pl.c.id == body.purchase_line_id))
        if line is None:
            raise AppError("purchase_line_not_found", 404)
        if line != body.item_id:
            raise AppError("line_item_mismatch", 422)
    sm = m.stock_moves
    row = (
        await ctx.conn.execute(
            insert(sm).values(org_id=ctx.org_id, **body.model_dump(mode="python")).returning(*sm.c)
        )
    ).one()
    await ctx.audit(
        "stock_move.create",
        "stock_move",
        row.id,
        after={**body.model_dump(mode="json")},
    )
    await calc.request(ctx.conn, ctx.org_id, calc.Scope.ITEM, body.item_id)
    background.add_task(_kick, request, ctx.org_id)
    return _out(row)


@router.delete("/orgs/{org_id}/stock-moves/{move_id}", status_code=204)
async def delete_stock_move(
    move_id: UUID, ctx: Manager, request: Request, background: BackgroundTasks
) -> Response:
    sm = m.stock_moves
    row = (
        await ctx.conn.execute(select(sm).where(sm.c.id == move_id, sm.c.kind.in_(KINDS)))
    ).first()
    if row is None:
        raise AppError("stock_move_not_found", 404)
    await ctx.conn.execute(delete(sm).where(sm.c.id == move_id))
    await ctx.audit(
        "stock_move.delete",
        "stock_move",
        move_id,
        before={"item_id": str(row.item_id), "kind": row.kind, "qty": row.qty},
    )
    await calc.request(ctx.conn, ctx.org_id, calc.Scope.ITEM, row.item_id)
    background.add_task(_kick, request, ctx.org_id)
    return Response(status_code=204)

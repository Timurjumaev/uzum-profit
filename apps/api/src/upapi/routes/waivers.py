"""``/fee-waivers``: Uzum bonuslari (ADR-031) — vaqtinchalik bepul xarajat davrlari.

O'qish — ``view_finance`` (hisobotlarni ko'radiganlar); qo'shish, tahrirlash, o'chirish — ``manage_settings`` (egasi,
menejer), har o'zgarish audit jurnaliga yoziladi. Tizim taklifini tasdiqlash — ``source = detected`` bilan qo'shish;
rad etish — ``dismissed = true`` bilan qo'shish (shu kunlar qayta taklif qilinmaydi, hech narsaga ta'sir qilmaydi).
Bonus haqiqiy foydani o'zgartirmaydi — faqat belgilaydi (``upapi.reports.waivers``).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select, update
from upcore.waivers import WaiverError, check, waiver_kinds

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import waivers as rw

router = APIRouter(tags=["settings"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
Reason = Annotated[str, Field(max_length=300)]


class FeeWaiversOut(BaseModel):
    items: list[rw.WaiverOut]
    kinds: list[str]  # tanlash mumkin bo'lgan turlar (``upcore.waivers.waiver_kinds``)


class WaiverIn(BaseModel):
    shop_id: UUID | None = None  # ``null`` — hamma do'kon
    start_on: date
    end_on: date
    kinds: list[str]
    reason: Reason = ""
    source: Literal["manual", "detected"] = "manual"
    dismissed: bool = False  # rad etilgan taklif


class WaiverPatch(BaseModel):
    shop_id: UUID | None = None
    start_on: date | None = None
    end_on: date | None = None
    kinds: list[str] | None = None
    reason: Reason | None = None


def _audit(values: dict[str, Any]) -> dict[str, Any]:
    """JSONB uchun: sana va UUID — satr."""
    return {
        k: v if isinstance(v, (str, bool, list)) or v is None else str(v) for k, v in values.items()
    }


def _checked(start: date, end: date, kinds: list[str]) -> list[str]:
    try:
        return check(start, end, kinds)
    except WaiverError as e:
        raise AppError(e.code, 422, detail=str(e)) from e


async def _shop_exists(ctx: OrgContext, shop_id: UUID | None) -> None:
    if shop_id is None:
        return
    found = await ctx.conn.scalar(select(m.shops.c.id).where(m.shops.c.id == shop_id))
    if found is None:
        raise AppError("shop_not_found", 404)


async def _one(ctx: OrgContext, waiver_id: UUID) -> Any:
    t = m.fee_waivers
    row = (await ctx.conn.execute(select(t).where(t.c.id == waiver_id))).first()
    if row is None:
        raise AppError("waiver_not_found", 404)
    return row


@router.get("/orgs/{org_id}/fee-waivers", response_model=FeeWaiversOut)
async def list_waivers(ctx: Finance) -> FeeWaiversOut:
    return FeeWaiversOut(
        items=[rw.WaiverOut.of(r) for r in await rw.rows(ctx.conn)], kinds=waiver_kinds()
    )


@router.post("/orgs/{org_id}/fee-waivers", response_model=rw.WaiverOut, status_code=201)
async def create_waiver(body: WaiverIn, ctx: Manager) -> rw.WaiverOut:
    kinds = _checked(body.start_on, body.end_on, body.kinds)
    await _shop_exists(ctx, body.shop_id)
    values = {
        "shop_id": body.shop_id,
        "start_on": body.start_on,
        "end_on": body.end_on,
        "kinds": kinds,
        "reason": body.reason.strip(),
        "source": body.source,
    }
    t = m.fee_waivers
    row = (
        await ctx.conn.execute(
            insert(t)
            .values(
                org_id=ctx.org_id,
                created_by=ctx.user.user_id,
                dismissed_at=func.now() if body.dismissed else None,
                **values,
            )
            .returning(t)
        )
    ).one()
    action = "fee_waiver.dismiss" if body.dismissed else "fee_waiver.create"
    await ctx.audit(action, "fee_waiver", row.id, after=_audit(values))
    return rw.WaiverOut.of(row)


@router.patch("/orgs/{org_id}/fee-waivers/{waiver_id}", response_model=rw.WaiverOut)
async def update_waiver(waiver_id: UUID, body: WaiverPatch, ctx: Manager) -> rw.WaiverOut:
    row = await _one(ctx, waiver_id)
    values = body.model_dump(exclude_unset=True)
    if values.get("reason") is None:
        values.pop("reason", None)  # sabab NULL bo'lmaydi
    for key in ("start_on", "end_on", "kinds"):
        if key in values and values[key] is None:
            raise AppError("bad_request", 422, detail=f"{key} bo'sh bo'lmaydi")
    start, end = values.get("start_on", row.start_on), values.get("end_on", row.end_on)
    kinds = _checked(start, end, values.get("kinds", list(row.kinds)))
    if "kinds" in values:
        values["kinds"] = kinds
    if "reason" in values:
        values["reason"] = values["reason"].strip()
    if "shop_id" in values:
        await _shop_exists(ctx, values["shop_id"])
    if values:
        before = {k: getattr(row, k) for k in values}
        t = m.fee_waivers
        row = (
            await ctx.conn.execute(
                update(t)
                .where(t.c.id == waiver_id)
                .values(**values, updated_at=func.now())
                .returning(t)
            )
        ).one()
        await ctx.audit(
            "fee_waiver.update",
            "fee_waiver",
            waiver_id,
            before=_audit(before),
            after=_audit(values),
        )
    return rw.WaiverOut.of(row)


@router.delete("/orgs/{org_id}/fee-waivers/{waiver_id}", status_code=204)
async def delete_waiver(waiver_id: UUID, ctx: Manager) -> Response:
    row = await _one(ctx, waiver_id)
    await ctx.conn.execute(delete(m.fee_waivers).where(m.fee_waivers.c.id == waiver_id))
    before = {k: getattr(row, k) for k in ("shop_id", "start_on", "end_on", "kinds", "reason")}
    await ctx.audit("fee_waiver.delete", "fee_waiver", waiver_id, before=_audit(before))
    return Response(status_code=204)

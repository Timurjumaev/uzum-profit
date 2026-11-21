"""``/deletion``: tashkilotni o'chirish (B8.13; M1, 06 §6) — faqat egasi (``delete_org``).

Tartib: egasi so'raydi (``POST``) → tashkilot **30 kun** ishlashda davom etadi, istalgan vaqt bekor qilinadi (``DELETE``) →
muddat o'tgach kunlik ``org.purge`` ishi uni butunlay o'chiradi (``upapi.purge``). Undan oldin to'liq eksport (B7.5) olish
tavsiya qilinadi (interfeys eslatadi). Har qadam audit jurnaliga yoziladi (tashkilot o'chgach jurnal ham o'chadi — yakuniy
o'chirish faqat logga: ``org_purged``, id bilan).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError

router = APIRouter(tags=["orgs"])
Owner = Annotated[OrgContext, Depends(require(Permission.DELETE_ORG))]
GRACE = timedelta(days=30)


class DeletionOut(BaseModel):
    requested_at: datetime | None
    delete_on: datetime | None
    days_left: int | None


def _out(requested: datetime | None, now: datetime) -> DeletionOut:
    if requested is None:
        return DeletionOut(requested_at=None, delete_on=None, days_left=None)
    due = requested + GRACE
    return DeletionOut(
        requested_at=requested, delete_on=due, days_left=max(0, (due - now).days + 1)
    )


async def _requested(ctx: OrgContext) -> datetime | None:
    return await ctx.conn.scalar(
        select(m.orgs.c.deletion_requested_at).where(m.orgs.c.id == ctx.org_id)
    )


@router.get("/orgs/{org_id}/deletion", response_model=DeletionOut)
async def status(ctx: Owner) -> DeletionOut:
    return _out(await _requested(ctx), datetime.now(UTC))


@router.post("/orgs/{org_id}/deletion", response_model=DeletionOut, status_code=202)
async def request_deletion(ctx: Owner) -> DeletionOut:
    if await _requested(ctx) is not None:
        raise AppError("deletion_already_requested", 409, detail="o'chirish allaqachon so'ralgan")
    now = datetime.now(UTC)
    await ctx.conn.execute(
        update(m.orgs).where(m.orgs.c.id == ctx.org_id).values(deletion_requested_at=now)
    )
    await ctx.audit("org.delete.request", "org", ctx.org_id)
    return _out(now, now)


@router.delete("/orgs/{org_id}/deletion", response_model=DeletionOut)
async def cancel_deletion(ctx: Owner) -> DeletionOut:
    if await _requested(ctx) is None:
        raise AppError("deletion_not_requested", 409, detail="o'chirish so'ralmagan")
    await ctx.conn.execute(
        update(m.orgs).where(m.orgs.c.id == ctx.org_id).values(deletion_requested_at=None)
    )
    await ctx.audit("org.delete.cancel", "org", ctx.org_id)
    return _out(None, datetime.now(UTC))

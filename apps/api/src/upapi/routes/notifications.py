"""``/notifications``: foydalanuvchining bildirishnoma sozlamalari va navbati (B6.1, 02 M15).

Har a'zo o'zi uchun sozlaydi (qoidalar shaxsiy, tashkilot ichida): qaysi hodisa yoqilgan, chegaralari (kunlik xulosa
vaqti, zarar zanjiri uzunligi, sinxron soatlari) va tinch soatlar. Ruxsat — tashkilot a'zoligi; rolga tegishli bo'lmagan
hodisa (masalan, omborchiga moliya xulosasi) ro'yxatda ``available=false``.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from upcore.notify import (
    CATALOG,
    PARAM_LIMITS,
    QUIET_FROM,
    QUIET_TO,
    Event,
    audience_of,
    merged_params,
    parse_hhmm,
)

from upapi.auth.deps import OrgContext, org_context
from upapi.db import models as m
from upapi.errors import AppError

router = APIRouter(tags=["notifications"])
Member = Annotated[OrgContext, Depends(org_context, scope="function")]


class NotificationEventOut(BaseModel):
    event: Event
    enabled: bool
    params: dict[str, Any]
    critical: bool  # tinch soatlarda ham keladi
    available: bool  # rolga tegishli va ishlaydi
    stage: str | None  # hali ishlamaydi — qaysi bosqichda


class NotificationSettingsOut(BaseModel):
    events: list[NotificationEventOut]
    quiet_from: time | None
    quiet_to: time | None


class NotificationRuleIn(BaseModel):
    event: Event
    enabled: bool
    params: dict[str, Any] = Field(default_factory=dict)


class NotificationSettingsIn(BaseModel):
    rules: list[NotificationRuleIn] = Field(default_factory=list, max_length=len(Event))
    quiet_from: time | None = QUIET_FROM
    quiet_to: time | None = QUIET_TO


class NotificationOut(BaseModel):
    id: UUID
    event: str
    status: str
    critical: bool
    payload: dict[str, Any]
    due_at: datetime
    sent_at: datetime | None
    created_at: datetime


class NotificationsOut(BaseModel):
    items: list[NotificationOut]


def _check_params(event: Event, params: dict[str, Any]) -> dict[str, Any]:
    allowed = CATALOG[event].params
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key not in allowed:
            raise AppError("bad_notification_params", 422, detail=f"{event.value}: {key}")
        if key == "at":
            try:
                parsed = parse_hhmm(str(value))
            except ValueError:
                raise AppError(
                    "bad_notification_params", 422, detail=f"{event.value}: at"
                ) from None
            out[key] = parsed.strftime("%H:%M")
        else:
            low, high = PARAM_LIMITS[key]
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise AppError(
                    "bad_notification_params", 422, detail=f"{event.value}: {key} {low}–{high}"
                )
            out[key] = value
    return out


async def _view(ctx: OrgContext) -> NotificationSettingsOut:
    nr, npf = m.notification_rules, m.notification_prefs
    rules = {
        r.event: r
        for r in await ctx.conn.execute(select(nr).where(nr.c.user_id == ctx.user.user_id))
    }
    pref = (await ctx.conn.execute(select(npf).where(npf.c.user_id == ctx.user.user_id))).first()
    audience = audience_of(ctx.role.value)
    events = []
    for event, spec in CATALOG.items():
        row = rules.get(event.value)
        events.append(
            NotificationEventOut(
                event=event,
                enabled=spec.default_enabled if row is None else row.enabled,
                params=merged_params(event, None if row is None else row.params),
                critical=spec.critical,
                available=spec.stage is None and spec.audience in audience,
                stage=spec.stage,
            )
        )
    return NotificationSettingsOut(
        events=events,
        quiet_from=QUIET_FROM if pref is None else pref.quiet_from,
        quiet_to=QUIET_TO if pref is None else pref.quiet_to,
    )


@router.get("/orgs/{org_id}/notifications/settings", response_model=NotificationSettingsOut)
async def get_settings(ctx: Member) -> NotificationSettingsOut:
    """Hodisalar katalogi foydalanuvchining qoidalari bilan (yo'q bo'lsa — standart)."""
    return await _view(ctx)


@router.put("/orgs/{org_id}/notifications/settings", response_model=NotificationSettingsOut)
async def put_settings(body: NotificationSettingsIn, ctx: Member) -> NotificationSettingsOut:
    """Berilgan hodisalar qoidasi va tinch soatlar (berilmagan hodisa o'zgarmaydi)."""
    if (body.quiet_from is None) != (body.quiet_to is None):
        raise AppError("bad_quiet_hours", 422, detail="ikkalasi ham kerak yoki ikkalasi bo'sh")
    nr, npf = m.notification_rules, m.notification_prefs
    for rule in body.rules:
        params = _check_params(rule.event, rule.params)
        stmt = insert(nr).values(
            org_id=ctx.org_id,
            user_id=ctx.user.user_id,
            event=rule.event.value,
            enabled=rule.enabled,
            params=params,
        )
        await ctx.conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["org_id", "user_id", "event"],
                set_={"enabled": stmt.excluded.enabled, "params": stmt.excluded.params},
            )
        )
    pref = insert(npf).values(
        org_id=ctx.org_id,
        user_id=ctx.user.user_id,
        quiet_from=body.quiet_from,
        quiet_to=body.quiet_to,
    )
    await ctx.conn.execute(
        pref.on_conflict_do_update(
            index_elements=["org_id", "user_id"],
            set_={"quiet_from": pref.excluded.quiet_from, "quiet_to": pref.excluded.quiet_to},
        )
    )
    return await _view(ctx)


@router.get("/orgs/{org_id}/notifications", response_model=NotificationsOut)
async def list_notifications(
    ctx: Member, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> NotificationsOut:
    """Foydalanuvchining oxirgi bildirishnomalari (yangisi birinchi)."""
    n = m.notifications
    rows = await ctx.conn.execute(
        select(n)
        .where(n.c.user_id == ctx.user.user_id)
        .order_by(n.c.created_at.desc(), n.c.id)
        .limit(limit)
    )
    return NotificationsOut(
        items=[
            NotificationOut(
                id=r.id,
                event=r.event,
                status=r.status,
                critical=r.critical,
                payload=r.payload,
                due_at=r.due_at,
                sent_at=r.sent_at,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )

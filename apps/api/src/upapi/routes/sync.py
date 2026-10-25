"""``/sync``: "Ma'lumotlar holati" (02 M3) va "Hozir yangilash" (B2.6). Ruxsat — tashkilotning har a'zosi (raqamlar
emas, faqat sinxron holati); boshqa tashkilot ma'lumoti RLS bilan ko'rinmaydi.

Holat: har do'kon × ma'lumot turi — oxirgi muvaffaqiyatli sinxron, oxirgi ish (holat, olingan/yozilgan, jami, xato
kodi, HTTP kod), akkaunt holati va kvota qoldig'i, Uzum uzilishi. "Yashil" — 24 soat ichida xato yo'q va sotuvlar
24 soat ichida yangilangan (02 M3 qabul mezoni). ``freshness`` — har tur bo'yicha eng eski oxirgi muvaffaqiyat
(sahifa yuqorisidagi "Yangilandi: N daqiqa oldin", 03 §8 ``meta.freshness``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import func, insert, select, text

from upapi.auth.deps import OrgContext, org_context
from upapi.db import models as m
from upapi.errors import AppError
from upapi.logs import get_logger
from upapi.reports.common import freshness
from upapi.settings import Settings
from upapi.sync import health
from upapi.sync.engine import ACCOUNT_KINDS, SHOP_KINDS, Kind, Trigger
from upapi.sync.jobs import JobQueue

router = APIRouter(tags=["sync"])
log = get_logger("upapi.sync.api")
Member = Annotated[OrgContext, Depends(org_context, scope="function")]
KINDS = [*ACCOUNT_KINDS, *SHOP_KINDS]
HEALTH_WINDOW = timedelta(hours=24)


class KindStatus(BaseModel):
    kind: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    status: str | None  # oxirgi ish: running / ok / warning / error / skipped
    mode: str | None
    started_at: datetime | None
    finished_at: datetime | None
    fetched: int | None
    written: int | None
    total: int | None
    error: str | None
    http_status: int | None


class ShopStatus(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    alias: str | None
    active: bool
    history_status: str | None
    first_sale_on: date | None
    healthy: bool
    errors_24h: int
    kinds: list[KindStatus]


class AccountStatus(BaseModel):
    id: UUID
    status: str
    quota_remaining: int | None
    checked_at: datetime | None


class OutageOut(BaseModel):
    active: bool
    since: datetime | None
    paused_until: datetime | None
    recovered_from: datetime | None
    recovered_at: datetime | None


class SyncStatusOut(BaseModel):
    healthy: bool
    outage: OutageOut
    accounts: list[AccountStatus]
    shops: list[ShopStatus]
    freshness: dict[str, datetime | None]


class RefreshOut(BaseModel):
    queued: int


def get_jobs(request: Request) -> JobQueue:
    jobs: JobQueue = request.app.state.jobs
    return jobs


@router.get("/orgs/{org_id}/sync", response_model=SyncStatusOut)
async def sync_status(request: Request, ctx: Member) -> SyncStatusOut:
    conn = ctx.conn
    now = (await conn.scalar(select(func.now()))) or datetime.now().astimezone()
    outage = await health.outage(request.app.state.engine)
    accounts = [
        AccountStatus(
            id=r.id, status=r.status, quota_remaining=r.quota_remaining, checked_at=r.checked_at
        )
        for r in await conn.execute(
            select(m.mp_accounts).order_by(m.mp_accounts.c.created_at, m.mp_accounts.c.id)
        )
    ]
    states = {(r.shop_id, r.kind): r for r in await conn.execute(select(m.sync_state))}
    latest = {
        (r.shop_id, r.kind): r
        for r in await conn.execute(
            text(
                "SELECT DISTINCT ON (shop_id, kind) * FROM sync_runs "
                "ORDER BY shop_id, kind, started_at DESC, created_at DESC"
            )
        )
    }
    errors = {
        r.shop_id: r.n
        for r in await conn.execute(
            select(m.sync_runs.c.shop_id, func.count().label("n"))
            .where(m.sync_runs.c.status == "error", m.sync_runs.c.started_at > now - HEALTH_WINDOW)
            .group_by(m.sync_runs.c.shop_id)
        )
    }
    shops: list[ShopStatus] = []
    for shop in await conn.execute(
        select(m.shops).order_by(m.shops.c.created_at, m.shops.c.external_id)
    ):
        kinds = []
        for kind in KINDS:
            state, run = states.get((shop.id, kind.value)), latest.get((shop.id, kind.value))
            kinds.append(
                KindStatus(
                    kind=kind.value,
                    last_success_at=state.last_success_at if state else None,
                    last_attempt_at=state.last_attempt_at if state else None,
                    status=run.status if run else None,
                    mode=run.mode if run else None,
                    started_at=run.started_at if run else None,
                    finished_at=run.finished_at if run else None,
                    fetched=run.fetched if run else None,
                    written=run.written if run else None,
                    total=run.total if run else None,
                    error=run.error if run else None,
                    http_status=run.http_status if run else None,
                )
            )
        orders = states.get((shop.id, Kind.ORDERS.value))
        last = orders.last_success_at if orders is not None else None
        fresh = last is not None and now - last <= HEALTH_WINDOW
        shops.append(
            ShopStatus(
                id=shop.id,
                account_id=shop.account_id,
                name=shop.name,
                alias=shop.alias,
                active=shop.active,
                history_status=shop.history_status,
                first_sale_on=shop.first_sale_on,
                healthy=fresh and not errors.get(shop.id),
                errors_24h=errors.get(shop.id, 0),
                kinds=kinds,
            )
        )
    active = [s for s in shops if s.active]
    return SyncStatusOut(
        healthy=bool(active)
        and all(s.healthy for s in active)
        and not outage.active
        and all(a.status in ("active", "disconnected") for a in accounts),
        outage=OutageOut(
            active=outage.active,
            since=outage.since,
            paused_until=outage.paused_until,
            recovered_from=outage.recovered_from,
            recovered_at=outage.recovered_at,
        ),
        accounts=accounts,
        shops=shops,
        freshness=await freshness(conn, [k.value for k in KINDS]),
    )


@router.post(
    "/orgs/{org_id}/sync/refresh", status_code=status.HTTP_202_ACCEPTED, response_model=RefreshOut
)
async def refresh(request: Request, ctx: Member) -> RefreshOut:
    """ "Hozir yangilash": sotuvlar, xarajatlar, mahsulotlar — ustuvor navbatda. Tashkilot bo'yicha
    ``sync_refresh_cooldown_seconds`` da bir marta; Uzum uzilishida — yo'q (sinxron to'xtatilgan)."""
    settings: Settings = request.app.state.settings
    if (await health.outage(request.app.state.engine)).active:
        raise AppError(
            "uzum_outage", 503, detail="Uzum hozir javob bermayapti, tiklangach yangilanadi"
        )
    recent = await ctx.conn.scalar(
        select(func.count())
        .select_from(m.events)
        .where(
            m.events.c.name == "sync_refresh",
            m.events.c.created_at
            > func.now() - timedelta(seconds=settings.sync_refresh_cooldown_seconds),
        )
    )
    if recent:
        raise AppError("sync_refresh_limited", 429, detail="Bir daqiqada bir marta")
    accounts = [
        r.id
        for r in await ctx.conn.execute(
            select(m.mp_accounts.c.id)
            .where(
                m.mp_accounts.c.status.not_in(("disconnected", "invalid")),
                select(m.shops.c.id)
                .where(m.shops.c.account_id == m.mp_accounts.c.id, m.shops.c.active)
                .exists(),
            )
            .order_by(m.mp_accounts.c.created_at)
        )
    ]
    if not accounts:
        raise AppError("no_accounts", 409, detail="Faol do'konli ulangan kalit yo'q")
    await ctx.conn.execute(
        insert(m.events).values(
            org_id=ctx.org_id,
            user_id=ctx.user.user_id,
            name="sync_refresh",
            props={"accounts": len(accounts)},
        )
    )
    jobs = get_jobs(request)
    queued = 0
    for account_id in accounts:
        queued += await jobs.defer_account(ctx.org_id, account_id, Trigger.USER)
    log.info("sync_refresh", queued=queued)
    return RefreshOut(queued=queued)

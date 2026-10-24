"""Procrastinate navbati (B2.6; 03 §2, ADR-003): davriy rejalashtiruvchi va akkaunt sinxroni ishlari.

- ``sync.tick`` — har daqiqada: ulangan akkauntlar (``sync_accounts()``, 0004) uchun ``sync.account`` ishini navbatga
  qo'yadi. Navbatda turgan ish bo'lsa qayta qo'yilmaydi (``queueing_lock``); akkaunt ishi o'zi qaysi turlar vaqti
  kelganini hal qiladi (:func:`upapi.sync.engine.plan`).
- ``sync.account`` — ``lock = account:<id>``: bitta kalitga bir vaqtda bitta ish (ishchilar va jarayonlar orasida).
  Ustuvorlik: foydalanuvchi ("Hozir yangilash") > kalit ulandi > jadval.

Ish argumentlarida faqat id'lar (kalit yo'q). Ishchi — ``python -m upapi.worker``; API navbatga :class:`JobQueue`
orqali qo'yadi.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from procrastinate import App, BaseConnector, JobContext, PsycopgConnector, RetryStrategy
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from upapi.db.url import normalize_url
from upapi.fx import sync_fx
from upapi.logs import get_logger
from upapi.settings import Settings
from upapi.sync.engine import Kind, Runtime, Trigger, sync_account

QUEUE = "sync"
TICK = "sync.tick"
ACCOUNT = "sync.account"
FX = "fx.cbu"
# Toshkent 09:05 va 16:05 (UTC+5, yoz vaqti yo'q) — CBU kursni ertalab e'lon qiladi, kunduzi tuzatishi mumkin.
FX_CRON = "5 4,11 * * *"
PRIORITY = {Trigger.SCHEDULE: 0, Trigger.CONNECT: 5, Trigger.USER: 10}
_log = get_logger("upapi.sync.jobs")


def connector_for(settings: Settings) -> PsycopgConnector:
    url = normalize_url(settings.database_url, async_driver=False).replace(
        "postgresql+psycopg://", "postgresql://"
    )
    return PsycopgConnector(conninfo=url, min_size=1, max_size=4)


def runtime(context: JobContext) -> Runtime:
    rt = context.additional_context.get("runtime")
    if not isinstance(rt, Runtime):
        raise RuntimeError("ishchi Runtime'siz ishga tushirilgan (additional_context['runtime'])")
    return rt


async def due_accounts(engine: AsyncEngine) -> list[tuple[UUID, UUID]]:
    """Ulangan akkauntlar (tashkilotlar bo'ylab, faqat id'lar) — ``SECURITY DEFINER`` funksiyasi orqali."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT org_id, account_id FROM sync_accounts()"))
        return [(r.org_id, r.account_id) for r in rows]


async def defer_account(
    app: App,
    org_id: UUID,
    account_id: UUID,
    trigger: Trigger,
    kinds: Sequence[Kind] | None = None,
) -> bool:
    """Akkaunt ishini navbatga qo'yish. ``False`` — xuddi shunday ish allaqachon navbatda."""
    try:
        await app.configure_task(
            ACCOUNT,
            queue=QUEUE,
            lock=f"account:{account_id}",
            queueing_lock=f"{trigger.value}:{account_id}",
            priority=PRIORITY[trigger],
        ).defer_async(
            org_id=str(org_id),
            account_id=str(account_id),
            trigger=trigger.value,
            kinds=[k.value for k in kinds] if kinds is not None else None,
        )
    except AlreadyEnqueued:
        return False
    return True


def build_app(connector: BaseConnector) -> App:
    """Navbat ilovasi (ishchi va API uchun bir xil vazifalar ro'yxati)."""
    app = App(connector=connector)

    @app.periodic(cron="* * * * *", periodic_id="tick")
    @app.task(name=TICK, queue=QUEUE, queueing_lock=TICK, pass_context=True)
    async def tick(context: JobContext, timestamp: int) -> int:
        rt = runtime(context)
        queued = 0
        for org_id, account_id in await due_accounts(rt.engine):
            queued += await defer_account(context.app, org_id, account_id, Trigger.SCHEDULE)
        return queued

    @app.periodic(cron=FX_CRON, periodic_id="fx")
    @app.task(
        name=FX,
        queue=QUEUE,
        queueing_lock=FX,
        pass_context=True,
        retry=RetryStrategy(max_attempts=3, wait=300),
    )
    async def fx_cbu(context: JobContext, timestamp: int) -> dict[str, Any]:
        result = await sync_fx(runtime(context))
        return {"latest": result.latest, "archived": result.archived, "days": result.days_filled}

    @app.task(name=ACCOUNT, queue=QUEUE, pass_context=True)
    async def account(
        context: JobContext,
        org_id: str,
        account_id: str,
        trigger: str = Trigger.SCHEDULE.value,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        result = await sync_account(
            runtime(context),
            UUID(org_id),
            UUID(account_id),
            trigger=Trigger(trigger),
            kinds=[Kind(k) for k in kinds] if kinds is not None else None,
        )
        return {"status": result.status, "reason": result.reason, "runs": len(result.runs)}

    return app


class JobQueue:
    """API tomoni: ishni navbatga qo'yish. Ulanish birinchi kerak bo'lganda ochiladi (API ishga tushishi navbat
    bazasiga bog'liq bo'lmasin)."""

    def __init__(self, app: App) -> None:
        self.app = app
        self._open = False

    @classmethod
    def from_settings(cls, settings: Settings) -> JobQueue:
        return cls(build_app(connector_for(settings)))

    async def defer_account(
        self,
        org_id: UUID,
        account_id: UUID,
        trigger: Trigger,
        kinds: Sequence[Kind] | None = None,
    ) -> bool:
        if not self._open:
            await self.app.open_async()
            self._open = True
        return await defer_account(self.app, org_id, account_id, trigger, kinds)

    async def aclose(self) -> None:
        if self._open:
            await self.app.close_async()
            self._open = False

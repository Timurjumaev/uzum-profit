"""Procrastinate navbati (B2.6; 03 §2, ADR-003): davriy rejalashtiruvchi va akkaunt sinxroni ishlari.

- ``sync.tick`` — har daqiqada: ulangan akkauntlar (``sync_accounts()``, 0004) uchun ``sync.account`` ishini navbatga
  qo'yadi. Navbatda turgan ish bo'lsa qayta qo'yilmaydi (``queueing_lock``); akkaunt ishi o'zi qaysi turlar vaqti
  kelganini hal qiladi (:func:`upapi.sync.engine.plan`).
- ``sync.account`` — ``lock = account:<id>``: bitta kalitga bir vaqtda bitta ish (ishchilar va jarayonlar orasida).
  Ustuvorlik: foydalanuvchi ("Hozir yangilash") > kalit ulandi > jadval.

- ``calc.org`` (B2.8) — tashkilot hisob ishi (:func:`upapi.calc.recalc_org`): ``lock = calc:<org>``, navbatda bitta.
  Akkaunt sinxroni biror narsa yozgan bo'lsa navbatga qo'yiladi (so'rovlar ``recalc_queue`` da — ma'lumot bilan
  bitta tranzaksiyada yozilgan). ``calc.nightly`` — Toshkent 03:40 da har tashkilot uchun to'liq qayta qurish
  (masalan, CBU arxivi keyinroq kelib, kurslar o'zgargan bo'lsa).

Sotuvchi tahrirlari (xaridlar, B4.6) ham ``calc.org`` ni API'dan navbatga qo'yadi (:meth:`JobQueue.defer_calc`).

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

from upapi import calc
from upapi.db.session import org_transaction
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
CALC_QUEUE = "calc"
CALC = "calc.org"
CALC_NIGHTLY = "calc.nightly"
CALC_CRON = "40 22 * * *"  # Toshkent 03:40 — sinxron va CBU ishlaridan uzoqda
QUEUES = [QUEUE, CALC_QUEUE]
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


async def defer_calc(app: App, org_id: UUID) -> bool:
    """Tashkilot hisob ishini navbatga qo'yish. ``False`` — allaqachon navbatda (u navbatdagi hamma so'rovlarni
    oladi)."""
    try:
        await app.configure_task(
            CALC, queue=CALC_QUEUE, lock=f"calc:{org_id}", queueing_lock=f"calc:{org_id}"
        ).defer_async(org_id=str(org_id))
    except AlreadyEnqueued:
        return False
    return True


async def request_full_rebuild(engine: AsyncEngine, org_id: UUID) -> None:
    async with org_transaction(engine, org_id) as conn:
        await calc.request_full(conn, org_id)


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
        if any(r.written for r in result.runs):
            await defer_calc(context.app, UUID(org_id))
        return {"status": result.status, "reason": result.reason, "runs": len(result.runs)}

    @app.task(name=CALC, queue=CALC_QUEUE, pass_context=True)
    async def calc_org(context: JobContext, org_id: str) -> dict[str, Any]:
        rt = runtime(context)
        result = await calc.recalc_org(rt.engine, UUID(org_id), rt.clock())
        return {
            "status": result.status,
            "costs": result.costs_written + result.costs_deleted,
            "metrics": result.metric_rows,
            "errors": len(result.errors),
        }

    @app.periodic(cron=CALC_CRON, periodic_id="calc")
    @app.task(name=CALC_NIGHTLY, queue=CALC_QUEUE, queueing_lock=CALC_NIGHTLY, pass_context=True)
    async def calc_nightly(context: JobContext, timestamp: int) -> int:
        rt = runtime(context)
        queued = 0
        for org_id in sorted({org for org, _ in await due_accounts(rt.engine)}):
            await request_full_rebuild(rt.engine, org_id)
            queued += await defer_calc(context.app, org_id)
        return queued

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
        await self._ensure_open()
        return await defer_account(self.app, org_id, account_id, trigger, kinds)

    async def defer_calc(self, org_id: UUID) -> bool:
        """Sotuvchi tahriridan keyin (xarid, B4.6) qayta hisob — tranzaksiya commit bo'lgach chaqiriladi, aks holda
        ishchi so'rovni ko'rmay "bo'sh navbat" deb tugatishi mumkin."""
        await self._ensure_open()
        return await defer_calc(self.app, org_id)

    async def _ensure_open(self) -> None:
        if not self._open:
            await self.app.open_async()
            self._open = True

    async def aclose(self) -> None:
        if self._open:
            await self.app.close_async()
            self._open = False

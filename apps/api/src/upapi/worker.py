"""Fon ishchisi (03 §1): ``python -m upapi.worker`` — Procrastinate navbatidagi sinxron (B2.6) va hisob
(B2.8) ishlari.

API bilan bir xil xavfsizlik shartlari: staging/prod'da xavfli sozlama yoki RLS'ni chetlab o'tadigan DB roli bilan
ishga tushmaydi. Ishchi ``up_app`` bilan ulanadi; tashkilot ma'lumoti faqat ``org_transaction`` ichida (RLS).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from upapi.crypto import CipherError
from upapi.logs import configure_logging, get_logger
from upapi.settings import Settings, get_settings
from upapi.startup import UnsafeConfiguration, check_role, check_settings
from upapi.sync.engine import Runtime
from upapi.sync.jobs import QUEUES, build_app, connector_for


async def wait_for_schema(engine: AsyncEngine, every: float = 2.0) -> None:
    """Navbat jadvallari migratsiyadan keyin paydo bo'ladi (deploy: zaxira → ``alembic upgrade`` → ishga tushirish;
    dev: ``make migrate``) — ungacha ishchi kutadi, yiqilmaydi."""
    log = get_logger("upapi.worker")
    warned = False
    while True:
        async with engine.connect() as conn:
            if await conn.scalar(text("SELECT to_regclass('procrastinate_jobs') IS NOT NULL")):
                return
        if not warned:
            log.warning("worker_waiting_for_migrations", hint="alembic upgrade head (make migrate)")
            warned = True
        await asyncio.sleep(every)


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    check_settings(settings)
    try:
        rt = Runtime.from_settings(settings)
    except CipherError as exc:
        raise UnsafeConfiguration(str(exc)) from None
    try:
        await check_role(rt.engine, settings)
        await wait_for_schema(rt.engine)
        app = build_app(connector_for(settings))
        get_logger("upapi.worker").info("worker_started", concurrency=settings.worker_concurrency)
        async with app.open_async():
            await app.run_worker_async(
                queues=QUEUES,
                concurrency=settings.worker_concurrency,
                additional_context={"runtime": rt},
                delete_jobs="successful",
            )
    finally:
        await rt.aclose()


def main() -> None:  # pragma: no cover — jarayon kirish nuqtasi
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()

"""FastAPI ilovasi (03-arxitektura.md §8): sozlamalar, loglar, xatolar, ``/api/v1`` marshrutlari."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from upapi import __version__
from upapi.auth.senders import CodeSender, build_sender
from upapi.crypto import CipherError, TokenCipher
from upapi.db.session import make_engine
from upapi.errors import Problem, install_error_handlers
from upapi.logs import configure_logging
from upapi.middleware import csrf_guard, request_context
from upapi.ratelimit import SlidingWindow
from upapi.routes import (
    accounts,
    auth,
    dashboard,
    expenses,
    health,
    inventory,
    orgs,
    pnl,
    sales,
    skus,
    sync,
    waivers,
)
from upapi.settings import Settings, get_settings
from upapi.startup import UnsafeConfiguration, check_role, check_settings
from upapi.sync.jobs import JobQueue
from upapi.uzum.limiter import RateLimiter

API_PREFIX = "/api/v1"


async def check_startup(app: FastAPI, settings: Settings) -> None:
    """DB roli (B2.10 chiqish mezoni): staging/prod — xato, dev/test — ogohlantirish."""
    await check_role(app.state.engine, settings)


def create_app(
    settings: Settings | None = None,
    sender: CodeSender | None = None,
    uzum_transport: httpx.AsyncBaseTransport | None = None,
    jobs: JobQueue | None = None,
) -> FastAPI:
    """``uzum_transport`` — testlarda Uzum javoblari (``httpx.MockTransport``); ``jobs`` — fon navbati (testlarda
    xotiradagi); production'da ikkalasi ``None``."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.json_logs)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        check_settings(settings)
        try:
            app.state.cipher = TokenCipher.from_settings(
                settings.token_keys, settings.token_key_version
            )
        except CipherError as exc:
            raise UnsafeConfiguration(str(exc)) from None
        app.state.engine = make_engine(settings.database_url)
        app.state.sender = sender or build_sender(settings)
        app.state.jobs = jobs or JobQueue.from_settings(settings)
        try:
            await check_startup(app, settings)
            yield
        finally:
            await app.state.jobs.aclose()
            await app.state.sender.aclose()
            await app.state.engine.dispose()

    app = FastAPI(
        title="SellerMax API",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
        responses={
            422: {"model": Problem, "description": "Validatsiya xatosi"},
            500: {"model": Problem, "description": "Ichki xato"},
        },
    )
    app.state.settings = settings
    app.state.uzum_transport = uzum_transport
    app.state.uzum_limiter = RateLimiter(settings.uzum_min_interval_seconds)
    app.state.otp_ip_limiter = SlidingWindow(settings.otp_per_ip_hour, 3600)
    app.middleware("http")(csrf_guard(API_PREFIX, settings.allowed_origins))
    # Oxirgi qo'shilgan — tashqi qatlam: so'rov id CSRF xatosida ham bo'ladi.
    app.middleware("http")(request_context)
    install_error_handlers(app, settings)
    app.include_router(health.router)  # /health — infratuzilma uchun (prefikssiz)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(orgs.router, prefix=API_PREFIX)
    app.include_router(accounts.router, prefix=API_PREFIX)
    app.include_router(sync.router, prefix=API_PREFIX)
    app.include_router(waivers.router, prefix=API_PREFIX)  # Uzum bonuslari (ADR-031)
    for reports in (dashboard, pnl, skus, sales, expenses, inventory):  # B2.9 o'qish API'lari
        app.include_router(reports.router, prefix=API_PREFIX)
    return app


app = create_app()

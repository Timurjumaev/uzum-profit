"""FastAPI ilovasi (03-arxitektura.md §8): sozlamalar, loglar, xatolar, ``/api/v1`` marshrutlari."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from upapi import __version__
from upapi.auth.senders import CodeSender, build_sender
from upapi.db.guard import role_problems
from upapi.db.session import make_engine
from upapi.errors import Problem, install_error_handlers
from upapi.logs import configure_logging, get_logger
from upapi.middleware import csrf_guard, request_context
from upapi.routes import auth, health, orgs
from upapi.settings import Settings, get_settings

API_PREFIX = "/api/v1"


class UnsafeConfiguration(RuntimeError):
    """Staging/prod'da xavfsizlik sharti bajarilmadi — ilova ishga tushmaydi."""


async def check_startup(app: FastAPI, settings: Settings) -> None:
    """DB roli (B2.10 chiqish mezoni): staging/prod — xato, dev/test — ogohlantirish."""
    log = get_logger("upapi.startup")
    try:
        problems = await role_problems(app.state.engine)
    except Exception as exc:
        if settings.strict:
            raise UnsafeConfiguration(
                f"DB rolini tekshirib bo'lmadi: {type(exc).__name__}"
            ) from exc
        log.warning("db_role_check_failed", error_code=type(exc).__name__)
        return
    if problems and settings.strict:
        raise UnsafeConfiguration("; ".join(problems))
    if problems:
        log.warning(
            "db_role_unsafe",
            problems=problems,
            hint="RLS ishlamaydi: UP_DATABASE_URL ni up_app roliga o'tkazing (infra/compose/dev.yml)",
        )


def create_app(settings: Settings | None = None, sender: CodeSender | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.json_logs)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.strict and (problems := settings.problems()):
            raise UnsafeConfiguration("; ".join(problems))
        app.state.engine = make_engine(settings.database_url)
        app.state.sender = sender or build_sender(settings)
        try:
            await check_startup(app, settings)
            yield
        finally:
            await app.state.sender.aclose()
            await app.state.engine.dispose()

    app = FastAPI(
        title="Uzum Profit API",
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
    app.middleware("http")(csrf_guard(API_PREFIX, settings.allowed_origins))
    # Oxirgi qo'shilgan — tashqi qatlam: so'rov id CSRF xatosida ham bo'ladi.
    app.middleware("http")(request_context)
    install_error_handlers(app, settings)
    app.include_router(health.router)  # /health — infratuzilma uchun (prefikssiz)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(orgs.router, prefix=API_PREFIX)
    return app


app = create_app()

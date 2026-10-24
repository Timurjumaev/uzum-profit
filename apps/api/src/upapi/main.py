"""FastAPI ilovasi (03-arxitektura.md §8): sozlamalar, loglar, xatolar, ``/api/v1`` marshrutlari."""

from fastapi import FastAPI

from upapi import __version__
from upapi.errors import Problem, install_error_handlers
from upapi.logs import configure_logging
from upapi.middleware import request_context
from upapi.routes import health
from upapi.settings import Settings, get_settings

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    app = FastAPI(
        title="Uzum Profit API",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        responses={
            422: {"model": Problem, "description": "Validatsiya xatosi"},
            500: {"model": Problem, "description": "Ichki xato"},
        },
    )
    app.state.settings = settings
    app.middleware("http")(request_context)
    install_error_handlers(app, settings)
    app.include_router(health.router)  # /health — infratuzilma uchun (prefikssiz)
    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()

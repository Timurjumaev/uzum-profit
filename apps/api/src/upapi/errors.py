"""Xatolar: RFC 9457 ``application/problem+json``, ``code`` maydoni bilan (03-arxitektura.md §8).

Frontend foydalanuvchi matnini ``code`` bo'yicha i18n'dan oladi; ``title`` / ``detail`` — dasturchi uchun.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from upapi.logs import get_logger
from upapi.middleware import REQUEST_ID_HEADER
from upapi.settings import Settings

PROBLEM_JSON = "application/problem+json"
TYPE_BASE = "https://uzum-profit.uz/problems/"  # brend domeni tanlangach (Q7) o'zgaradi; ichki identifikator


class Problem(BaseModel):
    """RFC 9457 problem details + ``code`` va ixtiyoriy ``errors`` (validatsiya)."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class AppError(Exception):
    """Biznes xatosi: ``raise AppError("shop_not_found", 404, "Do'kon topilmadi")``."""

    def __init__(
        self, code: str, status: int = 400, title: str | None = None, detail: str | None = None
    ) -> None:
        super().__init__(detail or title or code)
        self.code = code
        self.status = status
        self.title = title or HTTPStatus(status).phrase
        self.detail = detail


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "too_many_requests",
}


def problem_response(
    request: Request, problem: Problem, headers: dict[str, str] | None = None
) -> JSONResponse:
    problem.instance = problem.instance or request.url.path
    problem.request_id = getattr(request.state, "request_id", None)
    out = dict(headers or {})
    if problem.request_id:
        out[REQUEST_ID_HEADER] = problem.request_id  # 500 javobi middleware'dan tashqarida qaytadi
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_JSON,
        headers=out,
    )


def install_error_handlers(app: FastAPI, settings: Settings) -> None:
    log = get_logger("upapi.errors")

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            request,
            Problem(
                type=TYPE_BASE + exc.code,
                title=exc.title,
                status=exc.status,
                code=exc.code,
                detail=exc.detail,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, f"http_{exc.status_code}")
        detail = (
            exc.detail
            if isinstance(exc.detail, str) and exc.detail != HTTPStatus(exc.status_code).phrase
            else None
        )
        return problem_response(
            request,
            Problem(
                type=TYPE_BASE + code,
                title=HTTPStatus(exc.status_code).phrase,
                status=exc.status_code,
                code=code,
                detail=detail,
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "type": e.get("type"), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        return problem_response(
            request,
            Problem(
                type=TYPE_BASE + "validation_error",
                title="Validation error",
                status=422,
                code="validation_error",
                errors=errors,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path, error_code="internal")
        detail = f"{type(exc).__name__}: {exc}" if settings.show_error_details else None
        return problem_response(
            request,
            Problem(
                type=TYPE_BASE + "internal",
                title="Internal Server Error",
                status=500,
                code="internal",
                detail=detail,
            ),
        )

"""So'rov id va kirish logi (03-arxitektura.md §15)."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

from upapi.logs import get_logger

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")  # tashqi qiymat logga xavfsiz tushishi uchun


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Har so'rovga id (kelganini oladi, noto'g'ri bo'lsa yangisini beradi), logga kontekst va kirish yozuvi."""
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
    request.state.request_id = request_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    get_logger("upapi.access").info(
        "request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-Requested-With"


def csrf_guard(
    prefix: str, allowed_origins: list[str]
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """CSRF (03 §10): o'zgartiruvchi API so'rovlarida ``X-Requested-With`` majburiy (boshqa saytdan CORS
    ruxsatisiz yuborib bo'lmaydi) va ``Origin`` bo'lsa — ruxsat etilgan ro'yxatda."""
    origins = frozenset(o.rstrip("/") for o in allowed_origins)

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in SAFE_METHODS and request.url.path.startswith(prefix + "/"):
            origin = request.headers.get("origin")
            code = None
            if origin is not None and origin.rstrip("/") not in origins:
                code = "csrf_origin"
            elif not request.headers.get(CSRF_HEADER):
                code = "csrf_header"
            if code:
                from upapi.errors import Problem, problem_response

                problem = Problem(
                    type=f"https://uzum-profit.uz/problems/{code}",
                    title="Forbidden",
                    status=403,
                    code=code,
                )
                return problem_response(request, problem)
        return await call_next(request)

    return middleware

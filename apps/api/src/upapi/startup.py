"""Ishga tushishdagi xavfsizlik tekshiruvlari — API va ishchi uchun bir xil (03 §10, B2.10 chiqish mezoni)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from upapi.db.guard import role_problems
from upapi.logs import get_logger
from upapi.settings import Settings


class UnsafeConfiguration(RuntimeError):
    """Staging/prod'da xavfsizlik sharti bajarilmadi — ilova ishga tushmaydi."""


def check_settings(settings: Settings) -> None:
    if settings.strict and (problems := settings.problems()):
        raise UnsafeConfiguration("; ".join(problems))


async def check_role(engine: AsyncEngine, settings: Settings) -> None:
    """DB roli: staging/prod — xato, dev/test — ogohlantirish."""
    log = get_logger("upapi.startup")
    try:
        problems = await role_problems(engine)
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

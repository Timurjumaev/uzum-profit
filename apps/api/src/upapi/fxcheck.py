"""CBU kurslari diagnostikasi: ``python -m upapi.fxcheck`` (staging serverda, ``infra/staging/fxcheck.sh`` orqali).

"CNY uchun ... sanasigacha kurs yo'q" xatosida sabab uchta bo'lishi mumkin — shu hisobot ularni ajratadi:

- **tarmoq** — cbu.uz serverdan ochiladimi (HTTP holati yoki xato turi; javob tanasi chiqmaydi);
- **baza** — ``fx_rates`` da har valyutaning eng eski / eng yangi kuni va qatorlar soni;
- **ishlar** — oxirgi ``fx.cbu`` ishlari (holat, urinishlar, argumentlar, oxirgi hodisalar).

Sirlar o'qilmaydi. Natija — JSON (stdout); ``fx_rates`` global jadval (RLS yo'q), ishlar jadvali o'qib bo'lmasa
``jobs`` da sababi yoziladi.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from upapi import __version__
from upapi.db.session import make_engine
from upapi.settings import Settings, get_settings

JOBS = 10


async def network(settings: Settings, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    own = client is None
    client = client or httpx.AsyncClient(
        timeout=settings.fx_timeout_seconds,
        headers={"User-Agent": f"uzum-profit/{__version__}"},
    )
    try:
        resp = await client.get(settings.cbu_url)
        rows = None
        try:
            data = resp.json()
            rows = len(data) if isinstance(data, list) else None
        except ValueError:
            pass
        return {"url": settings.cbu_url, "status": resp.status_code, "rows": rows}
    except httpx.HTTPError as exc:
        return {"url": settings.cbu_url, "error": type(exc).__name__}
    finally:
        if own:
            await client.aclose()


async def database(engine: AsyncEngine) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT currency, source, min(day) AS first, max(day) AS last, count(*) AS n "
                "FROM fx_rates GROUP BY currency, source ORDER BY currency, source"
            )
        )
        return [
            {"currency": r.currency, "source": r.source, "first": r.first, "last": r.last, "n": r.n}
            for r in rows
        ]


async def jobs(engine: AsyncEngine) -> Any:
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT j.id, j.status, j.attempts, j.scheduled_at, j.args, "
                    "(SELECT array_agg(e.type::text ORDER BY e.at) FROM procrastinate_events e "
                    " WHERE e.job_id = j.id) AS events "
                    "FROM procrastinate_jobs j WHERE j.task_name = 'fx.cbu' "
                    "ORDER BY j.id DESC LIMIT :n"
                ),
                {"n": JOBS},
            )
            return [dict(r._mapping) for r in rows]
    except Exception as exc:  # jadval yo'q yoki huquq yetmaydi — hisobotni to'xtatmaydi
        return {"error": type(exc).__name__}


async def build(settings: Settings, engine: AsyncEngine) -> dict[str, Any]:
    return {
        "network": await network(settings),
        "rates": await database(engine),
        "jobs": await jobs(engine),
    }


def main() -> int:  # pragma: no cover — jarayon kirish nuqtasi
    async def go() -> dict[str, Any]:
        settings = get_settings()
        engine = make_engine(settings.database_url)
        try:
            return await build(settings, engine)
        finally:
            await engine.dispose()

    json.dump(asyncio.run(go()), sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

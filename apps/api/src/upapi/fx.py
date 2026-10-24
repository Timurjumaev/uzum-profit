"""CBU kurslari (B2.7; 02 M3, F20): cbu.uz JSON → ``fx_rates`` (manba ``cbu``), kuniga 2 marta + arxiv.

- **Joriy kurs:** ``<cbu_url>`` (hamma valyuta, bugungi kun) — faqat ``fx_currencies`` dagilari saqlanadi.
- **Arxiv:** ``<cbu_url><VALYUTA>/<YYYY-MM-DD>/`` — bazadagi eng eski kundan orqaga, ``fx_backfill_days`` gacha,
  har ishda ko'pi bilan ``fx_backfill_per_run`` kun. Tannarx (F20) to'lov sanasidagi kursni talab qiladi.
- **Dam olish kunlari:** CBU e'lon qilmagan kun uchun qator o'ylab topilmaydi — tanlashni ``upcore.fx.rate_on``
  qiladi (oxirgi ish kuni). Bu yerda faqat CBU bergan narsa saqlanadi; ``Nominal`` ga bo'lish ``parse_cbu_row`` da.
- **Yozuv:** ``fx_upsert()`` (0005) — ``up_sync`` egasidagi ``SECURITY DEFINER`` funksiya; ``up_app`` ning o'zi
  ``fx_rates`` ga yoza olmaydi. Manba doim ``cbu``: qo'lda kiritilgan kurslar bu jadvalga tegmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from upcore.fx import FxError, FxRate, parse_cbu_rows

from upapi import __version__
from upapi.logs import get_logger
from upapi.sync.engine import Runtime

TASHKENT = ZoneInfo("Asia/Tashkent")
ATTEMPTS = 3
_log = get_logger("upapi.fx")


class FxFetchError(Exception):
    """cbu.uz javobi olinmadi yoki tushunarsiz (kalit yo'q, javob tanasi xatoga qo'shilmaydi)."""


@dataclass(frozen=True, slots=True)
class FxSyncResult:
    latest: int  # joriy kurs javobidan saqlangan qatorlar
    archived: int  # arxivdan saqlangan qatorlar
    days_filled: int  # arxivdan qator olingan kunlar
    latest_day: date | None


def archive_url(base: str, currency: str, day: date) -> str:
    return f"{base.rstrip('/')}/{currency}/{day.isoformat()}/"


async def _get_json(client: httpx.AsyncClient, url: str, rt: Runtime) -> list[dict[str, Any]]:
    last = "tarmoq"
    for attempt in range(ATTEMPTS):
        if attempt:
            await rt.sleep(0.8 * 2 ** (attempt - 1))
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            last = "tarmoq xatosi"
            continue
        if resp.status_code >= 500 or resp.status_code == 429:
            last = f"HTTP {resp.status_code}"
            continue
        if resp.status_code != 200:
            raise FxFetchError(f"cbu.uz HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise FxFetchError("cbu.uz javobi JSON emas") from None
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise FxFetchError("cbu.uz javobi ro'yxat emas")
        return data
    raise FxFetchError(f"cbu.uz javob bermadi ({last})")


async def store(engine: AsyncEngine, rates: list[FxRate]) -> int:
    """Kurslarni yozadi (bir xil sana+valyuta qayta kelsa yangilanadi). Yozilgan qatorlar soni."""
    if not rates:
        return 0
    async with engine.begin() as conn:
        for r in rates:
            await conn.execute(
                text("SELECT fx_upsert(:day, :ccy, :rate)"),
                {"day": r.day, "ccy": r.currency.value, "rate": r.rate},
            )
    return len(rates)


async def _earliest(engine: AsyncEngine) -> date | None:
    async with engine.connect() as conn:
        result: date | None = await conn.scalar(
            text("SELECT min(day) FROM fx_rates WHERE source = 'cbu'")
        )
        return result


def _parse(rows: list[dict[str, Any]], wanted: set[str]) -> list[FxRate]:
    try:
        return [r for r in parse_cbu_rows(rows) if r.currency.value in wanted]
    except FxError as exc:
        raise FxFetchError(f"cbu.uz qatori tushunarsiz: {exc}") from None


async def sync_fx(rt: Runtime) -> FxSyncResult:
    """Joriy kurslarni oladi, keyin arxivni bir qism to'ldiradi. Tarmoq/format xatosi — ``FxFetchError``."""
    s = rt.settings
    wanted = {c.upper() for c in s.fx_currencies}
    async with httpx.AsyncClient(
        transport=rt.transport,
        timeout=s.fx_timeout_seconds,
        headers={"User-Agent": f"uzum-profit/{__version__}"},
    ) as client:
        base = s.cbu_url
        latest = _parse(await _get_json(client, base, rt), wanted)
        if not latest:
            raise FxFetchError("cbu.uz javobida kerakli valyutalar yo'q")
        saved = await store(rt.engine, latest)
        latest_day = max(r.day for r in latest)

        horizon = _today(rt.clock()) - timedelta(days=s.fx_backfill_days)
        earliest = min(await _earliest(rt.engine) or latest_day, latest_day)
        archived = days_filled = 0
        day = earliest - timedelta(days=1)
        for _ in range(s.fx_backfill_per_run):
            if day < horizon:
                break
            got: list[FxRate] = []
            for ccy in sorted(wanted):
                got += _parse(await _get_json(client, archive_url(base, ccy, day), rt), wanted)
            if got:
                archived += await store(rt.engine, got)
                days_filled += 1
            else:
                _log.warning("fx_archive_empty", day=day.isoformat())
            day -= timedelta(days=1)
    _log.info(
        "fx_synced",
        latest=saved,
        archived=archived,
        days_filled=days_filled,
        day=latest_day.isoformat(),
    )
    return FxSyncResult(saved, archived, days_filled, latest_day)


def _today(now: datetime) -> date:
    return now.astimezone(TASHKENT).date()

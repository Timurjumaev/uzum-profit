"""CBU kurslari (B2.7; 02 M3, F20): cbu.uz JSON → ``fx_rates`` (manba ``cbu``), kuniga 2 marta + arxiv.

- **Joriy kurs:** ``<cbu_url>`` (hamma valyuta, bugungi kun) — faqat ``fx_currencies`` dagilari saqlanadi.
- **Arxiv:** ``<cbu_url><VALYUTA>/<YYYY-MM-DD>/`` — orqaga, ``fx_backfill_days`` gacha, har ishda ko'pi bilan
  ``fx_backfill_per_run`` kun. Boshlanish — **eng kam to'lgan valyutaning** eng eski kuni (bitta valyuta tarixi uzoqroq
  bo'lsa, boshqasining bo'shlig'i yopilmay qolmaydi). Tannarx (F20) to'lov sanasidagi kursni talab qiladi: xarid
  saqlanganda kerakli sana kursi yo'q bo'lsa, ish ``since`` bilan qo'yiladi — o'sha sanadan 10 kun oldingacha cheklovsiz
  (``MAX_SINCE_DAYS`` gacha) to'ldiradi.
- **Dam olish kunlari:** CBU e'lon qilmagan kun uchun qator o'ylab topilmaydi — tanlashni ``upcore.fx.rate_on``
  qiladi (oxirgi ish kuni). Bu yerda faqat CBU bergan narsa saqlanadi; ``Nominal`` ga bo'lish ``parse_cbu_row`` da.
- **Yozuv:** ``fx_upsert()`` (0005) — ``up_sync`` egasidagi ``SECURITY DEFINER`` funksiya; ``up_app`` ning o'zi
  ``fx_rates`` ga yoza olmaydi. Manba ``cbu``: qo'lda kiritilgan kurslar bu jadvalga tegmaydi.
- **Zaxira — bozor kursi (ADR-045):** cbu.uz javob bermasa (staging AWS'dan ochilmaydi) joriy kurs va arxiv
  ``fx_market_urls`` dan olinadi (kuniga bitta fayl: ``{"date": ..., "cny": {"uzs": ...}}``), ``fx_upsert_market()``
  (0016) bilan manba ``market`` sifatida yoziladi. Bu rasmiy kurs emas: bir kunda CBU bo'lsa u ustun, hisobda esa
  ``market_rate`` belgisi chiqadi. Arxiv har manba uchun o'z bo'shlig'idan boshlanadi.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from upcore.fx import FxError, FxRate, RateSource, parse_cbu_rows
from upcore.money import Currency, to_decimal

from upapi import __version__
from upapi.logs import get_logger
from upapi.sync.engine import Runtime

TASHKENT = ZoneInfo("Asia/Tashkent")
ATTEMPTS = 3
SINCE_MARGIN_DAYS = (
    10  # dam olish / bayram kunlari uchun: kerakli sanadan oldingi ish kuni kursi ham bo'lsin
)
MAX_SINCE_DAYS = 800
_log = get_logger("upapi.fx")


class FxFetchError(Exception):
    """cbu.uz javobi olinmadi yoki tushunarsiz (kalit yo'q, javob tanasi xatoga qo'shilmaydi)."""


@dataclass(frozen=True, slots=True)
class FxSyncResult:
    latest: int  # joriy kurs javobidan saqlangan qatorlar
    archived: int  # arxivdan saqlangan qatorlar
    days_filled: int  # arxivdan qator olingan kunlar
    latest_day: date | None
    source: str = "cbu"  # kurslar qaysi manbadan keldi (``market`` — zaxira, ADR-045)


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


STORE_SQL = {
    RateSource.CBU: "SELECT fx_upsert(:day, :ccy, :rate)",
    RateSource.MARKET: "SELECT fx_upsert_market(:day, :ccy, :rate)",
}


async def store(engine: AsyncEngine, rates: list[FxRate]) -> int:
    """Kurslarni yozadi (bir xil sana+valyuta+manba qayta kelsa yangilanadi). Yozilgan qatorlar soni."""
    if not rates:
        return 0
    async with engine.begin() as conn:
        for r in rates:
            await conn.execute(
                text(STORE_SQL[r.source]),
                {"day": r.day, "ccy": r.currency.value, "rate": r.rate},
            )
    return len(rates)


async def _frontier(engine: AsyncEngine, wanted: set[str], source: str) -> date | None:
    """Arxiv boshlanadigan kun: har valyutaning eng eski kuni orasida eng kech biri (kursi umuman yo'q valyuta
    bo'lsa — ``None``: joriy kurs kelgach hammasida bor)."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT currency, min(day) FROM fx_rates WHERE source = :source "
                "AND currency = ANY(:ccy) GROUP BY currency"
            ),
            {"ccy": sorted(wanted), "source": source},
        )
        firsts = {r[0]: r[1] for r in rows}
    if not firsts or set(firsts) != wanted:
        return None
    first: date = max(firsts.values())
    return first


def _parse(rows: list[dict[str, Any]], wanted: set[str]) -> list[FxRate]:
    try:
        return [r for r in parse_cbu_rows(rows) if r.currency.value in wanted]
    except FxError as exc:
        raise FxFetchError(f"cbu.uz qatori tushunarsiz: {exc}") from None


async def _market_rate(
    client: httpx.AsyncClient, rt: Runtime, ccy: str, day: date | None
) -> FxRate | None:
    """Bozor kursi (zaxira): bitta valyuta, bitta kun (``None`` — joriy). Fayl yo'q (404) yoki kun mos kelmasa —
    ``None`` (o'ylab topilmaydi); hamma ko'zgu tarmoq xatosi bersa — ``FxFetchError``."""
    when = "latest" if day is None else day.isoformat()
    failure: FxFetchError | None = None
    missing = False  # biror ko'zgu aniq "fayl yo'q" dedi — bu xato emas, o'sha kunda kurs yo'q
    for template in rt.settings.fx_market_urls:
        url = template.format(date=when, ccy=ccy.lower())
        try:
            data = await _get_object(client, url, rt)
        except FxFetchError as exc:
            failure = exc
            continue
        if data is None:
            missing = True
            continue
        try:
            got = date.fromisoformat(str(data["date"]))
            rate = to_decimal(str(data[ccy.lower()]["uzs"]))
            if day is not None and got != day:
                continue
            return FxRate(got, Currency(ccy), rate, source=RateSource.MARKET)
        except (KeyError, TypeError, ValueError, FxError) as exc:
            failure = FxFetchError(f"zaxira manba javobi tushunarsiz ({type(exc).__name__})")
    if failure is not None and not missing:
        raise failure
    return None


async def _get_object(client: httpx.AsyncClient, url: str, rt: Runtime) -> dict[str, Any] | None:
    last = "tarmoq"
    for attempt in range(ATTEMPTS):
        if attempt:
            await rt.sleep(0.8 * 2 ** (attempt - 1))
        try:
            resp = await client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            last = "tarmoq xatosi"
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code >= 500 or resp.status_code == 429:
            last = f"HTTP {resp.status_code}"
            continue
        if resp.status_code != 200:
            raise FxFetchError(f"zaxira manba HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise FxFetchError("zaxira manba javobi JSON emas") from None
        if not isinstance(data, dict):
            raise FxFetchError("zaxira manba javobi obyekt emas")
        return data
    raise FxFetchError(f"zaxira manba javob bermadi ({last})")


async def _backfill(
    rt: Runtime,
    source: RateSource,
    fetch_day: Callable[[date], Awaitable[list[FxRate]]],
    wanted: set[str],
    latest_day: date,
    since: date | None,
) -> tuple[int, int]:
    """Arxivni orqaga to'ldiradi (``archived`` qatorlar, ``days_filled`` kunlar). Boshlanish — shu manbaning eng kam
    to'lgan valyutasi; ``since`` bo'lsa — shu sanadan ``SINCE_MARGIN_DAYS`` oldingacha cheklovsiz."""
    s = rt.settings
    today = _today(rt.clock())
    horizon = today - timedelta(days=s.fx_backfill_days)
    budget = s.fx_backfill_per_run
    if since is not None:
        horizon = max(
            horizon,
            since - timedelta(days=SINCE_MARGIN_DAYS),
            today - timedelta(days=MAX_SINCE_DAYS),
        )
    frontier = min(await _frontier(rt.engine, wanted, source.value) or latest_day, latest_day)
    if since is not None:
        budget = max(budget, (frontier - horizon).days)
    archived = days_filled = 0
    day = frontier - timedelta(days=1)
    for _ in range(budget):
        if day < horizon:
            break
        got = await fetch_day(day)
        if got:
            archived += await store(rt.engine, got)
            days_filled += 1
        else:
            _log.warning("fx_archive_empty", day=day.isoformat(), source=source.value)
        day -= timedelta(days=1)
    return archived, days_filled


async def _sync_market(
    rt: Runtime, client: httpx.AsyncClient, wanted: set[str], since: date | None, reason: str
) -> FxSyncResult:
    """CBU ochilmadi: joriy kurs va arxiv zaxira manbadan (ADR-045)."""
    _log.warning("fx_cbu_unavailable_using_market", reason=reason)
    latest = []
    for ccy in sorted(wanted):
        rate = await _market_rate(client, rt, ccy, None)
        if rate is not None:
            latest.append(rate)
    if not latest:
        raise FxFetchError(f"cbu.uz ham, zaxira manba ham kurs bermadi ({reason})")
    saved = await store(rt.engine, latest)
    latest_day = max(r.day for r in latest)

    async def fetch_day(day: date) -> list[FxRate]:
        got = [await _market_rate(client, rt, ccy, day) for ccy in sorted(wanted)]
        return [r for r in got if r is not None]

    archived, days_filled = await _backfill(
        rt, RateSource.MARKET, fetch_day, wanted, latest_day, since
    )
    _log.info(
        "fx_synced",
        source="market",
        latest=saved,
        archived=archived,
        days_filled=days_filled,
        day=latest_day.isoformat(),
    )
    return FxSyncResult(saved, archived, days_filled, latest_day, source="market")


async def sync_fx(rt: Runtime, since: date | None = None) -> FxSyncResult:
    """Joriy kurslarni oladi, keyin arxivni bir qism to'ldiradi; ``since`` — shu sana (va undan ``SINCE_MARGIN_DAYS``
    oldin) kursigacha cheklovsiz. cbu.uz javob bermasa — zaxira bozor kursi (ADR-045); u ham bo'lmasa
    ``FxFetchError``."""
    s = rt.settings
    wanted = {c.upper() for c in s.fx_currencies}
    async with httpx.AsyncClient(
        transport=rt.transport,
        timeout=s.fx_timeout_seconds,
        headers={"User-Agent": f"uzum-profit/{__version__}"},
    ) as client:
        base = s.cbu_url
        try:
            latest = _parse(await _get_json(client, base, rt), wanted)
            if not latest:
                raise FxFetchError("cbu.uz javobida kerakli valyutalar yo'q")
        except FxFetchError as exc:
            if not s.fx_market_urls:
                raise
            return await _sync_market(rt, client, wanted, since, str(exc))
        saved = await store(rt.engine, latest)
        latest_day = max(r.day for r in latest)

        async def fetch_day(day: date) -> list[FxRate]:
            got: list[FxRate] = []
            for ccy in sorted(wanted):
                got += _parse(await _get_json(client, archive_url(base, ccy, day), rt), wanted)
            return got

        archived, days_filled = await _backfill(
            rt, RateSource.CBU, fetch_day, wanted, latest_day, since
        )
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

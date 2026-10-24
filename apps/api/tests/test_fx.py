"""B2.7 CBU kurslari: joriy kurs, arxivni orqaga to'ldirish, xatolar, yozuv huquqlari, ish rejasi."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import dbtools
import httpx
import psycopg
import pytest
import sellerfake as sf
from procrastinate.testing import InMemoryConnector
from sellerfake import admin, runtime
from upapi import fx
from upapi.settings import Settings
from upapi.sync import jobs
from upapi.sync.engine import Runtime
from upcore.fx import FxRate, rate_on

TODAY = date(2026, 10, 24)  # sf.NOW (Toshkent 17:00)
BASE = "https://cbu.test/json/"


@pytest.fixture(scope="module")
def fresh() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as urls:
        yield urls


@pytest.fixture(autouse=True)
def clean(fresh: dict[str, str]) -> None:
    admin(fresh, "DELETE FROM fx_rates")


def row(ccy: str, rate: str, day: date, nominal: str = "1") -> dict[str, str]:
    return {
        "Ccy": ccy,
        "Nominal": nominal,
        "Rate": rate,
        "Date": day.strftime("%d.%m.%Y"),
        "CcyNm_UZ": "x",
    }


class FakeCbu:
    """cbu.uz o'rnida: joriy kurs va arxiv (kun bo'yicha); ``fail`` — birinchi shuncha so'rov 503."""

    def __init__(self, archive_from: date | None = None, fail: int = 0) -> None:
        self.archive_from = archive_from or date(2000, 1, 1)
        self.fail = fail
        self.calls: list[str] = []
        self.transport = httpx.MockTransport(self.handle)

    @staticmethod
    def latest() -> list[dict[str, str]]:
        return [
            row("USD", "12650.50", TODAY),
            row("CNY", "1792.29", TODAY),
            row("RUB", "135.10", TODAY),
            row("EUR", "14800.00", TODAY),
            row("JPY", "850.00", TODAY, nominal="10"),  # bizga kerak emas
            row("GBP", "16000.00", TODAY),
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if self.fail:
            self.fail -= 1
            return httpx.Response(503)
        assert url.startswith(BASE)
        parts = [p for p in url.removeprefix(BASE).split("/") if p]
        if not parts:
            return httpx.Response(200, json=self.latest())
        ccy, day = parts[0], date.fromisoformat(parts[1])
        if day < self.archive_from:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[row(ccy, "1700.00", day)])


def settings(urls: dict[str, str], **extra: Any) -> Settings:
    return sf.settings_for(urls, cbu_url=BASE, **extra)


def sync(urls: dict[str, str], cbu: FakeCbu, **extra: Any) -> fx.FxSyncResult:
    with runtime(urls, sf.seller(), cbu_url=BASE, **extra) as run:

        async def main(rt: Runtime) -> fx.FxSyncResult:
            rt.transport = cbu.transport
            return await fx.sync_fx(rt)

        return run(main)


def stored(urls: dict[str, str]) -> dict[tuple[date, str], Decimal]:
    rows = admin(urls, "SELECT day, currency, rate FROM fx_rates WHERE source = 'cbu'")
    return {(d, c): r for d, c, r in rows}


def test_latest_rates_saved_and_unknown_currencies_skipped(fresh: dict[str, str]) -> None:
    res = sync(fresh, FakeCbu(archive_from=TODAY), fx_backfill_per_run=0)
    assert (res.latest, res.archived, res.latest_day) == (4, 0, TODAY)
    assert stored(fresh) == {
        (TODAY, "USD"): Decimal("12650.500000"),
        (TODAY, "CNY"): Decimal("1792.290000"),
        (TODAY, "RUB"): Decimal("135.100000"),
        (TODAY, "EUR"): Decimal("14800.000000"),
    }


def test_rerun_updates_without_duplicates(fresh: dict[str, str]) -> None:
    sync(fresh, FakeCbu(archive_from=TODAY), fx_backfill_per_run=0)
    admin(fresh, "UPDATE fx_rates SET rate = 1, fetched_at = '2020-01-01' WHERE currency = 'CNY'")
    sync(fresh, FakeCbu(archive_from=TODAY), fx_backfill_per_run=0)
    assert len(stored(fresh)) == 4
    assert stored(fresh)[(TODAY, "CNY")] == Decimal("1792.290000")
    assert admin(fresh, "SELECT fetched_at > '2021-01-01' FROM fx_rates WHERE currency = 'CNY'")[0][
        0
    ]


def test_archive_walks_back_from_earliest_day_in_chunks(fresh: dict[str, str]) -> None:
    cbu = FakeCbu()
    res = sync(fresh, cbu, fx_backfill_per_run=3, fx_currencies=["USD", "CNY"])
    assert (res.latest, res.archived, res.days_filled) == (2, 6, 3)
    days = sorted({d for d, _ in stored(fresh)})
    assert days == [TODAY - timedelta(days=n) for n in (3, 2, 1, 0)]
    # Ikkinchi ish eng eski kundan davom etadi, takrorlamaydi.
    cbu.calls.clear()
    sync(fresh, cbu, fx_backfill_per_run=2, fx_currencies=["USD", "CNY"])
    archive_days = {c.rstrip("/").rsplit("/", 1)[1] for c in cbu.calls[1:]}
    assert archive_days == {str(TODAY - timedelta(days=n)) for n in (4, 5)}


def test_archive_stops_at_horizon(fresh: dict[str, str]) -> None:
    res = sync(fresh, FakeCbu(), fx_backfill_per_run=30, fx_backfill_days=2, fx_currencies=["CNY"])
    assert res.days_filled == 2
    assert min(d for d, _ in stored(fresh)) == TODAY - timedelta(days=2)


def test_archive_gap_day_is_not_invented(fresh: dict[str, str]) -> None:
    cbu = FakeCbu(archive_from=TODAY - timedelta(days=1))  # undan oldin CBU hech narsa bermaydi
    res = sync(fresh, cbu, fx_backfill_per_run=3, fx_currencies=["CNY"])
    assert res.days_filled == 1
    assert sorted({d for d, _ in stored(fresh)}) == [TODAY - timedelta(days=1), TODAY]


def test_retries_5xx_then_succeeds(fresh: dict[str, str]) -> None:
    cbu = FakeCbu(archive_from=TODAY, fail=2)
    assert sync(fresh, cbu, fx_backfill_per_run=0).latest == 4
    assert len(cbu.calls) == 3


@pytest.mark.parametrize(
    ("handler", "match"),
    [
        (lambda r: httpx.Response(503), "javob bermadi"),
        (lambda r: httpx.Response(404), "HTTP 404"),
        (lambda r: httpx.Response(200, text="<html>"), "JSON emas"),
        (lambda r: httpx.Response(200, json={"a": 1}), "ro'yxat emas"),
        (lambda r: httpx.Response(200, json=[row("JPY", "1", TODAY)]), "kerakli valyutalar yo'q"),
        (lambda r: httpx.Response(200, json=[row("CNY", "abc", TODAY)]), "tushunarsiz"),
        (lambda r: httpx.Response(200, json=[row("CNY", "0", TODAY)]), "tushunarsiz"),
    ],
)
def test_bad_responses_raise_and_store_nothing(
    fresh: dict[str, str], handler: Any, match: str
) -> None:
    with runtime(fresh, sf.seller(), cbu_url=BASE) as run:

        async def main(rt: Runtime) -> None:
            rt.transport = httpx.MockTransport(handler)
            await fx.sync_fx(rt)

        with pytest.raises(fx.FxFetchError, match=match):
            run(main)
    assert stored(fresh) == {}


def test_network_error_is_retried_then_reported(fresh: dict[str, str]) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    with runtime(fresh, sf.seller(), cbu_url=BASE) as run:

        async def main(rt: Runtime) -> None:
            rt.transport = httpx.MockTransport(down)
            await fx.sync_fx(rt)

        with pytest.raises(fx.FxFetchError, match="tarmoq"):
            run(main)


def test_stored_rates_feed_core_lookup_with_weekend_fallback(fresh: dict[str, str]) -> None:
    sync(fresh, FakeCbu(archive_from=TODAY), fx_backfill_per_run=0)
    friday, saturday = date(2026, 10, 23), date(2026, 10, 24)
    admin(fresh, "UPDATE fx_rates SET day = %s WHERE currency = 'CNY'", [friday])
    rates = [
        FxRate(day=d, currency=c, rate=r)
        for d, c, r in admin(
            fresh, "SELECT day, currency, rate FROM fx_rates WHERE currency = 'CNY'"
        )
    ]
    found = rate_on(rates, "CNY", saturday)
    assert found.is_fallback and found.rate.rate == Decimal("1792.290000")


def test_app_role_cannot_write_fx_rates_directly(fresh: dict[str, str]) -> None:
    with psycopg.connect(fresh["app"]) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO fx_rates (day, currency, source, rate) VALUES (%s, 'USD', 'cbu', 1)",
                [TODAY],
            )
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM fx_rates")


def test_fx_upsert_only_writes_cbu_and_leaves_manual_alone(fresh: dict[str, str]) -> None:
    admin(
        fresh,
        "INSERT INTO fx_rates (day, currency, source, rate) VALUES (%s, 'CNY', 'manual', 1800)",
        [TODAY],
    )
    with psycopg.connect(fresh["app"]) as conn:
        conn.execute("SELECT fx_upsert(%s, 'CNY', 1792.29)", [TODAY])
        conn.commit()
        with pytest.raises(psycopg.errors.NumericValueOutOfRange):
            conn.execute("SELECT fx_upsert(%s, 'CNY', 1e20)", [TODAY])
        conn.rollback()
    rows = dict(admin(fresh, "SELECT source, rate FROM fx_rates WHERE currency = 'CNY'"))
    assert rows == {"manual": Decimal("1800.000000"), "cbu": Decimal("1792.290000")}


def test_job_registered_twice_a_day_and_runs(fresh: dict[str, str]) -> None:
    app = jobs.build_app(InMemoryConnector())
    periodic = {p.task.name: p.cron for p in app.periodic_registry.periodic_tasks.values()}
    assert periodic[jobs.FX] == "5 4,11 * * *"  # Toshkent 09:05 va 16:05

    cbu = FakeCbu(archive_from=TODAY)
    with runtime(fresh, sf.seller(), cbu_url=BASE, fx_backfill_per_run=0) as run:

        async def main(rt: Runtime) -> dict[str, Any]:
            rt.transport = cbu.transport
            async with app.open_async():
                await app.configure_task(jobs.FX).defer_async(timestamp=0)
                await app.run_worker_async(
                    queues=[jobs.QUEUE],
                    wait=False,
                    install_signal_handlers=False,
                    additional_context={"runtime": rt},
                )
            job = next(iter(app.connector.jobs.values()))  # type: ignore[attr-defined]
            return dict(job)

        job = run(main)
    assert job["status"] == "succeeded"
    assert len(stored(fresh)) == 4


def test_settings_reject_plain_http_cbu() -> None:
    assert "UP_CBU_URL: faqat https://" in Settings(cbu_url="http://cbu.uz/x").problems()
    assert "UP_CBU_URL: faqat https://" not in Settings().problems()

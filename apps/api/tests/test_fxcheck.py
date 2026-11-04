"""CBU kurslari diagnostikasi (``upapi.fxcheck``): tarmoq holati, bazadagi kurslar, ``fx.cbu`` ishlari."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date

import dbtools
import httpx
import pytest
import sellerfake as sf
from sellerfake import admin
from upapi import fxcheck
from upapi.db.session import make_engine


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


def test_network_reports_status_rows_or_error_type() -> None:
    settings = sf.settings_for({"app": "postgresql://x"}, cbu_url="https://cbu.test/json/")

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"Ccy": "CNY"}, {"Ccy": "USD"}])

    def blocked(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret detail")

    async def go(handler: httpx.MockTransport) -> dict[str, object]:
        async with httpx.AsyncClient(transport=handler) as client:
            return await fxcheck.network(settings, client)

    assert asyncio.run(go(httpx.MockTransport(ok))) == {
        "url": "https://cbu.test/json/",
        "status": 200,
        "rows": 2,
    }
    # Xato turi chiqadi, matni (ichida sirlar bo'lishi mumkin) — yo'q.
    assert asyncio.run(go(httpx.MockTransport(blocked))) == {
        "url": "https://cbu.test/json/",
        "error": "ConnectError",
    }


def test_build_reports_rates_per_currency_and_jobs(urls: dict[str, str]) -> None:
    admin(urls, "DELETE FROM fx_rates")
    admin(
        urls,
        "INSERT INTO fx_rates (day, currency, source, rate) VALUES "
        "('2026-10-20', 'USD', 'cbu', 12000), ('2026-11-04', 'USD', 'cbu', 12100), "
        "('2026-11-04', 'CNY', 'cbu', 1790)",
    )
    settings = sf.settings_for(urls, cbu_url="https://cbu.test/json/")

    async def go() -> dict[str, object]:
        engine = make_engine(urls["app"])
        try:
            rates = await fxcheck.database(engine)
            return {"rates": rates, "jobs": await fxcheck.jobs(engine), "s": settings.cbu_url}
        finally:
            await engine.dispose()

    out = asyncio.run(go())
    assert out["rates"] == [
        {
            "currency": "CNY",
            "source": "cbu",
            "first": date(2026, 11, 4),
            "last": date(2026, 11, 4),
            "n": 1,
        },
        {
            "currency": "USD",
            "source": "cbu",
            "first": date(2026, 10, 20),
            "last": date(2026, 11, 4),
            "n": 2,
        },
    ]
    # Ishlar: ro'yxat (bo'sh bo'lishi mumkin) yoki sababi bilan xato — hisobot yiqilmaydi.
    assert isinstance(out["jobs"], list) or "error" in out["jobs"]  # type: ignore[operator]

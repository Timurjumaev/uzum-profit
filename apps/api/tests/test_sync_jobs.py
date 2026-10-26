"""B2.6 navbati (Procrastinate, xotiradagi konnektor + haqiqiy baza): rejalashtiruvchi, akkaunt ishi, qulf va
navbat qulfi, ustuvorlik, ishchi ishga tushishidagi xavfsizlik tekshiruvlari."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from procrastinate.testing import InMemoryConnector
from sellerfake import TOKEN, A, admin, create_account, runtime, seller
from upapi import worker
from upapi.settings import Environment
from upapi.startup import UnsafeConfiguration
from upapi.sync import jobs
from upapi.sync.engine import Kind, Runtime, Trigger


@pytest.fixture(scope="module")
def fresh() -> Iterator[dict[str, str]]:
    """Alohida baza: rejalashtiruvchi faqat shu moduldagi akkauntlarni ko'radi."""
    with dbtools.migrated_database() as urls:
        yield urls


def connector(app: Any) -> InMemoryConnector:
    assert isinstance(app.connector, InMemoryConnector)
    return app.connector


async def drain(app: Any, rt: Runtime) -> None:
    """Navbat bo'shaguncha ishlar bajariladi (``wait=False``)."""
    await app.run_worker_async(
        queues=jobs.QUEUES,
        wait=False,
        install_signal_handlers=False,
        additional_context={"runtime": rt},
    )


def test_tick_queues_accounts_and_worker_syncs(fresh: dict[str, str]) -> None:
    fake = seller()
    app = jobs.build_app(InMemoryConnector())
    with runtime(fresh, fake) as run:
        account = create_account(fresh, sf.settings_for(fresh), TOKEN, [A])
        disconnected = create_account(fresh, sf.settings_for(fresh), TOKEN, [A])
        admin(
            fresh,
            "UPDATE mp_accounts SET status = 'disconnected', token_encrypted = NULL, key_version = NULL, "
            "token_last4 = NULL WHERE id = %s",
            [disconnected.account_id],
        )

        async def main(rt: Runtime) -> list[dict[str, Any]]:
            async with app.open_async():
                await app.configure_task(jobs.TICK).defer_async(timestamp=0)
                await drain(app, rt)
            return list(connector(app).jobs.values())

        done = run(main)
    by_task: dict[str, list[dict[str, Any]]] = {}
    for job in done:
        by_task.setdefault(job["task_name"], []).append(job)
    assert [j["status"] for j in by_task[jobs.TICK]] == ["succeeded"]
    accounts = by_task[jobs.ACCOUNT]
    assert len(accounts) == 1 and accounts[0]["status"] == "succeeded"
    assert accounts[0]["lock"] == f"account:{account.account_id}"
    assert accounts[0]["args"]["trigger"] == "schedule" and accounts[0]["priority"] == 0
    runs = admin(fresh, "SELECT count(*) FROM sync_runs WHERE org_id = %s", [account.org_id])
    assert runs[0][0] >= 6


def test_defer_account_queueing_lock_and_priority(fresh: dict[str, str]) -> None:
    app = jobs.build_app(InMemoryConnector())
    org, acc = sf.uuid.uuid4(), sf.uuid.uuid4()

    async def main() -> list[bool]:
        async with app.open_async():
            return [
                await jobs.defer_account(app, org, acc, Trigger.SCHEDULE),
                await jobs.defer_account(app, org, acc, Trigger.SCHEDULE),  # navbatda bor
                await jobs.defer_account(app, org, acc, Trigger.USER, [Kind.ORDERS]),
            ]

    assert asyncio.run(main()) == [True, False, True]
    queued = sorted(connector(app).jobs.values(), key=lambda j: j["id"])
    assert [j["priority"] for j in queued] == [0, 10]
    assert [j["queueing_lock"] for j in queued] == [f"schedule:{acc}", f"user:{acc}"]
    assert queued[1]["args"] == {
        "org_id": str(org),
        "account_id": str(acc),
        "trigger": "user",
        "kinds": ["orders"],
    }


def test_job_queue_opens_lazily(fresh: dict[str, str]) -> None:
    queue = jobs.JobQueue(jobs.build_app(InMemoryConnector()))

    async def main() -> bool:
        await queue.aclose()  # ochilmagan — hech narsa
        ok = await queue.defer_account(sf.uuid.uuid4(), sf.uuid.uuid4(), Trigger.CONNECT)
        await queue.aclose()
        return ok

    assert asyncio.run(main()) is True
    assert [j["priority"] for j in connector(queue.app).jobs.values()] == [5]


def test_periodic_tick_registered() -> None:
    app = jobs.build_app(InMemoryConnector())
    periodic = list(app.periodic_registry.periodic_tasks.values())
    assert sorted((p.task.name, p.cron) for p in periodic) == [
        (jobs.CALC_NIGHTLY, jobs.CALC_CRON),
        (jobs.FX, jobs.FX_CRON),
        (jobs.TICK, "* * * * *"),
    ]
    assert jobs.connector_for(sf.settings_for({"app": "postgresql://u:p@h:5/d"}))


def test_job_without_runtime_fails(fresh: dict[str, str]) -> None:
    app = jobs.build_app(InMemoryConnector())

    async def main() -> str:
        async with app.open_async():
            await app.configure_task(jobs.TICK).defer_async(timestamp=0)
            await app.run_worker_async(wait=False, install_signal_handlers=False)
        return str(next(iter(connector(app).jobs.values()))["status"])

    assert asyncio.run(main()) == "failed"


def test_worker_refuses_unsafe_settings(fresh: dict[str, str]) -> None:
    staging = sf.settings_for(fresh, env=Environment.STAGING)
    with pytest.raises(UnsafeConfiguration, match="UP_OTP_SECRET"):
        asyncio.run(worker.run(staging))
    broken = sf.settings_for(fresh, token_key_version=9)
    with pytest.raises(UnsafeConfiguration):
        asyncio.run(worker.run(broken))


def test_worker_starts_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Haqiqiy navbat bazasi bilan ishga tushadi (rol tekshiruvi, ``up_app``), bekor qilinganda yopiladi. Alohida
    bo'sh baza: rejalashtiruvchi hech qanday akkauntni (va tashqi tarmoqni) ko'rmaydi.

    Rejalashtiruvchi vaqti kelgan hamma davriy ishni ishga tushishda navbatga qo'yadi: ``tick`` har daqiqada, kurs va
    tungi hisob esa faqat o'z soatidan keyingi bir necha daqiqada (UTC 04:05, 11:05, 22:40). Test devor soatiga
    bog'liq bo'lmasligi uchun uchalasi doim "vaqti kelgan" deb olinadi."""
    monkeypatch.setattr(jobs, "FX_CRON", "* * * * *")
    monkeypatch.setattr(jobs, "CALC_CRON", "* * * * *")
    with dbtools.migrated_database() as urls:
        settings = sf.settings_for(urls)

        async def main() -> None:
            task = asyncio.create_task(worker.run(settings))
            await asyncio.sleep(1.5)
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(main())
        defers = dict(
            admin(
                urls,
                "SELECT periodic_id, count(*) FROM procrastinate_periodic_defers GROUP BY periodic_id",
            )
        )
    # Davriy rejalashtiruvchi ishladi: sync.tick (har daqiqa — 1.5 s ichida daqiqa chegarasi o'tsa ikkinchisi ham)
    # va qolgan davriy ishlar navbatga qo'yildi.
    assert defers.keys() == {"tick", "fx", "calc"}
    assert defers["tick"] >= 1


def test_worker_waits_for_migrations() -> None:
    """Migratsiyasiz bazada ishchi yiqilmaydi — navbat jadvallari paydo bo'lguncha kutadi."""
    dbtools.require_admin()
    name = f"up_test_{sf.uuid.uuid4().hex[:10]}"
    urls = dbtools.create_database(name)
    try:

        async def main() -> None:
            rt_engine = sf.make_engine(urls["owner"])
            try:
                waiting = asyncio.create_task(worker.wait_for_schema(rt_engine, every=0.05))
                await asyncio.sleep(0.3)
                assert not waiting.done()
                await asyncio.to_thread(dbtools.alembic, urls["owner"], "upgrade", "head")
                await asyncio.wait_for(waiting, timeout=5)
            finally:
                await rt_engine.dispose()

        asyncio.run(main())
    finally:
        dbtools.drop_database(name)

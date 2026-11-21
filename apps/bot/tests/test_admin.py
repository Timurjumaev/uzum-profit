"""B8.5a admin kuzatuvi: yiqilgan ishlar (haqiqiy PostgreSQL), qotib qolgan ishlar, kritik takror oralig'i, kunlik jamlanma
kuniga bir marta (Toshkent 09:00 dan keyin)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import dbtools
import psycopg
import pytest
from upapi.db.session import make_engine
from upbot import admin
from upbot.admin import Snapshot, State

NOW = datetime(2026, 11, 21, 5, 0, tzinfo=UTC)  # Toshkent 10:00


@pytest.fixture(scope="module")
def urls() -> Any:
    with dbtools.migrated_database() as u:
        yield u


def _job(
    conn: psycopg.Connection, task: str, status: str, scheduled: datetime | None = None
) -> int:
    row = conn.execute(
        "INSERT INTO procrastinate_jobs (queue_name, task_name, status, scheduled_at) "
        "VALUES ('calc', %s, %s::procrastinate_job_status, %s) RETURNING id",
        [task, status, scheduled],
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_snapshot_counts_recent_failures_and_stuck_jobs(urls: dict[str, str]) -> None:
    with psycopg.connect(urls["admin"], autocommit=True) as conn:
        old = _job(conn, "calc.org", "failed")
        new1 = _job(conn, "calc.org", "failed")
        new2 = _job(conn, "sync.account", "failed")
        for job, at in (
            (old, NOW - timedelta(days=3)),
            (new1, NOW - timedelta(hours=2)),
            (new2, NOW - timedelta(hours=1)),
        ):
            conn.execute(
                "INSERT INTO procrastinate_events (job_id, type, at) VALUES (%s, 'failed', %s)",
                [job, at],
            )
        _job(conn, "calc.org", "todo", NOW - timedelta(hours=1))  # qotib qolgan
        _job(conn, "calc.org", "todo", NOW - timedelta(minutes=5))  # hali kutish normal

    async def main() -> Snapshot:
        engine = make_engine(urls["app"])
        try:
            return await admin.snapshot(engine, NOW)
        finally:
            await engine.dispose()

    snap = asyncio.run(main())
    assert snap.failed == {"calc.org": 1, "sync.account": 1}
    assert snap.stuck == 1
    assert 0 <= snap.disk_percent <= 100


def test_digest_once_a_day_after_nine_tashkent() -> None:
    state = State()
    snap = Snapshot({"calc.org": 2}, 0, 10)
    early = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)  # Toshkent 08:00
    assert admin.messages_due(snap, state, early) == []
    first = admin.messages_due(snap, state, NOW)
    assert len(first) == 1 and "calc.org: 2" in first[0] and "Disk: 10%" in first[0]
    assert admin.messages_due(snap, state, NOW + timedelta(hours=3)) == []  # shu kuni qayta emas
    assert len(admin.messages_due(snap, state, NOW + timedelta(days=1))) == 1  # ertasi kuni yana


def test_critical_alerts_repeat_every_six_hours_and_reset() -> None:
    state = State(digest_day=NOW.astimezone(admin.TASHKENT).date())
    bad = Snapshot({}, 3, 91)
    first = admin.messages_due(bad, state, NOW)
    assert (
        len(first) == 2
        and any("3 ta fon ishi" in x for x in first)
        and any("91%" in x for x in first)
    )
    assert admin.messages_due(bad, state, NOW + timedelta(hours=1)) == []
    assert len(admin.messages_due(bad, state, NOW + timedelta(hours=6))) == 2
    assert admin.messages_due(Snapshot(), state, NOW + timedelta(hours=7)) == []  # tuzaldi — jim
    assert (
        len(admin.messages_due(bad, state, NOW + timedelta(hours=8))) == 2
    )  # qaytadan buzilsa — darhol


def test_digest_is_calm_when_all_fine() -> None:
    text = admin.digest_text(Snapshot())
    assert "Yiqilgan fon ishlari yo'q" in text and "Qotib qolgan ishlar: 0" in text

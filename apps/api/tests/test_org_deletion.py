"""B8.13 tashkilotni o'chirish (haqiqiy PostgreSQL): faqat egasi, so'rash/bekor qilish/takror, 30 kun kutish, muddatdan
keyin ``purge`` butunlay o'chiradi (boshqa tashkilot tegilmaydi), audit."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import test_reports as tr
from upapi import purge
from upapi.auth.deps import COOKIE
from upapi.db.session import make_engine

db = tr.db
world = tr.world


def send(w: tr.World, method: str, role: str = "owner") -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.request(
        method, f"/api/v1/orgs/{w.org_id}/deletion", headers={"X-Requested-With": "fetch"}
    )


def run_purge(w: tr.World, now: datetime) -> int:
    async def main() -> int:
        engine = make_engine(w.a.db["app"])
        try:
            return await purge.purge_all(engine, now)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_request_cancel_and_permissions(world: tr.World) -> None:
    w = world
    assert send(w, "GET").json() == {"requested_at": None, "delete_on": None, "days_left": None}
    for role in ("manager", "accountant", "warehouse"):
        assert send(w, "POST", role).status_code == 403
        assert send(w, "GET", role).status_code == 403
        assert send(w, "DELETE", role).status_code == 403
    assert send(w, "DELETE").status_code == 409  # so'ralmagan
    r = send(w, "POST")
    assert r.status_code == 202, r.text
    assert r.json()["days_left"] == 31 or r.json()["days_left"] == 30
    assert send(w, "POST").status_code == 409  # takror
    assert send(w, "GET").json()["requested_at"] is not None
    assert send(w, "DELETE").json()["requested_at"] is None
    actions = [
        r[0]
        for r in w.a.sql(
            "SELECT action FROM audit_log WHERE org_id = %s AND action LIKE 'org.delete.%%' ORDER BY created_at",
            [w.org_id],
        )
    ]
    assert actions == ["org.delete.request", "org.delete.cancel"]


def test_purge_removes_only_due_org(world: tr.World) -> None:
    w = world
    now = datetime.now(UTC)
    assert run_purge(w, now) == 0  # hech kim so'ramagan
    # Boshqa tashkilot: 29 kun oldin so'ragan (hali muddat o'tmagan), bizniki — 31 kun oldin
    w.a.sql(
        "UPDATE orgs SET deletion_requested_at = %s WHERE id = %s",
        [now - timedelta(days=29), w.other],
    )
    assert run_purge(w, now) == 0
    assert w.a.sql("SELECT count(*) FROM orgs WHERE id = %s", [w.other]) == [(1,)]
    w.a.sql(
        "UPDATE orgs SET deletion_requested_at = %s WHERE id = %s",
        [now - timedelta(days=31), w.other],
    )
    sales_before = w.a.sql("SELECT count(*) FROM sale_items WHERE org_id = %s", [w.org_id])
    assert run_purge(w, now) == 1
    assert w.a.sql("SELECT count(*) FROM orgs WHERE id = %s", [w.other]) == [(0,)]
    for table in ("sale_items", "shops", "mp_accounts", "memberships", "audit_log"):
        assert w.a.sql(f"SELECT count(*) FROM {table} WHERE org_id = %s", [w.other]) == [(0,)], (
            table
        )
    # Bizning tashkilot butunligicha
    assert w.a.sql("SELECT count(*) FROM sale_items WHERE org_id = %s", [w.org_id]) == sales_before
    assert w.a.sql("SELECT count(*) FROM orgs WHERE id = %s", [w.org_id]) == [(1,)]

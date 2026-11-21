"""B7.5 to'liq eksport (haqiqiy PostgreSQL): ZIP tarkibi bazadagi qatorlar soniga teng, boshqa tashkilot qatorlari yo'q (RLS),
kalit/sessiya/chat id kirmaydi, faqat egasi, kuniga bir marta, bir martalik 24 soatlik havola."""

from __future__ import annotations

import asyncio
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import test_reports as tr
from sellerfake import TOKEN
from upapi import export_full
from upapi.auth.deps import COOKIE
from upapi.db import models as m
from upapi.db.session import make_engine

db = tr.db
world = tr.world


def send(w: tr.World, method: str, path: str, role: str = "owner") -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.request(
        method, f"/api/v1/orgs/{w.org_id}/{path}", headers={"X-Requested-With": "fetch"}
    )


def run_job(w: tr.World, export_id: str, now: datetime | None = None) -> str:
    async def main() -> str:
        engine = make_engine(w.a.db["app"])
        try:
            return await export_full.run_export(
                engine, w.org_id, uuid.UUID(export_id), now or datetime.now(UTC)
            )
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_every_tenant_table_is_exported_or_explained() -> None:
    assert set(export_full.EXCLUDED) <= set(m.TENANT)
    assert all(reason for reason in export_full.EXCLUDED.values())
    exported = set(export_full.exported_tables())
    assert exported | set(export_full.EXCLUDED) | {"orgs"} == set(m.TENANT) | {"orgs"}
    for must in ("purchases", "sale_items", "manual_expenses", "stock_moves", "items"):
        if must in m.TENANT:
            assert must in exported
    assert "mp_accounts" not in exported and "notification_channels" not in exported


def test_full_export_flow(world: tr.World) -> None:
    w = world
    # Faqat egasi
    assert send(w, "POST", "exports/full", role="manager").status_code == 403
    assert send(w, "GET", "exports/full", role="accountant").status_code == 403
    assert send(w, "GET", "exports/full").json() == []

    r = send(w, "POST", "exports/full")
    assert r.status_code == 202, r.text
    export_id = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert any(j["task_name"] == "export.full" for j in w.api.queued)
    # Kuniga bir marta
    assert send(w, "POST", "exports/full").status_code == 429
    # Tayyor bo'lmaguncha havola yo'q
    assert send(w, "POST", f"exports/full/{export_id}/link").status_code == 409

    assert run_job(w, export_id) == "ready"
    assert run_job(w, export_id) == "skipped"  # qayta bajarilmaydi
    (item,) = send(w, "GET", "exports/full").json()
    assert item["status"] == "ready" and item["size_bytes"] > 0 and not item["downloaded"]

    link = send(w, "POST", f"exports/full/{export_id}/link")
    assert link.status_code == 200, link.text
    url = link.json()["url"]
    assert send(w, "GET", f"exports/full/{export_id}/download?token={'x' * 30}").status_code == 403
    w.api.client.cookies.set(COOKIE, w.sessions["manager"])
    assert w.api.client.get(url).status_code == 403  # egasi emas
    w.api.client.cookies.set(COOKIE, w.sessions["owner"])
    got = w.api.client.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
    assert w.api.client.get(url).status_code == 403  # bir martalik
    assert send(w, "GET", "exports/full").json()[0]["downloaded"] is True

    archive = zipfile.ZipFile(io.BytesIO(got.content))
    names = set(archive.namelist())
    manifest = json.loads(archive.read("manifest.json"))
    assert "json/org.json" in names and "manifest.json" in names

    # Har jadval: qatorlar soni bazadagiga teng, hammasi shu tashkilotniki
    with psycopg.connect(w.a.db["admin"]) as conn:
        for table in export_full.exported_tables():
            (expected,) = conn.execute(
                f"SELECT count(*) FROM {table} WHERE org_id = %s", [w.org_id]
            ).fetchone()  # type: ignore[misc]
            rows = json.loads(archive.read(f"json/{table}.json"))
            assert len(rows) == expected == manifest["tables"][table], table
            assert all(r["org_id"] == str(w.org_id) for r in rows), table
            csv_lines = archive.read(f"csv/{table}.csv").decode("utf-8-sig").splitlines()
            assert len(csv_lines) >= 1  # sarlavha
        (other_rows,) = conn.execute(
            "SELECT count(*) FROM sale_items WHERE org_id = %s", [w.other]
        ).fetchone()  # type: ignore[misc]
    assert other_rows > 0  # boshqa tashkilot ma'lumoti bor edi — lekin faylda yo'q
    assert str(w.other) not in b"".join(archive.read(n) for n in names).decode("utf-8", "ignore")

    # Maxfiy narsalar kirmaydi
    blob = b"".join(archive.read(n) for n in names).decode("utf-8", "ignore")
    assert TOKEN not in blob
    with psycopg.connect(w.a.db["admin"]) as conn:
        phones = [r[0] for r in conn.execute("SELECT phone FROM users")]
    assert phones and not any(p in blob for p in phones if p)
    assert not any(n.startswith(("csv/mp_accounts", "json/mp_accounts")) for n in names)
    assert not any("chat" in n for n in names)

    # Audit: so'rov, havola, yuklash
    with psycopg.connect(w.a.db["admin"]) as conn:
        actions = {
            r[0]
            for r in conn.execute(
                "SELECT action FROM audit_log WHERE org_id = %s AND action LIKE 'export.full.%%'",
                [w.org_id],
            )
        }
    assert actions == {"export.full.request", "export.full.link", "export.full.download"}

    # Bildirishnoma: so'ragan egasiga bitta
    with psycopg.connect(w.a.db["admin"]) as conn:
        (n,) = conn.execute(
            "SELECT count(*) FROM notifications WHERE org_id = %s AND event = 'export_ready'",
            [w.org_id],
        ).fetchone()  # type: ignore[misc]
    assert n == 1


def test_expired_link_is_gone(world: tr.World) -> None:
    w = world
    with psycopg.connect(w.a.db["admin"]) as conn:
        conn.execute(
            "UPDATE data_exports SET created_at = now() - interval '2 days' WHERE org_id = %s",
            [w.org_id],
        )
        row = conn.execute("SELECT id FROM data_exports WHERE org_id = %s", [w.org_id]).fetchone()
    assert row is not None
    r = send(w, "POST", "exports/full")  # 24 soatdan keyin yana mumkin
    assert r.status_code == 202, r.text
    new_id = r.json()["id"]
    assert run_job(w, new_id, now=datetime.now(UTC) - timedelta(days=2)) == "ready"
    listed = {e["id"]: e for e in send(w, "GET", "exports/full").json()}
    assert listed[new_id]["status"] == "expired"
    assert send(w, "POST", f"exports/full/{new_id}/link").status_code == 409

"""B8.9 foydalanish hodisalari (haqiqiy PostgreSQL): bosqichlar holatdan bir martadan yoziladi, kunlik kirish kuniga bir marta,
tashkilot yaratilganda ``org_created``."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime

import dbtools
import pytest
import sellerfake as sf
from fastapi.testclient import TestClient
from sellerfake import TOKEN, A, create_account
from test_auth import CSRF, Api, _settings
from test_calc import Org
from upapi import activation
from upapi.auth.senders import MemorySender
from upapi.db.session import make_engine, org_transaction
from upapi.main import create_app

NOW = datetime(2026, 11, 21, 6, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


def track(db: dict[str, str], org: Org) -> list[str]:
    async def main() -> list[str]:
        engine = make_engine(db["app"])
        try:
            async with org_transaction(engine, org.org_id) as conn:
                return await activation.track(conn, org.org_id, NOW)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_milestones_are_recorded_once_each(db: dict[str, str]) -> None:
    account = create_account(db, sf.settings_for(db), TOKEN, [A])
    org = Org(db, account.org_id, account.shops[A])
    assert track(db, org) == []  # hech narsa erishilmagan (tarix yo'q, sotuv yo'q)

    org.sql("UPDATE shops SET history_status = 'done' WHERE org_id = %s", [org.org_id])
    assert track(db, org) == ["history_loaded"]
    assert track(db, org) == []  # takror yozilmaydi

    item, sku = org.item("Tovar")
    # 10 ta sotuv, 5 tasida tannarx (tushum 50%) → costs_60 hali yo'q
    sales = [org.sale(sku, date(2026, 11, 2 + i), 1, price=100_000) for i in range(10)]
    for sale in sales[:5]:
        org.insert("sale_costs", sale_item_id=sale, method="fifo", unit_cost=50_000, cogs=50_000)
    org.insert("item_costs", item_id=item, unit_cost=50_000)
    assert track(db, org) == ["first_cost"]
    for sale in sales[5:7]:  # 7/10 = 70% ≥ 60%
        org.insert("sale_costs", sale_item_id=sale, method="fifo", unit_cost=50_000, cogs=50_000)
    assert track(db, org) == ["costs_60"]

    user = org.sql("SELECT user_id FROM memberships WHERE org_id = %s", [org.org_id])[0][0]
    org.insert("notification_channels", user_id=user, kind="telegram", target="123")
    assert track(db, org) == ["telegram_linked"]
    assert track(db, org) == []
    names = sorted(r[0] for r in org.sql("SELECT name FROM events WHERE org_id = %s", [org.org_id]))
    assert names == ["costs_60", "first_cost", "history_loaded", "telegram_linked"]


def test_org_created_and_daily_visit_once_per_day(db: dict[str, str]) -> None:
    sender = MemorySender()
    app = create_app(_settings(db), sender=sender)
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as client:
        api = Api(client, sender, db)
        api.login()
        org = api.org()
        assert api.admin(
            "SELECT count(*) FROM events WHERE org_id = %s AND name = 'org_created'", [org]
        ) == [(1,)]
        for _ in range(3):
            assert client.get("/api/v1/auth/me").status_code == 200
        assert api.admin(
            "SELECT count(*) FROM events WHERE org_id = %s AND name = 'daily_visit'", [org]
        ) == [(1,)]
        # Ertasi kuni (kechagi yozuv bo'lsa) yana bitta yoziladi
        api.admin(
            "UPDATE events SET created_at = created_at - interval '1 day' WHERE org_id = %s AND name = 'daily_visit'",
            [org],
        )
        assert client.get("/api/v1/auth/me").status_code == 200
        assert api.admin(
            "SELECT count(*) FROM events WHERE org_id = %s AND name = 'daily_visit'", [org]
        ) == [(2,)]

"""B8.3a admin ko'rinishi: faqat migratsiya egasi chaqira oladi (ilova roli — yo'q), faqat ruxsat etilgan ustunlar,
o'chirilgan tashkilot ko'rinmaydi, sotuvchi biznes ma'lumoti chiqmaydi."""

from __future__ import annotations

import asyncio
import io

import psycopg
import pytest
import sellerfake as sf
from psycopg import errors
from sellerfake import TOKEN, A, create_account
from test_reports import db  # noqa: F401
from upapi import admin


def test_overview_lists_orgs_without_business_data(db: dict[str, str]) -> None:  # noqa: F811
    account = create_account(db, sf.settings_for(db), TOKEN, [A])
    deleted = create_account(db, sf.settings_for(db), TOKEN, [A])
    with psycopg.connect(db["admin"], autocommit=True) as conn:
        conn.execute("UPDATE orgs SET deleted_at = now() WHERE id = %s", [deleted.org_id])
        conn.execute(
            "INSERT INTO sync_state (org_id, shop_id, kind, last_status, last_error, failures, last_attempt_at) "
            "VALUES (%s, %s, 'orders', 'failed', 'Uzum 401', 3, now())",
            [account.org_id, account.shops[A]],
        )
    out = io.StringIO()
    n = asyncio.run(admin.overview(db["admin"], out))
    text = out.getvalue()
    assert (
        n >= 1
        and "a'zo=1 do'kon=1" in text
        and "xato=3" in text
        and "oxirgi xato: Uzum 401" in text
    )
    assert str(deleted.org_id) not in text
    assert TOKEN not in text


def test_app_role_cannot_call_overview(db: dict[str, str]) -> None:  # noqa: F811
    with psycopg.connect(db["app"]) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM admin_overview()")


def test_admin_role_cannot_read_business_columns(db: dict[str, str]) -> None:  # noqa: F811
    with psycopg.connect(db["admin"], autocommit=True) as conn:
        conn.execute("SET ROLE up_admin")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("SELECT sell_price FROM sale_items")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("SELECT token_encrypted FROM mp_accounts")


def test_funnel_shows_first_times_per_org(db: dict[str, str]) -> None:  # noqa: F811
    account = create_account(db, sf.settings_for(db), TOKEN, [A])
    with psycopg.connect(db["admin"], autocommit=True) as conn:
        conn.execute("UPDATE orgs SET name = 'Voronka' WHERE id = %s", [account.org_id])
        for name in ("org_created", "mp_account_connected", "daily_visit", "daily_visit"):
            conn.execute(
                "INSERT INTO events (org_id, name) VALUES (%s, %s)", [account.org_id, name]
            )
    out = io.StringIO()
    asyncio.run(admin.funnel(db["admin"], out))
    line = next(x for x in out.getvalue().splitlines() if x.startswith("Voronka"))
    cells = line.split("\t")
    assert cells[1] != "—" and cells[2] != "—" and cells[3] == "—" and cells[-1] == "2"
    with psycopg.connect(db["app"]) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM admin_funnel()")

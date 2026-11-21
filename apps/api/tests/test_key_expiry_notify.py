"""B8.16: ``keys_expiring`` — muddatidan 5 va 1 kun oldin bitta ogohlantirish; boshqa kunlarda, muddatsiz va yaroqsiz akkauntda yo'q."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date, timedelta

import dbtools
import pytest
import sellerfake as sf
from sellerfake import TOKEN, A, create_account
from upapi import notify
from upapi.db.session import make_engine, org_transaction

TODAY = date(2026, 11, 21)


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


def found(db: dict[str, str], org_id) -> list:  # type: ignore[no-untyped-def]
    async def main():  # type: ignore[no-untyped-def]
        engine = make_engine(db["app"])
        try:
            async with org_transaction(engine, org_id) as conn:
                return await notify.keys_expiring(conn, TODAY)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_warns_only_five_and_one_day_before(db: dict[str, str]) -> None:
    import psycopg

    account = create_account(db, sf.settings_for(db), TOKEN, [A])

    def set_expiry(days: int | None, status: str = "active") -> None:
        with psycopg.connect(db["admin"], autocommit=True) as conn:
            conn.execute(
                "UPDATE mp_accounts SET key_expires_on = %s, status = %s WHERE id = %s",
                [
                    None if days is None else TODAY + timedelta(days=days),
                    status,
                    account.account_id,
                ],
            )

    assert found(db, account.org_id) == []  # muddat yo'q
    for days in (30, 6, 4, 3, 2, 0, -2):
        set_expiry(days)
        assert found(db, account.org_id) == [], days
    set_expiry(5)
    (five,) = found(db, account.org_id)
    assert five.payload["days"] == 5 and five.payload["key_hint"].startswith("…")
    assert TOKEN not in str(five.payload)
    set_expiry(1)
    (one,) = found(db, account.org_id)
    assert one.payload["days"] == 1 and one.dedupe_key != five.dedupe_key
    set_expiry(1, "invalid")  # kalit allaqachon yaroqsiz — ogohlantirish ma'nosiz
    assert found(db, account.org_id) == []

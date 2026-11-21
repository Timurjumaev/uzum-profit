"""B8.4a: 20 sintetik tashkilot bilan tutun sinovi — har birida o'z do'koni va turli sondagi sotuv; hisob (calc) hammasi
uchun ishlaydi, egasi faqat o'z raqamini ko'radi (Bosh sahifa), boshqalarnikini emas, ro'yxatlar to'liq."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import dbtools
import pytest
import sellerfake as sf
from mptools import MpApi, mp_api
from sellerfake import TOKEN, A, create_account
from test_calc import Org
from test_reports import OCT, d
from upapi import calc
from upapi.auth.deps import COOKIE

ORGS = 20


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


def test_twenty_orgs_are_computed_and_isolated(db: dict[str, str]) -> None:
    settings = sf.settings_for(db)
    orgs: list[Org] = []
    for i in range(ORGS):
        account = create_account(db, settings, TOKEN, [A])
        org = Org(db, account.org_id, account.shops[A])
        for k in range(i + 1):  # i-tashkilotda i+1 ta sotuv — raqamlar har xil
            org.sale(None, d(10, 2 + k % 20), 1, price=100_000)
        org.run(lambda conn, org=org: calc.request_full(conn, org.org_id))
        orgs.append(org)
    now = datetime.now(UTC)
    for org in orgs:
        org.recalc(now)

    with mp_api(db) as api:
        sessions = _sessions(api, orgs)
        for i, org in enumerate(orgs):
            api.client.cookies.set(COOKIE, sessions[i])
            r = api.client.get(f"/api/v1/orgs/{org.org_id}/dashboard", params=OCT)
            assert r.status_code == 200, r.text
            in_window = sum(1 for k in range(i + 1) if 2 + k % 20 <= 20)  # OCT: 1–20 oktabr
            revenue = Decimal(r.json()["statement"]["revenue"])
            assert revenue == Decimal(in_window * 100_000), (i, revenue)
            # Boshqa tashkilotning manzili — 404
            other = orgs[(i + 1) % ORGS]
            assert (
                api.client.get(f"/api/v1/orgs/{other.org_id}/dashboard", params=OCT).status_code
                == 404
            )
            shops = api.client.get(f"/api/v1/orgs/{org.org_id}/shops").json()
            assert [s["id"] for s in shops] == [str(org.shop_id)]


def _sessions(api: MpApi, orgs: list[Org]) -> list[str]:
    out = []
    for org in orgs:
        phone = api.login()
        user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
        api.admin(
            "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, 'owner')",
            [org.org_id, user],
        )
        out.append(api.client.cookies[COOKIE])
    return out

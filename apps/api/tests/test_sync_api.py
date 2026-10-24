"""B2.6 API: "Ma'lumotlar holati" (``GET /orgs/{id}/sync``), "Hozir yangilash" (``POST .../sync/refresh``), kalit
ulanganda tarix navbatga qo'yilishi; ruxsat va tashkilotlarni ajratish."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
import sellerfake as sf
from mptools import MpApi, mp_api, shop
from sellerfake import NOW, A, Clock, admin, runtime, seller
from upapi.sync import engine as eng

TOKEN = sf.TOKEN


@pytest.fixture
def api(db: dict[str, str]) -> Iterator[MpApi]:
    admin(db, "DELETE FROM provider_health")
    with mp_api(db) as api:
        yield api
    admin(db, "DELETE FROM provider_health")


def connect(api: MpApi) -> tuple[str, str]:
    org = api.owner_org()
    api.uzum.keys[TOKEN] = [shop(A, "byDurii")]
    r = api.connect(org, TOKEN)
    assert r.status_code == 201, r.text
    return org, r.json()["id"]


def status(api: MpApi, org: str) -> dict[str, Any]:
    r = api.client.get(f"/api/v1/orgs/{org}/sync")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def kinds(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k["kind"]: k for k in body["shops"][0]["kinds"]}


def test_connect_queues_history(api: MpApi) -> None:
    org, account = connect(api)
    queued = api.queued
    assert len(queued) == 1
    job = queued[0]
    assert job["task_name"] == "sync.account" and job["priority"] == 5
    assert job["lock"] == f"account:{account}"
    assert job["args"] == {
        "org_id": org,
        "account_id": account,
        "trigger": "connect",
        "kinds": None,
    }


def test_status_before_and_after_sync(api: MpApi, db: dict[str, str]) -> None:
    org, account = connect(api)
    before = status(api, org)
    assert before["healthy"] is False and before["outage"]["active"] is False
    assert before["accounts"][0]["status"] == "active"
    assert set(kinds(before)) == {k.value for k in eng.Kind}
    assert all(k["status"] is None for k in kinds(before).values())
    assert before["freshness"]["orders"] is None

    fake = seller()
    clock = Clock(datetime.now(UTC))
    with runtime(db, fake, clock) as run:
        run(lambda rt: eng.sync_account(rt, UUID(org), UUID(account), trigger=eng.Trigger.CONNECT))
    after = status(api, org)
    shop_status = after["shops"][0]
    assert shop_status["history_status"] == "full" and shop_status["healthy"] is True
    assert shop_status["errors_24h"] == 0
    orders = kinds(after)["orders"]
    assert (orders["status"], orders["mode"], orders["fetched"], orders["total"]) == (
        "ok",
        "history",
        3,
        3,
    )
    assert orders["last_success_at"] is not None and orders["finished_at"] is not None
    assert kinds(after)["snapshot"]["status"] is None
    assert after["healthy"] is True
    assert after["freshness"]["orders"] == orders["last_success_at"]
    assert after["accounts"][0]["quota_remaining"] == 90_000


def test_status_shows_errors_and_outage(api: MpApi, db: dict[str, str]) -> None:
    org, account = connect(api)
    fake = seller(fail={"orders": "5xx"})
    with runtime(db, fake, Clock(datetime.now(UTC))) as run:
        run(lambda rt: eng.sync_account(rt, UUID(org), UUID(account)))
    body = status(api, org)
    orders = kinds(body)["orders"]
    assert (orders["status"], orders["error"], orders["http_status"]) == ("error", "upstream", 502)
    assert body["shops"][0]["errors_24h"] == 1 and body["healthy"] is False
    admin(
        db,
        "INSERT INTO provider_health (provider, outage_since, paused_until) "
        "VALUES ('uzum', now(), now() + interval '15 minutes') ON CONFLICT (provider) "
        "DO UPDATE SET outage_since = EXCLUDED.outage_since, paused_until = EXCLUDED.paused_until",
    )
    body = status(api, org)
    assert body["outage"]["active"] is True and body["outage"]["since"] is not None


def test_status_running(api: MpApi, db: dict[str, str]) -> None:
    org, _ = connect(api)
    shop_id = status(api, org)["shops"][0]["id"]
    admin(
        db,
        "INSERT INTO sync_runs (org_id, shop_id, kind, mode, total, fetched) "
        "VALUES (%s, %s, 'orders', 'history', 2500, 1000)",
        [org, shop_id],
    )
    orders = kinds(status(api, org))["orders"]
    assert (orders["status"], orders["fetched"], orders["total"]) == ("running", 1000, 2500)


def test_refresh_queues_user_job_with_cooldown(api: MpApi) -> None:
    org, account = connect(api)
    r = api.client.post(f"/api/v1/orgs/{org}/sync/refresh")
    assert r.status_code == 202 and r.json() == {"queued": 1}
    user = [j for j in api.queued if j["args"]["trigger"] == "user"]
    assert len(user) == 1 and user[0]["priority"] == 10
    assert user[0]["queueing_lock"] == f"user:{account}"
    again = api.client.post(f"/api/v1/orgs/{org}/sync/refresh")
    assert again.status_code == 429 and again.json()["code"] == "sync_refresh_limited"
    admin(
        api.urls,
        "UPDATE events SET created_at = created_at - interval '61 seconds' WHERE org_id = %s",
        [org],
    )
    third = api.client.post(f"/api/v1/orgs/{org}/sync/refresh")
    assert third.status_code == 202 and third.json() == {"queued": 0}  # oldingisi hali navbatda


def test_refresh_refused_in_outage(api: MpApi, db: dict[str, str]) -> None:
    org, _ = connect(api)
    admin(db, "INSERT INTO provider_health (provider, outage_since) VALUES ('uzum', now())")
    r = api.client.post(f"/api/v1/orgs/{org}/sync/refresh")
    assert r.status_code == 503 and r.json()["code"] == "uzum_outage"


def test_refresh_without_accounts(api: MpApi) -> None:
    org = api.owner_org()
    r = api.client.post(f"/api/v1/orgs/{org}/sync/refresh")
    assert r.status_code == 409 and r.json()["code"] == "no_accounts"
    org2, account = connect(api)
    assert api.client.delete(f"/api/v1/orgs/{org2}/accounts/{account}/token").status_code == 204
    r = api.client.post(f"/api/v1/orgs/{org2}/sync/refresh")
    assert r.status_code == 409


def test_other_org_cannot_see_or_refresh(api: MpApi) -> None:
    org, _ = connect(api)
    api.login()  # boshqa foydalanuvchi
    api.org()
    assert api.client.get(f"/api/v1/orgs/{org}/sync").status_code == 404
    assert api.client.post(f"/api/v1/orgs/{org}/sync/refresh").status_code == 404


def test_requires_login(api: MpApi) -> None:
    org, _ = connect(api)
    api.client.cookies.clear()
    assert api.client.get(f"/api/v1/orgs/{org}/sync").status_code == 401


def test_any_member_sees_status(api: MpApi, db: dict[str, str]) -> None:
    org, _ = connect(api)
    phone = api.phone()
    user = admin(db, "INSERT INTO users (phone) VALUES (%s) RETURNING id", [phone])[0][0]
    admin(
        db,
        "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, 'warehouse')",
        [org, user],
    )
    api.login(phone)
    assert api.client.get(f"/api/v1/orgs/{org}/sync").status_code == 200


def test_stale_success_is_not_healthy(api: MpApi, db: dict[str, str]) -> None:
    org, account = connect(api)
    with runtime(db, seller(), Clock(NOW - timedelta(days=30))) as run:
        run(lambda rt: eng.sync_account(rt, UUID(org), UUID(account)))
    body = status(api, org)
    assert body["shops"][0]["errors_24h"] == 0 and body["shops"][0]["healthy"] is False


def test_check_and_new_token_reset_sync_failures(api: MpApi, db: dict[str, str]) -> None:
    """Kalit qayta tekshirilib ishlasa (yoki almashtirilsa) — sinxronning ketma-ket kalit xatolari va pauzasi
    tozalanadi, aks holda bitta xatodan keyin yana "yaroqsiz" bo'lardi."""
    org, account = connect(api)
    reset = (
        "UPDATE mp_accounts SET status = 'invalid', auth_failures = 3, "
        "sync_paused_until = now() + interval '1 day' WHERE id = %s"
    )
    query = "SELECT status, auth_failures, sync_paused_until FROM mp_accounts WHERE id = %s"
    admin(db, reset, [account])
    assert api.client.post(f"/api/v1/orgs/{org}/accounts/{account}/check").status_code == 200
    assert admin(db, query, [account]) == [("active", 0, None)]
    admin(db, reset, [account])
    new = "uzk-new-" + TOKEN
    api.uzum.keys[new] = [shop(A, "byDurii")]
    r = api.client.put(f"/api/v1/orgs/{org}/accounts/{account}/token", json={"token": new})
    assert r.status_code == 200, r.text
    assert admin(db, query, [account]) == [("active", 0, None)]
    # Ulash ishi hali navbatda — ikkinchisi qo'yilmaydi (navbat qulfi).
    assert [j["args"]["trigger"] for j in api.queued] == ["connect"]

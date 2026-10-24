"""B2.3: kirish (OTP), sessiyalar, tashkilot, xodimlar, takliflar, rollar, CSRF — haqiqiy PostgreSQL'da."""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any

import dbtools
import psycopg
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from upapi.auth.deps import COOKIE, OrgContext, require
from upapi.auth.permissions import Permission
from upapi.auth.senders import DeliveryError, MemorySender
from upapi.main import create_app
from upapi.settings import Environment, Settings

CSRF = {"X-Requested-With": "test"}


@dataclass
class Api:
    client: TestClient
    sender: MemorySender
    urls: dict[str, str]

    def phone(self) -> str:
        return f"+99890{random.randint(0, 9_999_999):07d}"

    def request_code(self, phone: str) -> Any:
        return self.client.post("/api/v1/auth/otp", json={"phone": phone})

    def login(self, phone: str | None = None, ua: str = "test") -> str:
        """Kirish; joriy cookie — shu foydalanuvchi. Token qaytaradi (keyin almashtirish uchun)."""
        phone = phone or self.phone()
        assert self.request_code(phone).status_code == 202
        r = self.client.post(
            "/api/v1/auth/login",
            json={"phone": phone, "code": self.sender.last_code(phone)},
            headers={"User-Agent": ua},
        )
        assert r.status_code == 200, r.text
        return r.cookies[COOKIE]

    def use(self, token: str) -> None:
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE, token)

    def admin(self, sql: str, params: list[Any] | None = None) -> Any:
        with psycopg.connect(self.urls["admin"]) as conn:
            cur = conn.execute(sql, params or [])
            return cur.fetchall() if cur.description else cur.rowcount

    def org(self, name: str = "Do'kon") -> str:
        r = self.client.post("/api/v1/orgs", json={"name": name})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])


def _settings(urls: dict[str, str], **extra: Any) -> Settings:
    return Settings(env=Environment.TEST, log_json=True, database_url=urls["app"], **extra)


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def api(urls: dict[str, str]) -> Iterator[Api]:
    sender = MemorySender()
    app = create_app(_settings(urls), sender=sender)

    @app.get("/api/v1/orgs/{org_id}/test-finance")
    async def finance(
        ctx: Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))],
    ) -> dict[str, str]:
        return {"profit": "123.00"}

    @app.post("/api/v1/orgs/{org_id}/test-commit-fails")
    async def commit_fails(
        ctx: Annotated[OrgContext, Depends(require(Permission.VIEW_AUDIT))],
    ) -> dict[str, bool]:
        # Commit paytida buziladigan (kechiktirilgan) cheklov.
        await ctx.conn.exec_driver_sql(
            "CREATE TEMP TABLE t (x int UNIQUE DEFERRABLE INITIALLY DEFERRED) ON COMMIT DROP"
        )
        await ctx.conn.exec_driver_sql("INSERT INTO t VALUES (1), (1)")
        return {"ok": True}

    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as client:
        yield Api(client, sender, urls)


@pytest.fixture(autouse=True)
def _fresh_cookies(api: Api) -> None:
    api.client.cookies.clear()


# --- Kod va kirish -------------------------------------------------------------------------------


def test_login_creates_user_and_session(api: Api) -> None:
    phone = api.phone()
    r = api.request_code(phone.replace("+998", "").strip())  # mahalliy 9 xonali ko'rinish
    assert r.status_code == 202 and r.json() == {"phone": phone, "expires_in": 300}
    code = api.sender.last_code(phone)
    r = api.client.post("/api/v1/auth/login", json={"phone": phone, "code": code})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True and body["user"]["phone"] == phone and body["orgs"] == []
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=2592000" in cookie
    assert api.client.get("/api/v1/auth/me").json()["user"]["phone"] == phone
    # Bazada token va kod ochiq holda yo'q.
    token = r.cookies[COOKIE]
    rows = api.admin(
        "SELECT token_hash FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.phone = %s",
        [phone],
    )
    assert rows and all(token.encode() not in bytes(h) for (h,) in rows)
    assert (
        api.admin("SELECT count(*) FROM otp_codes WHERE code_hash = %s", [code.encode()])[0][0] == 0
    )
    # Ikkinchi kirish — o'sha foydalanuvchi.
    api.client.cookies.clear()
    assert api.request_code(phone).status_code == 202
    again = api.client.post(
        "/api/v1/auth/login", json={"phone": phone, "code": api.sender.last_code(phone)}
    )
    assert again.json()["created"] is False and again.json()["user"]["id"] == body["user"]["id"]


def test_code_is_single_use_and_replaced_by_new_one(api: Api) -> None:
    phone = api.phone()
    api.request_code(phone)
    first = api.sender.last_code(phone)
    api.request_code(phone)
    second = api.sender.last_code(phone)
    if first != second:
        r = api.client.post("/api/v1/auth/login", json={"phone": phone, "code": first})
        assert r.json()["code"] == "otp_invalid"  # eski kod bekor qilingan
    assert (
        api.client.post("/api/v1/auth/login", json={"phone": phone, "code": second}).status_code
        == 200
    )
    r = api.client.post("/api/v1/auth/login", json={"phone": phone, "code": second})
    assert r.status_code == 400 and r.json()["code"] == "otp_expired"


def test_wrong_code_five_times_blocks_for_15_minutes(api: Api) -> None:
    """M1 qabul mezoni: OTP 5 marta noto'g'ri → 15 daqiqa blok (to'g'ri kod ham, yangi kod ham)."""
    phone = api.phone()
    api.request_code(phone)
    good = api.sender.last_code(phone)
    bad = "000000" if good != "000000" else "111111"
    codes = [
        api.client.post("/api/v1/auth/login", json={"phone": phone, "code": bad}).json()["code"]
        for _ in range(5)
    ]
    assert codes == ["otp_invalid"] * 4 + ["otp_blocked"]
    r = api.client.post("/api/v1/auth/login", json={"phone": phone, "code": good})
    assert r.status_code == 429 and r.json()["code"] == "otp_blocked"
    assert api.request_code(phone).json()["code"] == "otp_blocked"
    # 15 daqiqa o'tdi.
    api.admin(
        "UPDATE otp_codes SET updated_at = now() - interval '16 minutes' WHERE phone = %s", [phone]
    )
    assert (
        api.client.post("/api/v1/auth/login", json={"phone": phone, "code": good}).status_code
        == 200
    )


def test_expired_code(api: Api) -> None:
    phone = api.phone()
    api.request_code(phone)
    api.admin(
        "UPDATE otp_codes SET expires_at = now() - interval '1 second' WHERE phone = %s", [phone]
    )
    r = api.client.post(
        "/api/v1/auth/login", json={"phone": phone, "code": api.sender.last_code(phone)}
    )
    assert r.status_code == 400 and r.json()["code"] == "otp_expired"


def test_code_rate_limit_per_phone(api: Api) -> None:
    phone = api.phone()
    assert [api.request_code(phone).status_code for _ in range(5)] == [202] * 5
    r = api.request_code(phone)
    assert r.status_code == 429 and r.json()["code"] == "otp_rate_limited"
    assert api.request_code(api.phone()).status_code == 202  # boshqa raqam — alohida


@pytest.mark.parametrize("phone", ["12", "+998 90 12", "0901234567", "abc"])
def test_invalid_phone(api: Api, phone: str) -> None:
    r = api.request_code(phone)
    assert r.status_code == 422


def test_login_validation(api: Api) -> None:
    r = api.client.post("/api/v1/auth/login", json={"phone": api.phone(), "code": "12ab56"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    r = api.client.post("/api/v1/auth/login", json={"phone": api.phone(), "code": "123456"})
    assert r.json()["code"] == "otp_expired"  # kod so'ralmagan


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (DeliveryError("PHONE_NUMBER_NOT_FOUND", not_on_telegram=True), 400, "telegram_not_found"),
        (DeliveryError("gateway_unavailable"), 502, "otp_delivery_failed"),
    ],
)
def test_delivery_errors(
    api: Api, monkeypatch: pytest.MonkeyPatch, exc: DeliveryError, status: int, code: str
) -> None:
    async def fail(phone: str, code: str, ttl: int) -> None:
        raise exc

    monkeypatch.setattr(api.sender, "send", fail)
    r = api.request_code(api.phone())
    assert r.status_code == status and r.json()["code"] == code


# --- Sessiyalar ----------------------------------------------------------------------------------


def test_unauthenticated(api: Api) -> None:
    assert api.client.get("/api/v1/auth/me").json()["code"] == "unauthenticated"
    api.use("soxta-token")
    assert api.client.get("/api/v1/auth/me").status_code == 401
    assert api.client.get("/api/v1/orgs").status_code == 401


def test_devices_list_and_logout(api: Api) -> None:
    phone = api.phone()
    phone_token = api.login(phone, ua="iPhone")
    laptop = api.login(phone, ua="Mac")
    tablet = api.login(phone, ua="iPad")
    api.use(laptop)
    sessions = api.client.get("/api/v1/auth/sessions").json()
    assert sorted(s["device"] for s in sessions) == ["Mac", "iPad", "iPhone"]
    assert [s["device"] for s in sessions if s["current"]] == ["Mac"]
    ipad = next(s["id"] for s in sessions if s["device"] == "iPad")
    assert api.client.delete(f"/api/v1/auth/sessions/{ipad}").status_code == 204
    assert api.client.delete(f"/api/v1/auth/sessions/{ipad}").status_code == 404
    api.use(tablet)
    assert api.client.get("/api/v1/auth/me").status_code == 401
    api.use(laptop)
    assert api.client.post("/api/v1/auth/sessions/revoke-others").json() == {"revoked": 1}
    api.use(phone_token)
    assert api.client.get("/api/v1/auth/me").status_code == 401
    api.use(laptop)
    r = api.client.post("/api/v1/auth/logout")
    assert r.status_code == 204 and 'up_session=""' in r.headers["set-cookie"]
    api.use(laptop)
    assert api.client.get("/api/v1/auth/me").status_code == 401


def test_cannot_revoke_other_users_session(api: Api) -> None:
    victim = api.login()
    api.use(victim)
    victim_session = api.client.get("/api/v1/auth/sessions").json()[0]["id"]
    api.use(api.login())
    assert api.client.delete(f"/api/v1/auth/sessions/{victim_session}").status_code == 404
    api.use(victim)
    assert api.client.get("/api/v1/auth/me").status_code == 200


def test_session_rotation_with_grace(api: Api) -> None:
    phone = api.phone()
    old = api.login(phone)
    api.admin(
        "UPDATE sessions SET updated_at = now() - interval '25 hours' WHERE token_hash = sha256(%s::bytea)",
        [old.encode()],
    )
    api.use(old)
    r = api.client.get("/api/v1/auth/me")
    assert r.status_code == 200
    new = r.cookies[COOKIE]
    assert new != old
    api.use(old)  # parallel so'rov eski token bilan — qisqa muddat ishlaydi, yana yangilanmaydi
    r = api.client.get("/api/v1/auth/me")
    assert r.status_code == 200 and COOKIE not in r.cookies
    api.admin(
        "UPDATE sessions SET prev_valid_until = now() - interval '1 second' WHERE token_hash = sha256(%s::bytea)",
        [new.encode()],
    )
    assert api.client.get("/api/v1/auth/me").status_code == 401
    api.use(new)
    assert api.client.get("/api/v1/auth/me").status_code == 200


def test_expired_session(api: Api) -> None:
    token = api.login()
    api.admin(
        "UPDATE sessions SET expires_at = now() WHERE token_hash = sha256(%s::bytea)",
        [token.encode()],
    )
    api.use(token)
    assert api.client.get("/api/v1/auth/me").status_code == 401


def test_profile_update(api: Api) -> None:
    api.use(api.login())
    r = api.client.patch("/api/v1/auth/me", json={"name": "Temur", "language": "ru"})
    assert r.status_code == 200 and r.json()["name"] == "Temur" and r.json()["language"] == "ru"
    me = api.client.get("/api/v1/auth/me").json()["user"]
    assert (me["name"], me["language"]) == ("Temur", "ru")
    assert api.client.patch("/api/v1/auth/me", json={}).status_code == 200
    # Telefon — kirish identifikatori, API orqali o'zgarmaydi (ortiqcha maydon e'tiborsiz).
    phone = api.client.get("/api/v1/auth/me").json()["user"]["phone"]
    api.client.patch("/api/v1/auth/me", json={"phone": "+998900000000"})
    assert api.client.get("/api/v1/auth/me").json()["user"]["phone"] == phone


# --- Tashkilot, xodimlar, takliflar --------------------------------------------------------------


def _invite(api: Api, org: str, phone: str, role: str) -> str:
    r = api.client.post(f"/api/v1/orgs/{org}/invites", json={"phone": phone, "role": role})
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.startswith("http://localhost:5173/invite/")
    return str(url.rsplit("/", 1)[1])


def test_create_org_and_isolation(api: Api) -> None:
    owner = api.login()
    api.use(owner)
    org = api.org("byDurii")
    body = api.client.get(f"/api/v1/orgs/{org}").json()
    assert (
        body["role"] == "owner"
        and body["name"] == "byDurii"
        and "delete_org" in body["permissions"]
    )
    assert [o["id"] for o in api.client.get("/api/v1/orgs").json()] == [org]
    r = api.client.patch(f"/api/v1/orgs/{org}", json={"name": "byDurii 2", "inn": "123456789"})
    assert r.status_code == 200 and r.json()["inn"] == "123456789"
    assert api.client.patch(f"/api/v1/orgs/{org}", json={}).status_code == 200
    # Boshqa foydalanuvchi: tashkilot borligi ham bilinmaydi.
    api.use(api.login())
    for path in (f"/api/v1/orgs/{org}", f"/api/v1/orgs/{org}/members", f"/api/v1/orgs/{org}/audit"):
        r = api.client.get(path)
        assert r.status_code == 404 and r.json()["code"] == "org_not_found"
    assert api.client.patch(f"/api/v1/orgs/{org}", json={"name": "x"}).status_code == 404
    assert api.client.get("/api/v1/orgs/00000000-0000-0000-0000-000000000000").status_code == 404
    api.use(owner)
    actions = [a["action"] for a in api.client.get(f"/api/v1/orgs/{org}/audit").json()]
    assert sorted(actions) == ["org.create", "org.update"]


def test_invite_flow_and_roles(api: Api) -> None:
    owner = api.login()
    api.use(owner)
    org = api.org()
    phone = api.phone()
    token = _invite(api, org, phone, "accountant")
    assert [i["phone"] for i in api.client.get(f"/api/v1/orgs/{org}/invites").json()] == [phone]
    accountant = api.login(phone)
    api.use(accountant)
    r = api.client.post("/api/v1/invites/accept", json={"token": token})
    assert r.status_code == 200 and r.json()["role"] == "accountant"
    assert "manage_members" not in r.json()["permissions"]
    assert (
        api.client.post("/api/v1/invites/accept", json={"token": token}).json()["code"]
        == "invite_used"
    )
    # Buxgalter: ko'radi, xodimlarni boshqara olmaydi, sozlamani o'zgartira olmaydi.
    assert api.client.get(f"/api/v1/orgs/{org}").status_code == 200
    assert api.client.get(f"/api/v1/orgs/{org}/test-finance").status_code == 200
    for method, path, body in (
        ("get", f"/api/v1/orgs/{org}/members", None),
        ("post", f"/api/v1/orgs/{org}/invites", {"phone": api.phone(), "role": "owner"}),
        ("patch", f"/api/v1/orgs/{org}", {"name": "x"}),
        ("get", f"/api/v1/orgs/{org}/audit", None),
    ):
        r = api.client.request(method, path, json=body)
        assert r.status_code == 403 and r.json()["code"] == "forbidden", path
    api.use(owner)
    members = api.client.get(f"/api/v1/orgs/{org}/members").json()
    assert sorted(mb["role"] for mb in members) == ["accountant", "owner"]
    accountant_id = next(mb["user_id"] for mb in members if mb["role"] == "accountant")
    # Omborchi: foyda summasini API orqali ham ololmaydi (M1 qabul mezoni).
    r = api.client.patch(f"/api/v1/orgs/{org}/members/{accountant_id}", json={"role": "warehouse"})
    assert r.status_code == 200 and r.json()["role"] == "warehouse"
    api.use(accountant)
    r = api.client.get(f"/api/v1/orgs/{org}/test-finance")
    assert r.status_code == 403 and r.json()["detail"] == "view_finance"
    api.use(owner)
    assert api.client.delete(f"/api/v1/orgs/{org}/members/{accountant_id}").status_code == 204
    assert api.client.delete(f"/api/v1/orgs/{org}/members/{accountant_id}").status_code == 404
    api.use(accountant)
    assert api.client.get(f"/api/v1/orgs/{org}").status_code == 404
    api.use(owner)
    actions = {a["action"] for a in api.client.get(f"/api/v1/orgs/{org}/audit").json()}
    assert {"invite.create", "member.join", "member.role", "member.remove"} <= actions


def test_last_owner_is_protected(api: Api) -> None:
    owner = api.login()
    api.use(owner)
    org = api.org()
    me = api.client.get("/api/v1/auth/me").json()["user"]["id"]
    assert (
        api.client.patch(f"/api/v1/orgs/{org}/members/{me}", json={"role": "manager"}).json()[
            "code"
        ]
        == "last_owner"
    )
    assert api.client.delete(f"/api/v1/orgs/{org}/members/{me}").json()["code"] == "last_owner"
    phone = api.phone()
    token = _invite(api, org, phone, "owner")
    api.use(api.login(phone))
    api.client.post("/api/v1/invites/accept", json={"token": token})
    api.use(owner)
    r = api.client.patch(f"/api/v1/orgs/{org}/members/{me}", json={"role": "manager"})
    assert r.status_code == 200  # endi boshqa egasi bor


def test_invite_rules(api: Api) -> None:
    owner = api.login()
    api.use(owner)
    org = api.org()
    phone = api.phone()
    token = _invite(api, org, phone, "manager")
    # Boshqa raqamli foydalanuvchi havolani ishlata olmaydi.
    api.use(api.login())
    r = api.client.post("/api/v1/invites/accept", json={"token": token})
    assert r.status_code == 403 and r.json()["code"] == "invite_phone_mismatch"
    assert (
        api.client.post("/api/v1/invites/accept", json={"token": "x" * 43}).json()["code"]
        == "invite_not_found"
    )
    # Muddati o'tgan.
    api.admin(
        "UPDATE invites SET expires_at = now() - interval '1 second' WHERE phone = %s", [phone]
    )
    api.use(api.login(phone))
    r = api.client.post("/api/v1/invites/accept", json={"token": token})
    assert r.status_code == 410 and r.json()["code"] == "invite_expired"
    # Bekor qilingan taklif.
    api.use(owner)
    token2 = _invite(api, org, phone, "manager")
    invite_id = api.client.get(f"/api/v1/orgs/{org}/invites").json()[0]["id"]
    assert api.client.delete(f"/api/v1/orgs/{org}/invites/{invite_id}").status_code == 204
    assert api.client.delete(f"/api/v1/orgs/{org}/invites/{invite_id}").status_code == 404
    api.use(api.login(phone))
    assert api.client.post("/api/v1/invites/accept", json={"token": token2}).status_code == 404
    api.use(owner)
    r = api.client.post(f"/api/v1/orgs/{org}/invites", json={"phone": "1234567", "role": "manager"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_phone"


def test_invite_for_existing_member_is_idempotent(api: Api) -> None:
    owner = api.login()
    api.use(owner)
    org = api.org()
    phone = api.phone()
    first, second = _invite(api, org, phone, "manager"), _invite(api, org, phone, "accountant")
    api.use(api.login(phone))
    assert (
        api.client.post("/api/v1/invites/accept", json={"token": first}).json()["role"] == "manager"
    )
    r = api.client.post("/api/v1/invites/accept", json={"token": second})
    assert r.status_code == 200
    assert api.client.get(f"/api/v1/orgs/{org}").json()["role"] == "manager"  # rol o'zgarmaydi


def test_commit_happens_before_response(api: Api) -> None:
    """Tranzaksiya javobdan oldin commit bo'ladi: commit xatosi mijozga 200 bo'lib bormaydi."""
    api.use(api.login())
    org = api.org()
    r = api.client.post(f"/api/v1/orgs/{org}/test-commit-fails")
    assert r.status_code == 500 and r.json()["code"] == "internal"


# --- CSRF ----------------------------------------------------------------------------------------


def test_csrf(api: Api) -> None:
    body = {"phone": api.phone()}
    r = api.client.post("/api/v1/auth/otp", json=body, headers={"X-Requested-With": ""})
    assert (
        r.status_code == 403 and r.json()["code"] == "csrf_header" and "X-Request-ID" in r.headers
    )
    r = api.client.post("/api/v1/auth/otp", json=body, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_origin"
    r = api.client.post("/api/v1/auth/otp", json=body, headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 202
    assert api.client.get("/api/v1/health", headers={"X-Requested-With": ""}).status_code == 200

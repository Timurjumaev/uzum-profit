"""ADR-072: dev-token — faqat staging'da, faqat o'qish, xeshlangan, muddatli, bekor qilinadi."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from uuid import UUID

import dbtools
import psycopg
import pytest
from mptools import MpApi, mp_api, settings_for
from psycopg import errors
from upapi import devtokens
from upapi.auth.tokens import token_hash
from upapi.settings import Environment, Settings


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def api(urls: dict[str, str]) -> Iterator[MpApi]:
    with mp_api(urls, dev_tokens_enabled=True) as a:
        yield a


def enabled(urls: dict[str, str], **extra: object) -> Settings:
    return settings_for(urls, dev_tokens_enabled=True, **extra)


def mint(urls: dict[str, str], phone: str, days: int = 30, label: str = "claude") -> str:
    out = io.StringIO()
    asyncio.run(devtokens.create(enabled(urls), phone, label, days, out))
    return out.getvalue().strip()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user(api: MpApi) -> tuple[str, str]:
    """Kirgan foydalanuvchi va uning tashkiloti; so'ng cookie tozalanadi (dev-token yolg'iz o'zi sinaladi)."""
    phone = api.login()
    org = api.org()
    api.client.cookies.clear()
    return phone, org


def test_read_only_access(api: MpApi, urls: dict[str, str], user: tuple[str, str]) -> None:
    phone, org = user
    token = mint(urls, phone)
    assert token.startswith("dvt_")
    me = api.client.get("/api/v1/auth/me", headers=bearer(token))
    assert me.status_code == 200, me.text
    assert me.json()["user"]["phone"] == phone
    assert [o["id"] for o in me.json()["orgs"]] == [org]
    assert [o["id"] for o in api.client.get("/api/v1/orgs", headers=bearer(token)).json()] == [org]
    assert api.client.get(f"/api/v1/orgs/{org}", headers=bearer(token)).status_code == 200
    assert api.client.get(f"/api/v1/orgs/{org}/shops", headers=bearer(token)).status_code == 200


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
def test_writes_are_forbidden(
    api: MpApi, urls: dict[str, str], user: tuple[str, str], method: str
) -> None:
    phone, org = user
    token = mint(urls, phone)
    before = api.admin("SELECT count(*) FROM orgs")
    other = "00000000-0000-0000-0000-000000000001"
    paths = {
        "post": ["/api/v1/orgs", "/api/v1/auth/logout", f"/api/v1/orgs/{org}/sync/refresh"],
        "patch": ["/api/v1/auth/me", f"/api/v1/orgs/{org}"],
        "put": [f"/api/v1/orgs/{org}/accounts/{other}/token"],
        "delete": [f"/api/v1/orgs/{org}/members/{other}", f"/api/v1/auth/sessions/{other}"],
    }[method]
    for path in paths:
        r = api.client.request(method.upper(), path, headers=bearer(token), json={"name": "x"})
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["code"] == "dev_token_read_only"
    assert api.admin("SELECT count(*) FROM orgs") == before
    assert api.admin("SELECT count(*) FROM orgs WHERE deleted_at IS NOT NULL") == [(0,)]


def test_wrong_flag_or_token_is_unauthenticated(
    api: MpApi, urls: dict[str, str], user: tuple[str, str]
) -> None:
    phone, _ = user
    token = mint(urls, phone)
    assert api.client.get("/api/v1/auth/me", headers=bearer(token + "x")).status_code == 401
    assert api.client.get("/api/v1/auth/me", headers=bearer("")).status_code == 401
    # Bayroq o'chiq (standart / production): yaroqli token ham ishlamaydi.
    with mp_api(urls) as off:
        assert off.client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_token_is_not_a_session_cookie(
    api: MpApi, urls: dict[str, str], user: tuple[str, str]
) -> None:
    """Dev-token cookie sifatida yuborilsa to'liq sessiya bo'lib qolmaydi (alohida jadval)."""
    phone, _ = user
    token = mint(urls, phone)
    api.client.cookies.set("up_session", token)
    try:
        assert api.client.get("/api/v1/auth/me").status_code == 401
        assert api.client.post("/api/v1/orgs", json={"name": "x"}).status_code == 401
    finally:
        api.client.cookies.clear()


def test_expired_and_revoked(api: MpApi, urls: dict[str, str], user: tuple[str, str]) -> None:
    phone, _ = user
    expired, revoked = mint(urls, phone), mint(urls, phone)
    api.admin(
        "UPDATE dev_tokens SET expires_at = now() - interval '1 second' WHERE token_hash = %s",
        [token_hash(expired)],
    )
    assert api.client.get("/api/v1/auth/me", headers=bearer(expired)).status_code == 401
    assert api.client.get("/api/v1/auth/me", headers=bearer(revoked)).status_code == 200
    token_id = api.admin("SELECT id FROM dev_tokens WHERE token_hash = %s", [token_hash(revoked)])
    out = io.StringIO()
    asyncio.run(devtokens.revoke(enabled(urls), UUID(str(token_id[0][0])), out))
    assert out.getvalue().strip() == "Bekor qilindi: 1"
    assert api.client.get("/api/v1/auth/me", headers=bearer(revoked)).status_code == 401


def test_revoke_all_and_list(api: MpApi, urls: dict[str, str], user: tuple[str, str]) -> None:
    phone, _ = user
    token = mint(urls, phone, label="ro'yxat sinovi")
    out = io.StringIO()
    asyncio.run(devtokens.list_tokens(enabled(urls), out))
    assert "ro'yxat sinovi" in out.getvalue()
    assert token not in out.getvalue()  # ro'yxatda sir va xesh yo'q
    asyncio.run(devtokens.revoke(enabled(urls), None, io.StringIO()))
    assert api.client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    out = io.StringIO()
    asyncio.run(devtokens.list_tokens(enabled(urls), out))
    assert "bekor" in out.getvalue()


def test_only_hash_is_stored_and_last_used_updates(
    api: MpApi, urls: dict[str, str], user: tuple[str, str]
) -> None:
    phone, _ = user
    token = mint(urls, phone)
    rows = api.admin(
        "SELECT token_hash, last_used_at FROM dev_tokens WHERE token_hash = %s", [token_hash(token)]
    )
    assert rows[0][0] == token_hash(token) and rows[0][1] is None
    assert token.encode() not in bytes(rows[0][0])
    api.client.get("/api/v1/auth/me", headers=bearer(token))
    used = api.admin(
        "SELECT last_used_at FROM dev_tokens WHERE token_hash = %s", [token_hash(token)]
    )
    assert used[0][0] is not None


def test_app_role_cannot_touch_table(urls: dict[str, str]) -> None:
    with psycopg.connect(urls["app"]) as conn:
        for sql in (
            "SELECT * FROM dev_tokens",
            "INSERT INTO dev_tokens (user_id, token_hash, label, expires_at) "
            "VALUES (gen_random_uuid(), '\\x00', 'x', now())",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute(sql)
            conn.rollback()


def test_create_validation(urls: dict[str, str], api: MpApi) -> None:
    def create(**kw: object) -> None:
        settings = kw.pop("settings", enabled(urls))
        args = {"phone": api.phone(), "label": "claude", "days": 30, **kw}
        asyncio.run(
            devtokens.create(settings, args["phone"], args["label"], args["days"], io.StringIO())
        )  # type: ignore[arg-type]

    with pytest.raises(devtokens.DevTokenError, match="foydalanuvchi yo'q"):
        create()  # bunday foydalanuvchi yo'q — yangisi yaratilmaydi
    with pytest.raises(devtokens.DevTokenError, match="muddat"):
        create(days=0)
    with pytest.raises(devtokens.DevTokenError, match="muddat"):
        create(days=91)
    with pytest.raises(devtokens.DevTokenError, match="label"):
        create(label="  ")
    with pytest.raises(devtokens.DevTokenError, match="telefon"):
        create(phone="123")
    with pytest.raises(devtokens.DevTokenError, match="yoqilmagan"):
        create(settings=settings_for(urls))
    with pytest.raises(devtokens.DevTokenError, match="production"):
        create(settings=enabled(urls, env=Environment.PROD))


def test_production_refuses_to_start_with_dev_tokens() -> None:
    assert not any("DEV_TOKENS" in p for p in Settings(env=Environment.STAGING).problems())
    prod = Settings(env=Environment.PROD, dev_tokens_enabled=True)
    assert any("UP_DEV_TOKENS_ENABLED" in p for p in prod.problems())
    assert Settings().dev_tokens_enabled is False  # standart — o'chiq

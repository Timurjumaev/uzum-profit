"""B2.3 xavfsizlik: auth_* funksiyalari, ilova roli chegaralari, ishga tushish tekshiruvi, Telegram Gateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import dbtools
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import errors
from upapi.auth import tokens
from upapi.auth.permissions import MATRIX, Permission, Role, allowed
from upapi.auth.senders import DeliveryError, MemorySender, TelegramGatewaySender, build_sender
from upapi.db.guard import role_problems
from upapi.db.session import make_engine
from upapi.main import UnsafeConfiguration, create_app
from upapi.settings import Environment, OtpSender, Settings

FUNCTIONS = [
    "auth_otp_issue",
    "auth_login",
    "auth_session",
    "auth_session_rotate",
    "auth_sessions",
    "auth_session_revoke",
    "auth_user_orgs",
    "auth_invite_accept",
]


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


# --- Telefon, kod, token --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("+998 90 123-45-67", "+998901234567"),
        ("998901234567", "+998901234567"),
        ("90 123 45 67", "+998901234567"),
        ("+7 912 345 67 89", "+79123456789"),
    ],
)
def test_normalize_phone(raw: str, phone: str) -> None:
    assert tokens.normalize_phone(raw) == phone


@pytest.mark.parametrize("raw", ["", "12345", "+998 90 123 45", "+0123456789", "+1234567890123456"])
def test_normalize_phone_rejects(raw: str) -> None:
    with pytest.raises(tokens.InvalidPhone):
        tokens.normalize_phone(raw)


def test_codes_and_hashes() -> None:
    code = tokens.new_code()
    assert len(code) == 6 and code.isdigit()
    h = tokens.code_hash("s" * 32, "+998901234567", code)
    assert h != tokens.code_hash("t" * 32, "+998901234567", code)  # sir bilan
    assert h != tokens.code_hash("s" * 32, "+998901234568", code)  # raqamga bog'langan
    assert len(tokens.new_token()) >= 43 and tokens.new_token() != tokens.new_token()
    assert tokens.mask_phone("+998901234567") == "+99890*****67"


def test_permission_matrix() -> None:
    """03 §10 jadvali."""
    assert MATRIX[Role.OWNER] == frozenset(Permission)
    for role in (Role.MANAGER, Role.ACCOUNTANT, Role.WAREHOUSE):
        for p in (
            Permission.MANAGE_ACCOUNTS,
            Permission.MANAGE_MEMBERS,
            Permission.MANAGE_BILLING,
            Permission.DELETE_ORG,
        ):
            assert not allowed(role, p), (role, p)
    assert allowed(Role.MANAGER, Permission.MANAGE_SETTINGS)
    assert not allowed(Role.ACCOUNTANT, Permission.MANAGE_SETTINGS) and allowed(
        Role.ACCOUNTANT, Permission.EXPORT
    )
    warehouse = MATRIX[Role.WAREHOUSE]
    assert (
        Permission.VIEW_FINANCE not in warehouse
        and Permission.VIEW_PURCHASE_AMOUNTS not in warehouse
    )
    assert {Permission.MANAGE_PURCHASES, Permission.EXPORT_INVENTORY} <= warehouse
    assert Permission.EXPORT not in warehouse and Permission.VIEW_SETTINGS not in warehouse


# --- DB: ilova roli chegaralari -------------------------------------------------------------------


def test_auth_functions_are_locked_down(urls: dict[str, str]) -> None:
    with psycopg.connect(urls["admin"]) as conn:
        rows = conn.execute(
            "SELECT p.proname, p.prosecdef, pg_get_userbyid(p.proowner), p.proconfig, "
            "has_function_privilege('public', p.oid, 'EXECUTE'), "
            "has_function_privilege(%s, p.oid, 'EXECUTE') "
            "FROM pg_proc p WHERE p.proname LIKE 'auth\\_%%'",
            [dbtools.APP_ROLE],
        ).fetchall()
    assert sorted(r[0] for r in rows) == sorted(FUNCTIONS)
    for name, definer, owner, config, public, app in rows:
        assert definer and owner == dbtools.AUTH_ROLE, name
        assert config == ["search_path=pg_catalog, public"], name
        assert not public and app, name


def test_app_role_cannot_become_auth_role(urls: dict[str, str]) -> None:
    with psycopg.connect(urls["app"]) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute(f"SET ROLE {dbtools.AUTH_ROLE}")


@pytest.mark.parametrize("table", ["sessions", "otp_codes"])
def test_app_role_cannot_touch_auth_tables(urls: dict[str, str], table: str) -> None:
    for sql in (f"SELECT * FROM {table}", f"DELETE FROM {table}", f"UPDATE {table} SET id = id"):
        with psycopg.connect(urls["app"]) as conn, pytest.raises(errors.InsufficientPrivilege):
            conn.execute(sql)


def test_functions_need_a_secret(urls: dict[str, str]) -> None:
    """Token/kodsiz hech narsa: soxta token bilan sessiya, tashkilotlar, bekor qilish — bo'sh."""
    fake = tokens.token_hash("soxta")
    with psycopg.connect(urls["app"]) as conn:
        assert conn.execute("SELECT * FROM auth_session(%s)", [fake]).fetchall() == []
        assert conn.execute("SELECT * FROM auth_sessions(%s)", [fake]).fetchall() == []
        assert conn.execute("SELECT * FROM auth_user_orgs(%s)", [fake]).fetchall() == []
        assert conn.execute(
            "SELECT auth_session_revoke(%s, 'others', NULL)", [fake]
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT auth_session_rotate(%s, %s, 60, 60)", [fake, fake]
        ).fetchone() == (False,)
        status = conn.execute(
            "SELECT status FROM auth_invite_accept(%s, %s)", [fake, fake]
        ).fetchone()
        assert status == ("unauthenticated",)


def test_user_phone_is_not_updatable(urls: dict[str, str]) -> None:
    with psycopg.connect(urls["admin"]) as conn:
        user = conn.execute(
            "INSERT INTO users (phone) VALUES ('+998911111111') RETURNING id"
        ).fetchone()[0]
    with psycopg.connect(urls["app"]) as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", [str(user)])
        conn.execute("UPDATE users SET name = 'ok' WHERE id = %s", [user])
        for column, value in (
            ("phone", "+998922222222"),
            ("telegram_user_id", 1),
            ("last_login_at", None),
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute(f"UPDATE users SET {column} = %s WHERE id = %s", [value, user])
            conn.rollback()
            conn.execute("SELECT set_config('app.user_id', %s, true)", [str(user)])
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("INSERT INTO users (phone) VALUES ('+998933333333')")


# --- Ishga tushish tekshiruvi (B2.10 chiqish mezoni) -----------------------------------------------


def _problems(url: str) -> list[str]:
    async def run() -> list[str]:
        engine = make_engine(url)
        try:
            return await role_problems(engine)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_role_problems(urls: dict[str, str]) -> None:
    assert _problems(urls["app"]) == []
    admin = _problems(urls["admin"])
    assert any("superuser" in p for p in admin) and any("BYPASSRLS" in p for p in admin)
    owner = _problems(urls["owner"])
    assert any("jadval egasi" in p for p in owner) and any(dbtools.AUTH_ROLE in p for p in owner)


def test_role_membership_is_flagged(urls: dict[str, str]) -> None:
    with psycopg.connect(dbtools.plain(dbtools.ADMIN_URL or ""), autocommit=True) as conn:
        conn.execute("DROP ROLE IF EXISTS up_app_member")
        conn.execute("CREATE ROLE up_app_member LOGIN PASSWORD 'x' NOSUPERUSER NOBYPASSRLS")
        conn.execute(f"GRANT {dbtools.APP_ROLE} TO up_app_member")
    try:
        url = dbtools.with_db(urls["admin"], urls["admin"].rsplit("/", 1)[1], "up_app_member", "x")
        assert any("boshqa rollar a'zosi" in p and dbtools.APP_ROLE in p for p in _problems(url))
    finally:
        with psycopg.connect(dbtools.plain(dbtools.ADMIN_URL or ""), autocommit=True) as conn:
            conn.execute("DROP ROLE up_app_member")


def test_guard_cli(urls: dict[str, str], capsys: pytest.CaptureFixture[str]) -> None:
    from upapi.db import guard

    assert guard.main(["guard", urls["app"]]) == 0 and "xavfsiz" in capsys.readouterr().out
    assert guard.main(["guard", urls["admin"]]) == 1 and "superuser" in capsys.readouterr().err


def _strict(url: str, **extra: Any) -> Settings:
    values: dict[str, Any] = {
        "env": Environment.STAGING,
        "log_json": True,
        "database_url": url,
        "otp_sender": OtpSender.TELEGRAM_GATEWAY,
        "otp_secret": "x" * 40,
        "telegram_gateway_token": "t",
        "allowed_origins": ["https://staging.example.uz"],
    }
    return Settings(**{**values, **extra})


@pytest.mark.parametrize("role", ["admin", "owner"])
def test_staging_refuses_privileged_db_role(urls: dict[str, str], role: str) -> None:
    app = create_app(_strict(urls[role]), sender=MemorySender())
    with pytest.raises(UnsafeConfiguration), TestClient(app):
        pass


def test_staging_starts_with_app_role(urls: dict[str, str]) -> None:
    app = create_app(_strict(urls["app"]), sender=MemorySender())
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_staging_refuses_unreachable_db() -> None:
    app = create_app(_strict("postgresql://up_app:x@127.0.0.1:1/yoq"), sender=MemorySender())
    with pytest.raises(UnsafeConfiguration, match="tekshirib bo'lmadi"), TestClient(app):
        pass


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"otp_secret": "dev-only-otp-secret"}, "UP_OTP_SECRET"),
        ({"otp_sender": OtpSender.CONSOLE}, "console"),
        ({"telegram_gateway_token": None}, "UP_TELEGRAM_GATEWAY_TOKEN"),
        ({"cookie_secure": False}, "UP_COOKIE_SECURE"),
        ({"allowed_origins": ["http://staging.example.uz"]}, "https://"),
    ],
)
def test_staging_refuses_unsafe_settings(extra: dict[str, Any], message: str) -> None:
    app = create_app(_strict("postgresql://up_app@localhost/x", **extra), sender=MemorySender())
    with pytest.raises(UnsafeConfiguration, match=message), TestClient(app):
        pass


def test_dev_warns_about_privileged_role(
    urls: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(env=Environment.DEV, log_json=True, database_url=urls["admin"])
    with TestClient(create_app(settings, sender=MemorySender())) as client:
        assert client.get("/health").status_code == 200
    events = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    warning = next(e for e in events if e["event"] == "db_role_unsafe")
    assert warning["level"] == "warning" and any("superuser" in p for p in warning["problems"])


def test_dev_warns_when_db_is_down(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(
        env=Environment.DEV, log_json=True, database_url="postgresql://x:y@127.0.0.1:1/z"
    )
    with TestClient(create_app(settings, sender=MemorySender())) as client:
        assert client.get("/health").status_code == 200
    assert '"db_role_check_failed"' in capsys.readouterr().out


# --- Telegram Gateway -----------------------------------------------------------------------------


def _gateway(handler: Any) -> TelegramGatewaySender:
    client = httpx.AsyncClient(
        base_url="https://gatewayapi.telegram.org", transport=httpx.MockTransport(handler)
    )
    return TelegramGatewaySender("tok", client)


def test_gateway_sends_our_code(capsys: pytest.CaptureFixture[str]) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"ok": True, "result": {"request_id": "r1", "request_cost": 0.01}}
        )

    sender = _gateway(handler)

    async def run() -> None:
        await sender.send("+998901234567", "123456", 300)
        await sender.aclose()

    asyncio.run(run())
    (request,) = seen
    assert request.url.path == "/sendVerificationMessage"
    assert request.headers["Authorization"] == "Bearer tok"
    assert json.loads(request.content) == {
        "phone_number": "+998901234567",
        "code": "123456",
        "ttl": 300,
    }
    out = capsys.readouterr().out
    assert "123456" not in out and "tok" not in out and "+998901234567" not in out


@pytest.mark.parametrize(
    ("response", "reason", "not_on_telegram"),
    [
        (
            httpx.Response(400, json={"ok": False, "error": "PHONE_NUMBER_NOT_FOUND"}),
            "PHONE_NUMBER_NOT_FOUND",
            True,
        ),
        (
            httpx.Response(200, json={"ok": False, "error": "BALANCE_NOT_ENOUGH"}),
            "BALANCE_NOT_ENOUGH",
            False,
        ),
        (httpx.Response(502, json=[1]), "bad_response", False),
        (httpx.Response(500, json={"ok": False}), "http_500", False),
        (httpx.Response(502, text="<html>"), "gateway_unavailable", False),
    ],
)
def test_gateway_errors(response: httpx.Response, reason: str, not_on_telegram: bool) -> None:
    sender = _gateway(lambda request: response)
    with pytest.raises(DeliveryError) as exc:
        asyncio.run(sender.send("+998901234567", "123456", 300))
    assert exc.value.reason == reason and exc.value.not_on_telegram is not_on_telegram


def test_gateway_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("yo'q")

    with pytest.raises(DeliveryError, match="gateway_unavailable"):
        asyncio.run(_gateway(handler).send("+998901234567", "123456", 300))


def test_build_sender(capsys: pytest.CaptureFixture[str]) -> None:
    dev = build_sender(Settings(env=Environment.DEV))
    assert isinstance(dev, MemorySender) and dev.echo
    asyncio.run(dev.send("+998901234567", "654321", 300))
    assert "654321" in capsys.readouterr().err  # dev: terminalga (logga emas)
    assert not build_sender(Settings(env=Environment.TEST)).echo  # type: ignore[attr-defined]
    gateway = build_sender(
        Settings(otp_sender=OtpSender.TELEGRAM_GATEWAY, telegram_gateway_token="t")
    )
    assert isinstance(gateway, TelegramGatewaySender)
    asyncio.run(gateway.aclose())
    with pytest.raises(RuntimeError):
        build_sender(Settings(otp_sender=OtpSender.TELEGRAM_GATEWAY))

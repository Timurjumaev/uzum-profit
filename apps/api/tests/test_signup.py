"""B8.11 ro'yxatdan o'tishni cheklash (haqiqiy PostgreSQL): yopiq rejimda yangi raqam faqat ruxsat ro'yxati yoki taklif bilan;
mavjud foydalanuvchi doim kiradi; CLI ruxsat/ro'yxat/o'chirish."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator

import dbtools
import pytest
from fastapi.testclient import TestClient
from test_auth import CSRF, Api, _settings
from upapi import signup
from upapi.auth.senders import MemorySender
from upapi.main import create_app


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def api(urls: dict[str, str]) -> Iterator[Api]:
    sender = MemorySender()
    app = create_app(_settings(urls, signup_open=False), sender=sender)
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as client:
        yield Api(client, sender, urls)


def _cli(urls: dict[str, str], action: str, *args: str) -> str:
    out = io.StringIO()
    settings = _settings(urls)
    if action == "allow":
        asyncio.run(signup.allow(settings, list(args), out))
    elif action == "list":
        asyncio.run(signup.list_allowed(settings, out))
    else:
        asyncio.run(signup.remove(settings, args[0], out))
    return out.getvalue()


def test_closed_signup_blocks_unknown_phone(api: Api) -> None:
    phone = api.phone()
    r = api.request_code(phone)
    assert r.status_code == 403 and r.json()["code"] == "signup_closed"
    assert all(p != phone for p, _ in api.sender.outbox)


def test_allowlist_cli_lets_phone_in_and_keeps_existing_users(
    api: Api, urls: dict[str, str]
) -> None:
    phone = api.phone()
    assert api.request_code(phone).status_code == 403
    assert "1 ta" in _cli(urls, "allow", phone)
    assert phone in _cli(urls, "list")
    api.login(phone)  # ruxsat berilgan — kirdi
    assert _cli(urls, "remove", phone) == "O'chirildi\n"
    # Foydalanuvchi allaqachon bor — ro'yxatdan chiqarilsa ham kiraveradi
    api.client.cookies.clear()
    assert api.request_code(phone).status_code == 202
    assert _cli(urls, "remove", phone) == "Ro'yxatda yo'q edi\n"
    with pytest.raises(signup.SignupError):
        _cli(urls, "allow", "123")


def test_invite_allows_new_phone(api: Api, urls: dict[str, str]) -> None:
    owner = api.phone()
    _cli(urls, "allow", owner)
    api.login(owner)
    org = api.org()
    invited = api.phone()
    assert api.request_code(invited).status_code == 403
    r = api.client.post(f"/api/v1/orgs/{org}/invites", json={"phone": invited, "role": "manager"})
    assert r.status_code == 201, r.text
    api.client.cookies.clear()
    assert api.request_code(invited).status_code == 202

"""B8.4a (09 X2): foydalanuvchi bo'yicha so'rov cheklovi — chegaradan oshsa 429 ``rate_limited``; boshqa foydalanuvchiga
ta'sir qilmaydi; kirish (login) cheklanmaydi."""

from __future__ import annotations

from collections.abc import Iterator

import dbtools
import pytest
from fastapi.testclient import TestClient
from test_auth import CSRF, Api, _settings
from upapi.auth.senders import MemorySender
from upapi.main import create_app


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def api(urls: dict[str, str]) -> Iterator[Api]:
    app = create_app(_settings(urls, user_requests_per_minute=5), sender=MemorySender())
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as client:
        yield Api(client, MemorySender(), urls)


def test_user_is_limited_but_others_are_not(api: Api) -> None:
    api.client.app.state.sender = api.sender  # type: ignore[attr-defined]
    first, second = api.phone(), api.phone()
    api.login(first)
    codes = [api.client.get("/api/v1/auth/me").status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and set(codes[5:]) == {429}
    body = api.client.get("/api/v1/auth/me").json()
    assert body["code"] == "rate_limited"
    api.client.cookies.clear()
    api.login(second)  # boshqa foydalanuvchi — o'z hisobi
    assert api.client.get("/api/v1/auth/me").status_code == 200

"""B8.4a: tashkilotlarni ajratish — endpointlarning 100% ida (ro'yxat ilovaning marshrutlaridan avtomatik olinadi, qo'lda
yuritilmaydi — yangi endpoint testsiz o'tmaydi). Har ``/orgs/{org_id}/...`` marshrutga: (1) kirmagan foydalanuvchi — 401;
(2) boshqa tashkilot a'zosi, A tashkilotining manzilida — 404 ``org_not_found`` (borligi ham bilinmaydi); yozuvchi usullarda
ham. Istisno (``EXEMPT``) faqat sababi bilan."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator

import dbtools
import pytest
from fastapi.testclient import TestClient
from test_auth import CSRF, Api, _settings
from upapi.auth.senders import MemorySender
from upapi.main import create_app

# (usul, yo'l) → nega tashkilot a'zoligi tekshiruvidan oldin boshqa javob beradi. Hozircha bo'sh bo'lishi kerak.
EXEMPT: dict[tuple[str, str], str] = {}
# Tanasi tekshiruvdan o'tishi kerak bo'lgan marshrutlar (aks holda 422 a'zolikdan oldin keladi). Yangi marshrut shu ro'yxatsiz
# ham tekshiriladi: tana tekshiruvi a'zolikdan oldin bo'lsa, bu yerga qo'shiladi.
BODIES: dict[tuple[str, str], dict[str, str]] = {
    ("POST", "/api/v1/orgs/{org_id}/accounts"): {"token": "k" * 40},
    ("PUT", "/api/v1/orgs/{org_id}/accounts/{account_id}/token"): {"token": "k" * 40},
}


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def world(urls: dict[str, str]) -> Iterator[tuple[Api, str, str, str]]:
    sender = MemorySender()
    app = create_app(_settings(urls, user_requests_per_minute=100_000), sender=sender)
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as client:
        api = Api(client, sender, urls)
        owner = api.login()
        org = api.org()
        stranger = api.login()
        yield api, org, owner, stranger


def org_routes() -> list[tuple[str, str]]:
    """OpenAPI sxemasidan (``/api/v1`` prefiksisiz) — ilovaning haqiqiy marshrutlari."""
    app = create_app(_settings({"app": "postgresql://x/x"}), sender=MemorySender())
    out = []
    for path, item in app.openapi()["paths"].items():
        if "{org_id}" in path:
            out += [(method.upper(), path) for method in item if method != "parameters"]
    return sorted(out)


ROUTES = org_routes()


def fill(path: str, org: str) -> str:
    path = path.replace("{org_id}", org)
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


def test_routes_are_discovered() -> None:
    assert (
        len(ROUTES) > 100
    )  # ro'yxat bo'sh qolmasin (marshrutlar topilmasa test jim o'tib ketmasin)


@pytest.mark.parametrize(("method", "path"), ROUTES, ids=[f"{m} {p}" for m, p in ROUTES])
def test_endpoint_is_isolated(world: tuple[Api, str, str, str], method: str, path: str) -> None:
    api, org, _, stranger = world
    url = fill(path, org)
    kwargs = (
        {"json": BODIES.get((method, path), {})}
        if method in ("POST", "PUT", "PATCH", "DELETE")
        else {}
    )
    api.client.cookies.clear()
    r = api.client.request(method, url, **kwargs)
    assert r.status_code == 401, (r.status_code, r.text[:200])
    api.use(stranger)
    r = api.client.request(method, url, **kwargs)
    if (method, path) in EXEMPT:
        pytest.skip(EXEMPT[(method, path)])
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert r.json().get("code") == "org_not_found", r.text[:200]


def test_owner_is_not_blocked(world: tuple[Api, str, str, str]) -> None:
    """Nazorat: egasi o'z tashkilotida 404 ``org_not_found`` olmaydi (aks holda yuqoridagi test hamma narsada o'tib ketardi)."""
    api, org, owner, _ = world
    api.use(owner)
    r = api.client.get(f"/api/v1/orgs/{org}/members")
    assert r.status_code == 200, r.text

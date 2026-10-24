"""B2.4 testlari uchun: soxta Uzum (``httpx.MockTransport``) va kirgan foydalanuvchi bilan API mijozi.

Haqiqiy Uzum'ga chiqilmaydi (sandbox va CI'da imkonsiz); real tekshiruv — B2.11 da staging'da.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg
from fastapi.testclient import TestClient
from upapi.auth.senders import MemorySender
from upapi.main import create_app
from upapi.settings import Environment, Settings

CSRF = {"X-Requested-With": "test"}
BASE = "https://uzum.test/api/seller-openapi"

# Uzum'ning yozib olingan javob shakllari (08 §8): JSON 401, WAF HTML 403, 429, 5xx.
MODES: dict[str, tuple[int, dict[str, str], bytes]] = {
    "auth": (401, {"content-type": "application/json"}, b'{"error":"Unauthorized"}'),
    "token_not_found": (
        404,
        {"content-type": "application/json"},
        b'{"message":"Token not found"}',
    ),
    "waf": (403, {"content-type": "text/html"}, b"<html><body>Access denied</body></html>"),
    "burst": (429, {"x-ratelimit-remaining-per-day": "500"}, b'{"error":"Too Many Requests"}'),
    "quota": (429, {"x-ratelimit-remaining-per-day": "0"}, b'{"error":"Too Many Requests"}'),
    "5xx": (502, {"content-type": "text/plain"}, b"Bad gateway"),
    "bad_request": (400, {"content-type": "application/json"}, b'{"error":"bad"}'),
    "teapot": (418, {}, b""),
    "html200": (200, {"content-type": "text/html"}, b"<html></html>"),
    "bad_shape": (200, {"content-type": "application/json"}, b'{"payload": {"id": 1}}'),
    "bad_shop": (200, {"content-type": "application/json"}, b'[{"name": "id yo\'q"}]'),
}


@dataclass
class FakeUzum:
    """Kalit → do'konlar. ``mode`` — keyingi javoblar shu xato bilan; ``"network"``/``"crash"`` — transport xatosi."""

    keys: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    mode: str | None = None
    quota: int = 99_000
    payload_wrapped: bool = False
    seen: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        auth = request.headers.get("authorization", "")
        if self.mode == "network":
            raise httpx.ConnectError(f"ulanib bo'lmadi: {auth}", request=request)
        if self.mode == "crash":
            # Sarlavhani xato matniga qo'shadigan "yomon" kutubxona — kalit baribir chiqmasligi kerak.
            raise RuntimeError(f"transport buzildi, sarlavha: Authorization={auth}")
        if self.mode:
            status, headers, body = MODES[self.mode]
            return httpx.Response(status, headers=headers, content=body)
        headers = {"x-ratelimit-remaining-per-day": str(self.quota)}
        if request.url.path != "/api/seller-openapi/v1/shops":
            return httpx.Response(404, headers=headers, json={"error": "not found"})
        if auth not in self.keys:
            return httpx.Response(401, headers=headers, json={"error": "Unauthorized"})
        shops = self.keys[auth]
        return httpx.Response(
            200, headers=headers, json={"payload": shops} if self.payload_wrapped else shops
        )

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def new_token() -> str:
    return f"uzk-{random.getrandbits(160):040x}"


def shop(ext: int, name: str | None = None) -> dict[str, Any]:
    return {"id": ext, "name": name or f"Do'kon {ext}"}


@dataclass
class MpApi:
    client: TestClient
    sender: MemorySender
    uzum: FakeUzum
    urls: dict[str, str]

    def phone(self) -> str:
        return f"+99891{random.randint(0, 9_999_999):07d}"

    def login(self, phone: str | None = None) -> str:
        phone = phone or self.phone()
        self.client.cookies.clear()
        assert self.client.post("/api/v1/auth/otp", json={"phone": phone}).status_code == 202
        r = self.client.post(
            "/api/v1/auth/login", json={"phone": phone, "code": self.sender.last_code(phone)}
        )
        assert r.status_code == 200, r.text
        return phone

    def org(self) -> str:
        r = self.client.post("/api/v1/orgs", json={"name": "Do'kon"})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    def owner_org(self) -> str:
        self.login()
        return self.org()

    def connect(self, org: str, token: str) -> httpx.Response:
        return self.client.post(f"/api/v1/orgs/{org}/accounts", json={"token": token})

    def admin(self, sql: str, params: list[Any] | None = None) -> Any:
        with psycopg.connect(self.urls["admin"]) as conn:
            cur = conn.execute(sql, params or [])
            return cur.fetchall() if cur.description else cur.rowcount


def settings_for(urls: dict[str, str], **extra: Any) -> Settings:
    values: dict[str, Any] = {
        "env": Environment.TEST,
        "log_json": True,
        "database_url": urls["app"],
        "uzum_base_url": BASE,
    }
    return Settings(**{**values, **extra})


@contextmanager
def mp_api(urls: dict[str, str], **extra: Any) -> Iterator[MpApi]:
    sender, uzum = MemorySender(), FakeUzum()
    app = create_app(settings_for(urls, **extra), sender=sender, uzum_transport=uzum.transport)
    with TestClient(app, headers=CSRF, raise_server_exceptions=False) as client:
        yield MpApi(client, sender, uzum, urls)


def log_lines(out: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]

"""B8.14 ochiq sozlamalar: yordam havolasi kirishsiz ochiq; berilmasa ``null``; http:// xavfli sozlama sifatida rad etiladi."""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_auth import CSRF, _settings
from upapi.auth.senders import MemorySender
from upapi.main import create_app


def client(**extra: str) -> TestClient:
    app = create_app(_settings({"app": "postgresql://x/x"}, **extra), sender=MemorySender())
    return TestClient(app, headers=CSRF)


def test_config_is_public_and_null_by_default() -> None:
    r = client().get("/api/v1/config")
    assert r.status_code == 200 and r.json() == {"support_url": None}


def test_config_returns_support_url() -> None:
    r = client(support_url="https://t.me/sellermax_help").get("/api/v1/config")
    assert r.json() == {"support_url": "https://t.me/sellermax_help"}


def test_insecure_support_url_is_a_problem() -> None:
    settings = _settings({"app": "postgresql://x/x"}, support_url="http://t.me/x")
    assert any("UP_SUPPORT_URL" in p for p in settings.problems())
    assert not any("UP_SUPPORT_URL" in p for p in _settings({"app": "postgresql://x/x"}).problems())

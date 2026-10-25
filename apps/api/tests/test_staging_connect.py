"""B2.11: ``scripts/staging_connect.py`` — haqiqiy API ilovasi (soxta Uzum va Telegram) bilan: kirish, tashkilot,
kalitni ulash, saqlangan sessiya, xatolar, sinxron holati; kalit hech qayerga yozilmaydi va chiqmaydi."""

from __future__ import annotations

import importlib.util
import json
import stat
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from mptools import MpApi, mp_api, new_token, shop

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "staging_connect", ROOT / "scripts" / "staging_connect.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sc = _load()


@pytest.fixture(scope="module")
def api(db: dict[str, str]) -> Iterator[MpApi]:
    with mp_api(db) as a:
        yield a


def transport(client: TestClient) -> Callable[..., tuple[int, list[str], Any]]:
    """Skript transporti → TestClient (cookie faqat skript yuborgani; mijozning o'z cookie'lari tozalanadi)."""

    def send(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Any:
        client.cookies.clear()
        r = client.request(method, urlsplit(url).path, headers=headers, content=body)
        return r.status_code, r.headers.get_list("set-cookie"), r.json() if r.content else None

    return send


class Io:
    """Javoblar navbati: qator yoki funksiya (masalan, oxirgi yuborilgan kod)."""

    def __init__(self, answers: list[Any], token: str | None = None) -> None:
        self.answers, self.token, self.out = list(answers), token, []
        self.secret_calls = 0

    def ask(self, prompt: str) -> str:
        self.out.append(prompt)
        answer = self.answers.pop(0)
        return answer() if callable(answer) else answer

    def secret(self, prompt: str) -> str:
        self.secret_calls += 1
        self.out.append(prompt)
        assert self.token is not None
        return self.token

    def say(self, text: str) -> None:
        self.out.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self.out)


def run(api: MpApi, session: Path, io: Io, *argv: str, **extra: Any) -> int:
    return sc.main(
        [*argv, "--url", "http://testserver", "--session", str(session)],
        transport(api.client),
        ask=io.ask,
        secret=io.secret,
        say=io.say,
        **extra,
    )


def test_connect_flow_and_saved_session(api: MpApi, tmp_path: Path) -> None:
    phone, token, session = api.phone(), new_token(), tmp_path / "s" / "session.json"
    api.uzum.keys[token] = [shop(106121, "byDurii"), shop(135204, "EL-ONE")]
    io = Io([phone, lambda: api.sender.last_code(phone), "Temur"], token)
    assert run(api, session, io) == 0, io.text
    text = io.text
    assert "Kod Telegram'ga yuborildi (5 daqiqa" in text
    assert "Tashkilot yaratildi: Temur" in text
    assert f"✓ Kalit ulandi (…{token[-4:]})" in text
    assert "  - byDurii (106121)" in text and "  - EL-ONE (135204)" in text
    assert "byDurii: tarix=yuklanmoqda" in text
    assert token not in text
    # Sessiya: faqat egasi o'qiydi, kalit yo'q; tarix navbatga qo'yildi.
    assert stat.S_IMODE(session.stat().st_mode) == 0o600
    assert stat.S_IMODE(session.parent.stat().st_mode) == 0o700
    saved = json.loads(session.read_text())
    assert saved["url"] == "http://testserver" and saved["cookie"]
    assert token not in session.read_text()
    assert any(j["task_name"] == "sync.account" for j in api.queued)

    # Qayta ishga tushirish: kod so'ralmaydi, kalit qayta so'ralmaydi.
    again = Io([], token)
    assert run(api, session, again) == 0, again.text
    assert f"Kalit allaqachon ulangan (…{token[-4:]}): byDurii, EL-ONE" in again.text
    assert again.secret_calls == 0

    # status --watch: tarix to'liq bo'lguncha kutadi.
    def finish(_: float) -> None:
        api.admin("UPDATE shops SET history_status = 'full' WHERE external_id IN (106121, 135204)")

    watch = Io([])
    assert run(api, session, watch, "status", "--watch", sleep=finish) == 0
    assert watch.text.count("soniyadan keyin yana") == 1
    assert "byDurii: tarix=full" in watch.text


def test_wrong_code_then_invalid_key(api: MpApi, tmp_path: Path) -> None:
    phone, session = api.phone(), tmp_path / "session.json"
    io = Io([phone, "000000", lambda: api.sender.last_code(phone), ""], "yaroqsiz-kalit-123")
    assert run(api, session, io) == 1
    assert "Kod noto'g'ri." in io.text
    assert "Tashkilot yaratildi: Mening do'konlarim" in io.text
    assert "✗ Uzum kalitni qabul qilmadi" in io.text and "yaroqsiz-kalit-123" not in io.text


def test_invalid_account_is_replaced(api: MpApi, tmp_path: Path) -> None:
    """Yaroqsiz deb belgilangan kalit — yangisi bilan almashtiriladi (PUT), yangi akkaunt ochilmaydi."""
    phone, old, new, session = api.phone(), new_token(), new_token(), tmp_path / "session.json"
    ext = 700_000 + int(new[-5:], 16) % 99_999
    api.uzum.keys[old] = api.uzum.keys[new] = [shop(ext)]
    assert run(api, session, Io([phone, lambda: api.sender.last_code(phone), "X"], old)) == 0
    api.admin("UPDATE mp_accounts SET status = 'invalid' WHERE token_last4 = %s", [old[-4:]])
    io = Io([], new)
    assert run(api, session, io) == 0, io.text
    assert f"✓ Kalit ulandi (…{new[-4:]})" in io.text
    rows = api.admin(
        "SELECT count(*) FROM mp_accounts a JOIN shops s ON s.account_id = a.id WHERE s.external_id = %s",
        [ext],
    )
    assert rows == [(1,)]


def test_expired_session_and_org_choice(api: MpApi, tmp_path: Path) -> None:
    phone, session = api.phone(), tmp_path / "session.json"
    api.login(phone)
    for name in ("Birinchi", "Ikkinchi"):
        assert api.client.post("/api/v1/orgs", json={"name": name}).status_code == 201
    api.client.cookies.clear()
    sc.save_session(session, "http://testserver", "eskirgan-cookie")
    token = new_token()
    api.uzum.keys[token] = [shop(800_000 + int(token[-5:], 16) % 99_999, "Uchinchi do'kon")]
    io = Io([phone, lambda: api.sender.last_code(phone), "2"], token)
    assert run(api, session, io) == 0, io.text
    assert "  1. Birinchi" in io.text and "  2. Ikkinchi" in io.text
    assert "\nIkkinchi: " in io.text and "Uchinchi do'kon" in io.text


def test_status_without_shops_and_errors(api: MpApi, tmp_path: Path) -> None:
    phone, session = api.phone(), tmp_path / "session.json"
    api.login(phone)
    assert api.client.post("/api/v1/orgs", json={"name": "Bo'sh"}).status_code == 201
    api.client.cookies.clear()
    io = Io([phone, lambda: api.sender.last_code(phone)])
    assert run(api, session, io, "status") == 0
    assert "Do'kon yo'q — avval kalitni ulang" in io.text
    bad = Io(["123"])
    assert run(api, tmp_path / "other.json", bad, "status") == 1
    assert "✗ Kiritilgan qiymat formati noto'g'ri" in bad.text


def test_urllib_transport(tmp_path: Path) -> None:
    """Haqiqiy HTTP: sarlavhalar (CSRF, cookie) yuboriladi, ``Set-Cookie`` o'qiladi, 4xx — ``ApiError``."""
    seen: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append(dict(self.headers))
            ok = self.path == "/api/v1/auth/login"
            body = json.dumps({"ok": True} if ok else {"code": "otp_invalid"}).encode()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            if ok:
                self.send_header("Set-Cookie", "up_session=yangi; HttpOnly; Path=/")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = sc.Api(f"http://127.0.0.1:{server.server_port}", cookie="eski")
        assert client.call("POST", "/auth/login", {"a": 1}) == {"ok": True}
        assert client.cookie == "yangi"
        with pytest.raises(sc.ApiError) as err:
            client.call("POST", "/auth/otp", {})
        assert err.value.status == 400 and err.value.message == "Kod noto'g'ri."
    finally:
        server.shutdown()
    assert seen[0]["X-Requested-With"] == "staging-connect"
    assert seen[0]["Cookie"] == "up_session=eski" and seen[1]["Cookie"] == "up_session=yangi"


def test_unreachable_server(tmp_path: Path) -> None:
    out: list[str] = []
    code = sc.main(
        ["status", "--url", "http://127.0.0.1:9", "--session", str(tmp_path / "s.json")],
        ask=lambda _: "+998901234567",
        say=out.append,
    )
    assert code == 1 and "Serverga ulanib bo'lmadi" in out[-1]

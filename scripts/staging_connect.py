#!/usr/bin/env python3
"""B2.11: staging'ga kirish va Uzum kalitini ulash (veb-interfeys B3 da; ungacha shu skript). Faqat standart
kutubxona (Python 3.12+; Temurning Mac'ida python3 3.15), hech narsa o'rnatish shart emas.

    python3 scripts/staging_connect.py            # kirish (Telegram kodi) → tashkilot → kalit → sinxron holati
    python3 scripts/staging_connect.py status     # sinxron holati (do'konlar, tarix, xatolar)
    python3 scripts/staging_connect.py status --watch   # tarix to'liq yuklanguncha har daqiqada

Kalit faqat yashirin so'raladi (``getpass`` — ekranda va shell tarixida ko'rinmaydi), HTTPS orqali API'ga ketadi va
serverda shifrlanadi (B2.4); skript uni hech qayerga yozmaydi. Sessiya cookie'si ``~/.uzum-profit/staging-session.json``
da (faqat egasi o'qiydi, 30 kun) — qayta ishga tushirganda kod qayta so'ralmaydi.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

if sys.version_info < (3, 12):  # noqa: UP036 - eski Python'da tushunarli xabar uchun
    sys.exit("Python 3.12 yoki yangisi kerak (Mac'da: python3 --version).")

DEFAULT_URL = "https://16-170-178-179.sslip.io"
SESSION = Path.home() / ".uzum-profit" / "staging-session.json"
COOKIE = "up_session"
PREFIX = "/api/v1"
WATCH_SECONDS = 60

# (status, headers, javob) ← (method, url, sarlavhalar, tana)
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, list[str], Any]]

MESSAGES = {
    "invalid_phone": "Telefon raqami noto'g'ri — +998XXXXXXXXX ko'rinishida yozing.",
    "telegram_not_found": "Bu raqam Telegram'da ro'yxatdan o'tmagan — kod yuborib bo'lmadi.",
    "otp_delivery_failed": "Kod Telegram'ga yuborilmadi — birozdan keyin qayta urining.",
    "otp_rate_limited": "Juda ko'p kod so'raldi — bir soatdan keyin urining.",
    "otp_ip_rate_limited": "Bu tarmoqdan juda ko'p kod so'raldi — bir soatdan keyin urining.",
    "otp_blocked": "Ko'p xato kod — 15 daqiqa kuting.",
    "otp_invalid": "Kod noto'g'ri.",
    "otp_expired": "Kod eskirgan — skriptni qayta ishga tushiring.",
    "mp_token_invalid": "Uzum kalitni qabul qilmadi — seller kabinetidan kalitni qayta nusxalang.",
    "mp_verify_limited": "Juda ko'p yaroqsiz kalit urinishi — bir soatdan keyin.",
    "mp_shops_already_connected": "Bu do'konlar boshqa akkauntda allaqachon ulangan.",
    "mp_waf_blocked": "Uzum serverimiz so'rovini to'sdi (WAF) — Claude'ga xabar bering.",
    "mp_quota_exhausted": "Uzum kunlik so'rovlar limiti tugagan — ertaga qayta urining.",
    "mp_rate_limited": "Uzum band — bir daqiqadan keyin qayta urining.",
    "mp_unavailable": "Uzum javob bermadi — birozdan keyin qayta urining.",
    "validation_error": "Kiritilgan qiymat formati noto'g'ri (telefon raqami yoki kalitni tekshiring).",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str | None, detail: str | None) -> None:
        super().__init__(f"{status} {code or ''}")
        self.status, self.code, self.detail = status, code, detail

    @property
    def message(self) -> str:
        return MESSAGES.get(
            self.code or "", self.detail or f"Server xatosi ({self.status}, {self.code or '—'})."
        )


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> tuple[int, list[str], Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            status, cookies, raw = (
                resp.status,
                resp.headers.get_all("Set-Cookie") or [],
                resp.read(),
            )
    except urllib.error.HTTPError as exc:
        status, cookies, raw = exc.code, exc.headers.get_all("Set-Cookie") or [], exc.read()
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    return status, cookies, data


class Api:
    def __init__(
        self, url: str, transport: Transport = urllib_transport, cookie: str | None = None
    ) -> None:
        self.url, self.transport, self.cookie = url.rstrip("/"), transport, cookie

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "staging-connect",  # CSRF (03 §10)
            "User-Agent": "uzum-profit staging_connect.py",
        }
        if self.cookie:
            headers["Cookie"] = f"{COOKIE}={self.cookie}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        status, cookies, payload = self.transport(method, self.url + PREFIX + path, headers, data)
        for header in cookies:  # kirishda va sessiya yangilanganda (har 24 soatda) — yangi token
            name, _, rest = header.partition("=")
            if name.strip() == COOKIE:
                self.cookie = rest.split(";", 1)[0] or None
        if status >= 400:
            payload = payload if isinstance(payload, dict) else {}
            raise ApiError(status, payload.get("code"), payload.get("detail"))
        return payload


# --- Sessiya -------------------------------------------------------------------------------------


def load_session(path: Path, url: str) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("cookie") if data.get("url") == url else None


def save_session(path: Path, url: str, cookie: str | None) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"url": url, "cookie": cookie}, fh)
    path.chmod(0o600)


class Cli:
    """Interaktiv qadamlar; ``ask``/``secret``/``say``/``sleep`` — testlarda almashtiriladi."""

    def __init__(
        self,
        api: Api,
        session: Path,
        ask: Callable[[str], str] = input,
        secret: Callable[[str], str] = getpass.getpass,
        say: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api, self.session = api, session
        self.ask, self.secret, self.say, self.sleep = ask, secret, say, sleep

    def save(self) -> None:
        save_session(self.session, self.api.url, self.api.cookie)

    def me(self) -> dict[str, Any]:
        """Saqlangan sessiya ishlasa — o'sha; aks holda telefon + Telegram kodi."""
        if self.api.cookie:
            try:
                me = self.api.call("GET", "/auth/me")
                self.save()
                return me
            except ApiError as exc:
                if exc.status != 401:
                    raise
                self.api.cookie = None
        phone = self.ask("Telefon raqamingiz (+998XXXXXXXXX): ").strip()
        sent = self.api.call("POST", "/auth/otp", {"phone": phone})
        self.say(f"Kod Telegram'ga yuborildi ({sent['expires_in'] // 60} daqiqa amal qiladi).")
        for attempt in range(3):
            code = self.ask("Telegram'dagi 6 xonali kod: ").strip()
            try:
                me = self.api.call("POST", "/auth/login", {"phone": phone, "code": code})
                break
            except ApiError as exc:
                if exc.code != "otp_invalid" or attempt == 2:
                    raise
                self.say(exc.message)
        self.save()
        return me

    def org(self, me: dict[str, Any]) -> dict[str, Any]:
        owned = [o for o in me["orgs"] if o["role"] == "owner"]
        if not owned:
            name = (
                self.ask("Tashkilot nomi (masalan, do'koningiz yoki ismingiz): ").strip()
                or "Mening do'konlarim"
            )
            org = self.api.call("POST", "/orgs", {"name": name})
            self.say(f"Tashkilot yaratildi: {org['name']}")
            return org
        if len(owned) == 1:
            return owned[0]
        for i, o in enumerate(owned, 1):
            self.say(f"  {i}. {o['name']}")
        choice = self.ask(f"Qaysi tashkilot (1–{len(owned)}): ").strip()
        return owned[int(choice) - 1 if choice.isdigit() and 0 < int(choice) <= len(owned) else 0]

    def connect(self) -> int:
        org = self.org(self.me())
        accounts = [
            a
            for a in self.api.call("GET", f"/orgs/{org['id']}/accounts")
            if a["status"] != "disconnected"
        ]
        active = [a for a in accounts if a["status"] == "active"]
        if active:
            for a in active:
                self.say(
                    f"Kalit allaqachon ulangan ({a['key_hint']}): {', '.join(s['name'] for s in a['shops'])}"
                )
            return self.status()
        self.say(
            "Uzum seller kabineti → Sozlamalar → API kalitlar: kalitni nusxalab shu yerga qo'ying."
        )
        token = self.secret("Uzum API kaliti (yozilgani ko'rinmaydi): ").strip()
        if not token:
            self.say("Kalit kiritilmadi.")
            return 1
        if accounts:  # yaroqsiz yoki bloklangan kalit — almashtirish
            path, method = f"/orgs/{org['id']}/accounts/{accounts[0]['id']}/token", "PUT"
        else:
            path, method = f"/orgs/{org['id']}/accounts", "POST"
        account = self.api.call(method, path, {"token": token})
        self.save()
        self.say(f"✓ Kalit ulandi ({account['key_hint']}). Do'konlar:")
        for s in account["shops"]:
            self.say(f"  - {s['name']} ({s['external_id']})")
        self.say("Tarix yuklanishi boshlandi (bir necha daqiqadan bir necha soatgacha).")
        return self.status()

    def status(self, watch: bool = False) -> int:
        me = self.me()
        while True:
            done = True
            for org in me["orgs"]:
                done &= self.show(org)
            if not watch or done:
                return 0
            self.say(f"... {WATCH_SECONDS} soniyadan keyin yana (to'xtatish: Ctrl+C)")
            self.sleep(WATCH_SECONDS)

    def show(self, org: dict[str, Any]) -> bool:
        """Tashkilot sinxron holati; tarix hamma do'konda to'liq va ishlayotgan ish yo'q bo'lsa ``True``."""
        data = self.api.call("GET", f"/orgs/{org['id']}/sync")
        self.save()
        health = "✓ sog'lom" if data["healthy"] else "✗ muammo bor"
        self.say(f"\n{org['name']}: {health}")
        if data["outage"]["active"]:
            self.say(f"  Uzum uzilishi: {data['outage']['since']} dan")
        done = bool(data["shops"])
        for s in data["shops"]:
            running = [k["kind"] for k in s["kinds"] if k["status"] == "running"]
            done &= s["history_status"] == "full" and not running
            self.say(
                f"  {s['name']}: tarix={s['history_status'] or 'yuklanmoqda'}, birinchi sotuv={s['first_sale_on'] or '—'}, "
                f"24 soatda xato={s['errors_24h']}{', hozir: ' + ', '.join(running) if running else ''}"
            )
            for k in s["kinds"]:
                if k["status"] in ("error", "warning"):
                    self.say(
                        f"    {k['kind']}: {k['status']} — {k['error'] or k['http_status'] or '—'}"
                    )
        if not data["shops"]:
            self.say("  Do'kon yo'q — avval kalitni ulang: python3 scripts/staging_connect.py")
        return done


def main(argv: list[str] | None = None, transport: Transport = urllib_transport, **io: Any) -> int:
    ap = argparse.ArgumentParser(description="Staging'ga kirish va Uzum kalitini ulash (B2.11)")
    ap.add_argument("command", nargs="?", choices=["connect", "status"], default="connect")
    ap.add_argument(
        "--watch", action="store_true", help="status: tarix to'liq yuklanguncha har daqiqada"
    )
    ap.add_argument("--url", default=os.environ.get("UP_STAGING_URL", DEFAULT_URL))
    ap.add_argument("--session", type=Path, default=SESSION, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    url = args.url.rstrip("/")
    cli = Cli(Api(url, transport, load_session(args.session, url)), args.session, **io)
    try:
        return cli.connect() if args.command == "connect" else cli.status(args.watch)
    except ApiError as exc:
        cli.say(f"✗ {exc.message}")
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        cli.say(f"✗ Serverga ulanib bo'lmadi ({url}): {exc}")
        return 1
    except KeyboardInterrupt:
        cli.say("\nTo'xtatildi.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

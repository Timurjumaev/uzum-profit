"""Uzum kaliti maxfiyligi (03 §10, tamoyil 6; B2.4 qabul sharti): kalit **faqat shifrlangan** holda saqlanadi va
**logga, API javobiga, xato matniga hech qachon** tushmaydi.

Bitta o'ziga xos kalit bilan hamma yo'llar (muvaffaqiyat, har xil Uzum xatolari, transport xatosi — hatto xato
matniga sarlavhani qo'shadigan "yomon" kutubxona, validatsiya, ziddiyat, tekshirish, almashtirish, uzish) o'tiladi,
so'ng quyidagilarning hech birida kalit (yoki uning oxirgi 4 belgisidan boshqa bo'lagi) yo'qligi tekshiriladi:

- har javobning tanasi va sarlavhalari;
- ilova loglari (structlog → stdout, ``DEBUG`` darajasida) va stdlib loglari (httpx, httpcore — ``DEBUG``);
- bazaning **hamma** jadvallari (matn va bayt ko'rinishida, hex ham).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import dbtools
import httpx
import psycopg
import pytest
from mptools import MpApi, mp_api, shop
from pydantic import SecretStr
from upapi.crypto import TokenCipher, account_aad
from upapi.routes.accounts import TokenIn
from upapi.settings import DEV_TOKEN_KEY, Settings
from upapi.uzum.client import UzumClient

# Boshqa hech qayerda uchramaydigan kalit: oxiri "Z9q7" — faqat shu 4 belgi (key_hint) ko'rinishi mumkin.
TOKEN = "SECRET-uzum-" + uuid.uuid4().hex + "-Z9q7"
OTHER = "SECRET-other-" + uuid.uuid4().hex + "-K3w1"


def _fragments(token: str) -> list[str]:
    """Kalitning o'zi va oxirgi 4 belgisiz har qanday 12 belgili bo'lagi (qisman sizish ham ushlanadi)."""
    body = token[:-4]
    return [token, body, *(body[i : i + 12] for i in range(0, len(body) - 12, 6))]


SECRETS = _fragments(TOKEN) + _fragments(OTHER)


def assert_clean(text: str, where: str) -> None:
    for fragment in SECRETS:
        assert fragment not in text, f"kalit bo'lagi {where} ichida: {fragment!r}"


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def api(urls: dict[str, str]) -> Iterator[MpApi]:
    with mp_api(urls, log_level="DEBUG") as a:
        yield a


def test_token_never_leaks(
    api: MpApi, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)  # httpx/httpcore ichki loglari ham
    capsys.readouterr()
    responses: list[httpx.Response] = []

    def call(method: str, path: str, **kwargs: object) -> httpx.Response:
        r = api.client.request(method, path, **kwargs)  # type: ignore[arg-type]
        responses.append(r)
        return r

    api.login()
    org = api.org()
    base = f"/api/v1/orgs/{org}/accounts"

    # 1. Uzum hali bilmaydi (JSON 401) va har xil xatolar — kalit saqlanmaydi, javobda yo'q.
    assert call("POST", base, json={"token": TOKEN}).status_code == 422
    for mode in (
        "waf",
        "burst",
        "quota",
        "5xx",
        "bad_request",
        "html200",
        "bad_shape",
        "network",
        "crash",
    ):
        api.uzum.mode = mode
        r = call("POST", base, json={"token": TOKEN})
        assert r.status_code in (502, 503), (mode, r.status_code)
    api.uzum.mode = None
    # 2. Validatsiya xatolari: kalit ichida bo'sh joy, juda uzun, buzuq JSON.
    assert call("POST", base, json={"token": TOKEN + " " + OTHER}).status_code == 422
    assert call("POST", base, json={"token": TOKEN * 30}).status_code == 422
    assert (
        call(
            "POST",
            base,
            content=f'{{"token": "{TOKEN}"',
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert call("POST", base, json={"token": TOKEN, "extra": OTHER}).status_code == 422
    # Endi Uzum ikkala kalitni taniydi.
    api.uzum.keys[TOKEN] = [shop(42, "byDurii")]
    api.uzum.keys[OTHER] = [shop(43)]
    r = call("POST", base, json={"token": TOKEN})
    assert r.status_code == 201, r.text
    account = r.json()["id"]
    assert r.json()["key_hint"] == "…Z9q7"
    # 3. Ziddiyat, tekshirish (muvaffaqiyat va xato), almashtirish (mos emas), ro'yxatlar, audit.
    assert call("POST", base, json={"token": TOKEN}).status_code == 409
    assert call("POST", f"{base}/{account}/check").status_code == 200
    for mode in ("auth", "crash", "network"):
        api.uzum.mode = mode
        call("POST", f"{base}/{account}/check")
    api.uzum.mode = None
    assert call("PUT", f"{base}/{account}/token", json={"token": OTHER}).status_code == 409
    call("GET", base)
    call("GET", f"/api/v1/orgs/{org}/shops")
    call("GET", f"/api/v1/orgs/{org}/audit")
    call("GET", "/api/v1/openapi.json")

    # Javoblar: tana va sarlavhalar.
    for r in responses:
        assert_clean(r.text, f"{r.request.method} {r.request.url.path} javobi")
        assert_clean(str(dict(r.headers)), f"{r.request.url.path} sarlavhalari")
    # Loglar: ilova (stdout) va stdlib (httpx/httpcore).
    out, err = capsys.readouterr()
    assert '"event": "mp_verify_failed"' in out or '"event":"mp_verify_failed"' in out.replace(
        " ", ""
    )
    assert_clean(out, "stdout loglari")
    assert_clean(err, "stderr")
    assert_clean(caplog.text, "stdlib loglari")
    # Kalit Uzum'ga haqiqatan sarlavhada ketgan (aks holda test hech narsani tekshirmagan bo'lardi).
    assert any(req.headers.get("authorization") == TOKEN for req in api.uzum.seen)

    # Baza: hamma jadvallarda ochiq kalit yo'q (matn, bytea hex), mp_accounts da — faqat shifrlangan.
    with psycopg.connect(api.urls["admin"]) as conn:
        tables = [
            t
            for (t,) in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        ]
        dump = "\n".join(
            row[0]
            for t in tables
            for row in conn.execute(f"SELECT row_to_json(x)::text FROM {t} x").fetchall()
        )
        blob, version = conn.execute(
            "SELECT token_encrypted, key_version FROM mp_accounts WHERE id = %s",
            [uuid.UUID(account)],
        ).fetchone()
    assert_clean(dump, "baza")
    for fragment in SECRETS:
        assert fragment.encode().hex() not in dump, "kalit bazada bayt ko'rinishida"
    blob = bytes(blob)
    assert TOKEN.encode() not in blob
    cipher = api.client.app.state.cipher  # type: ignore[attr-defined]
    aad = account_aad(uuid.UUID(org), uuid.UUID(account))
    assert cipher.decrypt(blob, version, aad).get_secret_value() == TOKEN


def test_disconnect_removes_ciphertext(api: MpApi) -> None:
    api.login()
    org = api.org()
    token = "SECRET-disc-" + uuid.uuid4().hex
    api.uzum.keys[token] = [shop(77)]
    account = api.connect(org, token).json()["id"]
    assert api.client.delete(f"/api/v1/orgs/{org}/accounts/{account}/token").status_code == 204
    rows = api.admin(
        "SELECT token_encrypted, token_last4 FROM mp_accounts WHERE id = %s", [uuid.UUID(account)]
    )
    assert rows == [(None, None)]


def test_secret_containers_hide_value() -> None:
    """Tasodifiy ``print``/``repr``/f-satr ham kalitni chiqarmaydi."""
    body = TokenIn(token=SecretStr(TOKEN))
    client = UzumClient(body.token, base_url="https://uzum.test")
    settings = Settings()
    cipher = TokenCipher.from_settings(settings.token_keys, settings.token_key_version)
    for obj in (body, body.token, client, cipher, settings):
        for text in (repr(obj), str(obj), f"{obj}"):
            assert_clean(text, type(obj).__name__)
            assert DEV_TOKEN_KEY not in text  # shifrlash kaliti ham
    assert TOKEN not in body.model_dump_json()


def test_sync_never_leaks_token(
    urls: dict[str, str], capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """B2.6: sinxron ishlari (muvaffaqiyat va har xil xatolar) — kalit logda, ``sync_runs``/``sync_state``, audit,
    navbat (Procrastinate) va boshqa jadvallarda yo'q."""
    import asyncio

    import sellerfake as sf
    from procrastinate.testing import InMemoryConnector
    from upapi.logs import configure_logging
    from upapi.sync import engine as eng
    from upapi.sync import jobs

    configure_logging("DEBUG", True)
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    token = "SECRET-sync-" + uuid.uuid4().hex + "-Z9q7"
    secrets = _fragments(token)
    fake = sf.seller(token=token)
    clock = sf.Clock()
    account = sf.create_account(urls, sf.settings_for(urls), token, [sf.A])
    with sf.runtime(urls, fake, clock, log_level="DEBUG") as run:
        run(lambda rt: eng.sync_account(rt, account.org_id, account.account_id))
        for mode in (
            "network",
            "crash",
            "5xx",
            "auth",
            "token_not_found",
            "waf",
            "quota",
            "html200",
        ):
            sf.admin(urls, "DELETE FROM provider_health")
            sf.admin(
                urls, "UPDATE mp_accounts SET status = 'active' WHERE id = %s", [account.account_id]
            )
            fake.fail = {"shops": mode, "orders": mode}
            run(
                lambda rt: eng.sync_account(
                    rt, account.org_id, account.account_id, kinds=[eng.Kind.SHOPS, eng.Kind.ORDERS]
                )
            )
    app = jobs.build_app(InMemoryConnector())

    async def queue() -> None:
        async with app.open_async():
            await jobs.defer_account(app, account.org_id, account.account_id, eng.Trigger.USER)

    asyncio.run(queue())
    assert any(r.headers.get("authorization") == token for r in fake.seen)
    out, err = capsys.readouterr()
    for text, where in ((out, "stdout"), (err, "stderr"), (caplog.text, "stdlib loglari")):
        for fragment in secrets:
            assert fragment not in text, f"kalit bo'lagi {where} ichida"
    assert '"sync_run_failed"' in out.replace(" ", "")
    jobs_text = str(list(app.connector.jobs.values()))  # type: ignore[attr-defined]
    with psycopg.connect(urls["admin"]) as conn:
        tables = [
            t
            for (t,) in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        ]
        dump = "\n".join(
            row[0]
            for t in tables
            for row in conn.execute(f"SELECT row_to_json(x)::text FROM {t} x").fetchall()
        )
    assert "sync_runs" in tables and "procrastinate_jobs" in tables
    for fragment in secrets:
        assert fragment not in dump and fragment.encode().hex() not in dump
        assert fragment not in jobs_text

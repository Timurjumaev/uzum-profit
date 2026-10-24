"""B2.4: marketplace kalitini ulash, tekshirish, almashtirish, uzish; do'konlarni tanlash; shifrlash; Uzum xatolari.

Kalit maxfiyligi (log, javob, xato matni, baza) — alohida: ``test_token_secrecy.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import dbtools
import pytest
from fastapi.testclient import TestClient
from mptools import MODES, MpApi, mp_api, new_token, settings_for, shop
from pydantic import SecretStr
from upapi import crypto
from upapi.crypto import CipherError, TokenCipher, account_aad
from upapi.main import UnsafeConfiguration, create_app
from upapi.uzum import client as uz


@pytest.fixture(scope="module")
def urls() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as u:
        yield u


@pytest.fixture(scope="module")
def api(urls: dict[str, str]) -> Iterator[MpApi]:
    with mp_api(urls) as a:
        yield a


@pytest.fixture(autouse=True)
def _reset(api: MpApi) -> None:
    api.client.cookies.clear()
    api.uzum.mode = None
    api.uzum.payload_wrapped = False


def _connected(api: MpApi, *shops: int) -> tuple[str, str, str, dict[str, Any]]:
    """Yangi egasi + tashkilot + ulangan akkaunt: (org, token, account_id, javob)."""
    org = api.owner_org()
    token = new_token()
    api.uzum.keys[token] = [shop(s) for s in shops or (uuid.uuid4().int % 10**6,)]
    r = api.connect(org, token)
    assert r.status_code == 201, r.text
    return org, token, r.json()["id"], r.json()


# --- Shifrlash -----------------------------------------------------------------------------------


def test_cipher_roundtrip_and_aad() -> None:
    cipher = TokenCipher({1: b"k" * 32}, 1)
    org, acc = uuid.uuid4(), uuid.uuid4()
    blob, version = cipher.encrypt(SecretStr("uzum-key-1234"), account_aad(org, acc))
    assert version == 1 and b"uzum-key" not in blob and len(blob) == 12 + 13 + 16
    assert cipher.decrypt(blob, 1, account_aad(org, acc)).get_secret_value() == "uzum-key-1234"
    # Har shifrlash — yangi nonce.
    assert cipher.encrypt(SecretStr("uzum-key-1234"), account_aad(org, acc))[0] != blob
    # Boshqa qator yoki tashkilotga ko'chirilgan shifrmatn ochilmaydi.
    for aad in (account_aad(uuid.uuid4(), acc), account_aad(org, uuid.uuid4())):
        with pytest.raises(CipherError, match="ochilmadi"):
            cipher.decrypt(blob, 1, aad)
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(CipherError):
        cipher.decrypt(tampered, 1, account_aad(org, acc))
    with pytest.raises(CipherError, match="versiyasi 7"):
        cipher.decrypt(blob, 7, account_aad(org, acc))


def test_cipher_rotation() -> None:
    old = TokenCipher({1: b"a" * 32}, 1)
    aad = account_aad(uuid.uuid4(), uuid.uuid4())
    blob, _ = old.encrypt(SecretStr("token-v1"), aad)
    new = TokenCipher({1: b"a" * 32, 2: b"b" * 32}, 2)
    assert new.needs_rotation(1) and not new.needs_rotation(2)
    assert new.decrypt(blob, 1, aad).get_secret_value() == "token-v1"
    blob2, version = new.encrypt(new.decrypt(blob, 1, aad), aad)
    assert version == 2 and new.decrypt(blob2, 2, aad).get_secret_value() == "token-v1"
    with pytest.raises(CipherError):
        new.decrypt(blob2, 1, aad)  # versiya almashtirilsa — boshqa kalit


def test_cipher_config_errors() -> None:
    with pytest.raises(CipherError, match="joriy kalit versiyasi"):
        TokenCipher({1: b"a" * 32}, 2)
    with pytest.raises(CipherError, match="32 bayt"):
        TokenCipher({1: b"short"}, 1)
    with pytest.raises(CipherError, match="base64 emas"):
        TokenCipher.from_settings({1: SecretStr("yo'q!")}, 1)
    with pytest.raises(CipherError, match="UP_TOKEN_KEYS: kalit 32 bayt"):
        TokenCipher.from_settings({1: SecretStr("YWJj")}, 1)
    key = crypto.keygen()
    assert len(crypto.decode_key(key)) == 32
    urlsafe = key.replace("+", "-").replace("/", "_").rstrip("=")
    assert crypto.decode_key(urlsafe) == crypto.decode_key(key)
    assert "versions=[1]" in repr(TokenCipher.from_settings({1: SecretStr(key)}, 1))


def test_keygen_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert crypto.main(["keygen"]) == 0
    assert len(crypto.decode_key(capsys.readouterr().out)) == 32
    assert crypto.main([]) == 2 and "keygen" in capsys.readouterr().err


def test_bad_key_config_stops_startup(urls: dict[str, str]) -> None:
    app = create_app(settings_for(urls, token_keys={1: "yaroqsiz!"}))
    with pytest.raises(UnsafeConfiguration, match="UP_TOKEN_KEYS"), TestClient(app):
        pass


# --- Uzum mijozi ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "error"),
    [
        ("auth", uz.AuthError),
        ("token_not_found", uz.AuthError),
        ("waf", uz.WafBlocked),
        ("burst", uz.BurstLimited),
        ("quota", uz.QuotaExhausted),
        ("5xx", uz.UpstreamError),
        ("bad_request", uz.BadRequest),
        ("teapot", uz.UnexpectedResponse),
        ("html200", uz.UnexpectedResponse),
        ("bad_shape", uz.UnexpectedResponse),
        ("bad_shop", uz.UnexpectedResponse),
        ("network", uz.UpstreamError),
        ("crash", uz.UpstreamError),
    ],
)
def test_client_error_kinds(mode: str, error: type[uz.UzumError]) -> None:
    from mptools import FakeUzum

    fake = FakeUzum(mode=mode)

    async def run() -> None:
        async with uz.UzumClient(
            SecretStr("k" * 20),
            base_url="https://uzum.test/api/seller-openapi",
            transport=fake.transport,
            retry=uz.NO_RETRY,  # qayta urinishlar — test_uzum_client.py
        ) as client:
            await client.shops()

    with pytest.raises(error) as info:
        asyncio.run(run())
    assert type(info.value) is error
    # Zanjir yo'q: transport xatosi (sarlavhalari bilan) traceback'ga tushmaydi.
    assert info.value.__cause__ is None
    assert info.value.__context__ is None or info.value.__suppress_context__
    if mode in MODES:
        assert info.value.status == MODES[mode][0]
    if mode == "quota":
        assert info.value.quota_remaining == 0


def test_client_shops_and_headers() -> None:
    from mptools import FakeUzum

    fake = FakeUzum(
        keys={"k" * 20: [shop(5, "  A  "), {"id": 6, "name": "  "}, shop(5, "A2")]}, quota=777
    )

    async def run() -> tuple[list[uz.UzumShop], int | None]:
        async with uz.UzumClient(
            SecretStr("k" * 20),
            base_url="https://uzum.test/api/seller-openapi/",
            transport=fake.transport,
        ) as client:
            assert "k" * 20 not in repr(client)
            return await client.shops(), client.quota_remaining

    shops, quota = asyncio.run(run())
    assert shops == [uz.UzumShop(5, "A2"), uz.UzumShop(6, "#6")] and quota == 777
    request = fake.seen[0]
    assert request.headers["authorization"] == "k" * 20  # "Bearer"siz (08 §8)
    assert request.headers["accept"] == "application/json"
    assert request.headers["user-agent"].startswith("uzum-profit/")


@pytest.mark.parametrize(
    ("raw", "clean"),
    [("  abc\n", "abc"), ("Bearer abc", "abc"), ("bearer   abc ", "abc"), ("abc", "abc")],
)
def test_normalize_token(raw: str, clean: str) -> None:
    assert uz.normalize_token(raw) == clean


# --- Ulash ---------------------------------------------------------------------------------------


def test_connect_account(api: MpApi) -> None:
    org = api.owner_org()
    token = new_token()
    api.uzum.keys[token] = [shop(106121, "byDurii"), shop(135204, "EL-ONE")]
    api.uzum.payload_wrapped = True
    r = api.connect(org, f"  Bearer {token}\n")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active" and body["provider"] == "uzum"
    assert body["key_hint"] == "…" + token[-4:] and body["quota_remaining"] == 99_000
    assert body["checked_at"] is not None
    assert [(s["external_id"], s["name"], s["active"]) for s in body["shops"]] == [
        (106121, "byDurii", True),
        (135204, "EL-ONE", True),
    ]
    assert api.uzum.seen[-1].headers["authorization"] == token
    # Ro'yxatlar.
    accounts = api.client.get(f"/api/v1/orgs/{org}/accounts").json()
    assert [a["id"] for a in accounts] == [body["id"]]
    assert len(api.client.get(f"/api/v1/orgs/{org}/shops").json()) == 2
    # Audit va mahsulot hodisasi.
    audit = api.client.get(f"/api/v1/orgs/{org}/audit").json()
    connect = next(a for a in audit if a["action"] == "account.connect")
    assert connect["after"] == {
        "provider": "uzum",
        "key_hint": "…" + token[-4:],
        "shops": [106121, 135204],
    }
    events = api.admin("SELECT name, props FROM events WHERE org_id = %s", [uuid.UUID(org)])
    assert events == [("mp_account_connected", {"shops": 2})]


@pytest.mark.parametrize(
    ("mode", "status", "code"),
    [
        ("auth", 422, "mp_token_invalid"),
        ("token_not_found", 422, "mp_token_invalid"),
        ("waf", 503, "mp_waf_blocked"),
        ("burst", 503, "mp_rate_limited"),
        ("quota", 503, "mp_quota_exhausted"),
        ("5xx", 502, "mp_unavailable"),
        ("network", 502, "mp_unavailable"),
        ("bad_request", 502, "mp_unexpected_response"),
        ("html200", 502, "mp_unexpected_response"),
    ],
)
def test_connect_errors_save_nothing(api: MpApi, mode: str, status: int, code: str) -> None:
    org = api.owner_org()
    api.uzum.mode = mode
    r = api.connect(org, new_token())
    assert r.status_code == status and r.json()["code"] == code
    assert r.headers["content-type"] == "application/problem+json"
    assert api.admin("SELECT count(*) FROM mp_accounts WHERE org_id = %s", [uuid.UUID(org)]) == [
        (0,)
    ]


def test_connect_unknown_key_and_no_shops(api: MpApi) -> None:
    org = api.owner_org()
    r = api.connect(org, new_token())  # soxta Uzum bilmaydi → JSON 401
    assert r.status_code == 422 and r.json()["code"] == "mp_token_invalid"
    empty = new_token()
    api.uzum.keys[empty] = []
    r = api.connect(org, empty)
    assert r.status_code == 422 and r.json()["code"] == "mp_no_shops"


@pytest.mark.parametrize("bad", ["short", "a" * 1025, "abc def ghi jkl", "abcdefgh\x00ij", ""])
def test_connect_validates_token_format(api: MpApi, bad: str) -> None:
    org = api.owner_org()
    seen = len(api.uzum.seen)
    r = api.connect(org, bad)
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    assert len(api.uzum.seen) == seen  # Uzum'ga so'rov ketmadi


def test_connect_same_shops_twice_conflicts(api: MpApi) -> None:
    org, _, _, _ = _connected(api, 501, 502)
    other = new_token()
    api.uzum.keys[other] = [shop(502), shop(503)]
    r = api.connect(org, other)
    assert r.status_code == 409 and r.json()["code"] == "mp_shops_already_connected"
    # Boshqa tashkilotda shu do'kon — mumkin (ajratilgan).
    org2 = api.org()
    assert api.connect(org2, other).status_code == 201


def test_failed_attempts_are_limited(urls: dict[str, str]) -> None:
    with mp_api(urls, mp_verify_failures_per_hour=3) as api:
        org = api.owner_org()
        for _ in range(3):
            assert api.connect(org, new_token()).status_code == 422
        seen = len(api.uzum.seen)
        r = api.connect(org, new_token())
        assert r.status_code == 429 and r.json()["code"] == "mp_verify_limited"
        assert len(api.uzum.seen) == seen
        audit = api.client.get(f"/api/v1/orgs/{org}/audit").json()
        failed = [a for a in audit if a["action"] == "account.verify_failed"]
        assert len(failed) == 3 and failed[0]["after"] == {"error_code": "auth"}
        # Vaqtinchalik xatolar (WAF, tarmoq) cheklovga kirmaydi; boshqa tashkilot — alohida hisob.
        assert api.connect(api.org(), new_token()).status_code == 422


# --- Ruxsatlar va ajratish -----------------------------------------------------------------------


def test_only_owner_manages_accounts(api: MpApi) -> None:
    org, token, account, body = _connected(api)
    shop_id = body["shops"][0]["id"]
    owner_cookies = dict(api.client.cookies)
    phone = api.phone()
    invite = api.client.post(
        f"/api/v1/orgs/{org}/invites", json={"phone": phone, "role": "manager"}
    ).json()
    api.login(phone)
    r = api.client.post("/api/v1/invites/accept", json={"token": invite["url"].rsplit("/", 1)[1]})
    assert r.status_code == 200, r.text
    seen = len(api.uzum.seen)
    for method, path, payload in [
        ("GET", "accounts", None),
        ("POST", "accounts", {"token": new_token()}),
        ("POST", f"accounts/{account}/check", None),
        ("PUT", f"accounts/{account}/token", {"token": token}),
        ("DELETE", f"accounts/{account}/token", None),
        ("PATCH", f"shops/{shop_id}", {"active": False}),
    ]:
        r = api.client.request(method, f"/api/v1/orgs/{org}/{path}", json=payload)
        assert r.status_code == 403 and r.json()["detail"] == "manage_accounts", (method, path)
    assert len(api.uzum.seen) == seen  # ruxsatsiz — Uzum'ga so'rov ham yo'q
    # Do'konlar ro'yxati — har a'zo uchun (filtrlar).
    assert len(api.client.get(f"/api/v1/orgs/{org}/shops").json()) == 1
    api.client.cookies.update(owner_cookies)


def test_other_org_sees_nothing(api: MpApi) -> None:
    org, token, account, body = _connected(api)
    api.owner_org()  # boshqa egasi, o'z tashkiloti
    for method, path in [
        ("GET", "accounts"),
        ("POST", f"accounts/{account}/check"),
        ("GET", "shops"),
    ]:
        assert api.client.request(method, f"/api/v1/orgs/{org}/{path}").status_code == 404
    org2 = api.org()
    assert api.client.get(f"/api/v1/orgs/{org2}/accounts").json() == []
    assert api.client.get(f"/api/v1/orgs/{org2}/shops").json() == []
    for method, path, payload in [
        ("POST", f"accounts/{account}/check", None),
        ("PUT", f"accounts/{account}/token", {"token": token}),
        ("DELETE", f"accounts/{account}/token", None),
        ("PATCH", f"shops/{body['shops'][0]['id']}", {"active": False}),
    ]:
        r = api.client.request(method, f"/api/v1/orgs/{org2}/{path}", json=payload)
        assert r.status_code == 404 and r.json()["code"] in ("account_not_found", "shop_not_found")


# --- Tekshirish ----------------------------------------------------------------------------------


def test_check_updates_status_and_shops(api: MpApi) -> None:
    org, token, account, _ = _connected(api, 701)
    check = f"/api/v1/orgs/{org}/accounts/{account}/check"
    # Yangi do'kon qo'shildi, eski nomi o'zgardi; sotuvchi taxallusi saqlanadi.
    shop_id = api.client.get(f"/api/v1/orgs/{org}/shops").json()[0]["id"]
    api.client.patch(f"/api/v1/orgs/{org}/shops/{shop_id}", json={"alias": "Asosiy"})
    api.uzum.keys[token] = [shop(701, "Yangi nom"), shop(702)]
    api.uzum.quota = 1234
    body = api.client.post(check).json()
    assert body["status"] == "active" and body["quota_remaining"] == 1234
    assert [(s["external_id"], s["name"], s["alias"]) for s in body["shops"]] == [
        (701, "Yangi nom", "Asosiy"),
        (702, "Do'kon 702", None),
    ]
    # Kalit Uzum'da bekor qilindi → yaroqsiz; WAF; kvota.
    for mode, status in [("auth", "invalid"), ("waf", "waf_blocked"), ("quota", "quota_exhausted")]:
        api.uzum.mode = mode
        r = api.client.post(check)
        assert r.status_code == 200 and r.json()["status"] == status, mode
    assert api.client.post(check).json()["quota_remaining"] == 0
    # Vaqtinchalik xato holatni o'zgartirmaydi.
    for mode, code in [("burst", "mp_rate_limited"), ("5xx", "mp_unavailable")]:
        api.uzum.mode = mode
        assert api.client.post(check).json()["code"] == code
    api.uzum.mode = None
    assert api.client.post(check).json()["status"] == "active"
    audit = [
        a
        for a in api.client.get(f"/api/v1/orgs/{org}/audit").json()
        if a["action"] == "account.check"
    ]
    assert [a["after"]["status"] for a in reversed(audit)] == [
        "invalid",
        "waf_blocked",
        "quota_exhausted",
        "active",
    ]
    assert audit[-1]["after"]["error_code"] == "auth"
    assert api.client.post(f"/api/v1/orgs/{org}/accounts/{uuid.uuid4()}/check").status_code == 404


def test_check_rotates_old_key_version(urls: dict[str, str]) -> None:
    k1, k2 = crypto.keygen(), crypto.keygen()
    with mp_api(urls, token_keys={1: k1}) as api:
        org, token, account, _ = _connected(api)
        uzum_keys = api.uzum.keys
    assert api.admin("SELECT key_version FROM mp_accounts WHERE id = %s", [uuid.UUID(account)]) == [
        (1,)
    ]
    with mp_api(urls, token_keys={1: k1, 2: k2}, token_key_version=2) as api2:
        api2.uzum.keys.update(uzum_keys)
        api2.client.cookies.update(api.client.cookies)
        r = api2.client.post(f"/api/v1/orgs/{org}/accounts/{account}/check")
        assert r.status_code == 200 and r.json()["status"] == "active"
        assert api2.uzum.seen[-1].headers["authorization"] == token
    ((blob, version),) = api.admin(
        "SELECT token_encrypted, key_version FROM mp_accounts WHERE id = %s", [uuid.UUID(account)]
    )
    assert version == 2
    cipher = TokenCipher.from_settings({2: SecretStr(k2)}, 2)
    aad = account_aad(uuid.UUID(org), uuid.UUID(account))
    assert cipher.decrypt(bytes(blob), 2, aad).get_secret_value() == token
    # Kalit sozlamadan olib tashlansa — qayta kiritish so'raladi (500 emas).
    with mp_api(urls, token_keys={3: crypto.keygen()}, token_key_version=3) as api3:
        api3.client.cookies.update(api.client.cookies)
        r = api3.client.post(f"/api/v1/orgs/{org}/accounts/{account}/check")
        assert r.status_code == 409 and r.json()["code"] == "mp_token_unreadable"


# --- Almashtirish va uzish -----------------------------------------------------------------------


def test_replace_token(api: MpApi) -> None:
    org, old, account, _ = _connected(api, 801, 802)
    path = f"/api/v1/orgs/{org}/accounts/{account}/token"
    # Boshqa sotuvchining kaliti — rad.
    stranger = new_token()
    api.uzum.keys[stranger] = [shop(899)]
    r = api.client.put(path, json={"token": stranger})
    assert r.status_code == 409 and r.json()["code"] == "mp_account_mismatch"
    # O'sha sotuvchining yangi kaliti.
    fresh = new_token()
    api.uzum.keys[fresh] = [shop(801), shop(802)]
    r = api.client.put(path, json={"token": fresh})
    assert r.status_code == 200 and r.json()["key_hint"] == "…" + fresh[-4:]
    api.client.post(f"/api/v1/orgs/{org}/accounts/{account}/check")
    assert api.uzum.seen[-1].headers["authorization"] == fresh
    # Yaroqsiz yangi kalit — eski saqlanadi.
    r = api.client.put(path, json={"token": new_token()})
    assert r.status_code == 422 and r.json()["code"] == "mp_token_invalid"
    assert api.client.get(f"/api/v1/orgs/{org}/accounts").json()[0]["key_hint"] == "…" + fresh[-4:]
    assert (
        api.client.put(
            f"/api/v1/orgs/{org}/accounts/{uuid.uuid4()}/token", json={"token": fresh}
        ).status_code
        == 404
    )
    audit = api.client.get(f"/api/v1/orgs/{org}/audit").json()
    replace = next(a for a in audit if a["action"] == "account.token_replace")
    assert replace["before"]["key_hint"] == "…" + old[-4:]
    assert replace["after"] == {"status": "active", "key_hint": "…" + fresh[-4:]}


def test_replace_token_cannot_steal_other_account_shops(api: MpApi) -> None:
    org, _, first, _ = _connected(api, 901)
    second_token = new_token()
    api.uzum.keys[second_token] = [shop(902)]
    second = api.connect(org, second_token).json()["id"]
    both = new_token()
    api.uzum.keys[both] = [shop(901), shop(902)]
    r = api.client.put(f"/api/v1/orgs/{org}/accounts/{first}/token", json={"token": both})
    assert r.status_code == 409 and r.json()["code"] == "mp_shops_already_connected"
    assert second


def test_disconnect_erases_key_and_keeps_shops(api: MpApi) -> None:
    org, token, account, _ = _connected(api, 1001)
    base = f"/api/v1/orgs/{org}/accounts/{account}"
    assert api.client.delete(f"{base}/token").status_code == 204
    assert api.client.delete(f"{base}/token").status_code == 204  # takror — o'zgarishsiz
    row = api.admin(
        "SELECT status, token_encrypted, key_version, token_last4 FROM mp_accounts WHERE id = %s",
        [uuid.UUID(account)],
    )
    assert row == [("disconnected", None, None, None)]
    body = api.client.get(f"/api/v1/orgs/{org}/accounts").json()[0]
    assert body["status"] == "disconnected" and body["key_hint"] is None and len(body["shops"]) == 1
    r = api.client.post(f"{base}/check")
    assert r.status_code == 409 and r.json()["code"] == "account_disconnected"
    # Qayta ulash — o'sha sotuvchining kaliti bilan.
    r = api.client.put(f"{base}/token", json={"token": token})
    assert r.status_code == 200 and r.json()["status"] == "active"
    actions = [a["action"] for a in api.client.get(f"/api/v1/orgs/{org}/audit").json()]
    assert actions.count("account.disconnect") == 1
    assert api.client.delete(f"/api/v1/orgs/{org}/accounts/{uuid.uuid4()}/token").status_code == 404


def test_token_state_constraint(api: MpApi) -> None:
    """Bazada ham: faol akkauntda kalit bor, uzilganida — yo'q."""
    import psycopg

    _, _, account, _ = _connected(api)
    for sql in (
        "UPDATE mp_accounts SET token_encrypted = NULL WHERE id = %s",
        "UPDATE mp_accounts SET status = 'disconnected' WHERE id = %s",
        "UPDATE mp_accounts SET key_version = NULL WHERE id = %s",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            api.admin(sql, [uuid.UUID(account)])


# --- Do'konlarni tanlash -------------------------------------------------------------------------


def test_update_shop(api: MpApi) -> None:
    org, _, _, body = _connected(api, 1101)
    shop_id = body["shops"][0]["id"]
    path = f"/api/v1/orgs/{org}/shops/{shop_id}"
    r = api.client.patch(path, json={"active": False, "alias": "A", "color": "#4F46E5"})
    assert r.status_code == 200
    assert (r.json()["active"], r.json()["alias"], r.json()["color"]) == (False, "A", "#4F46E5")
    r = api.client.patch(path, json={"alias": None, "active": None})
    assert r.json()["alias"] is None and r.json()["active"] is False  # active NULL bo'lmaydi
    assert api.client.patch(path, json={}).status_code == 200
    for bad in ({"color": "red"}, {"alias": ""}, {"alias": "x" * 41}):
        assert api.client.patch(path, json=bad).status_code == 422
    assert api.client.patch(f"/api/v1/orgs/{org}/shops/{uuid.uuid4()}", json={}).status_code == 404
    audit = api.client.get(f"/api/v1/orgs/{org}/audit").json()
    first = next(a for a in reversed(audit) if a["action"] == "shop.update")
    assert first["before"] == {"active": True, "alias": None, "color": None}

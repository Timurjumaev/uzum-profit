"""B2.5: ``scripts/record_uzum.py`` — soxta Uzum bilan: kalit, nomlar va id'lar kassetaga tushmaydi, tuzilish,
holat/kod qiymatlari va sonlar saqlanadi; natija mijoz testlari o'qiydigan kasseta formatida."""

from __future__ import annotations

import importlib.util
import json
import urllib.parse
from pathlib import Path
from types import ModuleType
from typing import Any

import cassette
import pytest

ROOT = Path(__file__).resolve().parents[3]
KEY = "REAL-uzum-key-7d1c2b9e4f6a8c0d1e3f5a7b"
SHOP_NAME = "byDurii Toshkent"
TITLE = "Ayollar sumkasi qora charm"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "record_uzum", ROOT / "scripts" / "record_uzum.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rec = _load()
J = {
    "content-type": "application/json",
    "x-ratelimit-remaining-per-day": "99000",
    "set-cookie": "s=1",
}


def fake_uzum(calls: list[tuple[str, str]]) -> Any:
    def fetch(path_qs: str, key: str) -> tuple[int, dict[str, str], bytes]:
        calls.append((path_qs, key))
        if key != KEY:
            return 401, {"content-type": "application/json"}, b'{"error":"Unauthorized"}'
        path, _, qs = path_qs.partition("?")
        params = dict(urllib.parse.parse_qsl(qs))
        if path == "/v1/shops":
            body: Any = [
                {"id": 106121, "name": SHOP_NAME},
                {"id": 135204, "name": "EL-ONE do'koni"},
            ]
        elif path == "/v1/finance/orders":
            if params.get("size") == "-1":
                return (
                    400,
                    J,
                    b'{"errors":[{"code":"bad-request","message":"size must be positive"}]}',
                )
            n = 0 if params.get("page") != "0" else min(int(params["size"]), 7)
            body = {
                "orderItems": [
                    {
                        "id": 5000 + i,
                        "orderId": 7000 + i,
                        "skuTitle": f"{TITLE} {i}",
                        "status": "TO_WITHDRAW",
                        "date": 1760000000000,
                        "sellPrice": 129000,
                        "amount": 1,
                        "commission": 25800,
                        "sellerProfit": 97950,
                        "paid": 129000,
                    }
                    for i in range(n)
                ],
                "totalElements": 7,
            }
        elif path == "/v1/finance/expenses":
            body = {
                "payload": {
                    "payments": [
                        {
                            "id": 1,
                            "code": "С000003",
                            "type": "OUTCOME",
                            "name": "Saqlash xizmati № 123",
                            "source": "Ombor",
                            "paymentPrice": 1200,
                            "dateCreated": "2026-10-01T10:00:00",
                        }
                    ]
                }
            }
        elif path.startswith("/v1/product/shop/"):
            body = {
                "productList": [
                    {
                        "productId": 300,
                        "title": TITLE,
                        "image": "https://images.uzum.uz/abc.jpg",
                        "skuList": [
                            {
                                "skuId": s,
                                "price": 1,
                                "barcode": "4780000000001",
                                "status": {"value": "ACTIVE", "title": "Faol"},
                            }
                            for s in (1, 2, 3)
                        ],
                    }
                ],
                "totalProductsAmount": 1,
            }
        elif path.endswith("/invoice"):
            body = [
                {
                    "id": 44,
                    "invoiceNumber": 55,
                    "invoiceStatus": {"value": "ACCEPTED", "title": "Qabul qilindi"},
                }
            ]
        elif path.endswith("/invoice/products"):
            assert params["invoiceId"] == "44"
            body = [{"skuId": 1, "quantityToStock": 5, "quantityAccepted": 5}]
        elif path.endswith("/return"):
            body = [{"id": 9, "type": "RETURN"}]
        else:
            return 404, J, b'{"error":"not found"}'
        return 200, J, json.dumps(body).encode()

    return fetch


@pytest.fixture
def recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, list[tuple[str, str]]]:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f'# izoh\nUZUM_API_KEY="{KEY}"\n', encoding="utf-8")
    monkeypatch.delenv("UZUM_API_KEY", raising=False)
    calls: list[tuple[str, str]] = []
    assert rec.main(["--out", "kasseta.json", "--shops", "1"], fetch=fake_uzum(calls)) == 0
    return (tmp_path / "kasseta.json").read_text(encoding="utf-8"), calls


def test_no_key_no_names_no_ids(recorded: tuple[str, list[tuple[str, str]]]) -> None:
    text, calls = recorded
    assert KEY not in text and KEY[:12] not in text
    for secret in (SHOP_NAME, "EL-ONE do'koni", TITLE, "Saqlash xizmati", "images.uzum.uz", "Faol"):
        assert secret not in text, secret
    for ident in ("106121", "135204", "4780000000001", "7000"):
        assert ident not in text, ident
    assert "set-cookie" not in text
    # Faqat GET yo'llari; noto'g'ri kalit faqat 401 shakli uchun.
    assert {k for _, k in calls} == {KEY, rec.INVALID_KEY}


def test_structure_and_values_kept(recorded: tuple[str, list[tuple[str, str]]]) -> None:
    data = json.loads(recorded[0])
    by_name = {i["name"]: i for i in data["interactions"]}
    orders = by_name["orders"]["response"]
    assert orders["status"] == 200
    assert orders["headers"] == {
        "content-type": "application/json",
        "x-ratelimit-remaining-per-day": "99000",
    }
    rows = orders["body"]["orderItems"]
    assert len(rows) == rec.ROWS and orders["body"]["totalElements"] == 7
    first = rows[0]
    assert first["status"] == "TO_WITHDRAW" and first["sellPrice"] == 129000
    assert first["paid"] == 129000  # "paid" — id emas
    assert first["skuTitle"].startswith("<skuTitle")
    # Id'lar izchil: so'rov parametri va yo'ldagi do'kon id bir xil o'rinbosar.
    shop = by_name["shops"]["response"]["body"][0]["id"]
    assert by_name["orders"]["request"]["params"]["shopIds"] == shop
    assert by_name["products"]["request"]["path"] == f"/v1/product/shop/{shop}"
    assert (
        by_name["orders"]["request"]["params"]["group"] == "false"
    )  # parametrlar bizniki — saqlanadi
    expense = by_name["expenses"]["response"]["body"]["payload"]["payments"][0]
    assert (
        expense["code"] == "С000003"
        and expense["type"] == "OUTCOME"
        and expense["source"] == "Ombor"
    )
    assert expense["dateCreated"] == "2026-10-01T10:00:00"
    sku = by_name["products"]["response"]["body"]["productList"][0]["skuList"]
    assert len(sku) == rec.NESTED_ROWS and sku[0]["status"]["value"] == "ACTIVE"
    assert by_name["auth_error"]["response"]["status"] == 401
    assert by_name["bad_request"]["response"]["status"] == 400
    assert by_name["orders_end"]["response"]["body"]["orderItems"] == []
    assert (
        by_name["invoice_products"]["request"]["params"]["invoiceId"]
        == (by_name["invoices"]["response"]["body"][0]["id"])
    )
    probes = {p["name"]: p for p in data["probes"]}
    assert probes["size_probe_orders"] == {
        "name": "size_probe_orders",
        "requested": 5000,
        "status": 200,
        "rows": 7,
        "total": 7,
    }
    assert data["source"].startswith("recorded ")


def test_output_loads_as_cassette(
    recorded: tuple[str, list[tuple[str, str]]], tmp_path: Path
) -> None:
    path = tmp_path / "recorded.json"
    path.write_text(recorded[0], encoding="utf-8")
    loaded = cassette.load(path)
    assert loaded.get("shops") and loaded.get("orders") and loaded.get("products")
    assert loaded.get("orders").response().json()["totalElements"] == 7  # type: ignore[union-attr]


def test_dump_refuses_leaks() -> None:
    with pytest.raises(SystemExit, match="kalit"):
        rec.dump({"interactions": [{"x": KEY}], "_originals": set()}, KEY)
    with pytest.raises(SystemExit, match="asl matn"):
        rec.dump({"interactions": [{"x": SHOP_NAME}], "_originals": {SHOP_NAME}}, KEY)


def test_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UZUM_API_KEY", raising=False)
    assert rec.main([], fetch=fake_uzum([])) == 2
    assert "UZUM_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("UZUM_API_KEY", "Bearer  abc ")
    assert rec.load_key() == "abc"


def test_network_error_is_logged_without_details(capsys: pytest.CaptureFixture[str]) -> None:
    def broken(path_qs: str, key: str) -> Any:
        raise RuntimeError(f"failed with {key}")

    cassette_data = rec.record(KEY, broken, log=print)
    out = capsys.readouterr().out
    assert "RuntimeError" in out and KEY not in out and cassette_data["interactions"] == []


def test_anonymizer_rules() -> None:
    anon = rec.Anonymizer()
    assert anon.value("status", "ACCEPTED") == "ACCEPTED"
    assert (
        anon.value("title", "ACCEPTED") != "ACCEPTED"
    )  # nom maydonida katta harf ham almashtiriladi
    assert anon.value("date", "2026-10-01") == "2026-10-01"
    assert anon.value("skuId", 5) == anon.value("productId", 5)  # bir qiymat — bir o'rinbosar
    assert anon.value("sellerItemCode", "ABC-1").startswith("ID")
    assert anon.value("name", "  ") == "  " and anon.value("x", None) is None
    assert anon.value("image", "https://x.uz/a.png").startswith("<url")
    # Temurning birinchi yozuvidan keyin: Uzum'ning kichik harfli kodlari va nuqtali sana saqlanadi.
    assert anon.value("code", "logistics-volume") == "logistics-volume"
    assert anon.value("code", "Saqlash xizmati") != "Saqlash xizmati"
    assert anon.value("dateCreated", "24.10.2026 10:00") == "24.10.2026 10:00"


def test_curl_fallback_on_ssl_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mac'dagi Python sertifikat xatosi → curl; kalit buyruq qatorida emas (stdin), sarlavhalar o'qiladi."""
    import ssl
    import subprocess
    import urllib.error

    monkeypatch.setattr(rec, "PAUSE", 0)
    monkeypatch.setattr(rec.shutil, "which", lambda name: "/usr/bin/curl")

    def ssl_fail(url: str, key: str) -> Any:
        raise urllib.error.URLError(ssl.SSLError("CERTIFICATE_VERIFY_FAILED"))

    runs: list[tuple[list[str], bytes]] = []

    def fake_run(cmd: list[str], input: bytes, capture_output: bool) -> Any:
        runs.append((cmd, input))
        out = (
            b"HTTP/1.1 100 Continue\r\n\r\n"
            b"HTTP/2 200\r\ncontent-type: application/json\r\nx-ratelimit-remaining-per-day: 42\r\n\r\n"
            b'[{"id": 1}]'
        )
        return subprocess.CompletedProcess(cmd, 0, out, b"")

    monkeypatch.setattr(rec, "_urllib", ssl_fail)
    monkeypatch.setattr(rec.subprocess, "run", fake_run)
    fetch = rec.make_fetch("https://uzum.test")
    status, headers, body = fetch("/v1/shops", KEY)
    assert (
        status == 200
        and headers["x-ratelimit-remaining-per-day"] == "42"
        and body == b'[{"id": 1}]'
    )
    cmd, stdin = runs[0]
    assert KEY not in " ".join(cmd) and KEY.encode() in stdin
    fetch("/v1/shops", KEY)  # keyingi so'rovlar to'g'ridan-to'g'ri curl orqali
    assert len(runs) == 2


def test_fetch_other_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    monkeypatch.setattr(rec, "PAUSE", 0)

    def refused(url: str, key: str) -> Any:
        raise urllib.error.URLError(ConnectionRefusedError(f"no route {key}"))

    monkeypatch.setattr(rec, "_urllib", refused)
    with pytest.raises(RuntimeError) as info:
        rec.make_fetch("https://uzum.test")("/v1/shops", KEY)
    assert KEY not in str(info.value) and "ConnectionRefusedError" in str(info.value)


def test_dump_ignores_key_names_and_placeholders() -> None:
    """Temurning birinchi yozuvi shu sababli to'xtagan: Uzum xato javobidagi ``"size"`` almashtirildi, lekin bu so'z
    so'rov parametrining nomi sifatida faylda qoladi — sizish emas."""
    anon = rec.Anonymizer()
    body = anon.value("body", {"errors": [{"field": "size", "message": "must be positive"}]})
    name = anon.value("name", "name")  # o'rinbosar "<name 2>" ichida "name" — sizish emas
    source = anon.value("source", "Ombor")
    title = anon.value("title", "Ombor")  # Uzum so'zi boshqa maydonda ham — sizish emas
    cassette_data = {
        "interactions": [
            {"params": {"size": -1}, "body": body, "name": name, "source": source, "title": title}
        ],
        "_originals": anon.originals,
    }
    assert '"size"' in rec.dump(cassette_data, KEY)


def test_dump_names_leaking_fields_only() -> None:
    with pytest.raises(SystemExit) as info:
        rec.dump(
            {"interactions": [{"source": f"{SHOP_NAME} ombori"}], "_originals": {SHOP_NAME}}, KEY
        )
    assert "maydonlar: source" in str(info.value) and SHOP_NAME not in str(info.value)

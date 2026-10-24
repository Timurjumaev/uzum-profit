#!/usr/bin/env python3
"""B2.5: Uzum Open API javoblarini yozib olish (test kassetasi) — Temurning Mac'ida, haqiqiy kalit bilan.

Faqat standart kutubxona (Python 3.12+), faqat GET so'rovlar, har biri orasida 0,7 s. Natija — anonimlashtirilgan
JSON (``uzum_cassette.json``): javob tuzilishi, maydon nomlari, holat va kod qiymatlari, sonlar saqlanadi;
**kalit, matnlar (nomlar, sarlavhalar), id'lar va havolalar almashtiriladi**, har ro'yxatdan 3 tadan qator.
Fayl yozilishidan oldin unda kalit va do'kon nomlari yo'qligi tekshiriladi.

Ishga tushirish (``.env`` dagi ``UZUM_API_KEY`` bilan; loyiha papkasida):

    python3 record_uzum.py                 # → uzum_cassette.json
    python3 record_uzum.py --out boshqa.json --shops 1

Kassetani ``apps/api/tests/fixtures/uzum/`` ga qo'yiladi — mijoz testlari unda ham ishlaydi (B2.5).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

if sys.version_info < (3, 12):  # noqa: UP036 - eski Python'da tushunarli xabar uchun
    sys.exit("Python 3.12 yoki yangisi kerak (Mac'da: python3 --version).")

BASE = "https://api-seller.uzum.uz/api/seller-openapi"
UA = "uzum-profit-recorder/1"
PAUSE = 0.7
ROWS = 3  # har ro'yxatdan shuncha qator
NESTED_ROWS = 2
INVALID_KEY = (
    "invalid-key-for-recording-0000"  # 401 javob shaklini yozish uchun (haqiqiy kalit emas)
)

# Saqlanadigan matnlar: holat, tur, kod va sana kabi qiymatlar (ma'lumot emas, lug'at).
ENUM = re.compile(
    r"^[A-Z\u0410-\u042f\u0401][A-Z\u0410-\u042f\u04010-9_.\-]{0,39}$"
)  # lotin va kirill
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ][\d:.]+(Z|[+-]\d{2}:?\d{2})?)?$")
# Faqat shu nomli (yoki shu qo'shimchali) maydonlarda — boshqa joyda katta harfli matn ham nom bo'lishi mumkin.
KEEP_TEXT = re.compile(r"^(status|type|code|currency|value)$|(Status|Type|Code|Currency|Cause)$")
# Uzum'ning o'z bo'lim nomlari ("Ombor", "Logistika", "Marketing") — xarajat toifasi shundan aniqlanadi (F9).
KEEP_ANY = {"source"}
# Id kabi maydonlar (camelCase: ``paid`` emas): son ham, matn ham — izchil almashtiriladi (bog'lanishlar saqlanadi).
ID_KEYS = re.compile(r"^(id|ids|barcode|ikpu|article)$|(Id|Ids|Number|Barcode|ItemCode)$")
HEADERS_KEPT = re.compile(r"^(content-type|x-ratelimit-.*)$", re.IGNORECASE)

Fetch = Callable[[str, str], tuple[int, dict[str, str], bytes]]


def load_key(path: str = ".env") -> str:
    key = os.environ.get("UZUM_API_KEY", "")
    if not key and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                name, sep, value = line.strip().partition("=")
                if sep and name.strip() == "UZUM_API_KEY":
                    key = value.strip().strip('"').strip("'")
    key = key.strip()
    if key[:7].lower() == "bearer ":
        key = key[7:].strip()
    return key


def _urllib(url: str, key: str) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(
        url, headers={"Authorization": key, "Accept": "application/json", "User-Agent": UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def _curl(url: str, key: str) -> tuple[int, dict[str, str], bytes]:
    """Python sertifikat xatosi bersa (Mac'da uchraydi). Kalit buyruq qatoriga emas, stdin orqali."""
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl topilmadi")

    def q(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    config = f'url = "{q(url)}"\nheader = "Authorization: {q(key)}"\nheader = "Accept: application/json"\n'
    proc = subprocess.run(
        [curl, "-sS", "--max-time", "60", "-D", "-", "--config", "-"],
        input=config.encode(),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl xatosi (kod {proc.returncode})")
    raw = proc.stdout
    head, _, body = raw.partition(b"\r\n\r\n")
    while head.startswith(b"HTTP/") and b" 100 " in head.split(b"\r\n", 1)[0]:
        head, _, body = body.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1])
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, headers, body


def make_fetch(base: str = BASE) -> Fetch:
    state = {"curl": False}

    def fetch(path_qs: str, key: str) -> tuple[int, dict[str, str], bytes]:
        url = base + path_qs
        time.sleep(PAUSE)
        if not state["curl"]:
            try:
                return _urllib(url, key)
            except urllib.error.URLError as e:
                if not isinstance(getattr(e, "reason", None), ssl.SSLError):
                    raise RuntimeError(f"ulanish xatosi: {type(e.reason).__name__}") from None
                state["curl"] = True
        return _curl(url, key)

    return fetch


class Anonymizer:
    """Izchil almashtirish: bir xil qiymat — bir xil o'rinbosar (fayl ichida bog'lanishlar saqlanadi)."""

    def __init__(self) -> None:
        self.ids: dict[Any, Any] = {}
        self.texts: dict[str, str] = {}
        self.originals: set[str] = set()  # tekshiruv uchun: almashtirilgan asl matnlar

    def _id(self, value: Any) -> Any:
        if value not in self.ids:
            n = len(self.ids) + 1
            self.ids[value] = 900_000 + n if isinstance(value, int) else f"ID{n:06d}"
        return self.ids[value]

    def _text(self, key: str, value: str) -> str:
        if value not in self.texts:
            if len(value) >= 4 and (" " in value or any(c.islower() for c in value)):
                self.originals.add(value)  # tabiiy matn — faylda qolmasligi tekshiriladi
            kind = "url" if value.startswith(("http://", "https://")) else key
            self.texts[value] = f"<{kind} {len(self.texts) + 1}>"
        return self.texts[value]

    def value(self, key: str, value: Any, depth: int = 0) -> Any:
        if isinstance(value, dict):
            return {k: self.value(k, v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            limit = ROWS if depth <= 2 else NESTED_ROWS
            return [self.value(key, v, depth + 1) for v in value[:limit]]
        if isinstance(value, bool) or value is None:
            return value
        if ID_KEYS.search(key) and isinstance(value, int | str) and value != "":
            return self._id(value)
        if isinstance(value, str):
            if (
                not value.strip()
                or DATE.match(value)
                or (KEEP_TEXT.search(key) and ENUM.match(value))
                or (key in KEEP_ANY and len(value) <= 40)
            ):
                return value
            return self._text(key, value)
        return value


def interactions(
    shops: list[dict[str, Any]], max_shops: int
) -> list[tuple[str, str, dict[str, Any]]]:
    """(nom, yo'l, parametrlar). Sanalar — oxirgi 90 kun, butun tarix sinovi — 2020-01-01 dan."""
    now = datetime.now(UTC)
    recent = int((now.timestamp() - 90 * 86400) * 1000)
    history = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1000)
    out = []
    for s in shops[:max_shops]:
        sid = s["id"]
        out += [
            (
                f"orders:{sid}",
                "/v1/finance/orders",
                {"shopIds": sid, "group": "false", "dateFrom": recent, "page": 0, "size": 5},
            ),
            (
                f"orders_end:{sid}",
                "/v1/finance/orders",
                {"shopIds": sid, "group": "false", "dateFrom": recent, "page": 100000, "size": 5},
            ),
            (
                f"expenses:{sid}",
                "/v1/finance/expenses",
                {"shopIds": sid, "dateFrom": recent, "page": 0, "size": 5},
            ),
            (f"products:{sid}", f"/v1/product/shop/{sid}", {"page": 0, "size": 3}),
            (f"invoices:{sid}", f"/v1/shop/{sid}/invoice", {"page": 0, "size": 3}),
            (f"returns:{sid}", f"/v1/shop/{sid}/return", {"page": 0, "size": 3}),
            (f"returns_all:{sid}", "/v1/return", {"shopId": sid, "page": 0, "size": 3}),
            # Katta sahifa hajmi sinovi: qator soni va jami soni yoziladi (Uzum hajmni kesadimi?).
            (
                f"size_probe_orders:{sid}",
                "/v1/finance/orders",
                {"shopIds": sid, "group": "false", "dateFrom": history, "page": 0, "size": 5000},
            ),
            (
                f"size_probe_expenses:{sid}",
                "/v1/finance/expenses",
                {"shopIds": sid, "dateFrom": history, "page": 0, "size": 5000},
            ),
            (f"bad_request:{sid}", "/v1/finance/orders", {"shopIds": sid, "page": 0, "size": -1}),
        ]
    return out


def _decode(body: bytes) -> Any:
    try:
        return json.loads(body)
    except ValueError:
        text = body.decode("utf-8", "replace")
        return {"__text__": "<html>" if "<html" in text.lower() else f"<matn {len(text)} belgi>"}


def _count(body: Any) -> tuple[int | None, Any]:
    """Javobdagi qatorlar soni va jami (kesish sinovi uchun)."""
    rows = None
    if isinstance(body, dict):
        for key in ("orderItems", "productList"):
            if isinstance(body.get(key), list):
                rows = len(body[key])
        payload = body.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("payments"), list):
            rows = len(payload["payments"])
        total = body.get("totalElements", body.get("totalProductsAmount"))
        return rows, total
    return (len(body) if isinstance(body, list) else None), None


def record(
    key: str, fetch: Fetch, max_shops: int = 2, log: Callable[[str], None] = print
) -> dict[str, Any]:
    anon = Anonymizer()
    entries: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []

    def call(name: str, path: str, params: dict[str, Any], use_key: str = key) -> tuple[int, Any]:
        qs = ("?" + urllib.parse.urlencode(params)) if params else ""
        try:
            status, headers, body = fetch(path + qs, use_key)
        except Exception as e:  # tarmoq: kalitsiz, faqat turi
            log(f"  {name:<28} XATO: {type(e).__name__}")
            return 0, None
        data = _decode(body)
        log(f"  {name:<28} HTTP {status}")
        if name.startswith("size_probe"):
            rows, total = _count(data)
            probes.append(
                {
                    "name": name.split(":")[0],
                    "requested": params["size"],
                    "status": status,
                    "rows": rows,
                    "total": total,
                }
            )
            return status, data
        entries.append(
            {
                "name": name.split(":")[0],
                "request": {"path": path, "params": anon.value("params", params)},
                "response": {
                    "status": status,
                    "headers": {k: v for k, v in sorted(headers.items()) if HEADERS_KEPT.match(k)},
                    "body": anon.value("body", data),
                },
            }
        )
        return status, data

    log("Uzum javoblari yozib olinmoqda (kalit faylga yozilmaydi):")
    status, shops_body = call("shops", "/v1/shops", {})
    shops = shops_body if isinstance(shops_body, list) else (shops_body or {}).get("payload") or []
    for s in shops:
        if isinstance(s.get("name"), str) and len(s["name"]) >= 4:
            anon.originals.add(s["name"])
    call("auth_error", "/v1/shops", {}, use_key=INVALID_KEY)
    for name, path, params in interactions(
        [s for s in shops if isinstance(s, dict) and "id" in s], max_shops
    ):
        status, data = call(name, path, params)
        if name.startswith("invoices:") and status == 200:
            rows = data if isinstance(data, list) else []
            for row in rows[:1]:
                if isinstance(row, dict) and row.get("id") is not None:
                    sid = name.split(":")[1]
                    call(
                        f"invoice_products:{sid}",
                        f"/v1/shop/{sid}/invoice/products",
                        {"invoiceId": row["id"], "page": 0, "size": 3},
                    )
    # Yo'llardagi do'kon id'lari ham almashtiriladi.
    for e in entries:
        e["request"]["path"] = _replace_ids(e["request"]["path"], anon)
    return {
        "source": f"recorded {datetime.now(UTC):%Y-%m-%d}, anonymized (scripts/record_uzum.py)",
        "interactions": entries,
        "probes": probes,
        "_originals": anon.originals,  # tekshiruv uchun; faylga yozilmaydi
    }


def _replace_ids(path: str, anon: Anonymizer) -> str:
    return re.sub(
        r"/(\d+)(?=/|$)",
        lambda m: f"/{anon.ids.get(int(m.group(1)), anon._id(int(m.group(1))))}",
        path,
    )


def dump(cassette: dict[str, Any], key: str) -> str:
    originals = cassette.pop("_originals", set())
    text = json.dumps(cassette, ensure_ascii=False, indent=2)
    leaks = [o for o in originals if o in text]
    if key and key in text:
        raise SystemExit(
            "XATO: kalit faylga tushib qoldi — yozilmadi. Claude'ga shu xabarni yuboring."
        )
    if leaks:
        raise SystemExit(
            f"XATO: {len(leaks)} ta asl matn almashtirilmadi — yozilmadi. Claude'ga shu xabarni yuboring."
        )
    return text


def main(argv: list[str] | None = None, fetch: Fetch | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="uzum_cassette.json")
    parser.add_argument("--shops", type=int, default=2, help="nechta do'kon (standart 2)")
    args = parser.parse_args(argv)
    key = load_key()
    if not key:
        print("UZUM_API_KEY topilmadi: buyruqni .env bor papkada ishga tushiring.", file=sys.stderr)
        return 2
    cassette = record(key, fetch or make_fetch(), args.shops)
    text = dump(cassette, key)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    statuses: dict[int, int] = {}
    for e in cassette["interactions"]:
        statuses[e["response"]["status"]] = statuses.get(e["response"]["status"], 0) + 1
    print(f"\nTayyor: {args.out} ({len(cassette['interactions'])} ta javob, holatlar: {statuses}).")
    print("Kalit va nomlar faylda yo'q. Shu faylni Claude'ga yuboring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

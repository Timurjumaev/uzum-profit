# -*- coding: utf-8 -*-
"""Uzum Seller OpenAPI mijozi. Faqat O'QISH (GET) so'rovlari.

Python sertifikat xatosi (CERTIFICATE_VERIFY_FAILED) bersa, avtomatik tizimdagi
curl'ga o'tadi. Sertifikat tekshiruvi hech qachon o'chirilmaydi.
"""
import json
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .util import cfg

DEFAULT_BASE = "https://api-seller.uzum.uz/api/seller-openapi"
UA = "uzum-profit/0.1"


class UzumError(Exception):
    pass


def _is_ssl_error(exc):
    return isinstance(getattr(exc, "reason", None), ssl.SSLError) or \
        "CERTIFICATE_VERIFY_FAILED" in str(exc)


class Uzum:
    def __init__(self, key, base=None, pause=0.7, log=print):
        key = (key or "").strip()
        if key.lower().startswith("bearer "):  # Uzum'da "Bearer" yozilmaydi
            key = key[7:].strip()
        if not key:
            raise UzumError("API kalit bo'sh")
        self.key = key
        self.base = (base or cfg("UZUM_BASE", DEFAULT_BASE)).rstrip("/")
        self.use_curl = cfg("UZUM_TRANSPORT", "auto") == "curl"
        self.auto = cfg("UZUM_TRANSPORT", "auto") == "auto"
        self.pause, self.log = float(cfg("UZUM_PAUSE", pause)), log

    # ---------- tarmoq ----------
    def _urllib(self, url):
        req = urllib.request.Request(url, headers={
            "Authorization": self.key, "Accept": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")

    def _curl(self, url):
        """Kalit buyruq qatoriga emas, stdin orqali beriladi."""
        curl = shutil.which("curl")
        if not curl:
            raise UzumError("curl topilmadi")

        def q(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')

        config = (f'url = "{q(url)}"\nheader = "Authorization: {q(self.key)}"\n'
                  f'header = "Accept: application/json"\nheader = "User-Agent: {UA}"\n')
        proc = subprocess.run(
            [curl, "-sS", "--max-time", "60", "-w", "\n%{http_code}", "--config", "-"],
            input=config, capture_output=True, text=True)
        if proc.returncode != 0:
            raise UzumError(f"curl xatosi: {proc.stderr.strip()[:300]}")
        body, _, code = proc.stdout.rpartition("\n")
        return int(code), body

    def _fetch(self, url):
        if self.use_curl:
            return self._curl(url)
        try:
            return self._urllib(url)
        except urllib.error.URLError as e:
            if self.auto and _is_ssl_error(e) and shutil.which("curl"):
                self.log("  (Python sertifikat xatosi berdi, curl orqali davom etaman)")
                self.use_curl = True
                return self._curl(url)
            raise UzumError(f"Ulanish xatosi: {e}")

    def get(self, path, params=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        time.sleep(self.pause)  # Uzum limiti ~2 so'rov/sekund
        status, body = self._fetch(url)
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if not (200 <= status < 300) or data is None:
            hint = " (Uzum himoyasi bloklagan bo'lishi mumkin: IP O'zbekistondan tashqarida?)" \
                if status == 403 and "<html" in body.lower() else ""
            raise UzumError(f"{path}: HTTP {status} {body[:200]}{hint}")
        return data

    def pull(self, label, path, params_fn, get_rows, sizes, total_fn=None, max_pages=60):
        """Barcha sahifalarni yig'adi; qator id bo'yicha takrorlanmaydi."""
        first, size, errors = None, None, []
        for sz in sizes:  # eng katta ishlaydigan sahifa hajmini topamiz
            try:
                first, size = self.get(path, params_fn(0, sz)), sz
                break
            except UzumError as e:
                errors.append(str(e))
        if first is None:
            raise UzumError(f"{label}: {errors[-1] if errors else 'xato'}")
        rows, seen = [], set()

        def add(data):
            for r in get_rows(data):
                rid = r.get("id", r.get("productId")) if isinstance(r, dict) else None
                if rid is not None:
                    if rid in seen:
                        continue
                    seen.add(rid)
                rows.append(r)

        batch, page = get_rows(first), 1
        add(first)
        while len(batch) >= size and page < max_pages:
            data = self.get(path, params_fn(page, size))
            batch = get_rows(data)
            if not batch:
                break
            add(data)
            page += 1
        total = total_fn(first) if total_fn else None
        self.log(f"  {label:<12} {len(rows)} ta qator" + (f" (Uzum bergan jami: {total})" if total else ""))
        return rows

    # ---------- yuqori daraja ----------
    def shops(self):
        data = self.get("/v1/shops")
        return data if isinstance(data, list) else (data.get("payload") or [])

    def orders(self, shop_id, date_from_ms):
        return self.pull(
            "sotuvlar", "/v1/finance/orders",
            lambda p, s: {"shopIds": shop_id, "group": "false", "page": p, "size": s,
                          "dateFrom": date_from_ms},
            lambda d: d.get("orderItems", []) if isinstance(d, dict) else [],
            [1000, 200, 50], lambda d: d.get("totalElements") if isinstance(d, dict) else None)

    def expenses(self, shop_id, date_from_ms):
        return self.pull(
            "xarajatlar", "/v1/finance/expenses",
            lambda p, s: {"shopIds": shop_id, "page": p, "size": s, "dateFrom": date_from_ms},
            lambda d: ((d.get("payload") or {}).get("payments") or []) if isinstance(d, dict) else [],
            [1000, 200, 50])

    def products(self, shop_id):
        return self.pull(
            "mahsulotlar", f"/v1/product/shop/{shop_id}",
            lambda p, s: {"page": p, "size": s},
            lambda d: d.get("productList", []) if isinstance(d, dict) else [],
            [100, 50, 20], lambda d: d.get("totalProductsAmount") if isinstance(d, dict) else None)

    def invoices(self, shop_id):
        return self.pull(
            "fakturalar", f"/v1/shop/{shop_id}/invoice",
            lambda p, s: {"page": p, "size": s},
            lambda d: d if isinstance(d, list) else [],
            [200, 50, 10])

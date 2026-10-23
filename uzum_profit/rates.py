# -*- coding: utf-8 -*-
"""Markaziy bank (CBU) rasmiy kursi: 1 CNY / 1 USD necha so'm.

Bu kurs faqat TAVSIYA: formadagi qiymatni har doim o'zingiz o'zgartira olasiz (haqiqiy
kursingiz bank kursidan farq qilishi mumkin: dastur sizning kiritgan kursingizni ishlatadi).

Manba: https://cbu.uz/uz/arkhiv-kursov-valyut/veb-masteram/
  joriy kurslar (hamma valyuta):  https://cbu.uz/uz/arkhiv-kursov-valyut/json/
  sana bo'yicha:                  .../json/CNY/2026-10-21/   yoki   .../json/all/2026-10-21/
  javob:  [{"Ccy": "CNY", "Nominal": "1", "Rate": "1792.29", "Date": "22.10.2026", ...}]

Faqat ochiq (GET) so'rovlar; hech qanday kalit yuborilmaydi. Python sertifikat xatosi bersa,
tizimdagi curl'ga o'tiladi (sertifikat tekshiruvi hech qachon o'chirilmaydi).
"""
import json
import math
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from .api import UA, _is_ssl_error
from .util import today

BASE = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
CURRENCIES = ("CNY", "USD")
MAX_STEPS_BACK = 5      # dam olish/bayram kunlari uchun: oldingi kunlarga qaytib qidiramiz
_cache = {}             # (valyuta, so'ralgan sana) -> (vaqt, natija)


class RateError(Exception):
    pass


def _curl(url, timeout):
    curl = shutil.which("curl")
    if not curl:
        raise RateError("curl topilmadi")
    proc = subprocess.run([curl, "-sS", "-f", "--max-time", str(timeout),
                           "-H", "Accept: application/json", "--url", url],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if proc.returncode != 0:
        raise RateError("curl xatosi: %s" % (proc.stderr.strip()[:200] or proc.returncode))
    return proc.stdout


def http_get(url, timeout=15):
    """Javob matnini qaytaradi; xatoda RateError."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise RateError("bank serveri HTTP %d javob berdi" % e.code)
    except (urllib.error.URLError, OSError) as e:
        if _is_ssl_error(e) and shutil.which("curl"):
            return _curl(url, timeout)
        raise RateError("bank serveriga ulanib bo'lmadi (%s)" % e)


def _float(x):
    s = str(x).strip().replace(" ", "").replace(" ", "")
    s = s.replace(",", "") if ("," in s and "." in s) else s.replace(",", ".")
    return float(s)


def _iso(s):
    for f in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s).strip(), f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_rate(data, ccy):
    """Bank javobidan (1 birlik kursi, 'YYYY-MM-DD' | None). Topilmasa (None, None)."""
    if isinstance(data, dict):
        inner = data.get("data") or data.get("payload") or data.get("result")
        data = inner if isinstance(inner, list) else [data]
    if not isinstance(data, list):
        return None, None
    for row in data:
        if not isinstance(row, dict) or str(row.get("Ccy") or "").upper() != ccy:
            continue
        try:
            rate = _float(row.get("Rate")) / (_float(row.get("Nominal") or 1) or 1)
        except (TypeError, ValueError):
            continue
        if math.isfinite(rate) and rate > 0:
            return round(rate, 4), _iso(row.get("Date"))
    return None, None


def _load(url, ccy, fetch):
    try:
        data = json.loads(fetch(url))
    except ValueError:
        raise RateError("bank javobi tushunarsiz (JSON emas)")
    return parse_rate(data, ccy)


def _lookup(ccy, ask, now, fetch):
    """Bankdan kursni topadi. ask >= now bo'lsa joriy kurs, aks holda arxiv."""
    if ask >= now:
        rate, rdate = _load(BASE, ccy, fetch)
        if rate is None:
            raise RateError("bank javobida %s kursi topilmadi" % ccy)
        return {"rate": rate, "date": rdate or now, "warn": ""}
    day, newer, last_error = ask, None, None
    for _ in range(MAX_STEPS_BACK + 1):
        answered = False
        for url in (BASE + "%s/%s/" % (ccy, day), BASE + "all/%s/" % day):
            try:
                rate, rdate = _load(url, ccy, fetch)
            except RateError as e:
                last_error = e
                continue
            if rate is None:
                continue
            answered = True
            if rdate is not None and rdate > ask:      # bank so'ralgandan yangiroq kurs qaytardi
                newer = newer or (rate, rdate)
                continue
            warn = ""
            if rdate and rdate < ask:
                warn = "Bank %s sanasiga kurs e'lon qilmagan, oxirgi e'lon qilingani olindi." % ask
            return {"rate": rate, "date": rdate or day, "warn": warn}
        if answered:        # bank javob berdi, lekin sanaga mos emas: orqaga yurishdan foyda yo'q
            break
        day = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    if newer:
        return {"rate": newer[0], "date": newer[1],
                "warn": "Bank %s sanasi uchun arxiv kursini bermadi: %s sanasidagi kurs olindi, "
                        "kerak bo'lsa o'zingiz yozing." % (ask, newer[1])}
    if last_error:
        raise last_error
    raise RateError("%s uchun %s atrofida kurs topilmadi" % (ccy, ask))


def get_rate(ccy, date=None, fetch=http_get, now=None):
    """{'rate': float, 'date': 'YYYY-MM-DD', 'warn': str}. Xatoda RateError."""
    ccy = (ccy or "").upper()
    if ccy not in CURRENCIES:
        raise RateError("valyuta noto'g'ri: %s" % ccy)
    now = now or today()
    ask = date if date and date < now else now          # bugungi va kelajak sana uchun joriy kurs
    key = (ccy, ask)
    hit = _cache.get(key)
    if hit and (ask < now or time.time() - hit[0] < 3600):
        result = hit[1]
    else:
        result = _lookup(ccy, ask, now, fetch)
        _cache[key] = (time.time(), result)
    if date and date > now:                               # ogohlantirish keshga yozilmaydi
        result = dict(result, warn=(result["warn"] + " " if result["warn"] else "") +
                      "Sana kelajakda: joriy kurs olindi.")
    return result

# -*- coding: utf-8 -*-
"""Umumiy yordamchi funksiyalar va sozlamalar."""
import os
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=5))  # Toshkent, GMT+5
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    """Loyiha papkasidagi .env faylini o'qiydi (UZUM_API_KEY=... ko'rinishida)."""
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cfg(name, default=None):
    return os.environ.get(name, default)


def cfg_num(name, default):
    try:
        return float(cfg(name, default))
    except (TypeError, ValueError):
        return float(default)


def db_path():
    return cfg("UZUM_DB", os.path.join(ROOT, "uzum.db"))


def ms_to_date(ms):
    return datetime.fromtimestamp(ms / 1000, TZ).strftime("%Y-%m-%d")


def day_start_ms(d):
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=TZ).timestamp() * 1000)


def day_end_ms(d):
    return day_start_ms(d) + 86400000 - 1


def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def days_ago(n):
    return (datetime.now(TZ) - timedelta(days=n)).strftime("%Y-%m-%d")


def fmt(n, dec=0):
    if n is None:
        return "—"
    return f"{n:,.{dec}f}".replace(",", " ")


def to_num(s):
    """'1 234,5' -> 1234.5 ; noto'g'ri qiymat -> ValueError."""
    s = str(s).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    return float(s)

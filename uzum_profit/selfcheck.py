# -*- coding: utf-8 -*-
"""`python3 -m uzum_profit selfcheck`: haqiqiy Uzum API bilan qisqa tekshiruv.

Faqat O'QISH (GET) so'rovlari; ma'lumot vaqtinchalik xotira bazasiga yuklanadi (uzum.db'ga tegilmaydi).
Chiqadigan matnda KALIT YO'Q: faqat holat kodlari, sonlar va maydon NOMLARI. Uni xavfsiz tarzda
Claude'ga yuborish mumkin.
"""
import platform
import sys
import time
from datetime import datetime, timezone

from .api import Uzum, UzumError
from .db import connect
from .sync import sync_api

EXPECTED = {
    "orders": ["id", "orderId", "skuTitle", "productId", "status", "date", "dateIssued", "sellPrice", "amount",
               "commission", "sellerProfit", "logisticDeliveryFee", "amountReturns"],
    "expenses": ["id", "dateCreated", "name", "source", "paymentPrice", "externalId", "code", "type"],
    "products": ["productId", "title", "skuList"],
    "sku": ["skuFullTitle", "skuId", "price", "commission", "barcode", "status", "quantitySold",
            "quantityReturned", "quantityDefected", "quantityAvailableByStockType"],
    "invoices": ["id", "invoiceNumber", "dateCreated", "invoiceStatus", "fullPrice", "totalAccepted",
                 "totalToStock", "hasIssue"],
}


def missing_keys(rows, expected):
    """Namunadagi qatorlarda hech uchramagan kutilgan maydonlar."""
    seen = set()
    for r in rows[:200]:
        if isinstance(r, dict):
            seen.update(k for k, v in r.items() if v is not None)
    return [k for k in expected if k not in seen]


def _keys(row):
    return sorted(row.keys()) if isinstance(row, dict) else []


def _shape(v, depth=0):
    """Qiymat tuzilishi: turlar va (son/mantiqiy bo'lsa) qiymat; matnlar yozilmaydi."""
    if isinstance(v, dict):
        if depth >= 4:
            return "{...}"
        return "{" + ", ".join("%s=%s" % (k, _shape(x, depth + 1)) for k, x in sorted(v.items())) + "}"
    if isinstance(v, list):
        return "[%d x %s]" % (len(v), _shape(v[0], depth + 1) if v else "-")
    if isinstance(v, (bool, int, float)):
        return repr(v)
    return "null" if v is None else "str"


def _probe(api, path, params, out, show_shape=False):
    """Noma'lum yo'lni sinab, holat va maydon nomlarini yozadi (qiymatlar yozilmaydi)."""
    try:
        data = api.get(path, params)
    except UzumError as e:
        out("  %-34s XATO: %s" % (path, str(e)[:160]))
        return None
    rows = data if isinstance(data, list) else None
    if rows is None and isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                rows = v
                break
            if isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, list):
                        rows = vv
                        break
    out("  %-34s OK, qatorlar: %s; maydonlar: %s" % (
        path, "?" if rows is None else len(rows), ", ".join(_keys(rows[0])) if rows else "-"))
    if show_shape and rows and isinstance(rows[0], dict):
        out("    tuzilishi: %s" % _shape(rows[0]))
    return rows


def run(key, days=7, out=print, api_factory=Uzum):
    t0 = time.time()
    out("== Uzum selfcheck ==")
    out("Python %s, %s, vaqt %s" % (platform.python_version(), platform.platform(),
                                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
    problems = 0
    api = api_factory(key, log=lambda s: None)
    try:
        shops = api.shops()
    except UzumError as e:
        out("DO'KONLAR: XATO: %s" % str(e)[:300])
        out("Kalit noto'g'ri, muddati o'tgan yoki Uzum bloklagan bo'lishi mumkin.")
        return 1
    out("Do'konlar: %s" % ", ".join("%s (%s)" % (s.get("name"), s.get("id")) for s in shops))

    date_from = int((datetime.now(timezone.utc).timestamp() - days * 86400) * 1000)
    for s in shops:
        sid = s["id"]
        inv_rows = []
        out("")
        out("-- %s (%s) --" % (s.get("name"), sid))
        for label, fetch, name in (("sotuvlar", lambda: api.orders(sid, date_from), "orders"),
                                   ("xarajatlar", lambda: api.expenses(sid, date_from), "expenses"),
                                   ("mahsulotlar", lambda: api.products(sid), "products"),
                                   ("fakturalar", lambda: api.invoices(sid), "invoices")):
            try:
                rows = fetch()
            except UzumError as e:
                out("  %-12s XATO: %s" % (label, str(e)[:200]))
                problems += 1
                continue
            exp = EXPECTED[name]
            if name == "products":
                skus = [k for p in rows for k in (p.get("skuList") or [])]
                miss = missing_keys(rows, exp)
                miss_sku = missing_keys(skus, EXPECTED["sku"])
                out("  %-12s %d ta mahsulot, %d ta SKU. Yo'q maydonlar: %s; SKU'da: %s" % (
                    label, len(rows), len(skus), miss or "yo'q", miss_sku or "yo'q"))
                problems += bool(miss or miss_sku)
            else:
                miss = missing_keys(rows, exp)
                out("  %-12s %d ta qator. Yo'q maydonlar: %s" % (label, len(rows), miss or "yo'q"))
                problems += bool(miss and rows)
                if name == "invoices":
                    inv_rows = rows
                    cnt = {}
                    for r in rows:
                        st = r.get("invoiceStatus")
                        st = st.get("value") if isinstance(st, dict) else st
                        cnt[st] = cnt.get(st, 0) + 1
                    out("    holatlar: %s" % cnt)
        out("  qo'shimcha so'rovlar (hisobotga hali kirmagan):")
        _probe(api, "/v1/shop/%s/return" % sid, {"page": 0, "size": 5}, out, True)
        def _st(r):
            st = r.get("invoiceStatus")
            return st.get("value") if isinstance(st, dict) else st
        cand = [r for r in inv_rows if _st(r) not in ("ACCEPTED", "CANCELED")] + inv_rows
        if cand and cand[0].get("id") is not None:
            out("  faktura holati: %s" % _st(cand[0]))
            _probe(api, "/v1/shop/%s/invoice/products" % sid, {"invoiceId": cand[0]["id"], "page": 0, "size": 5}, out, True)

    out("")
    out("-- To'liq yangilash sinovi: BUTUN TARIX (vaqtinchalik baza, uzum.db ga tegilmaydi) --")
    try:
        mem = connect(":memory:")
        counts = sync_api(mem, key, log=lambda m: out("  " + m.strip()))
        out("  OK: %s" % counts)
        from .util import ms_to_date
        for srow in mem.execute("SELECT id, name FROM shops"):
            lo, hi, n = mem.execute("SELECT MIN(created_ms), MAX(created_ms), COUNT(*) FROM order_items "
                                    "WHERE shop_id=?", (srow["id"],)).fetchone()
            tag = mem.execute("SELECT value FROM meta WHERE key=?", ("history_%s" % srow["id"],)).fetchone()
            out("  %s: %d ta sotuv, %s; tarix: %s" % (
                srow["name"], n, "%s dan %s gacha" % (ms_to_date(lo), ms_to_date(hi)) if lo else "yo'q",
                tag[0] if tag else "?"))
    except Exception as e:  # tekshiruv hisobotda ko'rinsin
        out("  XATO: %s" % str(e)[:300])
        problems += 1

    out("")
    try:
        from .rates import get_rate
        for ccy, day in (("CNY", None), ("USD", None), ("CNY", "2026-10-15"), ("USD", "2026-10-18")):
            r = get_rate(ccy, day)
            out("Bank kursi %s%s: %s so'm (%s)%s" % (ccy, " [so'raldi %s]" % day if day else "", r["rate"], r["date"],
                                                      " " + r["warn"] if r["warn"] else ""))
    except Exception as e:
        out("Bank kursi: XATO: %s" % str(e)[:200])
        problems += 1
    out("")
    out("Natija: %s (%.0f soniya)" % ("muammo topildi: %d" % problems if problems else "hammasi joyida",
                                     time.time() - t0))
    return 1 if problems else 0


def main(key):
    sys.exit(run(key))

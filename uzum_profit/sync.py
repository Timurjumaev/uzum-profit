# -*- coding: utf-8 -*-
"""API'dan (yoki uzum_history.json faylidan) ma'lumotlarni bazaga yuklash."""
import json
import re
from datetime import datetime, timezone

from .api import Uzum, UzumError
from .util import cfg
from .db import get_meta, set_meta

AD_RE = re.compile(r"olganida ([\d.]+) so")
ORDER_RE = re.compile(r"№\s*(\d+)")
AD_ID_RE = re.compile(r"^AD#(\d+)-")


def norm_code(code):
    """Uzum kodlarida kirill va lotin harflar aralash uchraydi: hammasini lotinga o'tkazamiz."""
    return (code or "").replace("С", "C").replace("У", "U")


def classify(code, source, name, typ):
    """Xarajat qatorini turiga ajratadi: ad, storage, fine, logistics, compensation..."""
    c, low = norm_code(code), (name or "").lower()
    if "kompensatsiya" in low:
        return "compensation"
    if c == "U000120" or source == "Marketing":
        return "ad"
    if c == "logistics-volume":
        return "logistics"
    if c == "return-logistics-volume":
        return "logistics_refund"
    if c in ("C000003", "C000004"):
        return "storage"
    if c == "C000007" or "jarima" in low:
        return "fine"
    if c.startswith("return-C") and typ == "INCOME":
        return "compensation"
    if source == "Ombor":
        return "storage"
    if source == "Logistika":
        return "logistics"
    return "other"


def _int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def upsert_shops(conn, shops):
    conn.executemany("INSERT OR REPLACE INTO shops (id, name) VALUES (?, ?)",
                     [(s["id"], s.get("name")) for s in shops])


def upsert_orders(conn, shop_id, rows):
    data = [(r["id"], shop_id, r.get("orderId"), r.get("skuTitle"), r.get("productId"),
             r.get("productTitle"), r.get("status"), r.get("date"), r.get("dateIssued"),
             _int(r.get("sellPrice")), _int(r.get("amount"), 1), _int(r.get("commission")),
             _int(r.get("sellerProfit")), _int(r.get("logisticDeliveryFee")),
             _int(r.get("amountReturns")), r.get("returnCause")) for r in rows]
    conn.executemany("INSERT OR REPLACE INTO order_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data)
    return len(data)


def upsert_expenses(conn, shop_id, rows):
    data = []
    for r in rows:
        name, ext, typ = r.get("name") or "", str(r.get("externalId") or ""), r.get("type")
        kind = classify(r.get("code"), r.get("source"), name, typ)
        price = float(r.get("paymentPrice") or 0)
        if kind == "ad":  # paymentPrice butun songa qirqilgan, aniq summa matnda
            m = AD_RE.search(name)
            if m:
                price = float(m.group(1))
        m = ORDER_RE.search(name)
        order_id = int(m.group(1)) if m else None
        item_id, m = None, AD_ID_RE.match(ext)
        if m:
            item_id = int(m.group(1))
        elif kind in ("logistics", "logistics_refund") and ext.isdigit():
            item_id = int(ext)
        data.append((r["id"], shop_id, r.get("dateCreated"), kind, typ, r.get("code"),
                     name, price, order_id, item_id))
    conn.executemany("INSERT OR REPLACE INTO expenses VALUES (?,?,?,?,?,?,?,?,?,?)", data)
    return len(data)


def upsert_products(conn, shop_id, rows):
    data = []
    for p in rows:
        for s in p.get("skuList") or []:
            if not s.get("skuFullTitle"):
                continue
            stock = s.get("quantityAvailableByStockType") or {}
            dim = s.get("skuDimension") or {}
            st = s.get("status")
            data.append((shop_id, s["skuFullTitle"], s.get("skuId"), p.get("productId"), p.get("title"),
                         str(s.get("barcode") or ""), s.get("commission"), _int(s.get("price")),
                         _int(stock.get("fbo")), _int(s.get("quantitySold")),
                         _int(s.get("quantityReturned")), _int(dim.get("weight")),
                         s.get("sellerItemCode"), st.get("value") if isinstance(st, dict) else st,
                         _int(s.get("quantityDefected"))))
    conn.executemany("INSERT OR REPLACE INTO skus VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data)
    return len(data)


def upsert_invoices(conn, shop_id, rows):
    data = []
    for r in rows:
        st = r.get("invoiceStatus")
        data.append((r["id"], shop_id, r.get("invoiceNumber"), r.get("dateCreated"),
                     st.get("value") if isinstance(st, dict) else r.get("status"),
                     _int(r.get("fullPrice")), _int(r.get("totalAccepted")),
                     _int(r.get("totalToStock")), 1 if r.get("hasIssue") else 0))
    conn.executemany("INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?)", data)
    return len(data)


def import_history(conn, path):
    """uzum_history.json faylini bazaga yuklaydi (API'ga murojaat qilmasdan)."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    shops = d.get("shops") or []
    if isinstance(shops, dict):
        shops = shops.get("payload") or []
    upsert_shops(conn, shops)
    counts = {"orders": 0, "expenses": 0, "products": 0, "invoices": 0}
    for sid, blk in (d.get("per_shop") or {}).items():
        sid = int(sid)
        counts["orders"] += upsert_orders(conn, sid, blk.get("orders", {}).get("rows", []))
        counts["expenses"] += upsert_expenses(conn, sid, blk.get("expenses", {}).get("rows", []))
        counts["products"] += upsert_products(conn, sid, blk.get("products", {}).get("rows", []))
        counts["invoices"] += upsert_invoices(conn, sid, blk.get("invoices", {}).get("rows", []))
    conn.commit()
    set_meta(conn, "last_import", datetime.now(timezone.utc).isoformat())
    return counts


HISTORY_FROM = "2020-01-01"          # Uzum Market'dan oldingi sana: "butun tarix" shu sanadan so'raladi
HISTORY_PAGES = 5000                 # butun tarix uchun sahifalar chegarasi (1 sahifa = 1000 qator)
FALLBACK_DAYS = (1825, 1095, 730, 365, 180, 100)   # Uzum butun tarixni bermasa, kamaytirib sinaymiz


def _ms(date_str):
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _pull_range(api, sid, start_ms, log, max_pages):
    return api.orders(sid, start_ms, max_pages=max_pages), api.expenses(sid, start_ms, max_pages=max_pages)


def _full_history(conn, api, sid, log):
    """Do'konning butun tarixi: avval eng eski sanadan, Uzum rad etsa qisqaroq davrlar bilan.
    Qaytaradi (orders, expenses, 'full' | 'limited:<kun>')."""
    now = datetime.now(timezone.utc).timestamp()
    tries = [(_ms(HISTORY_FROM), "full")] + [(int((now - d * 86400) * 1000), "limited:%d" % d) for d in FALLBACK_DAYS]
    last = None
    for start, tag in tries:
        try:
            log("  butun tarix so'ralmoqda" if tag == "full" else "  Uzum butun tarixni bermadi, %s kun sinab ko'riladi" % tag.split(":")[1])
            o, e = _pull_range(api, sid, start, log, HISTORY_PAGES)
            return o, e, tag
        except UzumError as ex:
            last = ex
            log("  rad etildi: %s" % str(ex)[:120])
    raise last


def sync_api(conn, key, days=None, log=print, full=False):
    """Uzum API'dan sotuv va xarajatlarni, hamma mahsulot va fakturalarni oladi.

    days=None (avtomatik, tavsiya): har bir do'kon uchun BIRINCHI marta butun tarix olinadi (do'kon qachon
    ochilgan bo'lsa ham: eng birinchi sotuvdan boshlab), keyingilarida faqat oxirgi SYNC_DAYS kun
    (oxirgi yangilanishdan beri uzoq vaqt o'tgan bo'lsa, o'sha oraliq ham).
    days=N: faqat oxirgi N kun. full=True: butun tarixni qayta oladi."""
    api = Uzum(key, log=log)
    shops = api.shops()
    upsert_shops(conn, shops)
    now = datetime.now(timezone.utc)
    counts = {"orders": 0, "expenses": 0}
    for s in shops:
        sid = s["id"]
        done_flag, new_tag = "history_%s" % sid, None
        if days is None and (full or not get_meta(conn, done_flag)):
            log(f"Do'kon: {s.get('name')} ({sid}), butun tarix")
            orders, expenses, new_tag = _full_history(conn, api, sid, log)
        else:
            if days is None:
                window = int(cfg("SYNC_DAYS", "30"))
                try:       # yangilanmay uzoq turilgan bo'lsa, oraliq ham qamrab olinadi
                    gap = (now - datetime.fromisoformat(get_meta(conn, "last_sync"))).days + 7
                    window = max(window, gap)
                except (TypeError, ValueError):
                    pass
            else:
                window = days
            log(f"Do'kon: {s.get('name')} ({sid}), oxirgi {window} kun")
            start = int((now.timestamp() - window * 86400) * 1000)
            orders, expenses = _pull_range(api, sid, start, log, 60)
        counts["orders"] += upsert_orders(conn, sid, orders)
        counts["expenses"] += upsert_expenses(conn, sid, expenses)
        for label, fetch, save in (("mahsulotlar", api.products, upsert_products),
                                   ("fakturalar", api.invoices, upsert_invoices)):
            try:  # bular muhim emas: xato bo'lsa sinxron to'xtamaydi
                save(conn, sid, fetch(sid))
            except UzumError as e:
                log(f"  {label}: o'tkazib yuborildi ({e})")
        conn.commit()
        if new_tag:
            set_meta(conn, done_flag, new_tag)
    set_meta(conn, "last_sync", datetime.now(timezone.utc).isoformat())
    return counts

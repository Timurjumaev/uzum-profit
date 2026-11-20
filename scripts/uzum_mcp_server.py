"""Uzum Seller API uchun LOKAL MCP server (faqat o'qish).

Claude Desktop / Claude Code shu serverga stdio orqali ulanadi va kabinetingizni tahlil qiladi:
do'konlar, tovarlar va qoldiq, sotuv va foyda (kun/oy/tovar/holat bo'yicha), xarajatlar, fakturalar,
qaytarishlar. Kalit faqat shu jarayonda (Mac'ingizda) qoladi — chatga yoki repozitoriyga tushmaydi.

Ishga tushirish: scripts/UZUM_MCP.md. Yagona tashqi bog'liqlik: `mcp` (pip install "mcp>=1.2").
Uzum bilan gaplashish uchun legacy `uzum_profit.api.Uzum` klienti ishlatiladi (faqat GET).

Eslatma: bu yerdagi "foyda" — Uzum bergan `sellerProfit` (F6: tushum − komissiya − logistika),
tannarxsiz. Tannarxli sof foyda — yangi tizimda (packages/core, F-formulalar).
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from uzum_profit.api import Uzum, UzumError  # noqa: E402
from uzum_profit.util import TZ, cfg, load_env  # noqa: E402

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

CACHE_TTL = int(cfg("UZUM_MCP_CACHE", "600"))  # sekund: bir xil so'rov qayta Uzum'ga bormaydi
MAX_ROWS = 200  # bitta javobdagi eng ko'p qator (kontekst to'lib ketmasligi uchun)
MAX_CHARS = 60000

mcp = _Server("uzum-seller")
_client = None
_cache = {}


def _err(msg):
    print(msg, file=sys.stderr, flush=True)


def client():
    global _client
    if _client is None:
        load_env()
        key = cfg("UZUM_API_KEY")
        if not key:
            raise UzumError("UZUM_API_KEY o'rnatilmagan (.env yoki MCP sozlamasidagi env)")
        _client = Uzum(key, log=_err)  # stdout — MCP kanali, log faqat stderr'ga
    return _client


def cached(key, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


# ---------- yordamchilar ----------
def D(v):
    try:
        return Decimal(str(v if v is not None else 0))
    except Exception:
        return Decimal(0)


def num(d):
    return int(d) if d == d.to_integral_value() else float(d)


def to_dt(v):
    """Millisekund, ISO yoki dd.MM.yyyy[ HH:mm] -> Toshkent vaqti."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        x = float(v)
        return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, TZ)
    s = str(v).strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19] if "T" in fmt else s, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=TZ)
    except ValueError:
        return None


def parse_day(s, default):
    if not s:
        return default
    d = to_dt(s)
    if d is None:
        raise ValueError(f"Sana tushunarsiz: {s!r} (YYYY-MM-DD yozing)")
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def period(date_from, date_to, default_days=30):
    now = datetime.now(TZ)
    end = parse_day(date_to, now.replace(hour=0, minute=0, second=0, microsecond=0)) + timedelta(
        days=1
    )
    start = parse_day(date_from, end - timedelta(days=default_days))
    return start, end


def ms(dt):
    return int(dt.timestamp() * 1000)


def rows_of(data):
    """Uzum javobidan qatorlar ro'yxatini ehtiyotkor ajratadi."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("payload", "content", "orderItems", "items", "rows", "data", "returns"):
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                r = rows_of(v)
                if r:
                    return r
    return []


def out(obj):
    s = json.dumps(obj, ensure_ascii=False, default=str, indent=1)
    if len(s) > MAX_CHARS:
        s = (
            s[:MAX_CHARS]
            + "\n... (qisqartirildi: so'rovni toraytiring — sana, limit yoki filtr bilan)"
        )
    return s


def fail(e):
    return out({"xato": str(e)})


# ---------- ma'lumot olish (keshli) ----------
def get_orders(shop_id, start):
    return cached(("orders", shop_id, ms(start)), lambda: client().orders(shop_id, ms(start)))


def get_expenses(shop_id, start):
    return cached(("expenses", shop_id, ms(start)), lambda: client().expenses(shop_id, ms(start)))


def get_products(shop_id):
    return cached(("products", shop_id), lambda: client().products(shop_id))


def in_period(rows, start, end, field="date"):
    res = []
    for r in rows:
        d = to_dt(r.get(field))
        if d is not None and start <= d < end:
            res.append(r)
    return res


def is_cancelled(r):
    return str(r.get("status") or "").upper().startswith("CANCEL")


# ---------- asboblar ----------
@mcp.tool()
def shops() -> str:
    """Kalitga ulangan do'konlar ro'yxati (id va nom). Boshqa asboblar uchun shop_id shu yerdan olinadi."""
    try:
        return out([{"id": s.get("id"), "name": s.get("name")} for s in client().shops()])
    except Exception as e:
        return fail(e)


@mcp.tool()
def sales_summary(
    shop_id: int, date_from: str = "", date_to: str = "", group_by: str = "month", top: int = 20
) -> str:
    """Do'kon sotuvlari va foydasi (Uzum `sellerProfit`, tannarxsiz) jamlanmasi.

    date_from/date_to — YYYY-MM-DD (bo'sh: oxirgi 30 kun). group_by: day | week | month | product | status.
    Bekor qilinganlar tushumga kirmaydi, alohida ko'rsatiladi. top — product/guruhlar soni chegarasi.
    """
    try:
        start, end = period(date_from, date_to)
        rows = in_period(get_orders(shop_id, start), start, end)
        if group_by not in ("day", "week", "month", "product", "status"):
            return fail("group_by: day | week | month | product | status")

        def key(r):
            if group_by == "status":
                return str(r.get("status"))
            if group_by == "product":
                return f"{r.get('productId')} | {r.get('productTitle')}"
            d = to_dt(r.get("date"))
            if group_by == "day":
                return d.strftime("%Y-%m-%d")
            if group_by == "week":
                y, w, _ = d.isocalendar()
                return f"{y}-H{w:02d}"
            return d.strftime("%Y-%m")

        groups = defaultdict(lambda: defaultdict(Decimal))
        total = defaultdict(Decimal)
        for r in rows:
            qty = D(r.get("amount") or 1)
            canc = is_cancelled(r)
            for g in (groups[key(r)], total):
                g["qatorlar"] += 1
                if canc:
                    g["bekor_dona"] += D(r.get("amountReturns")) or qty
                    continue
                g["dona"] += qty
                g["tushum"] += D(r.get("sellPrice")) * qty
                g["komissiya"] += D(r.get("commission"))
                g["logistika"] += D(r.get("logisticDeliveryFee"))
                g["uzum_foydasi"] += D(r.get("sellerProfit"))
                g["qaytgan_dona"] += D(r.get("amountReturns"))

        def fmt(g):
            return {k: num(v) for k, v in g.items()}

        items = sorted(
            groups.items(), key=lambda kv: kv[1]["uzum_foydasi"], reverse=(group_by == "product")
        )
        if group_by in ("day", "week", "month", "status"):
            items = sorted(groups.items())
        return out(
            {
                "davr": f"{start:%Y-%m-%d} .. {(end - timedelta(days=1)):%Y-%m-%d}",
                "jami": fmt(total),
                "guruh": group_by,
                "qatorlar": [{"kalit": k, **fmt(g)} for k, g in items[: max(1, min(top, 500))]],
                "eslatma": "uzum_foydasi = Uzum sellerProfit (tushum − komissiya − logistika), tannarxsiz",
            }
        )
    except Exception as e:
        return fail(e)


@mcp.tool()
def orders(
    shop_id: int,
    date_from: str = "",
    date_to: str = "",
    status: str = "",
    product_query: str = "",
    limit: int = 50,
) -> str:
    """Alohida sotuv qatorlari (ixcham). status: TO_WITHDRAW | PROCESSING | CANCELED ... (bo'sh: hammasi).
    product_query — tovar/SKU nomidan qidiruv. limit ≤ 200. Eng yangilari birinchi."""
    try:
        start, end = period(date_from, date_to)
        rows = in_period(get_orders(shop_id, start), start, end)
        q = product_query.lower()
        rows = [
            r
            for r in rows
            if (not status or str(r.get("status")).upper() == status.upper())
            and (not q or q in f"{r.get('productTitle')} {r.get('skuTitle')}".lower())
        ]
        rows.sort(key=lambda r: to_dt(r.get("date")), reverse=True)
        keys = (
            "id",
            "orderId",
            "date",
            "dateIssued",
            "status",
            "productTitle",
            "skuTitle",
            "sellPrice",
            "amount",
            "commission",
            "logisticDeliveryFee",
            "sellerProfit",
            "amountReturns",
            "returnCause",
            "purchasePrice",
        )
        return out(
            {
                "jami": len(rows),
                "korsatildi": min(len(rows), limit),
                "qatorlar": [
                    {k: r.get(k) for k in keys if k in r}
                    for r in rows[: max(1, min(limit, MAX_ROWS))]
                ],
            }
        )
    except Exception as e:
        return fail(e)


@mcp.tool()
def expenses_summary(
    shop_id: int, date_from: str = "", date_to: str = "", group_by: str = "code", top: int = 30
) -> str:
    """Xarajatlar (saqlash, reklama, jarimalar, pul yechish va h.k.) jamlanmasi.
    group_by: code | month | name. date_from/date_to — YYYY-MM-DD (bo'sh: oxirgi 30 kun)."""
    try:
        start, end = period(date_from, date_to)
        rows = in_period(get_expenses(shop_id, start), start, end, "dateCreated")
        groups = defaultdict(lambda: {"soni": 0, "summa": Decimal(0)})
        total = Decimal(0)
        for r in rows:
            if group_by == "month":
                k = to_dt(r.get("dateCreated")).strftime("%Y-%m")
            elif group_by == "name":
                k = str(r.get("name"))
            else:
                k = f"{r.get('code')} | {r.get('name')}"
            amount = D(r.get("paymentPrice"))
            groups[k]["soni"] += 1
            groups[k]["summa"] += amount
            total += amount
        items = sorted(groups.items(), key=lambda kv: abs(kv[1]["summa"]), reverse=True)
        if group_by == "month":
            items = sorted(groups.items())
        return out(
            {
                "davr": f"{start:%Y-%m-%d} .. {(end - timedelta(days=1)):%Y-%m-%d}",
                "jami_summa": num(total),
                "qatorlar_soni": len(rows),
                "guruhlar": [
                    {"kalit": k, "soni": g["soni"], "summa": num(g["summa"])}
                    for k, g in items[: max(1, min(top, 200))]
                ],
                "eslatma": "BALANCE_CORRECTION xarajat emas; bu yerda alohida ajratilmagan — kodga qarang",
            }
        )
    except Exception as e:
        return fail(e)


@mcp.tool()
def products(
    shop_id: int,
    query: str = "",
    sort_by: str = "sold",
    only_low_stock_below: int = -1,
    limit: int = 50,
) -> str:
    """Tovar (SKU) holati: narx, FBO qoldiq, sotilgan, qaytgan, brak. sort_by: sold | stock | price | returned.
    only_low_stock_below=N — qoldig'i N dan kam SKU'lar (-1: o'chiq). query — nom/kod bo'yicha qidiruv."""
    try:
        res = []
        q = query.lower()
        for p in get_products(shop_id):
            for s in p.get("skuList") or []:
                stock = s.get("quantityAvailableByStockType") or {}
                st = s.get("status")
                row = {
                    "sku": s.get("skuFullTitle"),
                    "skuId": s.get("skuId"),
                    "productId": p.get("productId"),
                    "tovar": p.get("title"),
                    "kod": s.get("sellerItemCode"),
                    "narx": s.get("price"),
                    "komissiya_foiz": s.get("commission"),
                    "fbo_qoldiq": stock.get("fbo"),
                    "fbs_qoldiq": stock.get("fbs"),
                    "sotilgan": s.get("quantitySold"),
                    "qaytgan": s.get("quantityReturned"),
                    "brak": s.get("quantityDefected"),
                    "tannarx_uzumda": s.get("purchasePrice"),
                    "holat": st.get("value") if isinstance(st, dict) else st,
                }
                if q and q not in f"{row['sku']} {row['tovar']} {row['kod']}".lower():
                    continue
                if only_low_stock_below >= 0 and D(row["fbo_qoldiq"]) >= only_low_stock_below:
                    continue
                res.append(row)
        keymap = {"sold": "sotilgan", "stock": "fbo_qoldiq", "price": "narx", "returned": "qaytgan"}
        k = keymap.get(sort_by, "sotilgan")
        res.sort(key=lambda r: D(r.get(k)), reverse=(sort_by != "stock"))
        return out(
            {
                "jami_sku": len(res),
                "korsatildi": min(len(res), limit),
                "sku_lar": res[: max(1, min(limit, MAX_ROWS))],
            }
        )
    except Exception as e:
        return fail(e)


@mcp.tool()
def invoices(shop_id: int, limit: int = 30) -> str:
    """FBO fakturalar (postavkalar): raqam, sana, holat, summa, qabul qilingan va omborga tushgan soni."""
    try:
        rows = cached(("invoices", shop_id), lambda: client().invoices(shop_id))
        res = []
        for r in rows:
            st = r.get("invoiceStatus")
            res.append(
                {
                    "id": r.get("id"),
                    "raqam": r.get("invoiceNumber"),
                    "sana": r.get("dateCreated"),
                    "holat": st.get("value") if isinstance(st, dict) else r.get("status"),
                    "summa": r.get("fullPrice"),
                    "qabul_qilingan": r.get("totalAccepted"),
                    "omborga": r.get("totalToStock"),
                    "muammo": bool(r.get("hasIssue")),
                }
            )
        return out({"jami": len(res), "fakturalar": res[: max(1, min(limit, MAX_ROWS))]})
    except Exception as e:
        return fail(e)


@mcp.tool()
def returns(shop_id: int = 0, limit: int = 50) -> str:
    """Qaytarishlar (`/v1/return`, butun akkaunt bo'yicha; shop_id berilsa shu do'kon qatorlari)."""
    try:

        def load():
            res, page = [], 0
            while page < 20:
                batch = rows_of(client().get("/v1/return", {"page": page, "size": 50}))
                res += batch
                if len(batch) < 50:
                    break
                page += 1
            return res

        rows = cached(("returns",), load)
        if shop_id:
            rows = [r for r in rows if r.get("shopId") in (None, shop_id)]
        return out({"jami": len(rows), "qaytarishlar": rows[: max(1, min(limit, 100))]})
    except Exception as e:
        return fail(e)


@mcp.tool()
def api_get(path: str, params_json: str = "{}") -> str:
    """Uzum Seller OpenAPI'ga xom GET so'rov (boshqa asboblar qamramagan joylar uchun: FBS buyurtmalar,
    FBS qoldiq va h.k.). path '/v1/...' yoki '/v2/...' bilan boshlanadi; params_json — JSON obyekt.
    Faqat o'qish. Javob uzun bo'lsa qisqartiriladi."""
    try:
        if not re.fullmatch(r"/v[0-9]+/[A-Za-z0-9_\-./]*", path) or ".." in path:
            return fail("path '/v1/...' ko'rinishida bo'lishi kerak")
        params = json.loads(params_json or "{}")
        if not isinstance(params, dict):
            return fail("params_json — JSON obyekt bo'lishi kerak")
        return out(client().get(path, params))
    except Exception as e:
        return fail(e)


@mcp.tool()
def clear_cache() -> str:
    """Keshni tozalaydi — keyingi so'rovlar Uzum'dan yangi ma'lumot oladi."""
    _cache.clear()
    return "Kesh tozalandi"


if __name__ == "__main__":
    mcp.run()

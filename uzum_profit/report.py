# -*- coding: utf-8 -*-
"""Foyda hisoboti: bosh sahifa va SKU jadvali uchun hisob-kitoblar.

Asosiy qoidalar:
  - Yakunlangan sotuv (TO_WITHDRAW) = haqiqiy foyda; kutilayotgan (PROCESSING) alohida,
    bekor bo'lish ehtimoli hisobga olingan koeffitsiyent bilan baholanadi.
  - Sotuvchi tushimi (sellerProfit) = narx*soni - komissiya - logistika (Uzum bergan raqam).
  - Reklama, saqlash va jarimalar Uzum hisobotida yo'q: xarajatlar oqimidan olinadi.
  - Tannarxi kiritilmagan sotuvlar foydaga qo'shilmaydi, alohida ko'rsatiladi.
  - Bepul logistika davrida (sozlanadi) "standart tarifdagi foyda" ham hisoblanadi.
"""
from .costs import CostBook
from .util import cfg, cfg_num, day_end_ms, day_start_ms, ms_to_date

GROUPS = {"TO_WITHDRAW": "done", "PROCESSING": "pending", "CANCELED": "canceled"}


def free_window():
    """Uzum logistika va saqlashni bepul qilgan davr (.env orqali o'zgartiriladi)."""
    return cfg("FREE_LOGISTICS_FROM", "2026-10-10"), cfg("FREE_LOGISTICS_TO", "2026-10-31")


def std_fee_map(conn, shop_id):
    """Har SKU uchun oxirgi ma'lum pullik logistika (1 dona) va umumiy standart qiymat."""
    last, fees = {}, []
    for r in conn.execute("SELECT sku, logistics_fee, amount FROM order_items "
                          "WHERE shop_id=? AND logistics_fee>0 AND amount>0 ORDER BY created_ms", (shop_id,)):
        per = r["logistics_fee"] / r["amount"]
        last[(r["sku"] or "").lower()] = per
        fees.append(per)
    default = max(set(fees), key=fees.count) if fees else cfg_num("STD_LOGISTICS", 5250)
    return last, default


def enriched_items(conn, shop_id, d_from, d_to):
    """Davrdagi sotuv qatorlari: tannarx, reklama va bepul logistika effekti bilan."""
    ms_from, ms_to = day_start_ms(d_from), day_end_ms(d_to)
    book = CostBook(conn, shop_id)
    last_fee, default_fee = std_fee_map(conn, shop_id)
    f_from, f_to = free_window()
    ads = {r["item_id"]: r["p"] for r in conn.execute(
        "SELECT item_id, SUM(price) p FROM expenses WHERE shop_id=? AND kind='ad' AND type='OUTCOME' "
        "AND item_id IS NOT NULL GROUP BY item_id", (shop_id,))}
    items = []
    for r in conn.execute("SELECT * FROM order_items WHERE shop_id=? AND created_ms BETWEEN ? AND ? "
                          "ORDER BY created_ms", (shop_id, ms_from, ms_to)):
        date = ms_to_date(r["created_ms"])
        group = GROUPS.get(r["status"], "other")
        unit_cost, flags = book.unit_cost(r["sku"], date)
        free = 0.0
        if group != "canceled" and r["logistics_fee"] == 0 and f_from <= date <= f_to:
            free = last_fee.get((r["sku"] or "").lower(), default_fee) * r["amount"]
        items.append({
            "id": r["id"], "date": date, "group": group, "sku": r["sku"], "title": r["title"],
            "amount": r["amount"], "revenue": r["sell_price"] * r["amount"],
            "commission": r["commission"], "logistics": r["logistics_fee"],
            "seller_profit": r["seller_profit"], "issued": r["issued_ms"] is not None,
            "ads": ads.get(r["id"], 0.0), "unit_cost": unit_cost, "approx": "early" in flags, "nocargo": "nocargo" in flags,
            "cogs": unit_cost * r["amount"] if unit_cost is not None else None,
            "free_saving": free})
    return items


def _blank():
    return dict(n=0, units=0, revenue=0, commission=0, logistics=0, seller_profit=0,
                k_n=0, k_units=0, k_revenue=0, k_commission=0, k_logistics=0, k_seller_profit=0,
                cogs=0.0, free_saving=0.0, k_free_saving=0.0, nocargo_n=0)


def summarize(items):
    S = {g: _blank() for g in ("done", "pending", "other")}
    canc = {"n": 0, "after_pickup": 0}
    for it in items:
        if it["group"] == "canceled":
            canc["n"] += 1
            canc["after_pickup"] += 1 if it["issued"] else 0
            continue
        s = S[it["group"]]
        s["n"] += 1
        s["units"] += it["amount"]
        s["revenue"] += it["revenue"]
        s["commission"] += it["commission"]
        s["logistics"] += it["logistics"]
        s["seller_profit"] += it["seller_profit"]
        s["free_saving"] += it["free_saving"]
        if it["cogs"] is not None:  # tannarxi ma'lum sotuvlar
            s["k_n"] += 1
            s["k_units"] += it["amount"]
            s["k_revenue"] += it["revenue"]
            s["k_commission"] += it["commission"]
            s["k_logistics"] += it["logistics"]
            s["k_seller_profit"] += it["seller_profit"]
            s["cogs"] += it["cogs"]
            s["k_free_saving"] += it["free_saving"]
            s["nocargo_n"] += 1 if it["nocargo"] else 0
    return S, canc


def expense_totals(conn, shop_id, d_from, d_to):
    d = {"ad": 0.0, "storage": 0.0, "fine": 0.0, "compensation": 0.0}
    for r in conn.execute("SELECT kind, type, SUM(price) p FROM expenses WHERE shop_id=? "
                          "AND created_ms BETWEEN ? AND ? GROUP BY kind, type",
                          (shop_id, day_start_ms(d_from), day_end_ms(d_to))):
        if r["kind"] in ("ad", "storage", "fine") and r["type"] == "OUTCOME":
            d[r["kind"]] += r["p"]
        elif r["kind"] == "compensation" and r["type"] == "INCOME":
            d["compensation"] += r["p"]
    return d


def raw_report(conn, shop_id, d_from, d_to):
    items = enriched_items(conn, shop_id, d_from, d_to)
    S, canc = summarize(items)
    name = conn.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
    return {"name": name["name"] if name else str(shop_id), "from": d_from, "to": d_to,
            "done": S["done"], "pending": S["pending"], "other": S["other"], "canceled": canc,
            "ex": expense_totals(conn, shop_id, d_from, d_to)}


def _add(a, b):
    if isinstance(a, dict):
        return {k: _add(a[k], b[k]) for k in a}
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return a + b
    return a


def build_report(conn, shop_ids, d_from, d_to):
    """Bitta yoki bir nechta do'kon uchun yig'ilgan hisobot (hosilaviy ko'rsatkichlar bilan)."""
    reports = [raw_report(conn, sid, d_from, d_to) for sid in shop_ids]
    r = reports[0]
    for x in reports[1:]:
        r = _add(r, x)
    if len(reports) > 1:
        r["name"] = "Hamma do'konlar"
    done, pend, ex = r["done"], r["pending"], r["ex"]
    realization = cfg_num("PENDING_REALIZATION", 0.75)
    r["realization"] = realization
    r["extras"] = ex["ad"] + ex["storage"] + ex["fine"] - ex["compensation"]
    r["net_before_cogs"] = done["seller_profit"] - r["extras"]      # tannarxsiz: Uzum sof tushimi - reklama/saqlash/jarima
    r["profit_before_extras"] = done["k_seller_profit"] - done["cogs"]
    r["profit"] = r["profit_before_extras"] - r["extras"]
    r["profit_std"] = r["profit"] - done["k_free_saving"]
    r["pending_expected"] = (pend["k_seller_profit"] - pend["cogs"]) * realization
    r["pending_std_expected"] = (pend["k_seller_profit"] - pend["cogs"] - pend["k_free_saving"]) * realization
    finished = done["n"] + r["canceled"]["n"]
    r["cancel_rate"] = r["canceled"]["n"] / finished if finished else None
    r["margin"] = r["profit"] / done["k_revenue"] if done["k_revenue"] else None
    r["roi"] = r["profit"] / done["cogs"] if done["cogs"] else None
    r["free_saving_total"] = done["free_saving"] + pend["free_saving"] + r["other"]["free_saving"]
    r["miss_n"] = done["n"] - done["k_n"]
    r["nocargo_n"] = done["nocargo_n"]   # tannarxida kargo hali yo'q sotuvlar
    r["miss_revenue"] = done["revenue"] - done["k_revenue"]
    return r


def sku_rows(conn, shop_id, d_from, d_to):
    """SKU bo'yicha yakunlangan sotuvlar foydasi."""
    items = enriched_items(conn, shop_id, d_from, d_to)
    info = {(r["sku"] or "").lower(): r for r in conn.execute("SELECT * FROM skus WHERE shop_id=?", (shop_id,))}
    agg = {}
    for it in items:
        if it["group"] != "done":
            continue
        a = agg.setdefault(it["sku"], dict(sku=it["sku"], title=it["title"], units=0, revenue=0,
                                           commission=0, logistics=0, ads=0.0, cogs=0.0, k_units=0,
                                           k_revenue=0, profit=0.0, free=0.0, miss_units=0, approx=False, nocargo=False))
        a["units"] += it["amount"]
        a["revenue"] += it["revenue"]
        a["commission"] += it["commission"]
        a["logistics"] += it["logistics"]
        a["ads"] += it["ads"]
        if it["cogs"] is None:
            a["miss_units"] += it["amount"]
        else:
            a["k_units"] += it["amount"]
            a["k_revenue"] += it["revenue"]
            a["cogs"] += it["cogs"]
            a["profit"] += it["seller_profit"] - it["ads"] - it["cogs"]
            a["free"] += it["free_saving"]
            a["approx"] = a["approx"] or it["approx"]
            a["nocargo"] = a["nocargo"] or it["nocargo"]
    rows = []
    for a in agg.values():
        ku = a["k_units"]
        a["avg_cost"] = a["cogs"] / ku if ku else None
        a["profit_unit"] = a["profit"] / ku if ku else None
        a["profit_unit_std"] = (a["profit"] - a["free"]) / ku if ku else None
        a["margin"] = a["profit"] / a["k_revenue"] if a["k_revenue"] else None
        i = info.get((a["sku"] or "").lower())
        # Uzumning o'z ta'rifi (returnedPercentage): qaytgan / (sotilgan + qaytgan)
        total = (i["qty_sold"] + i["qty_returned"]) if i else 0
        a["return_pct"] = 100.0 * i["qty_returned"] / total if total else None
        a["stock"] = i["qty_fbo"] if i else None
        rows.append(a)
    rows.sort(key=lambda a: (a["avg_cost"] is None, -a["profit"]))
    return rows

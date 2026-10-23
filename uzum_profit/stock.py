# -*- coding: utf-8 -*-
"""Ombor sahifasi: qoldiq, yo'ldagi partiyalar, sotuv tezligi va qachon buyurtma berish kerakligi.

Qoidalar (hammasi sahifada ham yozilgan):
  - Sotuv tezligi = oxirgi 30 kundagi BEKOR QILINMAGAN buyurtmalar soni / kun
    (30 kunda sotuv bo'lmasa, 60 kun olinadi). Yangi SKU uchun kunlar soni kamida 7 (yoki SKU yoshi).
  - Zaxira kunlari = FBO qoldiq / sotuv tezligi.
  - Holat faqat Uzum omboridagi (FBO) qoldiqqa qarab beriladi; yo'ldagi tovar alohida ko'rsatiladi.
  - Buyurtma muddati LEAD_DAYS (.env, standart 30 kun): buyurtmadan tovar Uzum omborida sotuvga chiqquncha.
"""
from datetime import datetime, timedelta

from .batches_pages import batch_title, chips_html
from .costs import CostBook, batch_state, batch_totals, load_batches
from .db import connect
from .ui import EMPTY, card, esc, layout, money
from .util import cfg_num, day_end_ms, day_start_ms, fmt, ms_to_date, today

BUFFER_DAYS = 14                       # "yaqinlashmoqda": muddatdan shuncha kun oldin ogohlantirish
MIN_VELOCITY = 0.2                     # kuniga shundan kam sotiladigan SKU'lar alohida (yig'ilgan) bo'limga tushadi
WINDOWS = (14, 30, 60)
MIN_DAYS = 7                           # tezlik kamida shuncha kunga bo'linadi (1-2 kunlik sakrash aldamasin)
HIDDEN_STATUSES = ("ARCHIVED", "ARCHIVED_BLOCKED")
ORDER = {"out": 0, "order": 1, "soon": 2, "ok": 3, "nosales": 4}
LABEL = {"out": ("Tugagan", "bad"), "order": ("Buyurtma vaqti", "bad"), "soon": ("Yaqinlashmoqda", "warn"),
         "ok": ("Yetarli", "ok"), "nosales": ("Sotuv yo'q", "")}


def lead_days():
    return max(1, int(cfg_num("LEAD_DAYS", 30)))


def _shift(date, days):
    return (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def _between(a, b):
    """a dan b gacha necha kun (b - a)."""
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def classify(stock, velocity, lead):
    """(kod, zaxira_kunlari). Kod: out | order | soon | ok | nosales."""
    if not velocity or velocity <= 0:
        return "nosales", None
    if stock <= 0:
        return "out", 0.0
    cover = stock / velocity
    if cover <= lead:
        return "order", cover
    if cover <= lead + BUFFER_DAYS:
        return "soon", cover
    return "ok", cover


def sales_stats(conn, shop_id, now):
    """{sku_kichik: {'u': {14: dona, 30: dona, 60: dona}, 'first': birinchi_buyurtma_sanasi}}."""
    starts = [day_start_ms(_shift(now, -(w - 1))) for w in WINDOWS]
    sql = ("SELECT sku, MIN(created_ms) AS first_ms, " + ", ".join(
        "SUM(CASE WHEN COALESCE(status, '') != 'CANCELED' AND created_ms >= ? THEN amount ELSE 0 END) AS u%d" % w
        for w in WINDOWS) +
        " FROM order_items WHERE shop_id=? AND created_ms <= ? AND sku IS NOT NULL AND sku != '' GROUP BY sku")
    out = {}
    for r in conn.execute(sql, tuple(starts) + (shop_id, day_end_ms(now))):
        e = out.setdefault(r["sku"].lower(), {"u": dict.fromkeys(WINDOWS, 0), "first": None})
        for w in WINDOWS:
            e["u"][w] += r["u%d" % w] or 0
        d = ms_to_date(r["first_ms"])
        if e["first"] is None or d < e["first"]:
            e["first"] = d
    return out


def velocities(stat, now):
    """{14: v, 30: v, 60: v} dona/kun."""
    if not stat:
        return dict.fromkeys(WINDOWS, 0.0)
    age = _between(stat["first"], now) + 1 if stat["first"] else 0
    return {w: stat["u"][w] / float(max(MIN_DAYS, min(w, age))) for w in WINDOWS}


def transit_batches(conn, shop_ids, now, lead):
    """Kargo narxi hali kiritilmagan partiyalar = hali qo'lga olinmagan (yo'ldagi) tovar."""
    out = []
    for sid in shop_ids:
        for b in load_batches(conn, sid):
            if b.get("cargo_usd") is not None:
                continue
            age = max(0, _between(b["date"], now))
            out.append({"batch": b, "state": batch_state(b), "totals": batch_totals(b), "age": age,
                        "eta": _shift(b["date"], lead), "late": age > lead + 15})
    out.sort(key=lambda x: (x["batch"]["date"], x["batch"]["id"]))
    return out


def stock_rows(conn, shop_ids, now=None):
    """(qatorlar, ko'rsatilmagan_soni). Qatorlar shoshilinchlik bo'yicha tartiblangan."""
    now, lead = now or today(), lead_days()
    shops = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM shops")}
    rows, hidden = [], 0
    for sid in shop_ids:
        stats, book = sales_stats(conn, sid, now), CostBook(conn, sid)
        transit = {}
        for b in load_batches(conn, sid):
            if b.get("cargo_usd") is None:
                for l in b["lines"]:
                    if l.get("sku"):
                        transit[l["sku"].lower()] = transit.get(l["sku"].lower(), 0) + l["qty"]
        for r in conn.execute("SELECT * FROM skus WHERE shop_id=? ORDER BY sku", (sid,)):
            if (r["status"] or "") in HIDDEN_STATUSES:
                continue
            key = r["sku"].lower()
            stock, defected, tr = r["qty_fbo"] or 0, r["qty_defected"] or 0, transit.get(key, 0)
            v = velocities(stats.get(key), now)
            base = v[30] or v[60]
            if not (stock or defected or tr or base):
                hidden += 1
                continue
            code, cover = classify(stock, base, lead)
            order_by = None
            if code in ("out", "order"):
                order_by = "hozir"
            elif code in ("soon", "ok"):
                left = int(cover - lead)
                order_by = "hozir" if left <= 0 else _shift(now, left)
            cost, flags = book.unit_cost(r["sku"], now)
            rows.append({
                "shop_id": sid, "shop": shops.get(sid, str(sid)), "sku": r["sku"], "title": r["title"] or "",
                "stock": stock, "defected": defected, "transit": tr, "v": v, "base": base, "code": code,
                "cover": cover, "order_by": order_by, "unit_cost": cost,
                "value": cost * stock if cost is not None else None,
                "defect_value": cost * defected if cost is not None else None,
                "nocargo": "nocargo" in flags})
    # tugaganlar: ko'p sotiladigani birinchi; qolganlari: tezroq tugaydigani birinchi
    rows.sort(key=lambda x: (ORDER[x["code"]], 0 if x["code"] == "out" else (x["cover"] or 0), -x["base"], x["sku"]))
    return rows, hidden


# ---------------------------------------------------------------- sahifa

def _rate(x):
    if not x:
        return "0"
    return "%.1f" % x if x >= 0.095 else "%.2f" % x


def _cover(x):
    return "—" if x is None else (">999 kun" if x > 999 else "%d kun" % round(x))


def _tag(code):
    text, kind = LABEL[code]
    return '<span class="tag tag-%s">%s</span>' % (kind, esc(text)) if kind else '<span class="tag">%s</span>' % esc(text)


def sku_table(rows, multi_shop):
    head = ["SKU", "Holat", "FBO qoldiq", "Yo'lda", "Sotuv/kun", "Kunga yetadi", "Buyurtma sanasi",
            "Tannarx", "Qoldiq qiymati", "Brak"]
    heads = "".join('<th class="l">%s</th>' % h if h in ("SKU", "Holat") else "<th>%s</th>" % h for h in head)
    out = []
    for x in rows:
        title = x["title"] if len(x["title"]) <= 60 else x["title"][:59].rstrip() + "…"
        sub = esc(title) + (" · " + esc(x["shop"]) if multi_shop else "")
        cost = "—" if x["unit_cost"] is None else money(x["unit_cost"]) + (
            ' <span class="mut" title="partiyada kargo narxi hali kiritilmagan">~</span>' if x["nocargo"] else "")
        out.append(
            '<tr><td class="l">%s<span class="sub">%s</span></td><td class="l">%s</td><td>%d</td><td>%s</td>'
            '<td>%s<span class="sub nw">14k: %s · 60k: %s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                esc(x["sku"]), sub, _tag(x["code"]), x["stock"], x["transit"] or "—",
                _rate(x["base"]), _rate(x["v"][14]), _rate(x["v"][60]), _cover(x["cover"]),
                x["order_by"] or "—", cost, "—" if x["value"] is None else money(x["value"]),
                x["defected"] or "—"))
    if rows:
        out.append('<tr class="sum"><td class="l">Jami</td><td></td><td>%d</td><td>%d</td><td></td><td></td><td></td>'
                   '<td></td><td>%s</td><td>%d</td></tr>' % (
                       sum(x["stock"] for x in rows), sum(x["transit"] for x in rows),
                       money(sum(x["value"] or 0 for x in rows)), sum(x["defected"] for x in rows)))
    body = "".join(out) or '<tr><td class="l mut" colspan="10">Ko\'rsatadigan SKU yo\'q</td></tr>'
    return '<div class="wrap"><table><tr>' + heads + "</tr>" + body + "</table></div>"


def transit_table(items, shops):
    if not items:
        return ('<p class="mut">Yo\'lda partiya yo\'q: hamma partiyada kargo narxi kiritilgan. Xitoyga yangi buyurtma '
                'bergan bo\'lsangiz, <a href="/batches/new">partiya oching</a> (faqat tovar CNY va kursi yetadi).</p>')
    head = ["Partiya", "Do'kon", "Buyurtma sanasi", "Necha kun o'tdi", "Taxminiy omborda", "Dona", "Sarflangan (so'm)", "Holat"]
    heads = "".join('<th class="l">%s</th>' % h if h in ("Partiya", "Do'kon", "Holat") else "<th>%s</th>" % h for h in head)
    rows = []
    for it in items:
        b, st = it["batch"], it["state"]
        late = ' <span class="tag tag-warn" title="Tovar kelgan bo\'lsa, kargo narxini kiriting">kechikdi?</span>' if it["late"] else ""
        units = "%d" % st["units"] if st["units"] else "—"
        rows.append(
            '<tr><td class="l"><a href="/batches/%d">%s</a></td><td class="l">%s</td><td>%s</td><td>%d%s</td><td>%s</td>'
            '<td>%s</td><td>%s</td><td class="l">%s</td></tr>' % (
                b["id"], esc(batch_title(b)), esc(shops.get(b["shop_id"], b["shop_id"])), esc(b["date"]),
                it["age"], late, esc(it["eta"]), units, money(it["totals"]["total"]), chips_html(b, st)))
    return '<div class="wrap"><table><tr>' + heads + "</tr>" + "".join(rows) + "</table></div>"


def invoice_block(conn, shop_ids):
    marks = ",".join("?" * len(shop_ids))
    rows = conn.execute(
        "SELECT * FROM invoices WHERE shop_id IN (%s) AND COALESCE(status, '') NOT IN ('ACCEPTED', 'CANCELED') "
        "ORDER BY id DESC" % marks, tuple(shop_ids)).fetchall()
    if not rows:
        return ""
    shops = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM shops")}
    body = "".join(
        '<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td>%s</td><td class="l">%s</td></tr>' % (
            esc(r["number"]), esc(shops.get(r["shop_id"], r["shop_id"])), esc(r["date_created"]), money(r["full_price"]),
            esc(r["status"]) + (' <span class="tag tag-bad">muammo bor</span>' if r["has_issue"] else ""))
        for r in rows)
    return ('<h2>Uzum omboriga yuborilgan, hali qabul qilinmagan fakturalar</h2><div class="wrap"><table><tr>'
            '<th class="l">Faktura</th><th class="l">Do\'kon</th><th class="l">Sana</th><th>Narxi</th>'
            '<th class="l">Holat</th></tr>' + body + "</table></div>"
            '<p class="mut">Faktura ichidagi SKU ro\'yxati hali yuklanmaydi, shuning uchun bu tovar qoldiqqa kirmaydi.</p>')


def page_stock(q):
    conn = connect()
    shops = conn.execute("SELECT id, name FROM shops ORDER BY name").fetchall()
    if not shops:
        return layout("Ombor", EMPTY, "/stock")
    sel = q.get("shop", ["all"])[0]
    ids = [s["id"] for s in shops if sel in ("all", str(s["id"]))]
    if not ids:
        sel, ids = "all", [s["id"] for s in shops]
    now, lead = today(), lead_days()
    rows, hidden = stock_rows(conn, ids, now)
    transit = transit_batches(conn, ids, now, lead)
    active = [x for x in rows if x["code"] != "nosales"]
    main = [x for x in active if x["base"] >= MIN_VELOCITY]
    slow = [x for x in active if x["base"] < MIN_VELOCITY]
    dead = [x for x in rows if x["code"] == "nosales"]
    count = dict.fromkeys(ORDER, 0)
    for x in main:
        count[x["code"]] += 1
    stock_units, stock_value = sum(x["stock"] for x in rows), sum(x["value"] or 0 for x in rows)
    with_stock = [x for x in rows if x["stock"]]
    no_cost = sum(1 for x in with_stock if x["unit_cost"] is None)
    defected, defect_value = sum(x["defected"] for x in rows), sum(x["defect_value"] or 0 for x in rows)
    transit_units = sum(t["state"]["units"] for t in transit)
    transit_spent = sum(t["totals"]["total"] for t in transit)
    need = count["out"] + count["order"]
    opts = '<option value="all">Hamma do\'konlar</option>' + "".join(
        '<option value="%s"%s>%s</option>' % (s["id"], " selected" if str(s["id"]) == sel else "", esc(s["name"]))
        for s in shops)
    cards = ('<div class="cards">' +
             card("Omborda (FBO)", "%s dona" % fmt(stock_units),
                  "tannarx kiritilmagan" if with_stock and no_cost == len(with_stock) else
                  "tannarxda %s so'm%s" % (money(stock_value), " (%d SKU'da tannarx yo'q)" % no_cost if no_cost else "")) +
             card("Yo'lda", "%s dona" % fmt(transit_units), "%d ta partiya, sarflangan %s so'm" % (len(transit), money(transit_spent))) +
             card("Buyurtma kerak", "%d ta SKU" % need, "yaqinlashmoqda: %d ta" % count["soon"], "bad" if need else "good") +
             (card("Brak (yaroqsiz)", "%d dona" % defected, "tannarxda %s so'm" % money(defect_value), "bad") if defected else "") +
             "</div>")
    note = ('<p class="mut">Buyurtma muddati: <b>%d kun</b> (buyurtmadan tovar Uzum omborida sotuvga chiqquncha; '
            '<code>.env</code> dagi <code>LEAD_DAYS</code> bilan o\'zgartiring).</p>'
            '<details><summary>Qanday hisoblanadi?</summary><p class="mut">Sotuv tezligi = oxirgi 30 kundagi bekor '
            'qilinmagan buyurtmalar / kun (30 kunda sotuv bo\'lmasa, 60 kun; yangi SKU uchun kamida 7 kunga bo\'linadi). '
            'Zaxira kunlari = FBO qoldiq / sotuv tezligi. Holat faqat Uzum omboridagi (FBO) qoldiqqa qarab beriladi: '
            '<b>buyurtma vaqti</b> = qoldiq %d kundan kam vaqtga yetadi, <b>yaqinlashmoqda</b> = %d kun ichida buyurtma '
            'berish kerak bo\'ladi. Yo\'ldagi tovar holatga ta\'sir qilmaydi, uni o\'zingiz solishtiring. Tugagan SKU\'larda '
            'haqiqiy talab ko\'rsatilganidan yuqori bo\'lishi mumkin (qoldiq yo\'q kunlarda sotuv ham bo\'lmagan). '
            'Kuniga %s dondan kam sotiladigan SKU\'lar pastda alohida ro\'yxatda.</p></details>'
            % (lead, lead, BUFFER_DAYS, MIN_VELOCITY))
    hid = ('<p class="mut">Yana %d ta SKU\'da qoldiq ham, oxirgi 60 kunda sotuv ham yo\'q: ko\'rsatilmadi.</p>' % hidden
           if hidden else "")
    multi = len(ids) > 1
    slow_html = ('<details><summary>Kam sotiladigan SKU\'lar (kuniga %s dondan kam): %d ta</summary>%s</details>'
                 % (MIN_VELOCITY, len(slow), sku_table(slow, multi)) if slow else "")
    dead_html = ('<details><summary>Omborda bor, lekin oxirgi 60 kunda sotilmagan: %d ta SKU, %d dona (tannarxda %s so\'m)'
                 '</summary>%s</details>' % (len(dead), sum(x["stock"] for x in dead),
                                              money(sum(x["value"] or 0 for x in dead)), sku_table(dead, multi))
                 if dead else "")
    body = ('<h1>Ombor</h1><form class="filters" method="get" action="/stock"><label>Do\'kon<select name="shop">%s</select>'
            '</label><button>Ko\'rsat</button></form>%s%s<h2>Yo\'ldagi partiyalar</h2>%s<h2>SKU bo\'yicha qoldiq va buyurtma vaqti</h2>%s%s%s%s'
            % (opts, cards, note, transit_table(transit, {sh['id']: sh['name'] for sh in shops}), sku_table(main, multi),
               slow_html, dead_html, hid + invoice_block(conn, ids)))
    return layout("Ombor", body, "/stock")

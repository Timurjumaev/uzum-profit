# -*- coding: utf-8 -*-
"""Partiya formasi: yaratish va tahrirlash (bir xil forma), tekshirish va saqlash.

Partiya bosqichma-bosqich to'ldiriladi: faqat tovar uchun CNY va CNY kursi shart.
Mahsulot qatorlari, kargo va qo'shimcha chiqimlar keyin ham qo'shiladi (tahrirlash orqali).
"""
import json
import math

from .costs import load_batch, match_sku, sku_catalog, sku_options
from .ui import esc, layout, valid_date
from .util import to_num, today


def numstr(x):
    """Raqamni formaga qo'yish uchun: 2000.0 -> '2000', 1712.5 -> '1712.5'."""
    if x is None:
        return ""
    x = float(x)
    if x == int(x):
        return str(int(x))
    return ("%.4f" % x).rstrip("0").rstrip(".")


def blank_state(shops):
    return {"shop": str(shops[0]["id"]) if shops else "", "date": today(), "title": "", "goods_cny": "",
            "cny_rate": "", "cargo_usd": "", "usd_rate": "", "cargo_date": "", "note": "",
            "lines": [], "extras": []}


def state_from_batch(b):
    return {"shop": str(b["shop_id"]), "date": b["date"], "title": b.get("title") or "",
            "goods_cny": numstr(b["goods_cny"]), "cny_rate": numstr(b["cny_rate"]),
            "cargo_usd": numstr(b["cargo_usd"]), "usd_rate": numstr(b["usd_rate"]) if b.get("usd_rate") else "",
            "cargo_date": b.get("cargo_date") or "", "note": b.get("note") or "",
            "lines": [{"text": l.get("sku") or l.get("label") or "", "sku": l.get("sku") or "",
                       "qty": str(l["qty"]), "cny": numstr(l["cny_unit"])} for l in b["lines"]],
            "extras": [{"amount": numstr(e["amount"]), "name": e["name"] or ""} for e in b["extras"]]}


def _json(obj):
    """<script> ichiga xavfsiz JSON (</script> va & belgilari ekranlanadi)."""
    return (json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")
            .replace(">", "\\u003e").replace("&", "\\u0026"))


def render_form(conn, state, errors=None, batch_id=None):
    shops = conn.execute("SELECT id, name FROM shops ORDER BY name").fetchall()
    catalog = {str(s["id"]): [list(o) for o in sku_options(conn, s["id"])] for s in shops}
    initial = {"lines": state["lines"], "extras": state["extras"]}
    title = "Yangi partiya" if batch_id is None else "Partiya #%d: tahrirlash" % batch_id
    action = "/batches/new" if batch_id is None else "/batches/%d/edit" % batch_id
    opts = "".join('<option value="%s"%s>%s</option>' % (
        s["id"], " selected" if str(s["id"]) == state["shop"] else "", esc(s["name"])) for s in shops)
    err = "".join('<div class="warn err">%s</div>' % esc(e) for e in (errors or []))

    def val(k):
        return esc(state.get(k, ""))

    body = (
        "<h1>" + esc(title) + "</h1>" + err +
        '<form id="bform" class="f" method="post" action="' + action + '" autocomplete="off">'
        '<fieldset class="sec" id="order"><legend>1. Xitoydan buyurtma</legend>'
        '<p class="hintp">Faqat shu qism shart. Mahsulotlar, kargo va chiqimlarni keyinroq ham qo\'shsa bo\'ladi.</p>'
        '<div class="grid2"><label>Do\'kon<select id="shop" name="shop">' + opts + '</select></label>'
        '<label>Buyurtma (to\'lov) sanasi<input id="date" type="date" name="date" value="' + val("date") + '"></label></div>'
        '<label>Partiya nomi (ixtiyoriy: o\'zingiz tanishingiz uchun)'
        '<input name="title" maxlength="80" placeholder="masalan: Qizil kurtka, oktyabr" value="' + val("title") + '"></label>'
        '<div class="grid2"><label>Tovar uchun jami to\'lov, CNY (narx + komissiya)'
        '<input id="goods_cny" name="goods_cny" inputmode="decimal" value="' + val("goods_cny") + '"></label>'
        '<label>CNY kursi (1 CNY = ? so\'m)<span class="inline">'
        '<input id="cny_rate" name="cny_rate" inputmode="decimal" style="flex:1" value="' + val("cny_rate") + '">'
        '<button type="button" class="ghost" id="fetch-cny">Bank kursi</button></span>'
        '<span class="rate-note" id="note-cny"></span></label></div></fieldset>'

        '<fieldset class="sec" id="lines-sec"><legend>2. Mahsulotlar (SKU)</legend>'
        '<p class="hintp">Do\'kondagi SKU\'ni qidirib tanlang (masalan «spo» deb yozing), soni yoniga yoziladi. '
        'Kartochkasi hali yo\'q yangi tovar bo\'lsa, «Yangi tovar» tugmasini bosing: nom (ixtiyoriy), soni va narxini '
        'yozasiz, SKU chiqqach shu qatorni tahrirlab biriktirasiz. '
        'Yangi SKU ko\'rinmasa, avval yuqoridagi «API\'dan yangilash»ni bosing.</p>'
        '<label class="inline"><input type="checkbox" id="per-price"> '
        'Mahsulotlar narxi har xil (har qatorga CNY narx yozaman)</label>'
        '<div id="lines" class="lines"></div>'
        '<div class="btns"><button type="button" class="add" id="add-line">+ Mahsulot qo\'shish (SKU tanlash)</button>'
        '<button type="button" class="add" id="add-new">+ Yangi tovar (kartochkasi hali yo\'q)</button></div></fieldset>'

        '<fieldset class="sec" id="cargo"><legend>3. Kargo (narxi chiqqanda)</legend>'
        '<p class="hintp">Kargo narxi odatda tovar O\'zbekistonga kelib, qo\'lingizga olganingizda ma\'lum bo\'ladi. '
        'Hozircha bo\'sh qoldiring: partiya «kargo kiritilmagan» deb belgilanadi, tannarx kargosiz hisoblanadi. '
        'Kargo bo\'lmasa, 0 yozing.</p>'
        '<div class="grid2"><label>Kargo, USD (butun partiya uchun)'
        '<input name="cargo_usd" inputmode="decimal" value="' + val("cargo_usd") + '"></label>'
        '<label>USD kursi (1 USD = ? so\'m)<span class="inline">'
        '<input id="usd_rate" name="usd_rate" inputmode="decimal" style="flex:1" value="' + val("usd_rate") + '">'
        '<button type="button" class="ghost" id="fetch-usd">Bank kursi</button></span>'
        '<span class="rate-note" id="note-usd"></span></label></div>'
        '<label>Kargo to\'langan (tovar qo\'lga olingan) sana'
        '<input id="cargo_date" type="date" name="cargo_date" value="' + val("cargo_date") + '"></label>'
        '<p class="hintp">Bu sana tannarx qaysi sotuvlardan boshlab hisobga olinishini belgilaydi: '
        'shundan oldingi sotuvlar eski partiyalar tannarxi bilan hisoblanadi. Tovar buyurtmadan keyin '
        'kelgan bo\'lsa, kelgan sanani yozing (bo\'sh qoldirsangiz, buyurtma sanasi olinadi).</p></fieldset>'

        '<fieldset class="sec" id="extras"><legend>4. Qo\'shimcha chiqimlar</legend>'
        '<p class="hintp">Shtrix kod rulon, paket, skotch, Uzum omboriga logistika va hokazo. '
        'Chiqim bo\'lsa, tugmani bosing: summani va nima uchun ekanini yozasiz.</p>'
        '<div id="extras-rows"></div>'
        '<button type="button" class="add" id="add-extra">+ Qo\'shimcha chiqim qo\'shish</button></fieldset>'

        '<label>Izoh<input name="note" value="' + val("note") + '"></label>'
        '<div class="btns"><button class="save">Saqlash</button><a href="' +
        ("/batches" if batch_id is None else "/batches/%d" % batch_id) + '">Bekor qilish</a></div></form>'
        '<script id="catalog" type="application/json">' + _json(catalog) + '</script>'
        '<script id="initial" type="application/json">' + _json(initial) + '</script>'
        '<script src="/static/batch_form.js"></script>')
    return layout(title, body, "/batches")


def _num(raw, label, required=False, positive=False):
    """(qiymat | None, xato | None)."""
    raw = (raw or "").strip()
    if raw == "":
        return None, ("%s kiritilmagan." % label) if required else None
    try:
        x = to_num(raw)
    except ValueError:
        return None, "%s: '%s' raqam emas." % (label, raw)
    if not math.isfinite(x) or x < 0 or (positive and x == 0):
        return None, "%s noto'g'ri (%s bo'lishi kerak)." % (label, "0 dan katta" if positive else "manfiy bo'lmagan son")
    return x, None


def parse_form(form, conn):
    """Formani tekshiradi. (state, errors, data) qaytaradi: state xato bo'lsa formani qayta chizish uchun."""
    def first(k):
        return (form.get(k) or [""])[0].strip()

    def many(k):
        return [v.strip() for v in (form.get(k) or [])]

    errors = []
    state = {k: first(k) for k in ("shop", "date", "title", "goods_cny", "cny_rate",
                                   "cargo_usd", "usd_rate", "cargo_date", "note")}
    state["title"] = state["title"][:80]
    d = {"title": state["title"], "note": state["note"]}

    try:
        d["shop"] = int(state["shop"])
        if not conn.execute("SELECT 1 FROM shops WHERE id=?", (d["shop"],)).fetchone():
            raise ValueError
    except ValueError:
        d["shop"] = None
        errors.append("Do'kon tanlanmagan.")
    d["date"] = valid_date(state["date"], None)
    if d["date"] is None:
        errors.append("Buyurtma sanasi noto'g'ri.")

    def take(key, label, **kw):
        v, e = _num(state[key], label, **kw)
        if e:
            errors.append(e)
        return v

    d["goods_cny"] = take("goods_cny", "Tovar uchun to'lov (CNY)", required=True, positive=True)
    d["cny_rate"] = take("cny_rate", "CNY kursi", required=True, positive=True)
    d["cargo_usd"] = take("cargo_usd", "Kargo (USD)")           # None = hali kiritilmagan
    need_rate = d["cargo_usd"] is not None and d["cargo_usd"] > 0
    d["usd_rate"] = take("usd_rate", "USD kursi", required=need_rate, positive=need_rate)
    d["cargo_date"] = None
    if state["cargo_date"]:
        d["cargo_date"] = valid_date(state["cargo_date"], None)
        if d["cargo_date"] is None:
            errors.append("Kargo sanasi noto'g'ri.")

    # --- mahsulot qatorlari (forma tartibida, qator raqami ko'rinadigan tartib) ---
    catalog = sku_catalog(conn, d["shop"]) if d["shop"] is not None else []
    texts, skus, qtys, cnys = many("line_text"), many("line_sku"), many("line_qty"), many("line_cny")
    n = max(len(texts), len(skus), len(qtys), len(cnys))
    pad = lambda lst: lst + [""] * (n - len(lst))  # noqa: E731
    texts, skus, qtys, cnys = pad(texts), pad(skus), pad(qtys), pad(cnys)
    state["lines"], d["lines"], seen = [], [], set()
    for i in range(n):
        text, sku_h, qty_raw, cny_raw = texts[i], skus[i], qtys[i], cnys[i]
        if not (text or sku_h or qty_raw or cny_raw):
            continue
        tag = "%d-qator" % (i + 1)
        canonical = None
        for cand in (sku_h, text):
            if cand:
                canonical, _ = match_sku(cand, catalog)
                if canonical:
                    break
        state["lines"].append({"text": canonical or text or sku_h, "sku": canonical or "",
                               "qty": qty_raw, "cny": cny_raw})
        name = canonical or text or sku_h
        if not name:                       # nomi yo'q yangi tovar: soni va narxi baribir kiritiladi
            name = "Nomsiz tovar (%s)" % tag
            state["lines"][-1]["text"] = name
        line_ok = True
        qty, e = _num(qty_raw, tag + ": soni", required=True, positive=True)
        if e:
            errors.append(e)
            line_ok = False
        elif qty != int(qty):
            errors.append("%s: soni butun son bo'lishi kerak." % tag)
            line_ok = False
        cny, e = _num(cny_raw, tag + ": CNY narxi", positive=True)
        if e:
            errors.append(e)
            line_ok = False
        key = canonical.lower() if canonical else "nom:" + name.lower()
        if key in seen:
            errors.append("%s: \u00ab%s\u00bb takrorlangan. Bitta qatorga jamlab yozing." % (tag, name))
            line_ok = False
        seen.add(key)
        if line_ok:
            d["lines"].append({"sku": canonical, "label": None if canonical else name,
                               "qty": int(qty), "cny_unit": cny})

    # --- qo'shimcha chiqimlar ---
    amounts, names = many("extra_amount"), many("extra_name")
    m = max(len(amounts), len(names))
    amounts, names = amounts + [""] * (m - len(amounts)), names + [""] * (m - len(names))
    state["extras"], d["extras"] = [], []
    for i in range(m):
        if not (amounts[i] or names[i]):
            continue
        state["extras"].append({"amount": amounts[i], "name": names[i]})
        amt, e = _num(amounts[i], "%d-chiqim summasi" % (i + 1), required=True, positive=True)
        if e:
            errors.append(e)
        else:
            d["extras"].append({"name": names[i] or "Chiqim", "amount": amt})
    return state, errors, d


def save_batch(conn, d, batch_id=None):
    """Yangi partiya yaratadi yoki mavjudini yangilaydi (qatorlar va chiqimlar qayta yoziladi)."""
    cols = (d["shop"], d["date"], d["goods_cny"], d["cny_rate"], d["cargo_usd"], d["usd_rate"],
            d["note"], d["title"], d["cargo_date"])
    try:
        if batch_id is None:
            cur = conn.execute("INSERT INTO batches (shop_id, date, goods_cny, cny_rate, cargo_usd, usd_rate, "
                               "note, title, cargo_date) VALUES (?,?,?,?,?,?,?,?,?)", cols)
            batch_id = cur.lastrowid
        else:
            conn.execute("UPDATE batches SET shop_id=?, date=?, goods_cny=?, cny_rate=?, cargo_usd=?, usd_rate=?, "
                         "note=?, title=?, cargo_date=? WHERE id=?", cols + (batch_id,))
            conn.execute("DELETE FROM batch_lines WHERE batch_id=?", (batch_id,))
            conn.execute("DELETE FROM batch_extras WHERE batch_id=?", (batch_id,))
        conn.executemany("INSERT INTO batch_lines (batch_id, sku, qty, cny_unit, label) VALUES (?,?,?,?,?)",
                         [(batch_id, l["sku"], l["qty"], l["cny_unit"], l["label"]) for l in d["lines"]])
        conn.executemany("INSERT INTO batch_extras (batch_id, name, amount) VALUES (?,?,?)",
                         [(batch_id, e["name"], e["amount"]) for e in d["extras"]])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return batch_id


def edit_state(conn, batch_id):
    b = load_batch(conn, batch_id)
    return state_from_batch(b) if b else None

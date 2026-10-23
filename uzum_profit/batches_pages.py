# -*- coding: utf-8 -*-
"""Partiyalar ro'yxati va partiya sahifasi (holat belgilari bilan)."""
from .costs import batch_state, batch_summary, batch_totals, batch_warnings, load_batch, load_batches
from .ui import card, esc, layout, money
from .util import fmt


def chips_html(batch, st):
    """Qaysi bosqich yetishmayotgani: bosilganda tahrirlash sahifasining kerakli joyiga olib boradi."""
    base = "/batches/%d/edit" % batch["id"]
    items = []
    if st["no_lines"]:
        items.append(("Mahsulotlar kiritilmagan", "warn", base + "#lines-sec"))
    elif st["unlinked"]:
        items.append(("SKU biriktirilmagan: %d qator" % st["unlinked"], "warn", base + "#lines-sec"))
    if st["cargo_missing"]:
        items.append(("Kargo narxi kiritilmagan", "warn", base + "#cargo"))
    if st["complete"]:
        items.append(("To'liq", "ok", None))
    out = []
    for text, kind, href in items:
        cls = "chip chip-" + kind
        out.append('<a class="%s" href="%s">%s</a>' % (cls, href, esc(text)) if href
                   else '<span class="%s">%s</span>' % (cls, esc(text)))
    return '<div class="chips">' + "".join(out) + "</div>"


def batch_title(b):
    return "#%d" % b["id"] + (" " + b["title"] if b.get("title") else "")


def page_batches(conn, flash=""):
    shops = {s["id"]: s["name"] for s in conn.execute("SELECT id, name FROM shops")}
    rows, incomplete = [], 0
    for b in sorted(load_batches(conn), key=lambda x: (x["date"], x["id"]), reverse=True):
        st, t, s = batch_state(b), batch_totals(b), batch_summary(b)
        incomplete += 0 if st["complete"] else 1
        cargo = "—" if b["cargo_usd"] is None else fmt(b["cargo_usd"], 2)
        rows.append(
            '<tr><td class="l"><a href="/batches/%d">%s</a></td><td class="l">%s</td><td class="l">%s</td>'
            '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class="l">%s</td></tr>' % (
                b["id"], esc(batch_title(b)), esc(b["date"]), esc(shops.get(b["shop_id"], b["shop_id"])),
                st["units"] or "—", fmt(b["goods_cny"], 2), cargo, money(t["total"]),
                money(s["avg"]) if s["avg"] is not None else "—", chips_html(b, st)))
    head = ["Partiya", "Sana", "Do'kon", "Dona", "Tovar (CNY)", "Kargo (USD)", "Jami sarf (so'm)",
            "O'rtacha tannarx", "Holat"]
    heads = "".join('<th class="l">%s</th>' % h if h in ("Do'kon", "Sana", "Partiya", "Holat")
                    else "<th>%s</th>" % h for h in head)
    table = ('<div class="wrap"><table><tr>' + heads + "</tr>" +
             ("".join(rows) or '<tr><td class="l mut" colspan="9">Hali partiya yo\'q</td></tr>') +
             "</table></div>")
    note = ('<p class="mut">%d ta partiya to\'liq emas: belgiga bosib yetishmayotgan qismni to\'ldiring.</p>' % incomplete
            if incomplete else "")
    body = ('<h1>Partiyalar</h1><p><a class="btnlink" href="/batches/new">+ Yangi partiya</a></p>' + note + table)
    return layout("Partiyalar", body, "/batches", flash)


def page_batch(conn, bid, flash=""):
    b = load_batch(conn, bid)
    if not b:
        return None
    shop = conn.execute("SELECT name FROM shops WHERE id=?", (b["shop_id"],)).fetchone()
    st, t, s = batch_state(b), batch_totals(b), batch_summary(b)
    edit = "/batches/%d/edit" % bid
    warns = list(batch_warnings(b))
    if st["cargo_missing"]:
        warns.append("Kargo narxi hali kiritilmagan: tannarx kargosiz hisoblangan, "
                     "kargo qo'shilgach o'zgaradi.")
    if st["unlinked"]:
        warns.append("SKU biriktirilmagan qatorlar foyda hisobiga kirmaydi. Mahsulot kartochkasi chiqqach, "
                     "tahrirlab SKU biriktiring.")
    if st["no_lines"]:
        warns.append("Mahsulotlar kiritilmagan: dona soni noma'lum, shuning uchun 1 dona tannarxi hisoblanmaydi.")
    cargo_val = "kiritilmagan" if b["cargo_usd"] is None else "%s so'm" % money(t["cargo"])
    cargo_note = ("narxi chiqqach qo'shiladi" if b["cargo_usd"] is None
                  else "%s USD × %s" % (fmt(b["cargo_usd"], 2), fmt(b["usd_rate"] or 0, 2)))
    cards = ('<div class="cards">' +
             card("Tovar (Xitoy)", "%s so'm" % money(t["goods"]), "%s CNY × %s" % (fmt(b["goods_cny"], 2), fmt(b["cny_rate"], 2))) +
             card("Kargo", cargo_val, cargo_note) +
             card("Qo'shimcha chiqimlar", "%s so'm" % money(t["extras"]), "%d ta" % len(b["extras"])) +
             card("Jami sarf", "%s so'm" % money(t["total"]), "shu paytgacha") +
             card("O'rtacha tannarx (dona)", money(s["avg"]) if s["avg"] is not None else "—",
                  "%d dona" % s["units"] if s["units"] else "dona soni noma'lum") + "</div>")
    rows = ""
    for r in s["rows"]:
        tag = ("" if r["sku"] else ' <a class="tag tag-warn" href="%s#lines-sec">SKU yo\'q</a>' % edit)
        rows += ('<tr><td class="l">%s%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                 '<td><b>%s</b></td><td>%s</td></tr>' % (
                     esc(r["name"]), tag, r["qty"], fmt(r["cny_unit"], 2), money(r["goods"]),
                     "—" if b["cargo_usd"] is None else money(r["cargo"]), money(r["extras"]),
                     money(r["unit_cost"]), money(r["unit_cost"] * r["qty"])))
    head = ["Mahsulot", "Soni", "CNY narx", "Tovar (so'm)", "Kargo", "Qo'shimcha", "Tannarx (dona)", "Jami"]
    heads = "".join('<th class="l">%s</th>' % h if h == "Mahsulot" else "<th>%s</th>" % h for h in head)
    if rows:
        rows += ('<tr class="sum"><td class="l">Jami</td><td>%d</td><td></td><td></td><td></td><td></td><td>%s</td>'
                 '<td>%s</td></tr>' % (s["units"], money(s["avg"]), money(s["total"])))
    table = ('<div class="wrap"><table><tr>' + heads + "</tr>" + rows + "</table></div>") if rows else ""
    extras = "".join("<li>%s: %s so'm</li>" % (esc(e["name"]), money(e["amount"])) for e in b["extras"]) or "<li>yo'q</li>"
    eff = ""
    if b.get("cargo_date"):
        eff = '<p class="mut">Tannarx %s dan boshlab sotuvlarga qo\'llanadi (kargo to\'langan sana).</p>' % esc(b["cargo_date"])
    body = (
        "<h1>Partiya " + esc(batch_title(b)) + "</h1>"
        '<p class="mut">' + esc(shop["name"] if shop else b["shop_id"]) + " · buyurtma sanasi " + esc(b["date"]) + "</p>"
        + chips_html(b, st) + "".join('<div class="warn">%s</div>' % esc(w) for w in warns) + cards + eff +
        '<div class="btns"><a class="btnlink" href="' + edit + '">Tahrirlash</a>'
        '<a class="btnlink ghost" href="' + edit + '#extras">+ Qo\'shimcha chiqim</a></div>'
        + table + "<h2>Qo'shimcha chiqimlar</h2><ul>" + extras + "</ul>"
        + ('<p class="mut">%s</p>' % esc(b["note"]) if b.get("note") else "")
        + '<form method="post" action="/batches/%d/delete" '
          'onsubmit="return confirm(&quot;Partiyani o\'chirasizmi?&quot;)">'
          '<p><button class="danger">O\'chirish</button></p></form>' % bid)
    return layout("Partiya " + batch_title(b), body, "/batches", flash)


def delete_batch(conn, bid):
    for table in ("batch_lines", "batch_extras"):
        conn.execute("DELETE FROM %s WHERE batch_id=?" % table, (bid,))
    conn.execute("DELETE FROM batches WHERE id=?", (bid,))
    conn.commit()

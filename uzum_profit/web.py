# -*- coding: utf-8 -*-
"""Mahalliy veb-interfeys (faqat standart kutubxona).

Ishga tushirish:  python3 -m uzum_profit serve   ->   http://127.0.0.1:8000
"""
import json
import os
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import report as rpt
from .batches_form import blank_state, edit_state, parse_form, render_form, save_batch
from .batches_pages import delete_batch, page_batch, page_batches
from .costs import load_batch
from .db import connect, get_meta
from .rates import RateError, get_rate
from .stock import page_stock
from .sync import sync_api
from .ui import (EMPTY, card, esc, filters_form, layout, money, pct, signed, tr, valid_date)
from .util import cfg, days_ago, today

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MIME = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
MAX_BODY = 1000000


def page_dashboard(q):
    conn = connect()
    shops = conn.execute("SELECT id, name FROM shops ORDER BY name").fetchall()
    flash = q.get("msg", [""])[0]
    if not shops:
        return layout("Bosh sahifa", EMPTY, "/", flash)
    sel = q.get("shop", ["all"])[0]
    d_from = valid_date(q.get("from", [""])[0], days_ago(29))
    d_to = valid_date(q.get("to", [""])[0], today())
    ids = [s["id"] for s in shops if sel in ("all", str(s["id"]))] or [shops[0]["id"]]
    R = rpt.build_report(conn, ids, d_from, d_to)
    done, pend, ex, canc = R["done"], R["pending"], R["ex"], R["canceled"]
    body = [f'<h1>{esc(R["name"])}: {d_from} — {d_to}</h1>', filters_form("/", shops, sel, d_from, d_to)]
    if R["miss_n"]:
        body.append(f'<div class="warn"><b>{R["miss_n"]} ta yakunlangan sotuvning tannarxi kiritilmagan</b> '
                    f'(tushim {money(R["miss_revenue"])} so\'m): ular foydaga qo\'shilmagan. '
                    f'<a href="/batches/new">Partiya kiriting</a>.</div>')
    if R["nocargo_n"]:
        body.append(f'<div class="warn"><b>{R["nocargo_n"]} ta sotuvning tannarxi kargosiz hisoblangan</b>: '
                    f'partiyada kargo narxi hali kiritilmagan, shuning uchun foyda hozircha yuqoriroq ko\'rinadi. '
                    f'Kargo narxi chiqqach <a href="/batches">Partiyalar</a>da to\'ldiring.</div>')
    prof = R["profit"]
    if done["k_n"] == 0:
        c_profit = card("Haqiqiy foyda", "—", "tannarx kiritilmagan")
    else:
        note = f"marja {pct(R['margin'])}, ROI {pct(R['roi'])}"
        if R["miss_n"]:
            note = f"faqat tannarxi kiritilgan {done['k_n']} / {done['n']} sotuv bo'yicha (taxminiy)"
        c_profit = card("Haqiqiy foyda", f"{money(prof)} so'm", note, "good" if prof >= 0 else "bad")
    c_pend = card("Kutilayotgan foyda", "—" if pend["k_n"] == 0 else f"{money(R['pending_expected'])} so'm",
                  f"qayta ishlanmoqdagilar × {R['realization']:g} (bekor bo'lishi hisobga olingan)")
    c_std = card("Standart tarifdagi foyda", "—" if done["k_n"] == 0 else f"{money(R['profit_std'])} so'm",
                 "bepul logistikasiz: narx qarorlari uchun shuni oling")
    body.append('<div class="cards">' + card(
        "Tannarxgacha sof tushim", f"{money(R['net_before_cogs'])} so'm",
        "Uzum sof tushimi − reklama − saqlash − jarima") + c_profit + c_pend + c_std + "</div>")
    pc = lambda a, b: pct(a / b) if b else "—"  # noqa: E731
    body.append("<h2>Uzum hisob-kitobi (yakunlangan sotuvlar)</h2><div class=\"wrap\"><table>" + "".join([
        tr("Sotuv tushimi", money(done["revenue"]), f'{done["n"]} qator, {done["units"]} dona'),
        tr("− Uzum komissiyasi", signed(-done["commission"]), pc(done["commission"], done["revenue"])),
        tr("− Uzum logistikasi", signed(-done["logistics"]), pc(done["logistics"], done["revenue"])),
        tr("= Uzum bergan sof tushim", money(done["seller_profit"]), "", "sum"),
        tr("− Reklama", signed(-ex["ad"]), "hisobotda yo'q xarajat"),
        tr("− Saqlash", signed(-ex["storage"]), "hisobotda yo'q xarajat"),
        tr("− Jarimalar", signed(-ex["fine"]), "hisobotda yo'q xarajat"),
        tr("+ Kompensatsiyalar", signed(ex["compensation"]), ""),
        tr("= Tannarxgacha sof tushim", signed(R["net_before_cogs"]), "", "sum")]) + "</table></div>")
    if done["k_n"]:
        body.append("<h2>Tannarx va foyda</h2><div class=\"wrap\"><table>" + "".join([
            tr("Tannarxi kiritilgan sotuvlar", f'{done["k_n"]} / {done["n"]} qator',
               f'{done["k_units"]} dona, tushim {money(done["k_revenue"])}'),
            tr("Ularning Uzum sof tushimi", money(done["k_seller_profit"]), ""),
            tr("− Tannarx", signed(-done["cogs"]), "partiyalardan (o'rtacha)"),
            tr("= Foyda (reklama va boshqalargacha)", signed(R["profit_before_extras"]), "", "sum"),
            tr("− Reklama, saqlash, jarima (+ kompensatsiya)", signed(-R["extras"]), "butun davr bo'yicha"),
            tr("= Haqiqiy foyda", signed(prof), "", "sum")]) + "</table></div>")
    body.append("<h2>Kutilayotgan va bekor qilinganlar</h2><div class=\"wrap\"><table>" + "".join([
        tr("Qayta ishlanmoqda", f'{pend["n"]} qator',
           f'Uzum sof tushimi {money(pend["seller_profit"])}'),
        tr("Bekor qilingan", f'{canc["n"]} qator',
           f'yakunlanganlar orasida {pct(R["cancel_rate"])}; {canc["after_pickup"]} tasi xaridor olib ketgandan keyin qaytgan'),
    ]) + "</table></div>")
    if R["free_saving_total"] > 0:
        f1, f2 = rpt.free_window()
        body.append(f'<h2>Bepul logistika davri ({f1} — {f2})</h2><div class="wrap"><table>' + tr(
            "Tejalgan logistika (taxminiy)", money(R["free_saving_total"]),
            "bu davr tugagach foyda shuncha kamayadi") + "</table></div>")
    last = get_meta(conn, "last_sync") or get_meta(conn, "last_import") or "—"
    body.append(f'<p class="mut">Oxirgi yangilanish: {esc(last[:19].replace("T", " "))} UTC</p>')
    return layout("Bosh sahifa", "".join(body), "/", flash)


def page_skus(q):
    conn = connect()
    shops = conn.execute("SELECT id, name FROM shops ORDER BY name").fetchall()
    if not shops:
        return layout("SKU foyda", EMPTY, "/skus")
    sel = q.get("shop", [str(shops[0]["id"])])[0]
    if sel == "all" or not any(str(s["id"]) == sel for s in shops):
        sel = str(shops[0]["id"])
    d_from = valid_date(q.get("from", [""])[0], days_ago(29))
    d_to = valid_date(q.get("to", [""])[0], today())
    rows = rpt.sku_rows(conn, int(sel), d_from, d_to)
    head = ["SKU", "Dona", "Tushim", "O'rtacha tannarx", "Foyda", "Foyda/dona", "Standart tarifda /dona",
            "Marja", "Qaytgan %", "Qoldiq (FBO)"]
    out = []
    for a in rows:
        flag = ""
        if a["miss_units"]:
            flag = f' <span class="neg" title="{a["miss_units"]} dona uchun tannarx yo\'q">⚠ tannarx yo\'q</span>'
        elif a["approx"]:
            flag = ' <span class="mut" title="sotuv sanasigacha partiya bo\'lmagan">~</span>'
        if a["nocargo"] and not a["miss_units"]:
            flag += ' <span class="mut" title="partiyada kargo narxi hali kiritilmagan: tannarx kargosiz">kargosiz</span>'
        ret = "—" if a["return_pct"] is None else "%.0f%%" % a["return_pct"]
        stock = "—" if a["stock"] is None else a["stock"]
        pu = "—" if a["profit_unit"] is None else signed(a["profit_unit"])
        pus = "—" if a["profit_unit_std"] is None else signed(a["profit_unit_std"])
        out.append(
            f'<tr><td class="l">{esc(a["sku"])}{flag}</td><td>{a["units"]}</td><td>{money(a["revenue"])}</td>'
            f'<td>{money(a["avg_cost"])}</td><td>{signed(a["profit"])}</td><td>{pu}</td><td>{pus}</td>'
            f'<td>{pct(a["margin"])}</td><td>{ret}</td><td>{stock}</td></tr>')
    table = ('<div class="wrap"><table><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
             + ("".join(out) or '<tr><td class="l mut" colspan="10">Bu davrda yakunlangan sotuv yo\'q</td></tr>')
             + "</table></div>")
    body = (f'<h1>SKU bo\'yicha foyda</h1>{filters_form("/skus", shops, sel, d_from, d_to, with_all=False)}'
            f'<p class="mut">Foyda = Uzum bergan sof tushim − reklama − tannarx. Tannarxi kiritilmagan SKU\'lar '
            f'foydaga qo\'shilmaydi. "Qaytgan %" Uzum hisoblagichidan olinadi.</p>{table}')
    return layout("SKU foyda", body, "/skus")


def run_sync():
    key = cfg("UZUM_API_KEY")
    if not key:
        return "UZUM_API_KEY topilmadi: loyiha papkasidagi .env fayliga yozing (README'ga qarang)."
    conn = connect()
    has = conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    days = int(cfg("SYNC_DAYS", "30")) if has else int(cfg("FIRST_SYNC_DAYS", "120"))
    try:
        c = sync_api(conn, key, days, log=lambda s: None)
        return f"Yangilandi: {c['orders']} sotuv va {c['expenses']} xarajat qatori ({days} kun)."
    except Exception as e:  # foydalanuvchiga xato matnini ko'rsatamiz
        return f"Yangilashda xato: {e}"


def page_form(state=None, errors=None, batch_id=None):
    conn = connect()
    shops = conn.execute("SELECT id, name FROM shops ORDER BY name").fetchall()
    if not shops:
        return layout("Yangi partiya", EMPTY, "/batches")
    return render_form(conn, state or blank_state(shops), errors, batch_id)


def page_edit(bid, state=None, errors=None):
    conn = connect()
    st = state or edit_state(conn, bid)
    return None if st is None else render_form(conn, st, errors, bid)


def api_rate(q):
    """Markaziy bank kursi (faqat tavsiya): {ok, rate, date, warn} yoki {ok: false, error}."""
    ccy = q.get("ccy", [""])[0].upper()
    date = valid_date(q.get("date", [""])[0], None)
    try:
        r = get_rate(ccy, date)
    except RateError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "rate": r["rate"], "date": r["date"], "warn": r.get("warn", "")}


def static_file(name):
    """(bayt, mime) | None. Faqat static/ papkadagi oddiy .js/.css fayllar."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        return None
    ext = os.path.splitext(name)[1].lower()
    path = os.path.join(STATIC_DIR, name)
    if ext not in MIME or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read(), MIME[ext]


def not_found(what="Sahifa"):
    return layout("Topilmadi", "<h1>%s topilmadi</h1>" % esc(what), "/batches" if what == "Partiya" else "")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _write(self, data, code=200, ctype="text/html; charset=utf-8", cache=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def _send(self, body, code=200):
        self._write(body.encode("utf-8"), code)

    def _json(self, obj, code=200):
        self._write(json.dumps(obj, ensure_ascii=False).encode("utf-8"), code,
                    "application/json; charset=utf-8", "no-store")

    def _redirect(self, url):
        self.send_response(303)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _host_ok(self):
        """Faqat o'z kompyuterimizdan: boshqa saytlar (DNS rebinding) orqali murojaat qilinmasin."""
        if not getattr(self.server, "loopback", True):
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _origin_ok(self):
        """Boshqa sayt bu serverga forma yubora olmasin (CSRF)."""
        origin = self.headers.get("Origin")
        return origin is None or origin.split("://", 1)[-1] == (self.headers.get("Host") or "")

    def do_GET(self):
        if not self._host_ok():
            return self._send(layout("Taqiqlangan", "<h1>Taqiqlangan</h1>"), 403)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path, flash = u.path, parse_qs(u.query).get("msg", [""])[0]
        try:
            m_view = re.fullmatch(r"/batches/(\d+)", path)
            m_edit = re.fullmatch(r"/batches/(\d+)/edit", path)
            m_static = re.fullmatch(r"/static/([^/]+)", path)
            if path == "/":
                self._send(page_dashboard(q))
            elif path == "/skus":
                self._send(page_skus(q))
            elif path == "/stock":
                self._send(page_stock(q))
            elif path == "/batches":
                self._send(page_batches(connect(), flash))
            elif path == "/batches/new":
                self._send(page_form())
            elif m_edit:
                page = page_edit(int(m_edit.group(1)))
                self._send(page or not_found("Partiya"), 200 if page else 404)
            elif m_view:
                page = page_batch(connect(), int(m_view.group(1)), flash)
                self._send(page or not_found("Partiya"), 200 if page else 404)
            elif m_static:
                f = static_file(m_static.group(1))
                if f:
                    self._write(f[0], 200, f[1], "no-cache")
                else:
                    self._send(not_found(), 404)
            elif path == "/api/rate":
                self._json(api_rate(q))
            elif path == "/favicon.ico":
                self._write(b"", 204)
            else:
                self._send(not_found(), 404)
        except Exception:
            self._send(layout("Xato", "<h1>Xato</h1><pre>%s</pre>" % esc(traceback.format_exc())), 500)

    def do_POST(self):
        if not (self._host_ok() and self._origin_ok()):
            return self._send(layout("Taqiqlangan", "<h1>Taqiqlangan</h1>"), 403)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(layout("Xato", "<h1>So'rov juda katta</h1>"), 413)
        path = urlparse(self.path).path
        form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"), keep_blank_values=True)
        try:
            m_edit = re.fullmatch(r"/batches/(\d+)/edit", path)
            m_del = re.fullmatch(r"/batches/(\d+)/delete", path)
            if path == "/sync":
                self._redirect("/?msg=" + quote(run_sync()))
            elif path == "/batches/new":
                conn = connect()
                state, errors, data = parse_form(form, conn)
                if errors:
                    self._send(page_form(state, errors), 400)
                else:
                    bid = save_batch(conn, data)
                    self._redirect("/batches/%d?msg=%s" % (bid, quote("Partiya saqlandi")))
            elif m_edit:
                conn, bid = connect(), int(m_edit.group(1))
                if not load_batch(conn, bid):
                    self._send(not_found("Partiya"), 404)
                    return
                state, errors, data = parse_form(form, conn)
                if errors:
                    self._send(page_edit(bid, state, errors), 400)
                else:
                    save_batch(conn, data, bid)
                    self._redirect("/batches/%d?msg=%s" % (bid, quote("O'zgarishlar saqlandi")))
            elif m_del:
                delete_batch(connect(), int(m_del.group(1)))
                self._redirect("/batches?msg=" + quote("Partiya o'chirildi"))
            else:
                self._send(not_found(), 404)
        except Exception:
            self._send(layout("Xato", "<h1>Xato</h1><pre>%s</pre>" % esc(traceback.format_exc())), 500)


def make_server(port=8000, host="127.0.0.1"):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.loopback = host in ("127.0.0.1", "localhost", "::1")
    return srv


def serve(port=8000):
    srv = make_server(port)
    print("Ochish: http://127.0.0.1:%d   (to'xtatish: Ctrl+C)" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nTo'xtatildi.")

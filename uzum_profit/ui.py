# -*- coding: utf-8 -*-
"""Umumiy interfeys yordamchilari: CSS, sahifa qobig'i (layout), jadval va karta qismlari."""
import html
from datetime import datetime

from .util import days_ago, fmt, today

CSS = """
:root{--bg:#fff;--fg:#1c1c1e;--mut:#6b7280;--card:#f4f4f6;--line:#e3e3e8;--acc:#2563eb;--bad:#b91c1c;--good:#15803d;--warn:#b45309}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--mut:#9ca3af;--card:#1f1f23;--line:#33333a;--acc:#60a5fa;--bad:#f87171;--good:#4ade80;--warn:#fbbf24}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,Segoe UI,sans-serif}
header{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:10px 20px;border-bottom:1px solid var(--line)}
nav{display:flex;gap:4px;flex:1;flex-wrap:wrap}nav a{padding:6px 12px;border-radius:8px;color:var(--fg);text-decoration:none}
nav a.on,nav a:hover{background:var(--card)}main{max-width:1180px;margin:0 auto;padding:20px}
h1{font-size:22px;margin:0 0 14px}h2{font-size:17px;margin:26px 0 8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:14px 0}
.card{background:var(--card);border-radius:12px;padding:14px 16px}.lbl{color:var(--mut);font-size:13px}.val{font-size:25px;font-weight:650;margin:2px 0}
.note{color:var(--mut);font-size:12px}.good .val{color:var(--good)}.bad .val{color:var(--bad)}
table{border-collapse:collapse;width:100%}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child,td.l,th.l{text-align:left}th{font-size:12px;color:var(--mut);font-weight:600}
tr.sum td{font-weight:650;background:var(--card)}.wrap{overflow-x:auto}.neg{color:var(--bad)}.pos{color:var(--good)}.mut{color:var(--mut)}
.flash,.warn{padding:10px 14px;border-radius:10px;margin:0 0 14px;background:var(--card);border-left:4px solid var(--acc)}
.warn{border-left-color:var(--warn)}.err{border-left-color:var(--bad)}
form.f{display:grid;gap:12px;max-width:760px}label{display:grid;gap:4px;font-size:13px;color:var(--mut)}
input,select,textarea{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);width:100%}
textarea{font-family:ui-monospace,Menlo,monospace;font-size:13px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
button{font:inherit;padding:8px 16px;border:0;border-radius:8px;background:var(--acc);color:#fff;cursor:pointer}
button.ghost{background:var(--card);color:var(--fg)}button.danger{background:var(--bad)}
.filters{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-bottom:6px}.filters label{min-width:140px}
.presets a{margin-right:10px;color:var(--acc);font-size:13px}details{margin-top:18px}
input[type=checkbox]{width:auto;margin-right:6px}
fieldset.sec{border:1px solid var(--line);border-radius:12px;padding:12px 16px 16px;margin:0 0 14px;min-width:0}
fieldset.sec legend{font-weight:650;padding:0 6px}.hintp{color:var(--mut);font-size:13px;margin:0 0 10px}
.row{display:grid;gap:8px;align-items:start;margin-bottom:8px}
.row.line{grid-template-columns:minmax(200px,1fr) 100px 36px}
.lines.pricing .row.line{grid-template-columns:minmax(200px,1fr) 100px 120px 36px}
.lines:not(.pricing) .cny{display:none}
.row.extra{grid-template-columns:150px minmax(160px,1fr) 36px}
button.x{padding:6px 0;background:var(--card);color:var(--mut);font-size:18px;line-height:1.3}
button.add{background:transparent;color:var(--acc);border:1px dashed var(--line)}
.cb{position:relative}
.dd{display:none;position:absolute;left:0;right:0;top:100%;z-index:30;max-height:280px;overflow:auto;background:var(--bg);border:1px solid var(--line);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);margin-top:2px}
.dd.open{display:block}.opt{padding:7px 10px;cursor:pointer;border-bottom:1px solid var(--line)}
.opt:last-child{border-bottom:0}.opt.hl,.opt:hover{background:var(--card)}.opt b{font-weight:600}
.opt small{display:block;color:var(--mut);font-size:12px;white-space:normal}.opt.new,.opt.empty{color:var(--warn)}
.row.linked .cb-input{border-color:var(--good)}.row.free .cb-input{border-color:var(--warn)}
.cb .hint{font-size:12px;color:var(--warn);margin-top:2px}.cb .hint:empty{display:none}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 14px}
.chip{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;background:var(--card);color:var(--fg);text-decoration:none;border:1px solid var(--line)}
.chip-warn{border-color:var(--warn);color:var(--warn)}.chip-ok{border-color:var(--good);color:var(--good)}
.rate-note{font-size:12px;color:var(--mut);margin-top:2px}.inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
label.inline{flex-wrap:nowrap;align-items:flex-start}
.btns{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0}
a.btnlink{display:inline-block;padding:8px 16px;border-radius:8px;background:var(--acc);color:#fff;text-decoration:none}
a.btnlink.ghost{background:var(--card);color:var(--fg)}
.sub{display:block;color:var(--mut);font-size:12px;font-weight:400;white-space:normal;max-width:340px}.sub.nw{white-space:nowrap}
.tag{font-size:12px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);white-space:nowrap}
.tag-bad{border-color:var(--bad);color:var(--bad)}.tag-warn{border-color:var(--warn);color:var(--warn)}.tag-ok{border-color:var(--good);color:var(--good)}
@media (max-width:640px){.grid2{grid-template-columns:1fr}.row.line,.lines.pricing .row.line{grid-template-columns:1fr 90px 36px}.row.extra{grid-template-columns:110px 1fr 36px}}
"""


def esc(x):
    return html.escape("" if x is None else str(x))


def money(x):
    return fmt(x)


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def signed(x):
    cls = "neg" if x < 0 else ("pos" if x > 0 else "")
    return f'<span class="{cls}">{fmt(x)}</span>'


def layout(title, body, active="/", flash=""):
    nav = [("/", "Bosh sahifa"), ("/skus", "SKU foyda"), ("/stock", "Ombor"), ("/batches", "Partiyalar")]
    links = "".join(f'<a href="{u}"{" class=on" if u == active else ""}>{esc(t)}</a>' for u, t in nav)
    fl = f'<div class="flash">{esc(flash)}</div>' if flash else ""
    return (f'<!doctype html><html lang="uz"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} · Uzum foyda</title><style>{CSS}</style></head><body>'
            f'<header><b>Uzum foyda</b><nav>{links}</nav>'
            f'<form method="post" action="/sync"><button class="ghost">API\'dan yangilash</button></form>'
            f'</header><main>{fl}{body}</main></body></html>')


def valid_date(s, default):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except (TypeError, ValueError):
        return default


def filters_form(action, shops, sel, d_from, d_to, with_all=True):
    opts = ('<option value="all">Hamma do\'konlar</option>' if with_all else "") + "".join(
        f'<option value="{s["id"]}"{" selected" if str(s["id"]) == sel else ""}>{esc(s["name"])}</option>'
        for s in shops)
    month = today()[:8] + "01"
    presets = (f'<a href="{action}?shop={sel}&from={days_ago(29)}&to={today()}">Oxirgi 30 kun</a>'
               f'<a href="{action}?shop={sel}&from={month}&to={today()}">Bu oy</a>'
               f'<a href="{action}?shop={sel}&from=2026-01-01&to={today()}">Hammasi</a>')
    return (f'<form class="filters" method="get" action="{action}">'
            f'<label>Do\'kon<select name="shop">{opts}</select></label>'
            f'<label>Dan<input type="date" name="from" value="{d_from}"></label>'
            f'<label>Gacha<input type="date" name="to" value="{d_to}"></label>'
            f'<button>Ko\'rsat</button></form><div class="presets">{presets}</div>')


def card(label, value, note="", cls=""):
    return (f'<div class="card {cls}"><div class="lbl">{esc(label)}</div>'
            f'<div class="val">{esc(value)}</div><div class="note">{esc(note)}</div></div>')


def tr(label, value, note="", cls=""):
    return (f'<tr class="{cls}"><td class="l">{label}</td><td>{value}</td>'
            f'<td class="l mut">{esc(note)}</td></tr>')


EMPTY = ("<h1>Hali ma'lumot yo'q</h1><p>Birinchi marta ma'lumot yuklash uchun yuqoridagi "
         "<b>API'dan yangilash</b> tugmasini bosing (avval .env fayliga UZUM_API_KEY yozilgan bo'lishi kerak), "
         "yoki terminalda: <code>python3 -m uzum_profit import-json uzum_history.json</code></p>")

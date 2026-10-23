# -*- coding: utf-8 -*-
"""Buyruqlar:
  python3 -m uzum_profit import-json uzum_history.json   # birinchi yuklash (API'siz)
  python3 -m uzum_profit sync [--days 30]                # API'dan yangilash (eski tarix uchun: --days 400)
  python3 -m uzum_profit serve [--port 8000]             # veb-interfeys
  python3 -m uzum_profit report [--shop ID] [--from ...] # terminalda qisqa hisobot
  python3 -m uzum_profit selfcheck                       # haqiqiy API bilan tekshiruv (kalitsiz hisobot)
"""
import argparse
import getpass
import sys

from . import report as rpt
from .db import connect
from .util import cfg, days_ago, fmt, load_env, ms_to_date, today


def cmd_report(args):
    conn = connect()
    shops = conn.execute("SELECT id, name FROM shops ORDER BY name").fetchall()
    ids = [s["id"] for s in shops if args.shop in (None, s["id"])]
    if not ids:
        sys.exit("Do'kon topilmadi. Avval ma'lumot yuklang (import-json yoki sync).")
    R = rpt.build_report(conn, ids, args.date_from, args.date_to)
    d, e = R["done"], R["ex"]
    print(f"{R['name']}: {args.date_from} — {args.date_to}")
    for s in shops:
        if s["id"] in ids:
            lo, hi = conn.execute("SELECT MIN(created_ms), MAX(created_ms) FROM order_items WHERE shop_id=?",
                                  (s["id"],)).fetchone()
            print(f"  bazadagi sotuvlar ({s['name']}): " + (f"{ms_to_date(lo)} dan {ms_to_date(hi)} gacha" if lo else "yo'q"))
    print(f"  yakunlangan: {d['n']} qator, tushim {fmt(d['revenue'])}, Uzum sof tushimi {fmt(d['seller_profit'])}")
    print(f"  tannarxi ma'lum: {d['k_n']} qator, tannarx {fmt(d['cogs'])}; tannarxsiz: {R['miss_n']} qator")
    print(f"  reklama {fmt(e['ad'])}, saqlash {fmt(e['storage'])}, jarima {fmt(e['fine'])}, kompensatsiya {fmt(e['compensation'])}")
    if R["nocargo_n"]:
        print(f"  diqqat: {R['nocargo_n']} qator tannarxi kargosiz hisoblangan (partiyada kargo narxi kiritilmagan)")
    if d["k_n"] == 0:
        print("  HAQIQIY FOYDA: — (tannarx kiritilmagan: Partiyalar bo'limida kiriting)")
    else:
        part = f"  (taxminiy: faqat tannarxi ma'lum {d['k_n']} / {d['n']} qator bo'yicha)" if R["miss_n"] else ""
        print(f"  HAQIQIY FOYDA: {fmt(R['profit'])}  | standart tarifda: {fmt(R['profit_std'])}{part}")
    print(f"  kutilayotgan foyda: {fmt(R['pending_expected'])}")
    print(f"  bekor: {R['canceled']['n']} (yakunlanganlar orasida {R['cancel_rate']:.1%})" if R["cancel_rate"] is not None else "  bekor: 0")


def main():
    load_env()
    p = argparse.ArgumentParser(prog="uzum_profit", description="Uzum sotuvchi foyda hisobi")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("import-json", help="uzum_history.json'ni bazaga yuklash")
    s.add_argument("path")
    s = sub.add_parser("sync", help="Uzum API'dan yangilash")
    s.add_argument("--days", type=int, default=int(cfg("SYNC_DAYS", "30")))
    s = sub.add_parser("serve", help="veb-interfeys")
    s.add_argument("--port", type=int, default=8000)
    s = sub.add_parser("report", help="terminalda qisqa hisobot")
    s.add_argument("--shop", type=int)
    s.add_argument("--from", dest="date_from", default=days_ago(29))
    s.add_argument("--to", dest="date_to", default=today())
    sub.add_parser("selfcheck", help="Uzum API va bank kursini tekshirish (natijani Claude'ga yuborish mumkin)")
    args = p.parse_args()

    if args.cmd == "import-json":
        from .sync import import_history
        print("Yuklandi:", import_history(connect(), args.path))
    elif args.cmd == "sync":
        from .sync import sync_api
        key = cfg("UZUM_API_KEY") or getpass.getpass("Uzum API kaliti (ekranda ko'rinmaydi): ")
        print("Yangilandi:", sync_api(connect(), key, args.days))
    elif args.cmd == "serve":
        from .web import serve
        serve(args.port)
    elif args.cmd == "selfcheck":
        from .selfcheck import main as selfcheck_main
        selfcheck_main(cfg("UZUM_API_KEY") or getpass.getpass("Uzum API kaliti (ekranda ko'rinmaydi): "))
    elif args.cmd == "report":
        cmd_report(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()

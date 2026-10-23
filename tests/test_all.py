# -*- coding: utf-8 -*-
"""Sinovlar. Ishga tushirish (loyiha papkasida):  python3 -m unittest tests.test_all -v"""
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp()
os.environ["UZUM_DB"] = os.path.join(_TMP, "test.db")
os.environ["FREE_LOGISTICS_FROM"] = "2026-10-10"
os.environ["FREE_LOGISTICS_TO"] = "2026-10-31"
os.environ["LEAD_DAYS"] = "30"

from uzum_profit import batches_form, costs, rates, report as rpt, selfcheck, stock, sync, web  # noqa: E402
from uzum_profit.db import connect  # noqa: E402
from uzum_profit.util import day_start_ms  # noqa: E402

HISTORY = os.environ.get("UZUM_TEST_HISTORY", os.path.join(os.path.dirname(__file__), "..", "uzum_history.json"))


def setUpModule():
    # sinovda bazaga ulanishlar axlat yig'uvchi orqali yopiladi: ogohlantirish shovqin bo'lmasin
    warnings.simplefilter("ignore", ResourceWarning)


def fresh_conn():
    path = os.environ["UZUM_DB"]
    if os.path.exists(path):
        os.remove(path)
    return connect()


def make_batch(conn, shop, date, goods, cny_rate, cargo, usd_rate, lines, extras=(), cargo_date=None, title=None):
    """lines: (sku, qty, cny_unit) yoki (sku, qty, cny_unit, label). sku=None bo'lsa label ishlatiladi."""
    cur = conn.execute("INSERT INTO batches (shop_id,date,goods_cny,cny_rate,cargo_usd,usd_rate,note,title,cargo_date) "
                       "VALUES (?,?,?,?,?,?,'',?,?)", (shop, date, goods, cny_rate, cargo, usd_rate, title, cargo_date))
    bid = cur.lastrowid
    for sku, qty, cny_unit, *rest in lines:
        conn.execute("INSERT INTO batch_lines (batch_id,sku,qty,cny_unit,label) VALUES (?,?,?,?,?)",
                     (bid, sku, qty, cny_unit, rest[0] if rest else None))
    for name, amt in extras:
        conn.execute("INSERT INTO batch_extras (batch_id,name,amount) VALUES (?,?,?)", (bid, name, amt))
    conn.commit()
    return bid


class CostMethodTests(unittest.TestCase):
    def test_users_example_50_jackets(self):
        """50 ta kurtka = 10 SKU x 5 dona; 2000 CNY, kargo 200 USD, qo'shimcha 50 000 so'm."""
        conn = fresh_conn()
        skus = [(f"JACKET-{s}-{c}", 5, None) for s in ("M", "L") for c in range(1, 6)]
        make_batch(conn, 1, "2026-08-01", 2000, 1800, 200, 12000, skus, [("rulon", 30000), ("paket", 20000)])
        row = costs.compute_batch(costs.load_batches(conn)[0])
        self.assertEqual(len(row), 10)
        for r in row:
            self.assertAlmostEqual(r["cny_unit"], 40)          # 2000 / 50
            self.assertAlmostEqual(r["goods"], 72000)          # 40 CNY * 1800
            self.assertAlmostEqual(r["cargo"], 48000)          # (200/50) USD * 12000
            self.assertAlmostEqual(r["extras"], 1000)          # 50 000 / 50
            self.assertAlmostEqual(r["unit_cost"], 121000)

    def test_explicit_unit_price(self):
        conn = fresh_conn()
        make_batch(conn, 1, "2026-08-01", 500, 1000, 0, 0, [("A", 10, 30.0), ("B", 10, None)])
        rows = {r["sku"]: r for r in costs.compute_batch(costs.load_batches(conn)[0])}
        self.assertAlmostEqual(rows["A"]["unit_cost"], 30000)   # 30 CNY
        self.assertAlmostEqual(rows["B"]["unit_cost"], 20000)   # (500 - 300) / 10 = 20 CNY

    def test_costbook_weighted_average_and_fallback(self):
        conn = fresh_conn()
        make_batch(conn, 1, "2026-08-01", 100, 1000, 0, 0, [("X", 10, None)])   # 10 CNY -> 10 000
        make_batch(conn, 1, "2026-09-01", 600, 1000, 0, 0, [("X", 30, None)])   # 20 CNY -> 20 000
        book = costs.CostBook(conn, 1)
        self.assertEqual(book.unit_cost("x", "2026-08-15"), (10000, set()))
        cost, flags = book.unit_cost("X", "2026-09-02")
        self.assertAlmostEqual(cost, (10 * 10000 + 30 * 20000) / 40)
        self.assertEqual(flags, set())
        cost, flags = book.unit_cost("X", "2026-07-01")      # sanagacha partiya yo'q -> hammasi, taxminiy
        self.assertAlmostEqual(cost, 17500)
        self.assertEqual(flags, {"early"})
        self.assertEqual(book.unit_cost("NOPE", "2026-09-02"), (None, set()))

    def test_sku_matching(self):
        self.assertEqual(costs.match_sku("abc-1", ["ABC-1", "ABC-2"]), ("ABC-1", []))
        code, sugg = costs.match_sku("ABC-3", ["ABC-1", "ABC-2"])
        self.assertIsNone(code)
        self.assertTrue(sugg)


class FakeUzum:
    """Haqiqiy API o'rniga: sample_rows() ma'lumotlarini qaytaradi."""
    def __init__(self, key, log=None, **kw):
        self.key = key

    def get(self, path, params=None):
        if path.endswith("/return"):
            raise sync.UzumError("%s: HTTP 404" % path)
        return []

    def shops(self):
        return [{"id": 1, "name": "TestShop"}]

    def orders(self, sid, date_from):
        return sample_rows()[0]

    def expenses(self, sid, date_from):
        return sample_rows()[1]

    def products(self, sid):
        return [{"productId": 1, "title": "T", "skuList": [{"skuFullTitle": "A-1", "skuId": 1, "price": 1,
                 "commission": 1, "barcode": "1", "status": {"value": "IN_STOCK"}, "quantitySold": 1,
                 "quantityReturned": 0, "quantityDefected": 0, "quantityAvailableByStockType": {"fbo": 2}}]}]

    def invoices(self, sid):
        return []


class SyncRedirectTests(unittest.TestCase):
    def test_sync_returns_to_same_page_and_rejects_open_redirect(self):
        os.environ.pop("UZUM_API_KEY", None)
        fresh_conn()
        srv = web.make_server(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % srv.server_address[1]

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)

        def where(nxt):
            req = urllib.request.Request(base + "/sync", data=urllib.parse.urlencode({"next": nxt}).encode())
            try:
                opener.open(req)
            except urllib.error.HTTPError as e:
                return e.headers["Location"]
        try:
            self.assertTrue(where("/stock?shop=1").startswith("/stock?shop=1&msg="))
            self.assertTrue(where("/skus?x=1&msg=eski").startswith("/skus?x=1&msg="))
            self.assertTrue(where("//evil.example").startswith("/?msg="))
            self.assertTrue(where("http://evil.example").startswith("/?msg="))
        finally:
            srv.shutdown()
            srv.server_close()


class SelfcheckTests(unittest.TestCase):
    def test_report_has_no_key_and_flags_missing_fields(self):
        from unittest import mock
        lines = []
        with mock.patch.object(sync, "Uzum", FakeUzum), \
                mock.patch.object(rates, "get_rate", return_value={"rate": 1800.0, "date": "2026-10-22", "warn": ""}):
            code = selfcheck.run("SECRET-KEY-123", days=7, out=lines.append, api_factory=FakeUzum)
        text = "\n".join(lines)
        self.assertNotIn("SECRET-KEY-123", text)
        self.assertIn("TestShop (1)", text)
        self.assertIn("OK: {'orders': 4", text)
        self.assertIn("/v1/shop/1/return", text)          # sinov yo'li xatosi hisobotda ko'rinadi
        self.assertEqual(code, 0)                          # kutilgan maydonlar bor; qo'shimcha so'rov xatosi muammo emas
        self.assertEqual(selfcheck.missing_keys([{"a": 1, "b": None}], ["a", "b", "c"]), ["b", "c"])


class ClassifyTests(unittest.TestCase):
    def test_codes_with_cyrillic_letters(self):
        c = sync.classify
        self.assertEqual(c("У000120", "Marketing", "x", "OUTCOME"), "ad")        # kirill У
        self.assertEqual(c("С000003", "Ombor", "x", "OUTCOME"), "storage")      # kirill С
        self.assertEqual(c("C000007", "Ombor", "x", "OUTCOME"), "fine")         # lotin C
        self.assertEqual(c("logistics-volume", "Logistika", "x", "OUTCOME"), "logistics")
        self.assertEqual(c("return-logistics-volume", "Logistika", "x", "INCOME"), "logistics_refund")
        self.assertEqual(c("return-С000003", "Ombor", "[Kompensatsiya] Saqlash", "INCOME"), "compensation")


def sample_rows():
    d = day_start_ms("2026-10-05") + 3600_000     # logistika pullik davr
    f = day_start_ms("2026-10-12") + 3600_000     # bepul logistika davri
    base = dict(skuTitle="A-1", productId=1, productTitle="Mahsulot A", shopId=1)
    orders = [
        dict(base, id=11, orderId=1, status="TO_WITHDRAW", date=d, dateIssued=d + 1, sellPrice=20000, amount=1,
             commission=4000, sellerProfit=10750, logisticDeliveryFee=5250, amountReturns=0),
        dict(base, id=12, orderId=2, status="TO_WITHDRAW", date=f, dateIssued=f + 1, sellPrice=20000, amount=2,
             commission=8000, sellerProfit=32000, logisticDeliveryFee=0, amountReturns=0),
        dict(base, id=13, orderId=3, status="PROCESSING", date=f, dateIssued=None, sellPrice=20000, amount=1,
             commission=4000, sellerProfit=16000, logisticDeliveryFee=0, amountReturns=0),
        dict(base, id=14, orderId=4, status="CANCELED", date=d, dateIssued=d + 1, sellPrice=20000, amount=1,
             commission=0, sellerProfit=0, logisticDeliveryFee=0, amountReturns=1),
    ]
    expenses = [
        dict(id=101, dateCreated=d + 5, name="Buyurtmalarni ko'paytirish. Sotuvdan foiz — 10%. Xaridor tovarni "
             "olganida 2000.5 so'm yechib oldik", source="Marketing", paymentPrice=2000, externalId="AD#11-1-2026-10-05",
             code="У000120", type="OUTCOME"),
        dict(id=102, dateCreated=d + 6, name="Saqlash", source="Ombor", paymentPrice=3000, externalId="x",
             code="С000003", type="OUTCOME"),
        dict(id=103, dateCreated=d + 7, name="Jarima", source="Ombor", paymentPrice=2500, externalId="y",
             code="C000007", type="OUTCOME"),
    ]
    return orders, expenses


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        orders, expenses = sample_rows()
        sync.upsert_shops(self.conn, [{"id": 1, "name": "TestShop"}])
        sync.upsert_orders(self.conn, 1, orders)
        sync.upsert_expenses(self.conn, 1, expenses)
        self.conn.commit()

    def test_totals_without_costs(self):
        r = rpt.build_report(self.conn, [1], "2026-10-01", "2026-10-31")
        self.assertEqual(r["done"]["n"], 2)
        self.assertEqual(r["done"]["seller_profit"], 42750)
        self.assertEqual(r["miss_n"], 2)                       # tannarx hali kiritilmagan
        self.assertEqual(r["canceled"], {"n": 1, "after_pickup": 1})
        self.assertAlmostEqual(r["ex"]["ad"], 2000.5)          # aniq summa matndan olinadi
        self.assertEqual(r["ex"]["storage"], 3000)
        self.assertEqual(r["ex"]["fine"], 2500)
        self.assertAlmostEqual(r["cancel_rate"], 1 / 3)

    def test_profit_with_costs_and_free_logistics(self):
        make_batch(self.conn, 1, "2026-10-01", 50, 1000, 0, 0, [("A-1", 10, None)])   # 5 CNY -> 5 000 so'm
        r = rpt.build_report(self.conn, [1], "2026-10-01", "2026-10-31")
        self.assertEqual(r["miss_n"], 0)
        self.assertAlmostEqual(r["done"]["cogs"], 3 * 5000)            # 1 + 2 dona
        self.assertAlmostEqual(r["profit_before_extras"], 42750 - 15000)
        self.assertAlmostEqual(r["profit"], 27750 - (2000.5 + 3000 + 2500))
        # 12-oktyabrdagi 2 dona bepul logistika: 2 * 5250 tejalgan
        self.assertAlmostEqual(r["done"]["k_free_saving"], 2 * 5250)
        self.assertAlmostEqual(r["profit_std"], r["profit"] - 10500)
        # kutilayotgan: (16000 - 5000) * 0.75
        self.assertAlmostEqual(r["pending_expected"], 11000 * 0.75)

    def test_cli_report_hides_profit_without_costs(self):
        import argparse
        import contextlib
        import io
        from uzum_profit import __main__ as cli
        args = argparse.Namespace(shop=None, date_from="2026-10-01", date_to="2026-10-31")

        def run():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.cmd_report(args)
            return buf.getvalue()

        self.assertIn("HAQIQIY FOYDA: —", run())                       # tannarx yo'q: manfiy "foyda" ko'rsatilmaydi
        make_batch(self.conn, 1, "2026-10-01", 50, 1000, 0, 0, [("A-1", 10, None)])
        out = run()
        self.assertNotIn("HAQIQIY FOYDA: —", out)
        self.assertIn("HAQIQIY FOYDA: 20", out)                        # 27 750 - 7 500,5 = 20 249,5

    def test_in_transit_replenishment_does_not_distort_report(self):
        make_batch(self.conn, 1, "2026-10-01", 50, 1000, 0, 0, [("A-1", 10, None)])             # 5 000, to'liq
        make_batch(self.conn, 1, "2026-10-03", 1000, 1000, None, None, [("A-1", 10, None)])     # 100 000, yo'lda
        r = rpt.build_report(self.conn, [1], "2026-10-01", "2026-10-31")
        self.assertEqual(r["nocargo_n"], 0)
        self.assertAlmostEqual(r["done"]["cogs"], 3 * 5000)

    def test_sku_rows(self):
        make_batch(self.conn, 1, "2026-10-01", 50, 1000, 0, 0, [("A-1", 10, None)])
        rows = rpt.sku_rows(self.conn, 1, "2026-10-01", "2026-10-31")
        self.assertEqual(len(rows), 1)
        a = rows[0]
        self.assertEqual(a["units"], 3)
        self.assertAlmostEqual(a["avg_cost"], 5000)
        self.assertAlmostEqual(a["profit"], 42750 - 2000.5 - 15000)    # ad item 11 ga bog'langan


class StagedBatchTests(unittest.TestCase):
    """Partiya bosqichma-bosqich: buyurtma -> mahsulotlar (SKU hali yo'q bo'lishi mumkin) -> kargo -> SKU biriktirish."""

    def test_order_only_batch(self):
        conn = fresh_conn()
        make_batch(conn, 1, "2026-10-01", 2000, 1800, None, None, [])
        b = costs.load_batches(conn)[0]
        st = costs.batch_state(b)
        self.assertTrue(st["no_lines"] and st["cargo_missing"])
        self.assertFalse(st["complete"])
        t = costs.batch_totals(b)
        self.assertEqual((t["goods"], t["cargo"], t["extras"], t["total"]), (3600000, 0, 0, 3600000))
        self.assertEqual(costs.compute_batch(b), [])
        self.assertEqual(costs.CostBook(conn, 1).by_sku, {})

    def test_free_label_lines_count_units_but_not_costbook(self):
        conn = fresh_conn()
        make_batch(conn, 1, "2026-10-01", 1000, 1000, None, None,
                   [(None, 10, None, "Qizil kurtka M"), ("A-1", 10, None)])
        b = costs.load_batches(conn)[0]
        rows = costs.compute_batch(b)
        self.assertEqual([r["name"] for r in rows], ["Qizil kurtka M", "A-1"])
        self.assertAlmostEqual(rows[0]["unit_cost"], 50000)          # 1000 CNY / 20 dona * 1000
        st = costs.batch_state(b)
        self.assertEqual((st["units"], st["unlinked"]), (20, 1))
        book = costs.CostBook(conn, 1)
        self.assertEqual(list(book.by_sku), ["a-1"])                 # nomi bor qator hisobga kirmaydi
        cost, flags = book.unit_cost("A-1", "2026-10-05")
        self.assertAlmostEqual(cost, 50000)
        self.assertEqual(flags, {"nocargo"})                         # kargo hali yo'q: belgilanadi

    def test_cargo_added_later_changes_cost_and_clears_flag(self):
        conn = fresh_conn()
        bid = make_batch(conn, 1, "2026-10-01", 1000, 1000, None, None, [("A-1", 20, None)])
        self.assertEqual(costs.CostBook(conn, 1).unit_cost("A-1", "2026-10-05"), (50000, {"nocargo"}))
        conn.execute("UPDATE batches SET cargo_usd=40, usd_rate=12000, cargo_date='2026-10-20' WHERE id=?", (bid,))
        conn.commit()
        book = costs.CostBook(conn, 1)
        cost, flags = book.unit_cost("A-1", "2026-10-21")
        self.assertAlmostEqual(cost, 50000 + 40 / 20 * 12000)       # tovar + kargo
        self.assertEqual(flags, set())
        # kargo sanasigacha tovar hali qo'lga olinmagan: zaxira qoidasi (taxminiy) ishlaydi
        self.assertEqual(book.unit_cost("A-1", "2026-10-10")[1], {"early"})

    def test_in_transit_batch_does_not_touch_cost_of_existing_stock(self):
        """Eski SKU uchun yangi partiya yo'lda (kargo hali yo'q): tovar kelguncha eski tannarx saqlanadi."""
        conn = fresh_conn()
        make_batch(conn, 1, "2026-08-01", 100, 1000, 0, 0, [("A-1", 10, None)])                 # 10 000, to'liq
        bid = make_batch(conn, 1, "2026-10-01", 1000, 1000, None, None, [("A-1", 20, None)])    # 50 000, yo'lda
        self.assertEqual(costs.CostBook(conn, 1).unit_cost("A-1", "2026-10-10"), (10000, set()))
        # tovar keldi, kargo to'landi: shu sanadan boshlab vaznli o'rtacha, undan oldingi sotuvlar o'zgarmaydi
        conn.execute("UPDATE batches SET cargo_usd=40, usd_rate=12000, cargo_date='2026-10-24' WHERE id=?", (bid,))
        conn.commit()
        book = costs.CostBook(conn, 1)
        self.assertEqual(book.unit_cost("A-1", "2026-10-10"), (10000, set()))
        cost, flags = book.unit_cost("A-1", "2026-10-25")
        self.assertAlmostEqual(cost, (10 * 10000 + 20 * (50000 + 24000)) / 30)
        self.assertEqual(flags, set())

    def test_early_sale_prefers_complete_batches(self):
        conn = fresh_conn()
        make_batch(conn, 1, "2026-09-01", 100, 1000, 0, 0, [("A-1", 10, None)])                 # to'liq, 10 000
        make_batch(conn, 1, "2026-10-20", 1000, 1000, None, None, [("A-1", 20, None)])          # yo'lda
        self.assertEqual(costs.CostBook(conn, 1).unit_cost("A-1", "2026-08-01"), (10000, {"early"}))

    def test_effective_date_never_before_order_date(self):
        self.assertEqual(costs.effective_date({"date": "2026-10-10", "cargo_date": "2026-10-01"}), "2026-10-10")
        self.assertEqual(costs.effective_date({"date": "2026-10-10", "cargo_date": "2026-10-20"}), "2026-10-20")
        self.assertEqual(costs.effective_date({"date": "2026-10-10", "cargo_date": None}), "2026-10-10")

    def test_zero_cargo_is_known_not_missing(self):
        conn = fresh_conn()
        make_batch(conn, 1, "2026-10-01", 100, 1000, 0, None, [("A-1", 10, None)])
        b = costs.load_batches(conn)[0]
        self.assertFalse(costs.batch_state(b)["cargo_missing"])
        self.assertTrue(costs.batch_state(b)["complete"])
        self.assertEqual(costs.CostBook(conn, 1).unit_cost("A-1", "2026-10-05"), (10000, set()))


class MigrationTests(unittest.TestCase):
    OLD_SCHEMA = """
    CREATE TABLE shops (id INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE skus (shop_id INTEGER, sku TEXT, sku_id INTEGER, product_id INTEGER, title TEXT, barcode TEXT,
      commission_pct REAL, price INTEGER, qty_fbo INTEGER, qty_sold INTEGER, qty_returned INTEGER,
      weight_g INTEGER, seller_code TEXT, status TEXT, PRIMARY KEY (shop_id, sku));
    CREATE TABLE batches (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, date TEXT, goods_cny REAL,
      cny_rate REAL, cargo_usd REAL, usd_rate REAL, note TEXT);
    CREATE TABLE batch_lines (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, sku TEXT, qty INTEGER,
      cny_unit REAL);
    CREATE TABLE batch_extras (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, name TEXT, amount REAL);
    """

    def test_old_database_keeps_data_and_gets_new_columns(self):
        path = os.path.join(_TMP, "old.db")
        if os.path.exists(path):
            os.remove(path)
        old = sqlite3.connect(path)
        old.executescript(self.OLD_SCHEMA)
        old.execute("INSERT INTO shops VALUES (1, 'S')")
        old.execute("INSERT INTO skus VALUES (1,'A-1',1,1,'Mahsulot','',10,1000,5,3,1,0,'','IN_STOCK')")
        old.execute("INSERT INTO batches (shop_id,date,goods_cny,cny_rate,cargo_usd,usd_rate,note) "
                    "VALUES (1,'2026-08-01',100,1000,10,12000,'eski')")
        old.execute("INSERT INTO batch_lines (batch_id,sku,qty,cny_unit) VALUES (1,'A-1',10,NULL)")
        old.commit()
        old.close()
        for _ in range(2):                     # ikkinchi marta ochish ham xato bermasligi kerak
            conn = connect(path)
        cols = lambda t: {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % t)}  # noqa: E731
        self.assertTrue({"title", "cargo_date"} <= cols("batches"))
        self.assertIn("label", cols("batch_lines"))
        self.assertIn("qty_defected", cols("skus"))
        b = costs.load_batches(conn)[0]
        self.assertEqual((b["note"], b["cargo_usd"], b["title"], b["cargo_date"]), ("eski", 10, None, None))
        self.assertTrue(costs.batch_state(b)["complete"])           # eski partiya: kargo ma'lum, SKU biriktirilgan
        cost, flags = costs.CostBook(conn, 1).unit_cost("A-1", "2026-09-01")
        self.assertAlmostEqual(cost, 100 * 1000 / 10 + 10 * 12000 / 10)
        self.assertEqual(flags, set())
        self.assertEqual(tuple(conn.execute("SELECT qty_fbo, qty_defected FROM skus").fetchone()), (5, None))
        # yangi yuklash eski bazada ishlaydi
        sync.upsert_products(conn, 1, [{"productId": 1, "title": "T", "skuList": [
            {"skuFullTitle": "A-2", "skuId": 2, "quantityAvailableByStockType": {"fbo": 3}, "quantityDefected": 1,
             "status": {"value": "IN_STOCK"}}]}])
        self.assertEqual(tuple(conn.execute("SELECT qty_fbo, qty_defected FROM skus WHERE sku='A-2'").fetchone()), (3, 1))


class FormParseTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        sync.upsert_shops(self.conn, [{"id": 1, "name": "TestShop"}])
        sync.upsert_orders(self.conn, 1, sample_rows()[0])         # A-1 do'kon katalogida bo'ladi
        self.conn.commit()

    def base(self, **kw):
        f = {"shop": ["1"], "date": ["2026-10-01"], "goods_cny": ["2000"], "cny_rate": ["1 800"]}
        for k, v in kw.items():
            f[k] = v if isinstance(v, list) else [v]
        return f

    def parse(self, **kw):
        return batches_form.parse_form(self.base(**kw), self.conn)

    def test_only_order_part_is_enough(self):
        state, errors, d = self.parse()
        self.assertEqual(errors, [])
        self.assertEqual((d["goods_cny"], d["cny_rate"], d["cargo_usd"], d["lines"], d["extras"]),
                         (2000.0, 1800.0, None, [], []))

    def test_required_fields_and_bad_numbers(self):
        cases = [(dict(goods_cny=""), "Tovar"), (dict(goods_cny="0"), "Tovar"), (dict(goods_cny="nan"), "Tovar"),
                 (dict(goods_cny="inf"), "Tovar"), (dict(cny_rate="abc"), "CNY kursi"),
                 (dict(cny_rate="-5"), "CNY kursi"), (dict(cny_rate=""), "CNY kursi"), (dict(date="2026-13-45"), "sana"),
                 (dict(shop="999"), "Do'kon")]
        for kw, word in cases:
            errors = self.parse(**kw)[1]
            self.assertTrue(any(word in e for e in errors), (kw, errors))

    def test_cargo_rules(self):
        self.assertTrue(any("USD kursi" in e for e in self.parse(cargo_usd="200")[1]))
        _, errors, d = self.parse(cargo_usd="0")                       # kargo yo'q: kurs shart emas
        self.assertEqual((errors, d["cargo_usd"]), ([], 0.0))
        _, errors, d = self.parse(cargo_usd="200", usd_rate="12 000", cargo_date="2026-10-20")
        self.assertEqual(errors, [])
        self.assertEqual((d["cargo_usd"], d["usd_rate"], d["cargo_date"]), (200.0, 12000.0, "2026-10-20"))
        _, errors, d = self.parse(cargo_usd="", usd_rate="12000")      # kargo hali yo'q, kurs oldindan yozilgan
        self.assertEqual(errors, [])
        self.assertIsNone(d["cargo_usd"])
        self.assertTrue(any("Kargo sanasi" in e for e in self.parse(cargo_date="31.12.2026")[1]))

    def test_lines_sku_and_free_label(self):
        state, errors, d = self.parse(line_text=["a-1", "Qizil kurtka M", ""], line_sku=["", "", ""],
                                      line_qty=["5", "7", ""], line_cny=["", "", ""])
        self.assertEqual(errors, [])
        self.assertEqual(d["lines"], [{"sku": "A-1", "label": None, "qty": 5, "cny_unit": None},
                                      {"sku": None, "label": "Qizil kurtka M", "qty": 7, "cny_unit": None}])
        self.assertEqual([l["sku"] for l in state["lines"]], ["A-1", ""])

    def test_hidden_sku_wins_over_text(self):
        _, errors, d = self.parse(line_text=["biror narsa"], line_sku=["A-1"], line_qty=["2"], line_cny=["12.5"])
        self.assertEqual(errors, [])
        self.assertEqual(d["lines"], [{"sku": "A-1", "label": None, "qty": 2, "cny_unit": 12.5}])

    def test_line_errors(self):
        def one(text, qty, cny="", sku=""):
            return self.parse(line_text=[text], line_sku=[sku], line_qty=[qty], line_cny=[cny])[1]
        self.assertTrue(any("soni" in e for e in one("A-1", "")))
        self.assertTrue(any("butun" in e for e in one("A-1", "2.5")))
        self.assertTrue(any("soni" in e for e in one("A-1", "0")))
        self.assertTrue(any("CNY narxi" in e for e in one("A-1", "3", "x")))
        self.assertEqual(one("", "3"), [])                            # nomsiz yangi tovar ham saqlanadi
        _, _, d = self.parse(line_text=["", ""], line_sku=["", ""], line_qty=["3", "4"], line_cny=["", ""])
        self.assertEqual([(l["label"], l["qty"]) for l in d["lines"]],
                         [("Nomsiz tovar (1-qator)", 3), ("Nomsiz tovar (2-qator)", 4)])
        dup = self.parse(line_text=["A-1", "a-1"], line_sku=["", ""], line_qty=["3", "4"], line_cny=["", ""])[1]
        self.assertTrue(any("takrorlangan" in e for e in dup))
        dup = self.parse(line_text=["Kurtka", "kurtka"], line_sku=["", ""], line_qty=["3", "4"], line_cny=["", ""])[1]
        self.assertTrue(any("takrorlangan" in e for e in dup))

    def test_extras(self):
        state, errors, d = self.parse(extra_amount=["30 000", "", "50000"], extra_name=["rulon", "", ""])
        self.assertEqual(errors, [])
        self.assertEqual(d["extras"], [{"name": "rulon", "amount": 30000.0}, {"name": "Chiqim", "amount": 50000.0}])
        self.assertEqual(len(state["extras"]), 2)                      # bo'sh qator tashlab ketiladi
        self.assertTrue(any("chiqim summasi" in e for e in self.parse(extra_amount=[""], extra_name=["paket"])[1]))
        self.assertTrue(self.parse(extra_amount=["-5"], extra_name=["x"])[1])
        self.assertTrue(self.parse(extra_amount=["abc"], extra_name=["x"])[1])

    def test_save_and_edit_roundtrip(self):
        _, errors, d = self.parse(title="Qizil", line_text=["A-1"], line_sku=["A-1"], line_qty=["5"], line_cny=[""],
                                  extra_amount=["1000"], extra_name=["rulon"])
        self.assertEqual(errors, [])
        bid = batches_form.save_batch(self.conn, d)
        s = batches_form.edit_state(self.conn, bid)
        self.assertEqual((s["title"], s["goods_cny"], s["cny_rate"], s["cargo_usd"], s["usd_rate"]),
                         ("Qizil", "2000", "1800", "", ""))
        self.assertEqual(s["lines"], [{"text": "A-1", "sku": "A-1", "qty": "5", "cny": ""}])
        self.assertEqual(s["extras"], [{"amount": "1000", "name": "rulon"}])
        # tahrirlash: qatorlar va chiqimlar to'liq almashadi
        _, errors, d2 = self.parse(line_text=["Kurtka L"], line_sku=[""], line_qty=["3"], line_cny=[""],
                                   cargo_usd="50", usd_rate="12000")
        self.assertEqual(errors, [])
        self.assertEqual(batches_form.save_batch(self.conn, d2, bid), bid)
        b = costs.load_batch(self.conn, bid)
        self.assertEqual([(l["sku"], l["label"], l["qty"]) for l in b["lines"]], [(None, "Kurtka L", 3)])
        self.assertEqual((b["extras"], b["cargo_usd"], b["usd_rate"]), ([], 50, 12000))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 1)

    def test_failed_save_rolls_back(self):
        _, _, d = self.parse(line_text=["A-1"], line_sku=["A-1"], line_qty=["5"], line_cny=[""])
        bid = batches_form.save_batch(self.conn, d)
        broken = dict(d, lines=[{"sku": "A-1"}])                       # "qty" yo'q: yozish o'rtasida xato
        with self.assertRaises(KeyError):
            batches_form.save_batch(self.conn, broken, bid)
        self.assertEqual(len(costs.load_batch(self.conn, bid)["lines"]), 1)   # eski qator saqlanib qoldi


class RatesTests(unittest.TestCase):
    def setUp(self):
        rates._cache.clear()

    @staticmethod
    def fake(responses):
        calls = []

        def fetch(url):
            calls.append(url)
            for suffix, val in responses.items():
                if url.endswith(suffix):
                    return json.dumps(val)
            return "[]"
        return fetch, calls

    @staticmethod
    def row(ccy, rate, date, nominal="1"):
        return {"id": 1, "Code": "156", "Ccy": ccy, "Nominal": nominal, "Rate": rate, "Diff": "0", "Date": date}

    def test_parse_rate(self):
        data = [self.row("USD", "11965.51", "22.10.2026"), self.row("CNY", "1792.29", "22.10.2026"),
                self.row("JPY", "800", "22.10.2026", nominal="10")]
        self.assertEqual(rates.parse_rate(data, "CNY"), (1792.29, "2026-10-22"))
        self.assertEqual(rates.parse_rate(data, "JPY"), (80.0, "2026-10-22"))      # nominal hisobga olinadi
        self.assertEqual(rates.parse_rate(data, "EUR"), (None, None))
        self.assertEqual(rates.parse_rate({"data": data}, "USD")[0], 11965.51)     # ramkali javob
        self.assertEqual(rates.parse_rate([self.row("CNY", "1 792,29", "2026-10-22")], "CNY"),
                         (1792.29, "2026-10-22"))                                   # vergul va bo'shliq
        self.assertEqual(rates.parse_rate([self.row("CNY", "abc", "22.10.2026")], "CNY"), (None, None))
        self.assertEqual(rates.parse_rate([self.row("CNY", "-5", "22.10.2026")], "CNY"), (None, None))
        self.assertEqual(rates.parse_rate("xato", "CNY"), (None, None))
        self.assertEqual(rates.parse_rate([self.row("CNY", "1700", "yaroqsiz")], "CNY"), (1700.0, None))

    def test_current_rate(self):
        fetch, calls = self.fake({"/json/": [self.row("CNY", "1792.29", "22.10.2026")]})
        r = rates.get_rate("cny", None, fetch=fetch, now="2026-10-22")
        self.assertEqual((r["rate"], r["date"], r["warn"]), (1792.29, "2026-10-22", ""))
        rates.get_rate("CNY", "2026-10-22", fetch=fetch, now="2026-10-22")           # bugun: keshdan
        self.assertEqual(len(calls), 1)

    def test_dated_rate_and_weekend_fallback(self):
        fetch, calls = self.fake({"/CNY/2026-10-15/": [self.row("CNY", "1790.00", "15.10.2026")]})
        r = rates.get_rate("CNY", "2026-10-15", fetch=fetch, now="2026-10-22")
        self.assertEqual((r["rate"], r["date"], r["warn"]), (1790.0, "2026-10-15", ""))
        # yakshanba: bank shanba kursini qaytaradi -> ogohlantirish bilan
        fetch, _ = self.fake({"/USD/2026-10-18/": [self.row("USD", "12055.90", "17.10.2026")]})
        r = rates.get_rate("USD", "2026-10-18", fetch=fetch, now="2026-10-22")
        self.assertEqual((r["rate"], r["date"]), (12055.9, "2026-10-17"))
        self.assertIn("e'lon qilmagan", r["warn"])

    def test_empty_day_steps_back(self):
        fetch, calls = self.fake({"/CNY/2026-10-16/": [self.row("CNY", "1788.00", "16.10.2026")]})
        r = rates.get_rate("CNY", "2026-10-18", fetch=fetch, now="2026-10-22")       # 18, 17 bo'sh -> 16
        self.assertEqual((r["rate"], r["date"]), (1788.0, "2026-10-16"))
        self.assertIn("e'lon qilmagan", r["warn"])

    def test_bank_returns_newer_rate_than_asked(self):
        """Arxiv so'ralganda bank joriy kursni qaytarsa: jimgina ishlatilmaydi, ogohlantiriladi."""
        newer = [self.row("CNY", "1792.29", "22.10.2026")]
        fetch, calls = self.fake({"/CNY/2026-10-15/": newer, "/all/2026-10-15/": newer})
        r = rates.get_rate("CNY", "2026-10-15", fetch=fetch, now="2026-10-22")
        self.assertEqual((r["rate"], r["date"]), (1792.29, "2026-10-22"))
        self.assertIn("arxiv kursini bermadi", r["warn"])
        self.assertEqual(len(calls), 2)                                              # orqaga yurib so'rovlar ko'paymaydi

    def test_failures(self):
        with self.assertRaises(rates.RateError):
            rates.get_rate("EUR", None, fetch=self.fake({})[0], now="2026-10-22")
        with self.assertRaises(rates.RateError):                                     # hamma kun bo'sh
            rates.get_rate("CNY", "2026-10-15", fetch=self.fake({})[0], now="2026-10-22")

        def boom(url):
            raise rates.RateError("ulanib bo'lmadi")
        rates._cache.clear()
        with self.assertRaises(rates.RateError):
            rates.get_rate("CNY", None, fetch=boom, now="2026-10-22")
        rates._cache.clear()
        with self.assertRaises(rates.RateError):                                     # JSON emas
            rates.get_rate("CNY", None, fetch=lambda url: "<html>", now="2026-10-22")

    def test_future_date_uses_current_with_warning(self):
        fetch, _ = self.fake({"/json/": [self.row("CNY", "1792.29", "22.10.2026")]})
        r = rates.get_rate("CNY", "2026-12-31", fetch=fetch, now="2026-10-22")
        self.assertEqual(r["rate"], 1792.29)
        self.assertIn("kelajakda", r["warn"])

    def test_past_rates_are_cached(self):
        fetch, calls = self.fake({"/CNY/2026-10-15/": [self.row("CNY", "1790.00", "15.10.2026")]})
        for _ in range(3):
            rates.get_rate("CNY", "2026-10-15", fetch=fetch, now="2026-10-22")
        self.assertEqual(len(calls), 1)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn = fresh_conn()
        orders, expenses = sample_rows()
        sync.upsert_shops(conn, [{"id": 1, "name": "TestShop"}])
        sync.upsert_orders(conn, 1, orders)
        sync.upsert_expenses(conn, 1, expenses)
        conn.commit()
        cls.srv = web.make_server(0)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        conn = connect()
        for t in ("batch_lines", "batch_extras", "batches"):
            conn.execute("DELETE FROM %s" % t)
        conn.commit()

    def req(self, path, fields=None, headers=None, follow=True):
        data = urllib.parse.urlencode(fields, doseq=True).encode() if fields is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request) as r:
                return r.status, r.read().decode("utf-8"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers

    def get(self, path):
        return self.req(path)[:2]

    def post(self, path, fields=None, **kw):
        return self.req(path, fields if fields is not None else {}, **kw)

    @staticmethod
    def form(**kw):
        f = {"shop": "1", "date": "2026-10-01", "goods_cny": "50", "cny_rate": "1000"}
        f.update(kw)
        return f

    def new_batch(self, **kw):
        code, body, headers = self.post("/batches/new", self.form(**kw), follow=False)
        self.assertEqual(code, 303, body[:300])
        self.location = headers["Location"]
        return int(re.search(r"/batches/(\d+)", self.location).group(1))

    def test_01_pages_open(self):
        q = "?from=2026-10-01&to=2026-10-31"
        for path in ("/" + q, "/skus" + q, "/stock", "/batches", "/batches/new"):
            code, body = self.get(path)
            self.assertEqual(code, 200, path)
            self.assertIn("Uzum foyda", body)
        self.assertIn("tannarxi kiritilmagan", self.get("/" + q)[1])
        self.assertEqual(self.get("/batches/999")[0], 404)
        self.assertEqual(self.get("/batches/999/edit")[0], 404)
        self.assertEqual(self.post("/batches/999/edit", self.form())[0], 404)
        self.assertEqual(self.get("/nope")[0], 404)
        self.assertEqual(self.get("/favicon.ico")[0], 204)

    def test_01b_navigation(self):
        for path in ("/", "/skus", "/stock", "/batches", "/batches/new"):
            body = self.get(path)[1]
            nav = body[body.index("<nav>"):body.index("</nav>")]
            self.assertNotIn("Yangi partiya", nav, path)           # yuqori menyuda yo'q
            self.assertIn("Ombor", nav)
        self.assertIn('class=on>Ombor', self.get("/stock")[1])
        self.assertIn('class=on>Partiyalar', self.get("/batches/new")[1])
        self.assertIn('href="/batches/new"', self.get("/batches")[1])        # Partiyalar ichida bor

    def test_02_static_files(self):
        code, body, headers = self.req("/static/batch_form.js")
        self.assertEqual(code, 200)
        self.assertIn("application/javascript", headers["Content-Type"])
        self.assertIn("bform", body)
        for bad in ("/static/../db.py", "/static/%2e%2e%2fdb.py", "/static/.hidden", "/static/batch_form.py",
                    "/static/nope.js", "/static/a/b.js", "/static/"):
            self.assertEqual(self.get(bad)[0], 404, bad)

    def test_03_form_page_contents(self):
        code, body = self.get("/batches/new")
        self.assertEqual(code, 200)
        for needle in ('id="bform"', 'id="lines-sec"', 'id="cargo"', 'id="extras"', 'id="fetch-cny"',
                       "/static/batch_form.js", 'type="application/json"'):
            self.assertIn(needle, body)
        self.assertIn("A-1", body)                                   # do'kon SKU katalogi formada
        self.assertEqual(body.count("<script"), body.count("</script>"))

    def test_10_staged_flow_from_order_to_cost(self):
        dash = "/?from=2026-10-01&to=2026-10-31"
        # 1) faqat Xitoyga buyurtma: tovar CNY + kurs
        bid = self.new_batch(title="Qizil kurtka")
        code, body = self.get(self.location)                         # saqlagandan keyingi sahifa (xabar bilan)
        self.assertEqual(code, 200)
        self.assertIn("Qizil kurtka", body)
        self.assertIn("Partiya saqlandi", body)
        self.assertIn("kiritilmagan", body)                           # kargo
        self.assertIn("Mahsulotlar kiritilmagan", body)
        lst = self.get("/batches")[1]
        self.assertIn("Kargo narxi kiritilmagan", lst)
        self.assertIn("Mahsulotlar kiritilmagan", lst)
        self.assertIn("/batches/%d/edit#cargo" % bid, lst)
        self.assertIn("tannarxi kiritilmagan", self.get(dash)[1])      # foydaga hali ta'sir yo'q
        # 2) mahsulot kartochkasi hali yo'q: faqat nom va soni
        f = self.form(title="Qizil kurtka", line_text="Qizil kurtka M", line_sku="", line_qty="10", line_cny="")
        self.assertEqual(self.post("/batches/%d/edit" % bid, f, follow=False)[0], 303)
        body = self.get("/batches/%d" % bid)[1]
        self.assertIn("SKU yo'q", body)
        self.assertIn("5 000", body)                                  # 50 000 so'm / 10 dona
        self.assertIn("SKU biriktirilmagan: 1 qator", self.get("/batches")[1])
        self.assertIn("tannarxi kiritilmagan", self.get(dash)[1])      # SKU yo'q: hisobga kirmaydi
        # 3) kartochka chiqdi: SKU biriktiriladi (kargo hali yo'q)
        f = self.form(title="Qizil kurtka", line_text="A-1", line_sku="A-1", line_qty="10", line_cny="")
        self.assertEqual(self.post("/batches/%d/edit" % bid, f, follow=False)[0], 303)
        body = self.get(dash)[1]
        self.assertNotIn("sotuvning tannarxi kiritilmagan", body)
        self.assertIn("kargosiz hisoblangan", body)
        self.assertNotIn("SKU yo'q", self.get("/batches/%d" % bid)[1])
        self.assertIn("Haqiqiy foyda", body)
        # 4) kargo narxi chiqdi + qo'shimcha chiqim
        f = self.form(title="Qizil kurtka", line_text="A-1", line_sku="A-1", line_qty="10", line_cny="",
                      cargo_usd="10", usd_rate="12 000", cargo_date="2026-10-08",
                      extra_amount="1000", extra_name="rulon")
        code, _, headers = self.post("/batches/%d/edit" % bid, f, follow=False)
        self.assertEqual(code, 303)
        self.assertIn("O&#x27;zgarishlar saqlandi", self.get(headers["Location"])[1])
        body = self.get("/batches/%d" % bid)[1]
        self.assertIn("17 100", body)                                 # 5 000 + 12 000 kargo + 100 qo'shimcha
        self.assertIn("To&#x27;liq", self.get("/batches")[1])
        self.assertNotIn("kargosiz hisoblangan", self.get(dash)[1])
        self.assertIn("A-1", self.get("/skus?shop=1&from=2026-10-01&to=2026-10-31")[1])
        # tahrirlash formasi saqlangan qiymatlar bilan ochiladi
        edit = self.get("/batches/%d/edit" % bid)[1]
        for needle in ('value="Qizil kurtka"', 'value="2026-10-08"', 'value="12000"', "rulon"):
            self.assertIn(needle, edit)
        # 5) o'chirish
        self.assertEqual(self.post("/batches/%d/delete" % bid, follow=False)[0], 303)
        self.assertIn("Hali partiya yo", self.get("/batches")[1])

    def test_11_invalid_post_keeps_input(self):
        code, body, _ = self.post("/batches/new", self.form(goods_cny="", title="Mening nomim", line_text="Kurtka",
                                                          line_sku="", line_qty="3", line_cny=""))
        self.assertEqual(code, 400)
        self.assertIn("kiritilmagan", body)
        self.assertIn('value="Mening nomim"', body)
        self.assertIn("Kurtka", body)                                 # qator yo'qolmaydi
        self.assertEqual(connect().execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)

    def test_12_user_text_is_escaped(self):
        bid = self.new_batch(title='"><script>alert(1)</script>', note="<b>x</b>",
                             line_text="x</script><b>y", line_sku="", line_qty="2", line_cny="")
        for path in ("/batches", "/batches/%d" % bid, "/batches/%d/edit" % bid, "/stock"):
            body = self.get(path)[1]
            self.assertNotIn("<script>alert(1)</script>", body, path)
            self.assertNotIn("<b>x</b>", body, path)
            self.assertEqual(body.count("<script"), body.count("</script>"), path)     # JSON ichida </script> yo'q
        self.assertIn("&lt;script&gt;", self.get("/batches/%d" % bid)[1])

    def test_13_cross_site_and_foreign_host_are_refused(self):
        code = self.post("/batches/new", self.form(), headers={"Origin": "http://evil.example"}, follow=False)[0]
        self.assertEqual(code, 403)
        code = self.post("/batches/new", self.form(), headers={"Origin": "null"}, follow=False)[0]
        self.assertEqual(code, 403)
        self.assertEqual(self.get("/batches")[1].count("/batches/1"), 0)
        self.assertEqual(self.req("/", headers={"Host": "evil.example"})[0], 403)       # DNS rebinding
        code = self.post("/batches/new", self.form(), headers={"Origin": self.base}, follow=False)[0]
        self.assertEqual(code, 303)                                                      # o'z sahifamizdan: mumkin

    def test_14_api_rate(self):
        original = web.get_rate
        web.get_rate = lambda ccy, date=None: {"rate": 1792.29, "date": "2026-10-21", "warn": ""}
        try:
            code, body, headers = self.req("/api/rate?ccy=cny&date=2026-10-21")
        finally:
            web.get_rate = original
        self.assertEqual(code, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body), {"ok": True, "rate": 1792.29, "date": "2026-10-21", "warn": ""})
        data = json.loads(self.get("/api/rate?ccy=EUR")[1])            # tarmoqsiz: valyuta noto'g'ri
        self.assertFalse(data["ok"])
        self.assertIn("error", data)

        def failing(ccy, date=None):
            raise rates.RateError("ulanib bo'lmadi")
        web.get_rate = failing
        try:
            data = json.loads(self.get("/api/rate?ccy=CNY")[1])
        finally:
            web.get_rate = original
        self.assertEqual(data, {"ok": False, "error": "ulanib bo'lmadi"})

    def test_15_stock_page_lists_transit_batches(self):
        self.assertIn("Yo&#x27;lda partiya yo&#x27;q", self.get("/stock")[1].replace("'", "&#x27;"))
        bid = self.new_batch(title="Yo'ldagi kurtkalar", date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                             line_text="A-1", line_sku="A-1", line_qty="40", line_cny="")
        body = self.get("/stock")[1]
        self.assertIn("/batches/%d" % bid, body)
        self.assertIn("Kargo narxi kiritilmagan", body)
        self.assertIn("40", body)

    def test_16_dashboard_warns_about_missing_cargo_and_still_counts(self):
        make = connect()
        make_batch(make, 1, "2026-10-01", 50, 1000, None, None, [("A-1", 10, None)])
        body = self.get("/?from=2026-10-01&to=2026-10-31")[1]
        self.assertIn("kargosiz hisoblangan", body)
        self.assertIn("Haqiqiy foyda", body)


class StockTests(unittest.TestCase):
    NOW = "2026-10-22"

    @staticmethod
    def day(offset):
        return (datetime.strptime(StockTests.NOW, "%Y-%m-%d") + timedelta(days=offset)).strftime("%Y-%m-%d")

    def order(self, oid, sku, offset, amount=1, status="TO_WITHDRAW"):
        ms = day_start_ms(self.day(offset)) + 3600_000
        return dict(id=oid, orderId=oid, skuTitle=sku, productId=1, productTitle=sku, status=status, date=ms,
                    dateIssued=ms + 1 if status != "PROCESSING" else None, sellPrice=10000, amount=amount,
                    commission=1000, sellerProfit=7000, logisticDeliveryFee=2000, amountReturns=0)

    def setUp(self):
        self.conn = fresh_conn()
        sync.upsert_shops(self.conn, [{"id": 1, "name": "TestShop"}])
        rows, n = [], [100]

        def add(sku, offsets, **kw):
            for o in offsets:
                n[0] += 1
                rows.append(self.order(n[0], sku, o, **kw))
        old = [-80]                                                      # eski buyurtma: faqat SKU yoshi uchun
        add("S-FAST", old + list(range(-29, 1)))                         # 30 kunda 30 dona = 1/kun
        add("S-FAST", list(range(-10, 0)), status="CANCELED")            # bekor qilinganlar hisobga kirmaydi
        add("S-SOON", old + list(range(-29, 1, 2)))                      # 15 dona = 0.5/kun
        add("S-OK", old + list(range(-29, 1, 5)))                        # 6 dona = 0.2/kun
        add("S-OUT", old + list(range(-29, 1, 2)))                       # 0.5/kun, qoldiq 0
        add("S-NEW", [-2, -2, -1, -1, 0, 0])                             # yangi: 6 dona, yoshi 3 kun
        add("S-SLOW", old + [-5])                                        # juda kam sotiladi
        sync.upsert_orders(self.conn, 1, rows)
        for sku, fbo, status, defected in (("S-FAST", 10, "IN_STOCK", 0), ("S-SOON", 20, "IN_STOCK", 0),
                                           ("S-OK", 100, "IN_STOCK", 0), ("S-OUT", 0, "RUN_OUT", 1),
                                           ("S-NEW", 30, "IN_STOCK", 0), ("S-DEAD", 5, "IN_STOCK", 0),
                                           ("S-ARCH", 7, "ARCHIVED", 0), ("S-GHOST", 0, "RUN_OUT", 0),
                                           ("S-SLOW", 3, "IN_STOCK", 0)):
            self.conn.execute("INSERT INTO skus (shop_id, sku, title, qty_fbo, qty_sold, qty_returned, status, "
                              "qty_defected) VALUES (1, ?, ?, ?, 0, 0, ?, ?)", (sku, sku + " nomi", fbo, status, defected))
        self.conn.commit()

    def rows(self):
        rows, hidden = stock.stock_rows(self.conn, [1], self.NOW)
        return {r["sku"]: r for r in rows}, hidden, rows

    def test_classify_boundaries(self):
        c = stock.classify
        self.assertEqual(c(0, 0, 30), ("nosales", None))
        self.assertEqual(c(50, 0, 30), ("nosales", None))
        self.assertEqual(c(0, 1.0, 30), ("out", 0.0))
        self.assertEqual(c(30, 1.0, 30)[0], "order")        # tugashiga lead kun: buyurtma vaqti
        self.assertEqual(c(31, 1.0, 30)[0], "soon")
        self.assertEqual(c(44, 1.0, 30)[0], "soon")
        self.assertEqual(c(45, 1.0, 30)[0], "ok")

    def test_statuses_and_velocity(self):
        by, hidden, rows = self.rows()
        self.assertAlmostEqual(by["S-FAST"]["v"][30], 1.0)
        self.assertEqual(by["S-FAST"]["code"], "order")
        self.assertAlmostEqual(by["S-FAST"]["cover"], 10.0)
        self.assertEqual(by["S-FAST"]["order_by"], "hozir")
        self.assertAlmostEqual(by["S-SOON"]["base"], 0.5)
        self.assertEqual(by["S-SOON"]["code"], "soon")                   # 40 kunlik qoldiq: 30 < 40 <= 44
        self.assertEqual(by["S-SOON"]["order_by"], self.day(10))
        self.assertEqual(by["S-OK"]["code"], "ok")
        self.assertEqual(by["S-OK"]["order_by"], self.day(int(500 - 30)))
        self.assertEqual(by["S-OUT"]["code"], "out")
        self.assertEqual(by["S-OUT"]["order_by"], "hozir")
        self.assertEqual(by["S-OUT"]["defected"], 1)
        self.assertEqual(by["S-DEAD"]["code"], "nosales")
        self.assertNotIn("S-ARCH", by)                                    # arxivdagi ko'rsatilmaydi
        self.assertNotIn("S-GHOST", by)                                   # qoldiq ham, sotuv ham yo'q
        self.assertEqual(hidden, 1)

    def test_new_sku_velocity_uses_age_floor(self):
        by, _, _ = self.rows()
        # 6 dona, birinchi sotuv 2 kun oldin: kamida 7 kunga bo'linadi (6 / 7), 3 kunga emas
        self.assertAlmostEqual(by["S-NEW"]["v"][30], 6 / 7.0)
        self.assertEqual(by["S-NEW"]["code"], "soon")                    # 30 / 0.857 = 35 kun

    def test_order_most_urgent_first(self):
        _, _, rows = self.rows()
        codes = [r["code"] for r in rows]
        self.assertEqual(codes, sorted(codes, key=lambda c: stock.ORDER[c]))
        self.assertEqual(rows[0]["sku"], "S-OUT")                         # tugagan birinchi
        order_class = [r for r in rows if r["code"] == "order"]
        self.assertEqual(order_class[0]["sku"], "S-FAST")

    def test_transit_units_and_value(self):
        make_batch(self.conn, 1, self.day(-5), 100, 1000, None, None, [("S-OUT", 40, None), (None, 5, None, "Yangi mahsulot")])
        make_batch(self.conn, 1, self.day(-60), 100, 1000, 0, None, [("S-OUT", 99, None)])       # allaqachon qo'lga olingan
        by, _, _ = self.rows()
        self.assertEqual(by["S-OUT"]["transit"], 40)                      # faqat kargosi kiritilmaganlar
        self.assertEqual(by["S-OUT"]["code"], "out")                      # holat faqat FBO qoldiqqa qarab
        items = stock.transit_batches(self.conn, [1], self.NOW, 30)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["age"], items[0]["eta"], items[0]["late"]), (5, self.day(25), False))
        self.assertEqual(items[0]["state"]["unlinked"], 1)
        late = stock.transit_batches(self.conn, [1], self.day(60), 30)
        self.assertTrue(late[0]["late"])
        self.assertEqual(by["S-OUT"]["unit_cost"] is not None, True)      # tannarx bor (SKU partiyada)

    def test_cost_value_of_stock(self):
        make_batch(self.conn, 1, self.day(-40), 50, 1000, 0, None, [("S-OK", 10, None)])         # 5000 so'm/dona
        by, _, _ = self.rows()
        self.assertAlmostEqual(by["S-OK"]["unit_cost"], 5000)
        self.assertAlmostEqual(by["S-OK"]["value"], 5000 * 100)
        self.assertIsNone(by["S-FAST"]["unit_cost"])

    def test_page_renders_with_all_sections(self):
        body = stock.page_stock({})
        self.assertIn("S-FAST", body)
        self.assertIn("Buyurtma vaqti", body)
        self.assertIn("Kam sotiladigan", body)                            # S-SLOW alohida bo'limda
        self.assertIn("sotilmagan", body)                                 # S-DEAD
        self.assertNotIn("S-ARCH", body)
        self.assertEqual(body.count("<details>"), body.count("</details>"))


@unittest.skipUnless(os.path.exists(HISTORY), "uzum_history.json topilmadi: haqiqiy ma'lumot sinovi o'tkazib yuborildi")
class RealDataTests(unittest.TestCase):
    """Haqiqiy tarix bilan: yuqorida Excel hisoboti bilan bir so'mgacha solishtirilgan raqamlar."""

    def test_bydurii_matches_verified_numbers(self):
        conn = fresh_conn()
        sync.import_history(conn, HISTORY)
        r = rpt.build_report(conn, [106121], "2026-07-14", "2026-10-22")
        d = r["done"]
        self.assertEqual((d["n"], d["revenue"], d["commission"], d["logistics"], d["seller_profit"]),
                         (1045, 30002480, 6882481, 5582500, 17537499))
        self.assertEqual(r["canceled"], {"n": 782, "after_pickup": 175})
        self.assertEqual(round(r["ex"]["ad"]), 671018)
        # hamma sotuv SKU'lari katalogda bor
        miss = conn.execute("SELECT COUNT(DISTINCT sku) FROM order_items o WHERE sku NOT IN "
                            "(SELECT sku FROM skus s WHERE s.shop_id=o.shop_id)").fetchone()[0]
        self.assertEqual(miss, 0)

    def test_return_percent_matches_uzum_own_counter(self):
        """'Qaytgan %' Uzumning returnedPercentage'si bilan bir xil: qaytgan / (sotilgan + qaytgan)."""
        conn = fresh_conn()
        sync.import_history(conn, HISTORY)
        with open(HISTORY, encoding="utf-8") as f:
            data = json.load(f)
        want = {}
        for sid, blk in data["per_shop"].items():
            for p in blk["products"]["rows"]:
                for s in p.get("skuList") or []:
                    if s.get("returnedPercentage") is not None and s.get("skuFullTitle"):
                        want[(int(sid), s["skuFullTitle"])] = s["returnedPercentage"]
        checked = 0
        for sid in (106121, 135204):
            for a in rpt.sku_rows(conn, sid, "2026-01-01", "2026-10-22"):
                if a["return_pct"] is not None and (sid, a["sku"]) in want:
                    self.assertAlmostEqual(a["return_pct"], want[(sid, a["sku"])], places=2, msg=a["sku"])
                    checked += 1
        self.assertGreater(checked, 20)

    def test_stock_page_on_real_data(self):
        conn = fresh_conn()
        sync.import_history(conn, HISTORY)
        rows, hidden = stock.stock_rows(conn, [106121, 135204], "2026-10-22")
        self.assertEqual(sum(r["stock"] for r in rows), 678)          # Uzum bergan jami FBO qoldiq bilan bir xil
        self.assertEqual(sum(r["defected"] for r in rows), 9)         # brak donalar
        self.assertTrue(all(r["code"] in stock.ORDER for r in rows))
        out = [r for r in rows if r["code"] == "out"]
        self.assertTrue(out and out[0]["base"] >= out[-1]["base"])     # ko'p sotiladigani yuqorida
        body = stock.page_stock({})
        self.assertIn("Omborda (FBO)", body)
        self.assertIn("678 dona", body)
        for path in ("/", "/skus"):                                   # real ma'lumotda sahifalar ochiladi
            self.assertTrue(getattr(web, "page_dashboard" if path == "/" else "page_skus")(
                {"from": ["2026-07-14"], "to": ["2026-10-22"]}))


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""SQLite bazasi: jadvallar va ulanish."""
import sqlite3

from .util import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS skus (
  shop_id INTEGER, sku TEXT, sku_id INTEGER, product_id INTEGER, title TEXT, barcode TEXT,
  commission_pct REAL, price INTEGER, qty_fbo INTEGER, qty_sold INTEGER, qty_returned INTEGER,
  weight_g INTEGER, seller_code TEXT, status TEXT, qty_defected INTEGER,
  PRIMARY KEY (shop_id, sku));
CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY, shop_id INTEGER, order_id INTEGER, sku TEXT, product_id INTEGER,
  title TEXT, status TEXT, created_ms INTEGER, issued_ms INTEGER, sell_price INTEGER,
  amount INTEGER, commission INTEGER, seller_profit INTEGER, logistics_fee INTEGER,
  amount_returns INTEGER, return_cause TEXT);
CREATE INDEX IF NOT EXISTS ix_items_shop_date ON order_items (shop_id, created_ms);
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY, shop_id INTEGER, created_ms INTEGER, kind TEXT, type TEXT, code TEXT,
  name TEXT, price REAL, order_id INTEGER, item_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_exp_shop_date ON expenses (shop_id, created_ms);
CREATE INDEX IF NOT EXISTS ix_exp_item ON expenses (item_id);
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY, shop_id INTEGER, number INTEGER, date_created TEXT, status TEXT,
  full_price INTEGER, accepted INTEGER, to_stock INTEGER, has_issue INTEGER);
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, date TEXT, goods_cny REAL,
  cny_rate REAL, cargo_usd REAL, usd_rate REAL, note TEXT, title TEXT, cargo_date TEXT);
CREATE TABLE IF NOT EXISTS batch_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, sku TEXT, qty INTEGER, cny_unit REAL,
  label TEXT);
CREATE TABLE IF NOT EXISTS batch_extras (
  id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, name TEXT, amount REAL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


# Eski uzum.db fayllari uchun: yangi ustunlar avtomatik qo'shiladi, ma'lumot saqlanib qoladi.
#   batches.title      : partiyaning qisqa nomi (SKU hali yo'q paytda tanib olish uchun)
#   batches.cargo_date : kargo to'langan (tovar qo'lga olingan) sana
#   batch_lines.label  : SKU hali yo'q mahsulot nomi (keyin SKU biriktiriladi; sku=NULL)
#   skus.qty_defected  : Uzum omborida yaroqsiz (brak) deb topilgan donalar (keyingi yangilashda to'ladi)
# Eslatma: batches.cargo_usd NULL = kargo narxi hali kiritilmagan, 0 = kargo yo'q.
MIGRATIONS = [
    ("batches", "title", "TEXT"),
    ("batches", "cargo_date", "TEXT"),
    ("batch_lines", "label", "TEXT"),
    ("skus", "qty_defected", "INTEGER"),
]


def _migrate(conn):
    changed = False
    for table, col, typ in MIGRATIONS:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        if col not in cols:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, typ))
            changed = True
    if changed:
        conn.commit()


def connect(path=None):
    conn = sqlite3.connect(path or db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

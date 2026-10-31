"""B4.9 ``/imports/legacy`` (haqiqiy PostgreSQL): legacy ``uzum.db`` → xaridlar, solishtirma hisobot.

Sintetik legacy bazasi haqiqiy legacy sxemasi bilan (``uzum_profit.db.SCHEMA``) yaratiladi. Tekshiriladi: avval
ko'rib chiqish (hech narsa yozilmaydi), import (qatorlar SKU → tovar, bog'lanmagan SKU'ga yangi tovar, topilmagan SKU —
"yangi tovar", qo'lda kurslar, dona bo'yicha taqsimot, bosqich sanalari), birlik tannarx legacy bilan bir xil (jonli
va lotlar), qayta yuklash xavfsiz (sotuvchi o'zgartirgani saqlanadi), eski fayl ustunlarsiz, buzilgan qator, noto'g'ri
fayl, ruxsatlar, audit, boshqa tashkilot SKU'lari ko'rinmaydi.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from mptools import mp_api
from sellerfake import TOKEN, A, create_account
from test_calc import Org
from test_reports import World
from upapi.auth.deps import COOKIE

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from uzum_profit import costs as legacy_costs
from uzum_profit.db import SCHEMA

D = Decimal
UNCONNECTED = 106121  # legacy'da bor, yangi tashkilotga ulanmagan do'kon


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as urls:
        yield urls


@pytest.fixture(scope="module")
def world(db: dict[str, str]) -> Iterator[World]:
    settings = sf.settings_for(db)
    account = create_account(db, settings, TOKEN, [A])
    other = create_account(db, settings, TOKEN, [A])
    a = Org(db, account.org_id, account.shops[A])
    b = Org(db, other.org_id, other.shops[A])
    with mp_api(db) as api:
        w = World(api, a, b, other.org_id)
        w.ids["item"], w.ids["sku"] = a.item("Mashina")  # tovarga bog'langan SKU
        a._ext += 1
        w.ids["free_sku"] = a.insert(  # tovarsiz SKU — import yangi tovar yaratib bog'laydi
            "mp_skus", shop_id=a.shop_id, external_id=a._ext, sku_code="Qalpoq-Qizil"
        )
        b.item("Begona")  # boshqa tashkilotda shu kod — ko'rinmasligi kerak
        for role in ("owner", "manager", "accountant", "warehouse"):
            phone = api.login()
            user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
            api.admin(
                "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, %s)",
                [a.org_id, user, role],
            )
            w.sessions[role] = api.client.cookies[COOKIE]
        yield w


def legacy_db(path: Path, schema: str = SCHEMA) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    conn.execute("INSERT INTO shops VALUES (?, 'byDurii'), (?, 'EL-ONE')", (A, UNCONNECTED))
    return conn


def fill(conn: sqlite3.Connection) -> None:
    """Uchta partiya: to'liq (narxli va narxsiz qatorlar, kargo sanasi, qo'shimchalar), yo'ldagi (kargo yo'q),
    ulanmagan do'kon."""
    conn.execute(
        "INSERT INTO batches (id, shop_id, date, goods_cny, cny_rate, cargo_usd, usd_rate, note, title, cargo_date) "
        "VALUES (1, ?, '2026-07-10', 5000, 1745.5, 120.5, 12650, 'Birinchi', 'Iyul partiyasi', '2026-07-30'), "
        "(2, ?, '2026-09-01', 3000, 1760, NULL, NULL, NULL, NULL, NULL), "
        "(3, ?, '2026-08-05', 700, 1750, 0, NULL, NULL, 'Boshqa do''kon', NULL)",
        (A, A, UNCONNECTED),
    )
    conn.execute(
        "INSERT INTO batch_lines (id, batch_id, sku, qty, cny_unit, label) VALUES "
        "(10, 1, 'mashina', 40, 50.25, NULL), "  # katta-kichik harfsiz moslanadi
        "(11, 1, 'Qalpoq-Qizil', 70, NULL, NULL), "
        "(12, 1, NULL, 13, NULL, 'Yangi sumka'), "
        "(13, 1, 'Yo''q-SKU', 7, NULL, NULL), "
        "(20, 2, 'Mashina', 100, NULL, NULL), "
        "(30, 3, 'Mashina', 10, NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO batch_extras (id, batch_id, name, amount) VALUES "
        "(1, 1, 'Bojxona', 350000), (2, 1, 'Qadoq', 125000.5)"
    )
    conn.commit()


@pytest.fixture(scope="module")
def uzum_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("legacy") / "uzum.db"
    conn = legacy_db(path)
    fill(conn)
    conn.close()
    return path


def post(w: World, data: bytes, role: str = "owner", dry_run: bool = True) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.post(
        f"/api/v1/orgs/{w.org_id}/imports/legacy",
        params={"dry_run": str(dry_run).lower()},
        content=data,
        headers={"X-Requested-With": "fetch", "Content-Type": "application/octet-stream"},
    )


def ok(r: Any) -> Any:
    assert r.status_code == 200, r.text
    return r.json()


def purchases(w: World) -> list[Any]:
    return w.a.sql(
        "SELECT legacy_batch_id, title, status, ordered_on, paid_on, sent_to_uzum_on, note, id "
        "FROM purchases WHERE org_id = %s ORDER BY legacy_batch_id",
        [w.org_id],
    )


def legacy_reference(path: Path) -> dict[int, list[Decimal]]:
    """Haqiqiy legacy kodi (``uzum_profit.costs``) natijasi — partiya → qatorlar birlik tannarxi."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {
            b["id"]: [D(repr(r["unit_cost"])) for r in legacy_costs.compute_batch(b)]
            for b in legacy_costs.load_batches(conn)
        }
    finally:
        conn.close()


def test_bad_files(world: World, tmp_path: Path) -> None:
    w = world
    r = post(w, b"not a database")
    assert r.status_code == 422 and r.json()["code"] == "bad_legacy_file"
    path = tmp_path / "other.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE foo (x)")
    conn.commit()
    conn.close()
    r = post(w, path.read_bytes())
    assert r.status_code == 422 and "batches" in r.json()["detail"]
    r = post(w, b"SQLite format 3\x00" + b"\x00" * 200)  # sarlavha bor, ichi buzuq
    assert r.status_code == 422 and r.json()["code"] == "bad_legacy_file"


def test_permissions(world: World, uzum_db: Path) -> None:
    for role in ("accountant", "warehouse"):
        assert post(world, uzum_db.read_bytes(), role).status_code == 403
    assert post(world, uzum_db.read_bytes(), "manager").status_code == 200  # dry run
    assert purchases(world) == []


def test_dry_run_then_import_and_compare(world: World, uzum_db: Path) -> None:
    w, a = world, world.a
    data = uzum_db.read_bytes()
    reference = legacy_reference(uzum_db)

    preview = ok(post(w, data))
    assert preview["dry_run"] and preview["created"] == 3 and preview["mismatched"] == 0
    assert purchases(w) == []  # hech narsa yozilmadi
    assert a.sql("SELECT item_id FROM mp_skus WHERE id = %s", [w.ids["free_sku"]])[0][0] is None
    assert all(b["purchase_id"] is None for b in preview["batches"])
    assert {s["legacy_id"]: s["connected"] for s in preview["shops"]} == {
        A: True,
        UNCONNECTED: False,
    }

    report = ok(post(w, data, dry_run=False))
    assert not report["dry_run"]
    assert (report["created"], report["existing"], report["errors"], report["mismatched"]) == (
        3,
        0,
        0,
        0,
    )
    # Ko'rib chiqish va import hisoboti bir xil (purchase_id dan tashqari).
    strip = [{k: v for k, v in b.items() if k != "purchase_id"} for b in report["batches"]]
    assert strip == [{k: v for k, v in b.items() if k != "purchase_id"} for b in preview["batches"]]

    by_id = {b["legacy_id"]: b for b in report["batches"]}
    first = by_id[1]
    assert first["title"] == "Iyul partiyasi" and first["shop"] == "byDurii"
    assert first["status"] == "created" and first["match"] is True
    assert first["stage"] == "sent_to_uzum" and first["units"] == 130
    assert first["new_items"] == 1 and first["unmatched"] == ["Yo'q-SKU"]
    assert [x["item_name"] for x in first["lines"]] == ["Mashina", "Qalpoq-Qizil", None, None]
    for line, ref in zip(first["lines"], reference[1], strict=True):
        assert abs(D(line["legacy_unit_cost"]) - ref) <= D("0.01")
        assert abs(D(line["new_unit_cost"]) - ref) <= D("0.01")  # M9: 1 tiyingacha
    total = D(5000) * D("1745.5") + D("120.5") * 12650 + D("475000.5")
    assert D(first["total_new"]) == total.quantize(D("0.01"))
    assert abs(D(first["total_legacy"]) - total) <= D("0.01")

    road = by_id[2]
    assert road["stage"] == "paid" and road["match"] is True  # kargo kiritilmagan — "yo'lda"
    assert road["title"] == "Legacy #2"
    assert road["lines"][0]["new_unit_cost"] == road["lines"][0]["legacy_unit_cost"] == "52800.00"
    other_shop = by_id[3]
    assert other_shop["shop"] == "EL-ONE" and other_shop["unmatched"] == ["Mashina"]
    assert any("ulanmagan" in x for x in other_shop["warnings"])
    assert other_shop["stage"] == "sent_to_uzum"  # 0 — kargo yo'q, buyurtma sanasi

    rows = {r[0]: r for r in purchases(w)}
    assert set(rows) == {1, 2, 3}
    _, title, status, ordered, paid, sent, note, pid = rows[1]
    assert (title, status, ordered, paid, sent) == (
        "Iyul partiyasi",
        "sent_to_uzum",
        date(2026, 7, 10),
        date(2026, 7, 10),
        date(2026, 7, 30),
    )
    assert "Birinchi" in note and "Bojxona: 350000.00 so'm" in note and "#1" in note
    assert rows[2][2] == "paid" and rows[2][5] is None

    # Qatorlar: SKU → tovar (bog'langan), bog'lanmagan SKU → yangi tovar va SKU bog'landi, qolganlari — "yangi tovar".
    lines = a.sql(
        "SELECT item_id, temp_name, ordered_qty, received_qty, unit_price, currency FROM purchase_lines "
        "WHERE purchase_id = %s ORDER BY created_at",
        [pid],
    )
    new_item = a.sql("SELECT item_id FROM mp_skus WHERE id = %s", [w.ids["free_sku"]])[0][0]
    assert new_item is not None
    assert a.sql("SELECT name FROM items WHERE id = %s", [new_item])[0][0] == "Qalpoq-Qizil"
    assert lines == [
        (w.ids["item"], None, 40, 40, D("50.2500"), "CNY"),
        (new_item, None, 70, 70, None, None),
        (None, "Yangi sumka", 13, 13, None, None),
        (None, "Yo'q-SKU", 7, 7, None, None),
    ]
    comps = a.sql(
        "SELECT kind, amount, currency, paid_on, rate_mode, rate, allocation, targets->'lines' IS NULL "
        "FROM cost_components WHERE purchase_id = %s ORDER BY created_at",
        [pid],
    )
    assert comps == [
        ("goods", D("2010.0000"), "CNY", date(2026, 7, 10), "manual", D("1745.5"), "units", False),
        ("goods", D("2990.0000"), "CNY", date(2026, 7, 10), "manual", D("1745.5"), "units", False),
        ("cargo", D("120.5000"), "USD", date(2026, 7, 30), "manual", D("12650"), "units", True),
        ("other", D("350000.0000"), "UZS", date(2026, 7, 10), "cbu", None, "units", True),
        ("other", D("125000.5000"), "UZS", date(2026, 7, 10), "cbu", None, "units", True),
    ]

    # Xarid sahifasi ham xuddi shu tannarxni ko'rsatadi; hisob ishidan keyin lotlar ham.
    w.api.client.cookies.set(COOKIE, w.sessions["owner"])
    det = w.get(f"purchases/{pid}")
    assert [x["flags"] for x in det["lines"]] == [[], [], [], []]
    a.recalc(datetime.now(UTC))
    lots = a.sql(
        "SELECT l.unit_cost, l.ready_on FROM lots l JOIN purchase_lines pl ON pl.id = l.purchase_line_id "
        "WHERE pl.purchase_id = %s ORDER BY pl.created_at",
        [pid],
    )
    assert [r[1] for r in lots] == [date(2026, 7, 30)] * 4
    for (unit, _), ref in zip(lots, reference[1], strict=True):
        assert abs(unit - ref) <= D("0.01")

    actions = {r[0] for r in a.sql("SELECT action FROM audit_log WHERE org_id = %s", [w.org_id])}
    assert {"purchase.import_legacy", "legacy.import", "sku.link_item"} <= actions
    # Boshqa tashkilotning shu kodli SKU'si ko'rinmadi va tegilmadi.
    assert w.b.sql("SELECT count(*) FROM purchases WHERE org_id = %s", [w.other])[0][0] == 0


def test_reimport_keeps_seller_edits(world: World, uzum_db: Path) -> None:
    w, a = world, world.a
    pid = next(r[7] for r in purchases(w) if r[0] == 2)
    # Sotuvchi o'zgartirdi: kargo qo'shdi (legacy'da yo'q edi).
    a.sql(
        "INSERT INTO cost_components (org_id, purchase_id, kind, amount, currency) "
        "VALUES (%s, %s, 'cargo', 1000000, 'UZS')",
        [w.org_id, pid],
    )
    report = ok(post(w, uzum_db.read_bytes(), dry_run=False))
    assert (report["created"], report["existing"]) == (0, 3)
    by_id = {b["legacy_id"]: b for b in report["batches"]}
    assert by_id[2]["status"] == "exists" and by_id[2]["purchase_id"] == str(pid)
    assert by_id[2]["match"] is False  # kargo qo'shildi — endi legacy'dan farq qiladi
    assert D(by_id[2]["lines"][0]["difference"]) == D(10000)
    assert by_id[2]["lines"][0]["item_name"] == "Mashina"
    assert by_id[1]["match"] is True
    assert len(purchases(w)) == 3
    # Qator o'chirilsa — qatorma-qator solishtirilmaydi.
    pid1 = next(r[7] for r in purchases(w) if r[0] == 1)
    a.sql(
        "DELETE FROM cost_components WHERE purchase_id = %s AND targets->'lines' IS NOT NULL",
        [pid1],
    )
    a.sql("DELETE FROM purchase_lines WHERE purchase_id = %s AND temp_name = 'Yangi sumka'", [pid1])
    again = {b["legacy_id"]: b for b in ok(post(w, uzum_db.read_bytes()))["batches"]}
    assert again[1]["match"] is None and any("o'zgartirilgan" in x for x in again[1]["warnings"])


OLD_SCHEMA = """
CREATE TABLE shops (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE batches (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, date TEXT, goods_cny REAL,
  cny_rate REAL, cargo_usd REAL, usd_rate REAL, note TEXT);
CREATE TABLE batch_lines (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, sku TEXT, qty INTEGER,
  cny_unit REAL);
CREATE TABLE batch_extras (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, name TEXT, amount REAL);
"""


def test_old_file_without_new_columns_and_broken_rows(world: World, tmp_path: Path) -> None:
    w = world
    path = tmp_path / "old.db"
    conn = legacy_db(path, OLD_SCHEMA)
    conn.execute(
        "INSERT INTO batches VALUES (101, ?, '2026-05-01', 1000, 1700, 10, 12500, NULL), "
        "(102, ?, 'kecha', 1, 1, 1, 1, NULL), (103, ?, '2026-05-02', 'abc', 1, NULL, NULL, NULL)",
        (A, A, A),
    )
    conn.execute("INSERT INTO batch_lines VALUES (1, 101, 'Mashina', 20, NULL)")
    conn.commit()
    conn.close()
    report = ok(post(w, path.read_bytes()))
    by_id = {b["legacy_id"]: b for b in report["batches"]}
    assert by_id[101]["status"] == "created" and by_id[101]["match"] is True
    assert by_id[101]["stage"] == "sent_to_uzum"  # kargo sanasi ustuni yo'q — buyurtma sanasi
    assert by_id[101]["lines"][0]["new_unit_cost"] == "91250.00"  # 1000×1700/20 + 10×12500/20
    assert by_id[102]["status"] == "error" and by_id[103]["status"] == "error"
    assert report["errors"] == 2

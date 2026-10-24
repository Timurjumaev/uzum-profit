"""B1.9 solishtirish skripti: sintetik legacy bazasida majburiy tekshiruvlar o'tadi."""

import json
import os
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "compare_legacy.py"


def ms(day: str, hour: int = 10) -> int:
    from datetime import datetime, timedelta, timezone

    return int(
        datetime.fromisoformat(day)
        .replace(hour=hour, tzinfo=timezone(timedelta(hours=5)))
        .timestamp()
        * 1000
    )


ORDERS = [
    {
        "id": 11,
        "orderId": 1,
        "skuTitle": "A-1",
        "status": "TO_WITHDRAW",
        "date": ms("2026-09-05"),
        "sellPrice": 20000,
        "amount": 1,
        "commission": 4000,
        "sellerProfit": 10750,
        "logisticDeliveryFee": 5250,
        "amountReturns": 0,
    },
    {
        "id": 12,
        "orderId": 2,
        "skuTitle": "A-1",
        "status": "TO_WITHDRAW",
        "date": ms("2026-10-12"),
        "sellPrice": 20000,
        "amount": 2,
        "commission": 8000,
        "sellerProfit": 32000,
        "logisticDeliveryFee": 0,
        "amountReturns": 0,
    },
    {
        "id": 13,
        "orderId": 3,
        "skuTitle": "b-2",
        "status": "TO_WITHDRAW",
        "date": ms("2026-10-13"),
        "sellPrice": 55000,
        "amount": 3,
        "commission": 33000,
        "sellerProfit": 116250,
        "logisticDeliveryFee": 15750,
        "amountReturns": 1,
    },
    {
        "id": 14,
        "orderId": 4,
        "skuTitle": "A-1",
        "status": "PROCESSING",
        "date": ms("2026-10-20"),
        "sellPrice": 20000,
        "amount": 1,
        "commission": 4000,
        "sellerProfit": 16000,
        "logisticDeliveryFee": 0,
        "amountReturns": 0,
    },
    {
        "id": 15,
        "orderId": 5,
        "skuTitle": "A-1",
        "status": "PARTIALLY_CANCELLED",
        "date": ms("2026-10-21"),
        "sellPrice": 20000,
        "amount": 1,
        "commission": 4000,
        "sellerProfit": 16000,
        "logisticDeliveryFee": 0,
        "amountReturns": 0,
    },
    {
        "id": 16,
        "orderId": 6,
        "skuTitle": "C-3",
        "status": "CANCELED",
        "date": ms("2026-10-22"),
        "sellPrice": 9000,
        "amount": 1,
        "commission": 0,
        "sellerProfit": 0,
        "logisticDeliveryFee": 0,
        "amountReturns": 0,
    },
]
EXPENSES = [
    {
        "id": 101,
        "dateCreated": ms("2026-10-05"),
        "name": "Xaridor tovarni olganida 2000.5 so'm yechib oldik",
        "source": "Marketing",
        "paymentPrice": 2000,
        "externalId": "AD#11-1",
        "code": "У000120",
        "type": "OUTCOME",
    },
    {
        "id": 102,
        "dateCreated": ms("2026-10-06"),
        "name": "Saqlash",
        "source": "Ombor",
        "paymentPrice": 3000,
        "externalId": "x",
        "code": "С000003",
        "type": "OUTCOME",
    },
    {
        "id": 103,
        "dateCreated": ms("2026-10-07"),
        "name": "Fotostudiya",
        "source": "Boshqa",
        "paymentPrice": 7000,
        "externalId": "y",
        "code": "Y000002",
        "type": "OUTCOME",
    },
    {
        "id": 104,
        "dateCreated": ms("2026-10-08"),
        "name": "Reklama qaytarildi",
        "source": "Marketing",
        "paymentPrice": 500,
        "externalId": "AD#11-2",
        "code": "Y000120",
        "type": "INCOME",
    },
    {
        "id": 105,
        "dateCreated": ms("2026-10-09"),
        "name": "Reklama",
        "source": "Marketing",
        "paymentPrice": 900,
        "externalId": "AD#11-3",
        "code": "Y000120",
        "type": "OUTCOME",
        "status": "CANCELED",
    },
]


@pytest.fixture
def legacy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    db = tmp_path / "uzum.db"
    monkeypatch.setenv("UZUM_DB", str(db))
    sys.path.insert(0, str(ROOT))
    from uzum_profit import sync
    from uzum_profit.db import connect

    conn = connect(str(db))
    history = {
        "shops": [{"id": 106121, "name": "byDurii"}],
        "per_shop": {"106121": {"orders": {"rows": ORDERS}, "expenses": {"rows": EXPENSES}}},
    }
    hist = tmp_path / "uzum_history.json"
    hist.write_text(json.dumps(history), encoding="utf-8")
    sync.import_history(conn, str(hist))
    for date, goods, rate, cargo, usd, cargo_date, lines, extras in [
        (
            "2026-08-20",
            500,
            1790,
            30,
            12650,
            "2026-09-01",
            [("A-1", 60, None), ("B-2", 40, "3.5")],
            [8000],
        ),
        ("2026-10-01", 300, 1800, None, None, None, [("A-1", 30, None)], []),
        ("2026-10-02", 0, 0, 0, 0, None, [("Z-0", 0, None)], []),
    ]:
        cur = conn.execute(
            "INSERT INTO batches (shop_id,date,goods_cny,cny_rate,cargo_usd,usd_rate,note,title,cargo_date) "
            "VALUES (106121,?,?,?,?,?,'','t',?)",
            (date, goods, rate, cargo, usd, cargo_date),
        )
        for sku, qty, unit in lines:
            conn.execute(
                "INSERT INTO batch_lines (batch_id,sku,qty,cny_unit) VALUES (?,?,?,?)",
                (cur.lastrowid, sku, qty, None if unit is None else float(unit)),
            )
        for amount in extras:
            conn.execute(
                "INSERT INTO batch_extras (batch_id,name,amount) VALUES (?,?,?)",
                (cur.lastrowid, "x", amount),
            )
    conn.commit()
    conn.close()
    return db, hist


def run(*argv: str) -> int:
    old = sys.argv
    sys.argv = [str(SCRIPT), *argv]
    try:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = old
    return 0


def test_compare_with_history(
    legacy_db: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, hist = legacy_db
    out = tmp_path / "farq.md"
    assert run("--db", str(db), "--history", str(hist), "--out", str(out)) == 0
    text = out.read_text(encoding="utf-8")
    assert "✓ Majburiy tekshiruvlar o'tdi." in text and "✗" not in text
    assert "xom qatorlar (uzum_history.json)" in text
    assert "`PARTIALLY_CANCELLED`: **1** qator" in text
    assert "photo_studio (legacy'da yo'q)" in text
    assert "Xarajat farqlari qatorlar bo'yicha" in text
    assert (
        "| hisobga kirmaydi (ad, INCOME) | ad | Y000120 | INCOME | — | 1 | 0 | -500 | -500 |"
        in text
    )
    assert "| ad | chiqarildi: status | Y000120 | OUTCOME | CANCELED | 1 | 900 | 0 | -900 |" in text
    assert "| 2026-09 |" in text and "| 2026-10 |" in text
    assert "Hisobot saqlandi" in capsys.readouterr().err


def test_compare_db_only_and_period(legacy_db: tuple[Path, Path], tmp_path: Path) -> None:
    db, _ = legacy_db
    out = tmp_path / "farq.md"
    assert (
        run("--db", str(db), "--from", "2026-10-01", "--to", "2026-10-31", "--out", str(out)) == 0
    )
    text = out.read_text(encoding="utf-8")
    assert "uzum.db dan tiklangan" in text and "2026-10-01 — 2026-10-31" in text


def test_missing_history_falls_back_to_db(
    legacy_db: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, _ = legacy_db
    out = tmp_path / "farq.md"
    assert run("--db", str(db), "--history", str(tmp_path / "yoq.json"), "--out", str(out)) == 0
    assert "uzum.db dan tiklangan" in out.read_text(encoding="utf-8")
    assert "topilmadi" in capsys.readouterr().err


def test_missing_db(tmp_path: Path) -> None:
    assert run("--db", str(tmp_path / "yoq.db"), "--out", os.devnull) == 2

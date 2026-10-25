"""B2.11: ``scripts/compare_staging.py`` — realcheck JSON (soxta Uzum bilan haqiqiy sinxron va ``upapi.realcheck``)
legacy ``uzum.db`` (o'sha qatorlar legacy importi orqali) bilan: format kontrakti, majburiy tekshiruvlar, qator
farqlari, taxminlar va ``amount``/``amountReturns`` hukmlari."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sellerfake as sf
from sellerfake import NOW, TOKEN, A, create_account, runtime, seller
from upapi import realcheck as rc
from upapi.sync import engine as eng

ROOT = Path(__file__).resolve().parents[3]
DAY = timedelta(days=1)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "compare_staging", ROOT / "scripts" / "compare_staging.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cs = _load()


def orders() -> list[dict[str, Any]]:
    price = 100_000
    return [
        sf.order(1, A, NOW - 100 * DAY),
        sf.order(2, A, NOW - 40 * DAY, amount=2, commission=30_000, logisticDeliveryFee=5_000),
        sf.order(3, A, NOW - 10 * DAY, status="PROCESSING"),
        # Qisman bekor: sellerProfit qolgan amount bilan F6 ga mos.
        sf.order(
            4, A, NOW - 5 * DAY, status="PARTIALLY_CANCELLED", amount=1, amountReturns=0,
            commission=20_000, logisticDeliveryFee=4_000, sellerProfit=price - 24_000,
        ),
        sf.order(5, A, NOW - DAY, amount=2, sellerProfit=2 * price - 40_000 - 4_000),
    ]  # fmt: skip


def legacy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> Path:
    db = tmp_path / "uzum.db"
    monkeypatch.setenv("UZUM_DB", str(db))
    sys.path.insert(0, str(ROOT))
    from uzum_profit import sync
    from uzum_profit.db import connect

    history = tmp_path / "uzum_history.json"
    history.write_text(
        json.dumps(
            {
                "shops": [{"id": A, "name": "byDurii"}],
                "per_shop": {str(A): {"orders": {"rows": rows}, "expenses": {"rows": []}}},
            }
        ),
        encoding="utf-8",
    )
    conn = connect(str(db))
    sync.import_history(conn, str(history))
    conn.close()
    return db


def staging_json(
    db: dict[str, str], tmp_path: Path, fake: sf.FakeSeller, shops: list[int] | None = None
) -> Path:
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, shops or [A])
        run(lambda rt: eng.sync_account(rt, account.org_id, account.account_id))
        report = run(lambda rt: rc.build(rt.engine, [account.org_id], now=NOW))
    path = tmp_path / "realcheck.json"
    path.write_text(json.dumps(report, default=rc._json), encoding="utf-8")
    return path


def compare(staging: Path, legacy: Path, tmp_path: Path, *extra: str) -> tuple[int, str]:
    out = tmp_path / "farq.md"
    code = cs.main(["--staging", str(staging), "--db", str(legacy), "--out", str(out), *extra])
    return code, out.read_text(encoding="utf-8") if out.exists() else ""


def test_all_match(db: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = orders()
    legacy = legacy_db(tmp_path, monkeypatch, rows)
    staging = staging_json(db, tmp_path, seller(orders={A: rows}))
    code, text = compare(staging, legacy, tmp_path)
    assert code == 0, text
    assert "✓ Hammasi mos." in text and "| ✗ |" not in text
    assert "Staging tarixi: full ✓" in text and "24 soatda xato ishlar: 0 ✓" in text
    assert "| 2026-07 |" in text and "| 2026-09 |" in text and "| 2026-10 |" in text
    assert "Davrdagi hamma qatorlar ikkala tomonda bir xil" in text
    assert "✓ `PARTIALLY_CANCELLED`" in text
    assert "≈ `amountReturns` > 0 qator yo'q" in text
    # Postavka tarkibi (SKU 5011) bog'langan, logistika externalId = qator id (sellerfake standarti).
    assert "| Postavka tarkibi: `skuForInvoiceDtoList[].id` = SKU id | 1/1" in text
    assert "| Logistika `externalId` = sotuv qatori id | 1/1 bog'landi" in text


def test_differences_fail(
    db: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = orders()
    legacy = legacy_db(tmp_path, monkeypatch, rows)
    with sqlite3.connect(legacy) as conn:
        conn.execute("UPDATE order_items SET commission = commission + 5 WHERE id = 2")
        conn.execute("UPDATE order_items SET status = 'PROCESSING' WHERE id = 5")
        conn.execute("DELETE FROM order_items WHERE id = 1")
    staging = staging_json(db, tmp_path, seller(orders={A: rows}))
    code, text = compare(staging, legacy, tmp_path)
    assert code == 1
    assert "✗ Mos kelmagan joy bor" in text
    assert "| summa/dona boshqa | 1 | 2 (Komissiya) |" in text
    assert "| holat boshqa (legacy → staging) | 1 | 5 PROCESSING → TO_WITHDRAW |" in text
    # Legacy davri 2-qatordan boshlanadi (1 o'chirildi) — 1 davrdan tashqarida, farq sifatida chiqmaydi.
    assert "faqat staging'da" not in text
    assert "| 2026-09 |" in text and "| 2026-07 |" not in text
    assert "| 0 / 0 / -5 / 0 | ✗ |" in text  # sentabr: komissiya


def test_amount_returns_net_and_wrong_assumptions(
    db: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``sellerProfit`` (amount − amountReturns) bilan mos va logistika ``externalId`` buyurtma id'si — ✗."""
    rows = [
        sf.order(1, A, NOW - DAY, amount=3, amountReturns=1, commission=40_000,
                 logisticDeliveryFee=8_000, sellerProfit=200_000 - 48_000),
    ]  # fmt: skip
    legacy = legacy_db(tmp_path, monkeypatch, rows)
    logistics = sf.expense(
        102, A, NOW - DAY, "logistics-volume", 4_000, name="Logistika", source="Logistika",
        externalId="10",
    )  # fmt: skip
    staging = staging_json(db, tmp_path, seller(orders={A: rows}, expenses={A: [logistics]}))
    code, text = compare(staging, legacy, tmp_path)
    assert code == 1
    assert "✗ `amountReturns`: `sellerProfit` (amount − amountReturns) bilan mos" in text
    assert "buyurtma id'siga mos 1" in text and "0/1 bog'landi" in text


def test_shop_missing_in_staging(
    db: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = orders()
    legacy = legacy_db(tmp_path, monkeypatch, rows)
    staging = tmp_path / "realcheck.json"
    staging.write_text(json.dumps({"format": 1, "generated_at": "x", "orgs": []}))
    code, text = compare(staging, legacy, tmp_path, "--from", "2026-10-01", "--to", "2026-10-31")
    assert code == 1
    assert "✗ Staging'da bu do'kon yo'q" in text and "davr 2026-10-01 — 2026-10-31" in text


def test_missing_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cs.main(["--staging", str(tmp_path / "yoq.json"), "--db", str(tmp_path)]) == 2
    assert "topilmadi" in capsys.readouterr().err


def test_empty_staging_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Serverdagi skript xato bersa ``> realcheck.json`` bo'sh qoladi — traceback emas, tushunarli xabar."""
    empty = tmp_path / "realcheck.json"
    empty.write_text("")
    assert cs.main(["--staging", str(empty), "--db", str(tmp_path)]) == 2
    assert "JSON emas yoki bo'sh" in capsys.readouterr().err

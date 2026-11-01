"""B2.11 real sinov hisoboti (``upapi.realcheck``): soxta Uzum bilan sinxrondan keyin oylar va holatlar bo'yicha
yig'indilar, qatorlar ro'yxati, taxminlar tekshiruvi (postavka SKU id, faktura sanasi, qaytarishlar sahifalari,
logistika ``externalId``, ``amount``/``amountReturns`` semantikasi) va kalit hisobotga chiqmasligi.
"""

from __future__ import annotations

import io
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import sellerfake as sf
from sellerfake import BOTH, NOW, TOKEN, A, B, admin, create_account, runtime, seller
from upapi import realcheck as rc
from upapi.sync import engine as eng

DAY = timedelta(days=1)


def synced(db: dict[str, str], fake: sf.FakeSeller) -> tuple[sf.Account, dict[str, Any]]:
    """Sinxron + hisobot (faqat shu testning tashkiloti — baza testlar orasida umumiy)."""
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A, B])
        run(lambda rt: eng.sync_account(rt, account.org_id, account.account_id))
        report = run(lambda rt: rc.build(rt.engine, [account.org_id], now=NOW))
    return account, report


def shop(report: dict[str, Any], ext: int) -> dict[str, Any]:
    (org,) = report["orgs"]
    return next(s for s in org["shops"] if s["external_id"] == ext)


def test_sales_by_month_and_status(db: dict[str, str]) -> None:
    fake = seller(shops=BOTH)
    _, report = synced(db, fake)
    a = shop(report, A)["sales"]
    # NOW − 100 kun = 2026-07-16, NOW − 10 va NOW − 1 kun — oktyabr (Toshkent sanasi).
    assert set(a["months"]) == {"2026-07", "2026-10"}
    july = a["months"]["2026-07"]["TO_WITHDRAW"]
    assert july == {
        "lines": 1,
        "units": 1,
        "revenue": "100000",
        "commission": "20000",
        "logistics": "4000",
        "seller_profit": "80000",
        "amount_returns": 0,
    }
    october = a["months"]["2026-10"]
    assert october["TO_WITHDRAW"]["units"] == 2 and october["TO_WITHDRAW"]["revenue"] == "200000"
    assert october["PROCESSING"]["lines"] == 1
    # Qator: [id, buyurtma, holat, sana, dona, narx, komissiya, logistika, sellerProfit, qaytgan]
    assert a["lines"][0] == [
        1,
        10,
        "TO_WITHDRAW",
        "2026-07-16",
        1,
        "100000",
        "20000",
        "4000",
        "80000",
        0,
    ]
    assert [line[0] for line in a["lines"]] == [1, 2, 3]
    assert shop(report, B)["sales"]["months"]["2026-10"]["TO_WITHDRAW"]["lines"] == 1


def test_month_uses_tashkent_date(db: dict[str, str]) -> None:
    # UTC 2026-09-30 20:00 = Toshkent 2026-10-01 01:00 → oktyabr.
    late = NOW.replace(month=9, day=30, hour=20)
    fake = seller(shops=BOTH, orders={A: [sf.order(1, A, late)], B: []})
    _, report = synced(db, fake)
    sales = shop(report, A)["sales"]
    assert list(sales["months"]) == ["2026-10"]
    assert sales["lines"][0][3] == "2026-10-01"


def test_amount_semantics(db: dict[str, str]) -> None:
    """``sellerProfit`` qaysi dona bilan F6 ga mos — ``amount`` sof (qolgan) donami, asl donami."""
    price, commission, logistics = 100_000, 40_000, 8_000
    net = sf.order(
        1,
        A,
        NOW - DAY,
        status="PARTIALLY_CANCELLED",
        amount=2,
        amountReturns=0,
        commission=commission,
        logisticDeliveryFee=logistics,
        sellerProfit=price * 2 - commission - logistics,
    )
    gross = sf.order(
        2,
        A,
        NOW - DAY,
        amount=3,
        amountReturns=1,
        commission=commission,
        logisticDeliveryFee=logistics,
        sellerProfit=price * 2 - commission - logistics,
    )
    fake = seller(shops=BOTH, orders={A: [net, gross], B: []})
    _, report = synced(db, fake)
    sem = shop(report, A)["sales"]["semantics"]
    assert sem["PARTIALLY_CANCELLED"] | {"examples": []} == {
        "lines": 1,
        "no_seller_profit": 0,
        "f6_amount": 1,
        "f6_without_logistics": 0,
        "with_returns": 0,
        "returns_f6_amount": 0,
        "returns_f6_net": 0,
        "examples": [],
    }
    withdraw = sem["TO_WITHDRAW"]
    assert (withdraw["f6_amount"], withdraw["with_returns"]) == (0, 1)
    assert (withdraw["returns_f6_amount"], withdraw["returns_f6_net"]) == (0, 1)
    assert withdraw["examples"] == [
        {
            "id": 2,
            "status": "TO_WITHDRAW",
            "amount": 3,
            "amount_returns": 1,
            "sell_price": "100000",
            "commission": "40000",
            "logistics": "8000",
            "seller_profit": "152000",
        }
    ]
    assert sem["PARTIALLY_CANCELLED"]["examples"][0]["id"] == 1


def test_assumption_checks(db: dict[str, str]) -> None:
    fake = seller(
        shops=BOTH,
        invoices={
            A: [
                sf.invoice(601),
                sf.invoice(602, created=sf.ms(NOW)),
                sf.invoice(603, created="kecha"),
            ],
            B: [],
        },
        # 602: tarkibdagi id — mahsulot id'si (501), SKU emas → bog'lanmaydi, "mahsulotga mos" sanaladi.
        invoice_products={601: [sf.invoice_product(5011)], 602: [sf.invoice_product(501)], 603: []},
        expenses={
            A: [
                sf.expense(
                    102,
                    A,
                    NOW - DAY,
                    "logistics-volume",
                    4_000,
                    name="Logistika",
                    source="Logistika",
                    externalId="3",
                ),
                # externalId — buyurtma id'si (order 1 → 10): bog'lanmaydi, "buyurtmaga mos".
                sf.expense(
                    104,
                    A,
                    NOW - DAY,
                    "logistics-volume",
                    4_000,
                    name="Logistika",
                    source="Logistika",
                    externalId="10",
                ),
                sf.expense(105, A, NOW - DAY, "Z999999", 700, name="Noma'lum", source="Boshqa"),
            ],
            B: [],
        },
    )
    _, report = synced(db, fake)
    checks = shop(report, A)["checks"]
    inv = checks["invoices"]
    assert (inv["invoices"], inv["date_parsed"]) == (3, 2)
    assert inv["date_patterns"] == {"99.99.9999 99:99": 1, "<number>": 1, "kecha": 1}
    assert (
        inv["items"],
        inv["items_linked"],
        inv["unlinked_ids"],
        inv["unlinked_match_product"],
    ) == (2, 1, 1, 1)

    ret = checks["returns"]
    assert ret["by_type"] == {"RETURN": 1} and (ret["returns"], ret["date_parsed"]) == (1, 1)
    assert (ret["items"], ret["items_linked"], ret["units"]) == (1, 1, 2)
    assert ret["date_patterns"] == {"<number>": 1}
    # Oxirgi ish: shu do'konning qatorlari (butun akkaunt ro'yxatidan) va so'rovlar (sahifalar) soni.
    assert ret["last_run"]["status"] == "ok" and ret["last_run"]["fetched"] == 1
    assert ret["last_run"]["requests"] >= 1

    lg = checks["logistics"]
    assert (lg["expenses"], lg["with_external_id"], lg["linked"]) == (2, 2, 1)
    assert (lg["unlinked_match_order"], lg["unlinked_no_sale"]) == (1, 1)
    assert Decimal(lg["amount"]) == 8000

    ex = checks["expenses"]
    assert ex["other_codes"] == [{"code": "Z999999", "source": "Boshqa", "n": 1, "amount": "700"}]
    assert ex["statuses"] == {"CONFIRMED": 3}
    assert {c["category"] for c in ex["by_category"]} == {"logistics", "other"}

    sync = shop(report, A)["sync"]
    assert sync["errors_24h"] == 0 and sync["problems"] == []
    assert sync["state"]["orders"]["last_status"] == "ok"
    assert sync["runs_24h"]["orders"] == {"ok": 1}


def test_sync_errors_reported(db: dict[str, str]) -> None:
    fake = seller(shops=BOTH, fail={"expenses": "server"})
    _, report = synced(db, fake)
    sync = shop(report, A)["sync"]
    assert sync["errors_24h"] >= 1
    assert sync["problems"][0]["kind"] == "expenses"
    assert sync["state"]["expenses"]["failures"] >= 1


def test_json_output_without_secrets(db: dict[str, str]) -> None:
    """Hisobot (stdout) — JSON; kalit (ochiq ham, shifrlangan ham) va oxirgi 4 belgisi yo'q. Tashkilotlar
    ``sync_accounts()`` dan, ``up_app`` roli bilan (RLS)."""
    fake = seller(shops=BOTH)
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A, B])
        run(lambda rt: eng.sync_account(rt, account.org_id, account.account_id))
        stream = io.StringIO()
        code = run(lambda rt: rc.run(rt.settings, stream))
    assert code == 0
    text = stream.getvalue()
    report = json.loads(text)
    assert report["format"] == rc.FORMAT
    assert str(account.org_id) in {o["id"] for o in report["orgs"]}
    blob = admin(db, "SELECT token_encrypted FROM mp_accounts WHERE id = %s", [account.account_id])[
        0
    ][0]
    assert TOKEN not in text and f"…{TOKEN[-4:]}" not in text and bytes(blob).hex() not in text


def test_no_accounts(db: dict[str, str]) -> None:
    fake = seller(shops=BOTH)
    with runtime(db, fake) as run:
        stream = io.StringIO()
        code = run(lambda rt: rc.run(rt.settings, stream, orgs=[]))
    assert code == 1
    assert json.loads(stream.getvalue())["orgs"] == []


def test_pattern_and_money() -> None:
    assert rc.pattern("24.10.2026 10:30") == "99.99.9999 99:99"
    assert rc.pattern(1_700_000_000_000) == "<number>"
    assert rc.pattern(None) == "<null>"
    assert rc.pattern({"a": 1}) == "<dict>"
    assert rc.pattern(True) == "<bool>"
    assert rc.money(Decimal("1000.00")) == "1000"
    assert rc.money(Decimal("12.50")) == "12.50"
    assert rc.money(Decimal("-0")) == "0"


def test_stock_fields_report(db: dict[str, str]) -> None:
    """ADR-034: qoldiq maydonlari yig'indilari, SKU holati bo'yicha, munosabatlar, postavka va qaytarish holatlari."""
    product = sf.product(
        501,
        [(5011, "SKU-A"), (5012, "SKU-B")],
        quantityAvailable=10,
        quantityReserved=1,
        quantityOnPhotoStudio=2,
        quantityNew=7,  # hujjatda yo'q maydon — "extra" ga tushadi
        quantityAvailableByStockType={"FBO": 10},
        status={"value": "BLOCKED"},
    )
    fake = seller(
        shops=BOTH,
        products={A: [product], B: []},
        invoices={A: [sf.invoice(601), sf.invoice(602, status="CREATED")], B: []},
    )
    _, report = synced(db, fake)
    stock = shop(report, A)["checks"]["stock"]
    assert stock["skus"] == 2
    f = stock["fields"]
    assert f["quantityActive"] == {"sum": 20, "nonzero": 2, "missing": 0}
    assert f["quantityOnPhotoStudio"]["sum"] == 4 and f["quantityArchived"]["missing"] == 2
    assert stock["by_status"]["IN_STOCK / BLOCKED"]["skus"] == 2
    assert stock["by_status"]["IN_STOCK / BLOCKED"]["quantityPending"] == 4
    assert stock["extra_quantity_keys"] == {"quantityNew": 2}
    assert stock["available_by_stock_type"] == {"FBO: <number>": 2}
    assert stock["mismatches"] == {}  # available = active (= active + fbs, FBS 0)
    statuses = {r["status"]: r for r in stock["invoices_by_status"]}
    assert set(statuses) == {"ACCEPTED", "CREATED"} and statuses["CREATED"]["to_stock"] == 5
    assert {(r["type"], r["status"]) for r in stock["returns_by_type_status"]} == {
        ("RETURN", "ASSEMBLED")
    }
    sales = {r["status"]: r for r in stock["sales_last_60d_by_status"]}
    assert set(sales) == {"PROCESSING", "TO_WITHDRAW"}  # 100 kun oldingi sotuv oynadan tashqarida
    assert json.dumps(report, default=rc._json)  # JSON'ga yoziladi

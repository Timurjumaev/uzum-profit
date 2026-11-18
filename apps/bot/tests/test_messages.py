"""Bot xabarlari matni (B6.2): har hodisa uz/ru, so'm formati, noma'lum hodisa."""

from decimal import Decimal

import pytest
from upbot import messages as msg

SUMMARY = {
    "start": "2026-11-15",
    "end": "2026-11-15",
    "orders": 12,
    "units": 14,
    "revenue": "1234567.50",
    "net_profit": "-7000.00",
    "canceled": 2,
    "uncosted_lines": 3,
    "fresh_at": "2026-11-16T04:30:00+00:00",
}


def test_money_and_language() -> None:
    assert msg.money("1234567.50", "uz") == "1 234 568 soʻm"
    assert msg.money(Decimal("-7000"), "ru") == "−7 000 сум"
    assert (
        msg.lang_of("ru") == "ru" and msg.lang_of("uz-Cyrl") == "uz" and msg.lang_of(None) == "uz"
    )


def test_summary_daily_and_partial() -> None:
    m = msg.notification("daily_summary", SUMMARY, "uz", "byDurii")
    assert m.path == "/"
    assert m.text.splitlines() == [
        "📊 Kecha, 15.11.2026",
        "Buyurtmalar: 12",
        "Tushum: 1 234 568 soʻm",
        "Sof foyda: −7 000 soʻm",
        "Bekorlar: 2 dona",
        "Tannarxsiz qatorlar: 3 — sof foydaga kirmagan",
        "",
        "— byDurii",
    ]
    partial = msg.summary(SUMMARY, "ru", "today", partial=True)
    assert partial.splitlines()[0] == "📊 Сегодня, 15.11.2026"
    assert partial.splitlines()[-1] == "Данные на 16.11 09:30"
    assert msg.summary({**SUMMARY, "fresh_at": None}, "uz", "week", partial=True).endswith(
        "raqamlar toʻliq emas"
    )
    week = msg.notification("weekly_summary", {**SUMMARY, "start": "2026-11-09"}, "uz")
    assert week.path == "/pnl?from=2026-11-09&to=2026-11-15"
    assert week.text.startswith("📊 Hafta: 09.11.2026 – 15.11.2026")


@pytest.mark.parametrize(
    ("event", "payload", "path", "part"),
    [
        (
            "stock_critical",
            {
                "count": 2,
                "skus": [{"title": "Mashina", "days": "3.5"}, {"title": None, "days": None}],
            },
            "/inventory",
            "• Mashina — 3.5 kunga\n• —",
        ),
        (
            "loss_sales",
            {"count": 1, "streak": 3, "skus": [{"title": "Kamar"}]},
            "/products",
            "oxirgi 3 ta",
        ),
        ("uncosted_sales", {"lines": 4, "day": "2026-11-15"}, "/orders", "4 ta qator (15.11.2026)"),
        (
            "new_fine",
            {
                "amount": "7000.00",
                "name": "Kamomad",
                "shop": "byDurii",
                "on": "2026-11-15",
                "code": "C000007",
            },
            "/expenses",
            "Kamomad, byDurii, 15.11.2026",
        ),
        (
            "receiving_shortage",
            {
                "invoice_number": 18324,
                "title": "Mashina",
                "shipped": 10,
                "accepted": 7,
                "missing": 3,
            },
            "/receiving",
            "Postavka № 18324: Mashina — joʻnatildi 10, qabul qilindi 7 (3 dona kam)",
        ),
        (
            "sync_stopped",
            {"shop": "byDurii", "reason": "key_invalid", "since": None},
            "/settings",
            "kaliti yaroqsiz",
        ),
        (
            "sync_stopped",
            {"shop": "byDurii", "reason": "stale", "since": "2026-11-15T09:00:00+00:00"},
            "/status",
            "15.11 14:00",
        ),
    ],
)
def test_events(event: str, payload: dict[str, object], path: str, part: str) -> None:
    m = msg.notification(event, payload, "uz")
    assert m.path == path and part in m.text
    assert msg.notification(event, payload, "ru").text != m.text


def test_unknown_event() -> None:
    with pytest.raises(ValueError):
        msg.notification("payout_late", {}, "uz")


def test_new_sku_notifications_uz_ru() -> None:
    """B6.4 (A2, A3): faqat YANGI SKU haqida xabar — "yangi N ta (jami M)", tannarxsiz yangi SKU."""
    skus = [{"sku_id": "s1", "title": "Mashina", "days": "3"}]
    stock = {"count": 1, "total": 4, "new": True, "skus": skus, "ids": ["s1"]}
    uz = msg.notification("stock_critical", stock, "uz")
    assert (
        "yangi 1 ta SKU (jami 4)" in uz.text and "• Mashina" in uz.text and uz.path == "/inventory"
    )
    assert "новых 1 SKU (всего 4)" in msg.notification("stock_critical", stock, "ru").text
    loss = {"count": 1, "total": 2, "streak": 3, "new": True, "skus": skus[:1]}
    assert "yangi 1 ta SKU (jami 2; oxirgi 3 ta" in msg.notification("loss_sales", loss, "uz").text
    unc = {"day": "2026-11-15", "count": 2, "lines": 5, "skus": skus}
    text = msg.notification("uncosted_sales", unc, "uz").text
    assert "Tannarxsiz yangi tovar sotildi (15.11.2026): 2 ta SKU, 5 ta qator" in text
    assert "• Mashina" in text
    # Eski ko'rinish (`/qoldiq` buyrug'i — hamma kritik) o'zgarmagan.
    assert (
        "Qoldiq kritik: 2 ta SKU"
        in msg.notification("stock_critical", {"count": 2, "skus": skus}, "uz").text
    )

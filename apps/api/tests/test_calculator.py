"""B5.9 ``/calculator`` (haqiqiy PostgreSQL): xariddan oldingi birlik tannarx (1688, kargo, kurs), F37 logistika, soliq taklifi
va F35/F36; kurs yo'q bo'lsa taxmin qilinmaydi. Ma'lumot — ``test_reports`` dunyosi."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import test_reports as tr
from upapi.reports.common import today

D = Decimal
db = tr.db
world = tr.world

PARAMS = {
    "price_cny": "10",
    "qty": 50,
    "china_cny_total": "50",
    "weight_kg": "0.3",
    "cargo_usd_per_kg": "4",
    "extra_uzs": "1000",
    "commission_pct": "15",
    "price": "90000",
    "tax_pct": "4",
}


def test_calculator_landed_cost_logistics_and_unit_economics(world: tr.World) -> None:
    w = world
    # Kurs yo'q — taxmin qilinmaydi: 422; maydonlar bo'sh, qo'lda kurs bilan hisoblanadi.
    w.a.sql("DELETE FROM fx_rates")
    r = w.call("calculator", **PARAMS)
    assert r.status_code == 422 and r.json()["code"] == "fx_rate_missing"
    empty = w.get("calculator/defaults")
    assert empty["rates"] == {"cny": None, "usd": None, "day": None, "source": None}
    manual = w.get("calculator", cny_rate="2000", usd_rate="13000", **PARAMS)
    assert D(manual["landed"]["goods"]) == D(20_000) and manual["rates"]["source"] == "manual"
    assert D(manual["landed"]["cargo"]) == D(15_600)  # 4 × 0,3 × 13 000

    day = today() - timedelta(days=1)
    w.a.sql(
        "INSERT INTO fx_rates (day, currency, source, rate) VALUES (%s, 'CNY', 'cbu', 1750), (%s, 'USD', 'cbu', 12600)",
        [day, day],
    )
    try:
        defaults = w.get("calculator/defaults")
        assert D(defaults["rates"]["cny"]) == D(1750) and D(defaults["rates"]["usd"]) == D(12_600)
        assert defaults["rates"]["source"] == "cbu" and defaults["rates"]["day"] == day.isoformat()
        assert D(defaults["tariff"]["base_fee"]) == D(5250) and D(
            defaults["tariff"]["no_dims_fee"]
        ) == D(50_000)

        out = w.get("calculator", length_cm="10", width_cm="10", height_cm="10", **PARAMS)
        landed = out["landed"]
        # 10 × 1 750 + 50 / 50 × 1 750 + 4 × 0,3 × 12 600 + 1 000
        assert (D(landed["goods"]), D(landed["china"]), D(landed["cargo"]), D(landed["extra"])) == (
            D(17_500),
            D(1_750),
            D(15_120),
            D(1_000),
        )
        assert D(landed["unit_cost"]) == D(35_370) and landed["cargo_basis"] == "weight"
        assert out["logistics"] == {"fee": "5250.00", "liters": 1, "source": "dims"}  # F37: 1 litr
        unit = out["unit"]
        assert D(unit["fixed"]) == D(40_620)  # tannarx + logistika
        assert D(unit["commission"]) == D(13_500) and D(unit["tax"]) == D(3_600)
        assert D(unit["profit"]) == D(32_280)  # 90 000 − 40 620 − 13 500 − 3 600
        assert unit["breakeven"] is not None and D(out["tax_pct"]) == D(4)

        # O'lcham yo'q — F37 "o'lchamsiz" narx; 20 litr = 5 250 + 19 × 250.
        assert w.get("calculator", **PARAMS)["logistics"] == {
            "fee": "50000.00",
            "liters": None,
            "source": "no_dims",
        }
        big = w.get("calculator", length_cm="20", width_cm="20", height_cm="50", **PARAMS)
        assert big["logistics"]["liters"] == 20 and D(big["logistics"]["fee"]) == D(5250 + 19 * 250)

        # Hajm bo'yicha kargo: $/m³ berilsa va kattaroq bo'lsa shu olinadi.
        vol = w.get(
            "calculator",
            length_cm="50",
            width_cm="40",
            height_cm="30",
            cargo_usd_per_m3="400",
            **PARAMS,
        )
        assert vol["landed"]["cargo_basis"] == "volume"  # 400 × 0,06 × 12 600 = 302 400 > 15 120

        # Soliq % berilmasa — profildan taklif (yoki 0), 422 emas; maqsadli marja narxi (F36).
        target = w.get(
            "calculator",
            target_margin_pct="20",
            **{k: v for k, v in PARAMS.items() if k != "tax_pct"},
        )
        assert target["unit"]["target_price"] is not None and D(target["tax_pct"]) >= 0

        # Tekshiruv: noto'g'ri qiymat — 422; ombor roli moliya ma'lumotini ko'rmaydi.
        assert w.call("calculator", **{**PARAMS, "qty": 0}).status_code == 422
        assert w.call("calculator", **{**PARAMS, "commission_pct": "101"}).status_code == 422
        assert w.call("calculator", "warehouse", **PARAMS).status_code == 403
        assert w.call("calculator/defaults", "warehouse").status_code == 403
    finally:
        w.a.sql("DELETE FROM fx_rates")

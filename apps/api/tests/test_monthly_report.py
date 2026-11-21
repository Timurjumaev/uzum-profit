"""B7.3 ``/reports/monthly`` (haqiqiy PostgreSQL): oylik hisobot raqamlari Foyda sahifasi bilan tiyinigacha teng, oldingi oy bilan farq
kalendar oy bo'yicha, "dastlabki" / "yakuniy" holati, ruxsat, kelajak oyi. Ma'lumot — ``test_reports`` dunyosi."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import test_reports as tr
from upapi.reports.common import today

D = Decimal
db = tr.db
world = tr.world


def test_monthly_report_equals_pnl_and_compares_calendar_months(world: tr.World) -> None:
    w = world
    rep = w.get("reports/monthly", month="2026-10-15")  # oyning istalgan kuni
    assert rep["month"] == "2026-10-01"
    assert rep["period"] == {"start": "2026-10-01", "end": "2026-10-31", "days": 31}
    assert rep["previous"] == {"start": "2026-09-01", "end": "2026-09-30", "days": 30}
    assert rep["month_over"] is True
    # Foyda sahifasi bilan tiyinigacha teng (xuddi shu davr)
    pnl = w.get("pnl", start="2026-10-01", end="2026-10-31")
    assert rep["statement"] == pnl["statement"]
    assert D(rep["statement"]["net_profit"]) == D(pnl["statement"]["net_profit"])
    # Oldingi oy — kalendar oy (Sentabr), oldingi 31 kun emas
    sept = w.get("pnl", start="2026-09-01", end="2026-09-30")["statement"]
    by_code = {r["code"]: r for r in rep["rows"]}
    assert D(by_code["revenue"]["previous"]) == D(sept["revenue"])
    assert D(by_code["net_profit"]["previous"]) == D(sept["net_profit"])
    assert D(by_code["net_profit"]["diff"]) == D(rep["statement"]["net_profit"]) - D(
        sept["net_profit"]
    )
    # F49 bo'laklari va SKU ro'yxatlari bor; sof foyda bo'yicha tartiblangan
    assert rep["flow"] and rep["flow"][0]["formula"] == "F44"
    profits = [D(x["net_profit"]) for x in rep["top"]]
    assert profits == sorted(profits, reverse=True)
    # Oyning yopilishi: Jarayondagi qator bor — dastlabki; yo'q — yakuniy
    expected = "preliminary" if rep["processing_lines"] > 0 else "final"
    assert rep["status"] == expected
    assert (rep["processing_lines"] > 0) == (D(rep["processing_revenue"]) > 0)


def test_monthly_report_current_month_is_preliminary_and_future_rejected(world: tr.World) -> None:
    w = world
    now = today()
    cur = w.get("reports/monthly")
    assert cur["month"] == now.replace(day=1).isoformat() and cur["month_over"] is False
    assert cur["status"] == "preliminary"  # oy tugamagan
    assert cur["period"]["end"] == now.isoformat()  # bugungacha
    nxt = date(now.year + (now.month == 12), now.month % 12 + 1, 1)
    r = w.call("reports/monthly", month=nxt.isoformat())
    assert r.status_code == 422 and r.json()["code"] == "bad_day"


def test_monthly_report_permissions(world: tr.World) -> None:
    w = world
    assert w.call("reports/monthly", "accountant", month="2026-10-01").status_code == 200
    assert w.call("reports/monthly", "manager", month="2026-10-01").status_code == 200
    assert w.call("reports/monthly", "warehouse", month="2026-10-01").status_code == 403

"""B2.9 o'qish API'lari (haqiqiy PostgreSQL): dashboard, pnl, skus, sales, expenses, inventory.

Ma'lumot superuser bilan yoziladi, hosila jadvallar haqiqiy hisob ishi bilan quriladi (lotlar → ``sale_costs`` →
``daily_sku_metrics``). Asosiy tekshiruvlar — M5 qabul mezonlari: P&L sof foydasi = bosh sahifa = SKU jadvali
yig'indisi; ustunlar (oylar, do'konlar, SKU) yig'indisi = jami; drill-down yig'indisi = qator summasi; kunlik agregat
ustidagi P&L = sotuv qatorlaridan qurilgan P&L (``upcore``). Ruxsatlar va tashkilotlarni ajratish ham shu yerda.
"""

from __future__ import annotations

import calendar
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import dbtools
import pytest
import sellerfake as sf
from mptools import MpApi, mp_api
from sellerfake import TOKEN, A, B, create_account
from test_calc import Org
from upapi import calc
from upapi.auth.deps import COOKIE
from upapi.reports.common import fold
from upcore.expenses import ExpenseCategory
from upcore.inventory import DayStat, StockStatus, velocity
from upcore.metrics import TASHKENT, ManualExpense, Period, SaleLine, business_date, run_rate
from upcore.money import Money
from upcore.pnl import ExpenseItem, OwnExpense, TaxRule, build_cells

D = Decimal
OCT = {"start": "2026-10-01", "end": "2026-10-20"}
AS_OF = date(2026, 10, 20)


def d(month: int, day: int) -> date:
    return date(2026, month, day)


def at(day: date, hour: int = 7) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


@dataclass
class World:
    api: MpApi
    a: Org
    b: Org
    other: uuid.UUID  # boshqa tashkilot
    sessions: dict[str, str] = field(default_factory=dict)
    ids: dict[str, uuid.UUID] = field(default_factory=dict)

    @property
    def org_id(self) -> uuid.UUID:
        return self.a.org_id

    def call(
        self, path: str, role: str = "owner", org: uuid.UUID | None = None, **params: Any
    ) -> Any:
        self.api.client.cookies.set(COOKIE, self.sessions[role])
        return self.api.client.get(f"/api/v1/orgs/{org or self.org_id}/{path}", params=params)

    def get(self, path: str, role: str = "owner", **params: Any) -> Any:
        r = self.call(path, role, **params)
        assert r.status_code == 200, r.text
        return r.json()

    def expense(
        self, shop: Org, day: date, category: str, amount: int, type_: str = "OUTCOME", **extra: Any
    ) -> uuid.UUID:
        shop._ext += 1
        return shop.insert(
            "mp_expenses",
            shop_id=shop.shop_id,
            external_id=shop._ext,
            category=category,
            type=type_,
            amount=D(amount),
            created_on=at(day),
            **extra,
        )


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    with dbtools.migrated_database() as urls:
        yield urls


def _populate(w: World) -> None:
    a, b = w.a, w.b
    # Do'kon A: tovar X (lot 100 dona × 100 000, bosqich sanalari bilan), SKU y (tovarsiz), bog'lanmagan sotuv.
    x = a.insert("items", name="Mashina")
    w.ids["xa"] = a.insert(
        "mp_skus",
        shop_id=a.shop_id,
        external_id=11,
        sku_code="Oʻyinchoq mashina qizil",
        article="ART-1",
        barcode="4780001",
        item_id=x,
        qty_active=80,
        qty_fbs=5,
        qty_defected=2,
        rank="A",
    )
    w.ids["ya"] = a.insert(
        "mp_skus", shop_id=a.shop_id, external_id=12, sku_code="Кружка белая", qty_active=0
    )
    p1 = a.purchase(
        d(9, 1),
        ordered_on=d(8, 1),
        paid_on=d(8, 2),
        cn_warehouse_on=d(8, 10),
        shipped_on=d(8, 12),
        arrived_on=d(8, 25),
        sent_to_uzum_on=d(9, 3),
    )
    a.line(p1, x, 100)
    a.component(p1, "goods", 10_000_000)
    p3 = a.purchase(None, ordered_on=d(10, 15))  # yo'lda: 20 dona × 120 000
    a.line(p3, x, 20, received=None)
    a.component(p3, "goods", 2_400_000)
    w.ids["p1"] = p1

    xa, ya = w.ids["xa"], w.ids["ya"]
    a.sale(xa, d(9, 20), 2)  # oldingi davr (11–30 sentabr)
    w.ids["s_oct2"] = a.sale(xa, d(10, 2), 2)
    a.sale(xa, d(10, 5), 1, amount_returns=1)
    w.ids["s_oct10"] = a.sale(xa, d(10, 10), 3)
    a.sale(xa, d(10, 12), 1, "CANCELED")
    a.sale(xa, d(10, 15), 1, "PROCESSING")
    a.sale(ya, d(10, 3), 1, price=150_000)
    a.sale(None, d(10, 4), 1, price=50_000, sku_title="Noma'lum")
    for i in range(1, 21):
        a.insert("sku_daily", sku_id=xa, day=d(10, i), qty_active=0 if i == 8 else 10, qty_fbs=0)

    # Do'kon B: tovar Z (lot 50 × 50 000, sanasiz — muddat noma'lum).
    z = b.insert("items", name="Chiroq")
    w.ids["zb"] = b.insert(
        "mp_skus",
        shop_id=b.shop_id,
        external_id=21,
        sku_code="Chiroq LED",
        item_id=z,
        qty_active=40,
    )
    p2 = b.purchase(d(9, 15))
    b.line(p2, z, 50)
    b.component(p2, "goods", 2_500_000)
    b.sale(w.ids["zb"], d(10, 2), 4, price=100_000)
    today = datetime.now(TASHKENT).date()
    b.sale(w.ids["zb"], today, 1, price=100_000)  # bosh sahifa "Bugun"

    # Logistikasi 0 sotuvlar (avgust — boshqa testlar davridan tashqari): API bergandek olinadi (ADR-035).
    # B: 10-avgust ikkala qator logistikasi 0, 11-avgustda pullik (7 000).
    # A: 10-avgust y SKU va bog'lanmagan qator 0; 12-avgust bittasi 0, bittasi pullik (5 000).
    lamp = b.insert("items", name="Lampa")
    w.ids["lb"] = b.insert(
        "mp_skus", shop_id=b.shop_id, external_id=22, sku_code="Lampa", item_id=lamp
    )
    p4 = b.purchase(d(8, 1))
    b.line(p4, lamp, 10)
    b.component(p4, "goods", 300_000)
    b.sale(w.ids["lb"], d(8, 10), 2, price=100_000, logistics=0)
    b.sale(w.ids["lb"], d(8, 10), 1, price=100_000, logistics=0)
    b.sale(w.ids["lb"], d(8, 11), 1, price=100_000, logistics=7_000)
    a.sale(ya, d(8, 10), 1, price=150_000, logistics=0)
    a.sale(None, d(8, 10), 1, price=50_000, logistics=0)
    a.sale(ya, d(8, 12), 1, price=150_000, logistics=0)
    a.sale(ya, d(8, 12), 1, price=150_000)

    # Uzum xarajatlari (A): do'kon darajasi, sotuvga bog'langan reklama, kompensatsiya, jarimalar, chiqarilganlar.
    w.expense(a, d(10, 1), "storage", 12_000)  # 1-oktabr — sotuvsiz kun: taqsimlanmagan
    w.expense(a, d(10, 2), "storage", 30_000)
    w.expense(a, d(10, 10), "advertising", 20_000, sale_item_id=w.ids["s_oct10"])
    w.expense(a, d(10, 5), "compensation", 10_000, "INCOME")
    w.ids["fine50"] = w.expense(a, d(10, 6), "fine", 50_000)
    w.ids["fine70"] = w.expense(a, d(10, 7), "fine", 70_000)
    w.ids["excluded"] = w.expense(
        a, d(10, 8), "storage", 99_000, status="CANCELED", excluded="status"
    )
    w.expense(a, d(10, 9), "logistics", 5_000, excluded="not_expense")
    w.expense(b, d(10, 2), "storage", 8_000)

    # O'z xarajatlari: tashkilot ijarasi (oktabr, kuniga 10 000) va B do'koni interneti (bir kun).
    rent = a.insert("expense_categories", name="ijara")
    net = a.insert("expense_categories", name="internet")
    a.insert(
        "manual_expenses", category_id=rent, amount=D(310_000), start_on=d(10, 1), end_on=d(10, 31)
    )
    a.insert(
        "manual_expenses",
        category_id=net,
        shop_id=b.shop_id,
        amount=D(200_000),
        start_on=d(10, 2),
        end_on=d(10, 2),
    )
    pack = a.insert(
        "expense_categories", name="qadoq"
    )  # tovarga bog'langan: bitta SKU — o'sha SKU'ga
    a.insert(
        "manual_expenses",
        category_id=pack,
        item_id=x,
        amount=D(50_000),
        start_on=d(10, 10),
        end_on=d(10, 10),
    )
    a.insert("tax_profiles", valid_from=d(1, 1), regime="turnover", rate_pct=D(4))

    a.run(lambda conn: calc.request_full(conn, a.org_id))
    assert a.recalc(datetime.now(UTC)).errors == {}


@pytest.fixture(scope="module")
def world(db: dict[str, str]) -> Iterator[World]:
    settings = sf.settings_for(db)
    account = create_account(db, settings, TOKEN, [A, B])
    other = create_account(db, settings, TOKEN, [A])
    a = Org(db, account.org_id, account.shops[A])
    b = Org(db, account.org_id, account.shops[B], _ext=1_000)
    o = Org(db, other.org_id, other.shops[A])
    # Boshqa tashkilot sotuvi — bizning raqamlarda ko'rinmasligi kerak.
    o.sale(None, d(10, 2), 5, price=1_000_000)
    o.run(lambda conn: calc.request_full(conn, o.org_id))
    o.recalc(datetime.now(UTC))
    with mp_api(db) as api:
        w = World(api, a, b, other.org_id)
        _populate(w)
        for role in ("owner", "manager", "accountant", "warehouse"):
            phone = api.login()
            user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
            api.admin(
                "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, %s)",
                [a.org_id, user, role],
            )
            w.sessions[role] = api.client.cookies[COOKIE]
        yield w


def money(x: Any) -> Decimal:
    return D(x) if x is not None else D(0)


# --- P&L ------------------------------------------------------------------------------------------


def _reference(w: World, period: Period) -> Any:
    """Mustaqil yo'l: sotuv qatorlari (``sale_items`` + ``sale_costs``) va xarajatlardan ``upcore`` P&L'i."""
    rows = w.a.sql(
        "SELECT s.shop_id, s.sku_id, s.ordered_at, s.status, s.sell_price, s.amount, s.commission, "
        "s.logistics_fee, c.cogs FROM sale_items s LEFT JOIN sale_costs c ON c.sale_item_id = s.id "
        "WHERE s.org_id = %s",
        [w.org_id],
    )
    lines = [
        SaleLine(
            sku="unlinked" if sku is None else str(sku),
            order_date=business_date(ordered),
            status=status,
            sell_price=price,
            amount=amount,
            commission=commission,
            logistics=logistics,
            unit_cost=None if cogs is None else cogs / amount,
            shop=str(shop),
        )
        for shop, sku, ordered, status, price, amount, commission, logistics, cogs in rows
    ]
    exp_rows = w.a.sql(
        "SELECT e.shop_id, e.created_on, e.category, e.type, e.amount, e.sale_item_id, s.sku_id "
        "FROM mp_expenses e LEFT JOIN sale_items s ON s.id = e.sale_item_id "
        "WHERE e.org_id = %s AND e.excluded IS NULL",
        [w.org_id],
    )
    expenses = [
        ExpenseItem(
            business_date(created),
            str(shop),
            ExpenseCategory(cat),
            Money.of(amount if kind == "OUTCOME" else -amount, "UZS"),
            None if sale is None else str(sku),
        )
        for shop, created, cat, kind, amount, sale, sku in exp_rows
        if ExpenseCategory(cat).in_pnl
    ]
    own = [
        OwnExpense(
            ManualExpense(Money.of(310_000, "UZS"), d(10, 1), d(10, 31)), "ijara", None, None
        ),
        OwnExpense(
            ManualExpense(Money.of(200_000, "UZS"), d(10, 2), d(10, 2)),
            "internet",
            str(w.b.shop_id),
        ),
        OwnExpense(
            ManualExpense(Money.of(50_000, "UZS"), d(10, 10), d(10, 10)),
            "qadoq",
            str(w.a.shop_id),
            str(w.ids["xa"]),
        ),
    ]
    return build_cells(period, lines, expenses, own, TaxRule(D(4)))


def test_pnl_matches_line_level_core(world: World) -> None:
    body = world.get("pnl", **OCT)
    ref = _reference(world, Period(d(10, 1), d(10, 20))).statement()
    s = body["statement"]
    # ADR-036: 15-oktabr Jarayondagi sotuv (1 × 200 000) ham kiradi.
    assert money(s["revenue"]) == ref.revenue.amount == D(2_000_000)
    for key in ("commission", "logistics", "cogs", "tax", "net_profit", "expenses_deducted"):
        assert money(s[key]) == getattr(ref, key).amount, key
    assert s["units"] == ref.units == 13 and s["lines"] == ref.lines == 7
    assert s["covered_units"] == ref.covered_units == 11
    assert s["units_processing"] == 1 and money(s["revenue_processing"]) == D(200_000)
    assert s["uncovered"]["lines"] == 2 and money(s["uncovered"]["revenue"]) == D(200_000)
    assert D(s["coverage"]) == ref.coverage
    assert {k: money(v) for k, v in s["uzum_expenses"].items()} == {
        "advertising": D(20_000),
        "compensation": D(-10_000),
        "fine": D(120_000),
        "storage": D(50_000),
    }
    assert money(s["own_expenses"]["ijara"]) == D(200_000)  # 20 kun × 10 000
    assert money(s["own_expenses"]["internet"]) == D(200_000)
    assert money(s["own_expenses"]["qadoq"]) == D(50_000)
    assert money(s["direct_total"]) + money(s["allocated_total"]) + money(s["tax"]) == (
        sum(map(money, s["uzum_expenses"].values()))
        + sum(map(money, s["own_expenses"].values()))
        + money(s["tax"])
    )
    meta = body["meta"]
    assert meta["period"] == {"start": "2026-10-01", "end": "2026-10-20", "days": 20}
    assert meta["previous"] == {"start": "2026-09-11", "end": "2026-09-30", "days": 20}
    assert set(meta["freshness"]) == {"orders", "expenses"}


def test_pnl_untaxed_regimes(world: World) -> None:
    """K7: QQS + foyda yoki agent rejimida soliq hisoblanmaydi — davr javobida aytiladi (aylanma rejimida bo'sh)."""
    assert world.get("pnl", **OCT)["untaxed_regimes"] == []
    # 2026-01-01 dan aylanma profili bor; undan oldingi davrlar ta'sir qilmaydigan eski profil qo'shiladi.
    world.a.insert(
        "tax_profiles",
        valid_from=date(2025, 6, 1),
        regime="vat_profit",
        vat_pct=D(12),
        profit_pct=D(15),
    )
    old = {"start": "2025-12-01", "end": "2025-12-31"}
    assert world.get("pnl", **old)["untaxed_regimes"] == ["vat_profit"]
    crossing = {"start": "2025-12-15", "end": "2026-01-15"}
    assert world.get("pnl", **crossing)["untaxed_regimes"] == ["vat_profit"]
    assert world.get("pnl", **OCT)["untaxed_regimes"] == []


def test_pnl_tax_lines_and_fixed_tax(world: World) -> None:
    """ADR-058: soliq qatorlari bazadan — foizli va qat'iy (n × BHM) qator hisob varag'ida "Soliq" ostida alohida."""
    a = world.a
    a.sql(
        "INSERT INTO ref_amounts (code, valid_from, amount) VALUES ('bhm', %s, %s)",
        [date(2025, 1, 1), 400_000],
    )
    profile = a.insert("tax_profiles", valid_from=date(2025, 2, 1), regime="turnover")
    a.insert(
        "tax_lines", profile_id=profile, name="Aylanmadan soliq", kind="percent", rate_pct=D(1)
    )
    a.insert(
        "tax_lines",
        profile_id=profile,
        name="Ijtimoiy soliq",
        kind="fixed",
        bhm_count=D(1),
        position=1,
    )
    body = world.get("pnl", start="2025-02-01", end="2025-02-28")
    rows = {r["code"]: r for r in body["rows"]}
    assert money(rows["tax:Ijtimoiy soliq"]["amount"]) == D(-400_000)  # fevral: 1 × BHM, aniq
    assert money(rows["tax:Aylanmadan soliq"]["amount"]) == D(0)  # sotuv yo'q
    assert money(rows["tax"]["amount"]) == D(-400_000)
    assert money(body["statement"]["tax"]) == D(400_000)
    assert "own:tax:Ijtimoiy soliq" not in rows  # o'z xarajati sifatida ko'rinmaydi
    assert body["tax_missing_bhm"] is False
    # Bir oy ichidagi qisman davr: 10 kun × 400 000 / 28.
    part = world.get("pnl", start="2025-02-01", end="2025-02-10")
    assert money(part["statement"]["tax"]) == D("142857.14")


def test_pnl_fixed_tax_uses_seed_bhm_when_reference_table_lacks_it(world: World) -> None:
    """Deploy ``ref_amounts`` ni to'ldirmaydi: bazada qiymat bo'lmasa ham BHM upcore boshlang'ich qiymatidan (bazadagi
    yozuv ustun) olinadi — 2035-yilda eng yangi BHM (440 000) qo'llanadi, "BHM yo'q" bayrog'i ko'tarilmaydi."""
    a = world.a
    profile = a.insert("tax_profiles", valid_from=date(2035, 1, 1), regime="turnover")
    a.insert("tax_lines", profile_id=profile, name="Ijtimoiy soliq", kind="fixed", bhm_count=D(1))
    body = world.get("pnl", start="2035-01-01", end="2035-01-31")
    assert money(body["statement"]["tax"]) == D(440_000)
    assert body["tax_missing_bhm"] is False


def test_pnl_tax_missing_bhm_flag(world: World) -> None:
    """BHM ma'lumotnomada yo'q kunlarda BHM'ga bog'liq qat'iy soliq hisoblanmaydi va bu aytiladi (0 deb yashirilmaydi)."""
    a = world.a
    profile = a.insert("tax_profiles", valid_from=date(2024, 1, 1), regime="turnover")
    a.insert("tax_lines", profile_id=profile, name="Ijtimoiy soliq", kind="fixed", bhm_count=D(1))
    body = world.get(
        "pnl", start="2024-12-01", end="2024-12-05"
    )  # BHM ma'lumotnomada 2025-01-01 dan
    assert body["tax_missing_bhm"] is True
    assert money(body["statement"]["tax"]) == D(0)
    assert world.get("pnl", **OCT)["tax_missing_bhm"] is False


def test_pnl_rows_and_previous(world: World) -> None:
    body = world.get("pnl", **OCT)
    rows = {r["code"]: r for r in body["rows"]}
    assert money(rows["revenue"]["amount"]) == D(2_000_000)
    assert money(rows["revenue"]["previous"]) == D(400_000)  # 20-sentabr, 2 dona
    assert money(rows["revenue"]["diff"]) == D(1_600_000)
    assert D(rows["revenue"]["share_of_revenue"]) == D(1)
    assert D(rows["revenue"]["change"]) == D("4")  # 1 600 000 / 400 000
    assert money(rows["net_profit"]["amount"]) == money(body["statement"]["net_profit"])
    assert money(body["previous"]["revenue"]) == D(400_000)
    assert "uzum:fine" in rows and "own:ijara" in rows and "uncovered_payout" in rows


@pytest.mark.parametrize("view", ["month", "day", "shop", "sku"])
def test_pnl_columns_sum_to_total(world: World, view: str) -> None:
    body = world.get("pnl", view=view, **OCT)
    total = body["statement"]
    cols = body["columns"]
    assert cols
    for key in ("revenue", "net_profit", "cogs", "tax", "allocated_total"):
        assert sum(money(c["statement"][key]) for c in cols) == money(total[key]), key
    if view == "sku":
        keys = {c["key"] for c in cols}
        assert {str(world.ids["xa"]), str(world.ids["ya"]), "unlinked", None} <= keys
    if view == "shop":
        # null — tashkilot xarajatining hech qaysi do'konda sotuv bo'lmagan kunlari (1-oktabr ijarasi).
        assert {c["key"] for c in cols} == {str(world.a.shop_id), str(world.b.shop_id), None}
    if view == "month":
        assert [c["key"] for c in cols] == ["2026-10-01"]


def test_pnl_shop_filter_equals_shop_column(world: World) -> None:
    by_shop = {c["key"]: c["statement"] for c in world.get("pnl", view="shop", **OCT)["columns"]}
    for shop in (world.a.shop_id, world.b.shop_id):
        alone = world.get("pnl", shop=str(shop), **OCT)["statement"]
        assert alone == by_shop[str(shop)]
    both = world.get("pnl", shop=[str(world.a.shop_id), str(world.b.shop_id)], **OCT)
    assert money(both["statement"]["revenue"]) == D(2_000_000)
    assert both["meta"]["shops"] == sorted([str(world.a.shop_id), str(world.b.shop_id)])


AUG = {"start": "2026-08-10", "end": "2026-08-12"}


def test_zero_logistics_is_taken_as_is(world: World) -> None:
    """ADR-035: logistikasi 0 sotuvlar API bergandek olinadi — hech narsa qo'shilmaydi, hech narsa so'ralmaydi."""
    body = world.get("pnl", **AUG)
    ref = _reference(world, Period(d(8, 10), d(8, 12))).statement()
    assert money(body["statement"]["net_profit"]) == ref.net_profit.amount
    assert money(body["statement"]["logistics"]) == D(7_000) + D(5_000)  # faqat Uzum olgani
    assert "waivers" not in body and "waiver_suggestions" not in body
    assert "waivers" not in world.get("dashboard", **AUG)


def test_pnl_sku_columns_have_titles(world: World) -> None:
    cols = {c["key"]: c for c in world.get("pnl", view="sku", **AUG)["columns"]}
    assert cols[str(world.ids["lb"])]["title"] == "Lampa"
    assert cols[str(world.ids["lb"])]["shop_id"] == str(world.b.shop_id)
    assert cols["unlinked"]["title"] is None
    body = world.get("pnl", **OCT)
    s = body["statement"]
    assert money(s["uzum_total"]) == sum(map(money, s["uzum_expenses"].values()))
    assert money(s["own_total"]) == sum(map(money, s["own_expenses"].values()))
    # ADR-026: do'kon kesimida to'g'ridan-to'g'ri + taqsimlangan = jami; SKU kesimida — xuddi shunday.
    for view in ("shop", "sku"):
        for col in world.get("pnl", view=view, **OCT)["columns"]:
            c = col["statement"]
            assert money(c["uzum_direct"]) + money(c["uzum_allocated_total"]) == money(
                c["uzum_total"]
            )
            assert money(c["own_direct"]) + money(c["own_allocated_total"]) == money(c["own_total"])
    assert money(s["uzum_allocated_total"]) + money(s["own_allocated_total"]) == money(
        s["allocated_total"]
    )


def test_cell_sales_columns_match_fields() -> None:
    """``daily_sku_metrics`` ustunlari ``CellSales`` ga pozitsiya bo'yicha o'qiladi — tartib bir xil bo'lishi shart."""
    from dataclasses import fields

    from upapi.reports.cells import _SALES
    from upcore.pnl import CellSales

    assert [name for name, _ in _SALES] == [f.name for f in fields(CellSales)]


def test_pnl_expected_profit(world: World) -> None:
    """ADR-037: kutilayotgan sof foyda (F16) — 15-oktabr Jarayondagi sotuv: 200 000 − 40 000 − 5 000 − tannarx 100 000 −
    o'sha kungi ijara (10 000, kunning yagona sotuvi — hammasi shu katakka) − soliq 4% (8 000) = 37 000; yakunlangan = jami −
    kutilayotgan; har qator ikki qismda. R — 50 donadan kam (noma'lum)."""
    body = world.get("pnl", **OCT)
    e = body["expected"]
    assert (e["units"], e["lines"], money(e["revenue"])) == (1, 1, D(200_000))
    assert (money(e["commission"]), money(e["logistics"]), money(e["cogs"])) == (
        D(40_000),
        D(5_000),
        D(100_000),
    )
    assert money(e["expenses"]) == D(18_000) and money(e["net_profit"]) == D(37_000)
    assert e["rate"] is None and e["uncovered_lines"] == 0
    assert money(e["logistics_estimated"]) == 0 and e["logistics_missing_lines"] == 0
    assert [x["shop_id"] for x in body["expected_shops"]] == [str(world.a.shop_id)]
    assert money(body["expected_shops"][0]["net_profit"]) == D(37_000)
    s = body["statement"]
    assert money(s["net_profit_processing"]) == D(37_000)
    assert money(s["net_profit_done"]) + D(37_000) == money(s["net_profit"])
    assert (s["units_done"], s["lines_processing"]) == (s["units"] - 1, 1)
    rows = {r["code"]: r for r in body["rows"]}
    for r in rows.values():
        assert money(r["done"]) + money(r["processing"]) == money(r["amount"])
    assert money(rows["net_profit"]["processing"]) == D(37_000)
    assert money(rows["own:ijara"]["processing"]) == D(-10_000)
    assert money(rows["tax"]["processing"]) == D(-8_000)
    assert money(rows["uzum:storage"]["processing"]) == 0  # 15-oktabrda saqlash yo'q


def test_change_scales_processing_by_completion(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-057 Q4: R noma'lum — "▲ %" eskicha (taxminiy emas); R ma'lum — Jarayondagi qism × R bilan, summalar o'zgarmaydi."""
    plain = {r["code"]: r for r in world.get("pnl", **OCT)["rows"]}
    assert not any(r["change_estimated"] for r in plain.values())

    from upapi.reports import cells as rc

    async def half(conn: Any, f: Any) -> rc.Realization:
        return rc.Realization(total=Decimal("0.5"), shops={})

    monkeypatch.setattr(rc, "realization", half)
    rows = {r["code"]: r for r in world.get("pnl", **OCT)["rows"]}
    revenue = rows["revenue"]
    assert revenue["change_estimated"] is True
    assert (revenue["amount"], revenue["previous"]) == (
        plain["revenue"]["amount"],
        plain["revenue"]["previous"],
    )
    now = money(revenue["done"]) + money(revenue["processing"]) * Decimal("0.5")
    before = money(revenue["previous"])  # oldingi davrda Jarayondagi sotuv yo'q
    assert D(revenue["change"]) == ((now - before) / abs(before)).quantize(D(revenue["change"]))
    home = world.get("dashboard", **OCT)
    assert {r["code"]: r["change_estimated"] for r in home["rows"]}["revenue"] is True


def test_expected_logistics_estimate(world: World) -> None:
    """F5 (ADR-037, ADR-042): Uzum logistikasini hali yozmagan (topshirilmagan, 0) Jarayondagi sotuv — F40 tarifi × dona
    (SKU'ning oxirgi pullik Yakunlangan sotuvi: 5 000/dona) taxminiy qo'shiladi; drill-down qatorida ham shu summa,
    yig'indi qator bilan bir xil; topshirilgan bo'lsa (0 — Uzum bergani) taxmin yo'q."""
    a = world.a
    before = world.get("pnl", **OCT)

    def resync(logistics: int, issued: datetime | None) -> dict[str, Any]:
        a.sql(
            "UPDATE sale_items SET logistics_fee = %s, issued_at = %s WHERE org_id = %s AND sku_id = %s "
            "AND (ordered_at AT TIME ZONE 'Asia/Tashkent')::date = %s",
            [logistics, issued, a.org_id, world.ids["xa"], d(10, 15)],
        )
        a.run(lambda conn: calc.request(conn, world.org_id, calc.Scope.SHOP, a.shop_id, d(10, 15)))
        assert a.recalc(datetime.now(UTC)).errors == {}
        return world.get("pnl", **OCT)

    try:
        due = resync(0, None)
        s = due["statement"]
        assert money(s["logistics_estimated"]) == D(5_000)
        assert (s["logistics_estimated_units"], s["logistics_estimated_lines"]) == (1, 1)
        assert money(s["logistics"]) == money(
            before["statement"]["logistics"]
        )  # 5 000 → taxmin 5 000
        assert money(due["expected"]["logistics_estimated"]) == D(5_000)
        assert money(due["expected"]["net_profit"]) == D(37_000)
        sales = world.get("sales", counted="true", **OCT)["items"]
        row = next(x for x in sales if x["group"] == "processing")
        assert money(row["logistics"]) == D(5_000) and money(row["logistics_estimated"]) == D(5_000)
        assert money(row["payout"]) == D(200_000 - 40_000 - 5_000)
        assert sum(money(x["logistics"]) for x in sales) == money(s["logistics"])
        assert all(x["logistics_estimated"] is None for x in sales if x["group"] != "processing")
        free = resync(0, at(d(10, 18)))  # topshirilgan, Uzum 0 yozgan — taxmin yo'q (ADR-035)
        assert money(free["statement"]["logistics_estimated"]) == 0
        assert money(free["expected"]["net_profit"]) == D(42_000)
    finally:
        after = resync(5_000, None)
    assert after["statement"] == before["statement"]


def test_logistics_is_what_uzum_charged(world: World) -> None:
    """F5 (ADR-042): sotuv logistikasi — Uzum aslida yechgani (sotuvga bog'langan logistika chiqimlari): qatorda 10 000,
    Uzum 0 yechgan (bonus olib ketilgan kunga qarab) — 0; qatorda 0, olib ketilgach Uzum 5 250 yechgan — 5 250."""
    a = world.a
    before = world.get("pnl", **OCT)["statement"]

    def rebuild() -> dict[str, Any]:
        a.run(lambda conn: calc.request(conn, world.org_id, calc.Scope.SHOP, a.shop_id, d(10, 1)))
        assert a.recalc(datetime.now(UTC)).errors == {}
        return world.get("pnl", **OCT)

    free = world.expense(
        a, d(10, 9), "logistics", 0, excluded="not_expense", sale_item_id=world.ids["s_oct2"]
    )
    a.sql(
        "UPDATE sale_items SET logistics_fee = 0, issued_at = %s WHERE org_id = %s AND sku_id = %s "
        "AND (ordered_at AT TIME ZONE 'Asia/Tashkent')::date = %s",
        [at(d(11, 2)), a.org_id, world.ids["xa"], d(10, 15)],
    )
    ((pending,),) = a.sql(
        "SELECT id FROM sale_items WHERE org_id = %s AND upper(status) = 'PROCESSING'",
        [world.org_id],
    )
    paid = world.expense(
        a, d(11, 2), "logistics", 5_250, excluded="not_expense", sale_item_id=pending
    )
    try:
        body = rebuild()
        s = body["statement"]
        # 2-okt: 10 000 → 0; 15-okt: 5 000 (qatorda) → 0 qatorda, Uzum 5 250 yechgan.
        assert money(s["logistics"]) == money(before["logistics"]) - D(10_000) + D(250)
        assert money(s["logistics_estimated"]) == 0
        assert money(body["expected"]["logistics"]) == D(5_250)
        sales = world.get("sales", counted="true", **OCT)["items"]
        assert sum(money(x["logistics"]) for x in sales) == money(s["logistics"])
    finally:
        a.sql("DELETE FROM mp_expenses WHERE id IN (%s, %s)", [free, paid])
        a.sql(
            "UPDATE sale_items SET logistics_fee = 5000, issued_at = NULL WHERE id = %s", [pending]
        )
        after = rebuild()
    assert after["statement"] == before


def _sku_cols(world: World, **period: str) -> dict[str, Any]:
    return {c["key"]: c["statement"] for c in world.get("pnl", view="sku", **period)["columns"]}


def test_linked_ad_on_order_day(world: World) -> None:
    """ADR-039 (07 Q10): sotuvga bog'langan reklama — 18-oktabrda yechilgan, buyurtma 2-oktabr — P&L'da va
    ``/expenses`` da buyurtma kuniga, o'sha SKU'ga va sotuv qismiga (Yakunlangan) yoziladi."""
    a, xa = world.a, str(world.ids["xa"])
    early = {"start": "2026-10-01", "end": "2026-10-05"}
    late = {"start": "2026-10-15", "end": "2026-10-20"}
    before = world.get("pnl", **early)["statement"]
    before_late = world.get("pnl", **late)["statement"]
    before_xa = _sku_cols(world, **early)[xa]
    ad = world.expense(a, d(10, 18), "advertising", 7_000, sale_item_id=world.ids["s_oct2"])
    try:
        s = world.get("pnl", **early)["statement"]
        assert money(s["uzum_expenses"]["advertising"]) == (
            money(before["uzum_expenses"].get("advertising")) + 7_000
        )
        assert money(s["net_profit_done"]) == money(before["net_profit_done"]) - 7_000
        assert s["net_profit_processing"] == before["net_profit_processing"]
        assert (
            world.get("pnl", **late)["statement"]["uzum_expenses"] == before_late["uzum_expenses"]
        )
        col = _sku_cols(world, **early)[xa]
        assert money(col["uzum_direct"]) == money(before_xa["uzum_direct"]) + 7_000
        body = world.get("expenses", **early)
        row = next(i for i in body["items"] if i["id"] == str(ad))
        assert (row["day"], row["order_date"]) == ("2026-10-18", "2026-10-02")
        uzum = {c["category"]: money(c["amount"]) for c in body["uzum"]}
        assert uzum == {k: money(v) for k, v in s["uzum_expenses"].items()}
        assert str(ad) not in {i["id"] for i in world.get("expenses", **late)["items"]}
    finally:
        a.sql("DELETE FROM mp_expenses WHERE id = %s", [ad])


def test_storage_split_by_stock(world: World) -> None:
    """F43 (ADR-040): saqlash — Uzum qoidasi bo'yicha pullik saqlashdagi SKU'larga (aylanma > 60 kun, yangi emas),
    qoldiq × saqlash narxi; qoida hech kimni topmasa — hamma qoldiq bo'yicha; snapshot yo'q do'kon (B) — tushum
    ulushida (taqsimlangan). Qaytim saqlash — qaytarishdagi SKU'larga."""
    a, xa, ya = world.a, world.ids["xa"], world.ids["ya"]
    a.sql("UPDATE mp_skus SET storage_price = 2 WHERE id = %s", [xa])
    a.sql("UPDATE mp_skus SET storage_price = 1 WHERE id = %s", [ya])
    snap = a.insert("sku_daily", sku_id=ya, day=d(10, 2), qty_active=30, qty_fbs=0)
    ret = a.insert(
        "mp_returns", shop_id=a.shop_id, external_id=7_000_001, type="RETURN", status="ASSEMBLED"
    )
    a.insert("mp_return_items", return_id=ret, sku_external_id=12, quantity=1, sku_id=ya)
    rs = world.expense(
        a,
        d(10, 3),
        "return_storage",
        1_000,
        name="7000001 - sonli yukxat boʻyicha qaytarishni saqlash",
    )
    try:
        cols = _sku_cols(world, **OCT)
        # 1-okt 12 000: x yangi (birinchi sotuvdan 30 kun o'tmagan) — pullik SKU yo'q, hamma qoldiq bo'yicha → x.
        # 2-okt 30 000: y — eski, 15 kunda sotuvsiz (aylanma cheksiz) → pullik; x hali yangi → hammasi y ga.
        assert money(cols[str(xa)]["uzum_expenses"]["storage"]) == D(12_000)
        assert money(cols[str(ya)]["uzum_expenses"]["storage"]) == D(30_000)
        assert money(cols[str(ya)]["uzum_expenses"]["return_storage"]) == D(1_000)
        assert "storage" not in cols[str(xa)]["uzum_allocated"]
        assert money(cols[str(world.ids["zb"])]["uzum_allocated"]["storage"]) == D(8_000)
        assert money(world.get("pnl", **OCT)["statement"]["uzum_expenses"]["storage"]) == D(50_000)
    finally:
        a.sql("DELETE FROM mp_expenses WHERE id = %s", [rs])
        a.sql("DELETE FROM mp_return_items WHERE return_id = %s", [ret])
        a.sql("DELETE FROM mp_returns WHERE id = %s", [ret])
        a.sql("DELETE FROM sku_daily WHERE id = %s", [snap])
        a.sql("UPDATE mp_skus SET storage_price = NULL WHERE id IN (%s, %s)", [xa, ya])


def test_expected_ads_estimate(world: World) -> None:
    """F42 (ADR-039): hali topshirilmagan Jarayondagi sotuvga kutilayotgan reklama — SKU'ning oxirgi 30 kunda
    topshirilgan sotuvlaridagi bog'liq reklama ulushi (20 000 / 600 000) × tushum (200 000), "≈"; Uzum yechgan
    xarajatlar ro'yxatida yo'q."""
    a = world.a
    before = world.get("pnl", **OCT)
    a.sql(
        "UPDATE sale_items SET issued_at = %s WHERE id = %s",
        [datetime.now(UTC), world.ids["s_oct10"]],
    )
    try:
        body = world.get("pnl", **OCT)
        s, e = body["statement"], body["expected"]
        assert money(s["uzum_estimated"]["advertising"]) == D("6666.60")
        assert money(e["uzum_estimated"]["advertising"]) == D("6666.60")
        assert money(e["net_profit"]) == money(before["expected"]["net_profit"]) - D("6666.60")
        assert money(s["uzum_expenses"]["advertising"]) == D("26666.60")
        rows = {r["code"]: r for r in body["rows"]}
        assert money(rows["uzum:advertising"]["processing"]) == D("-6666.60")
        uzum = {c["category"]: money(c["amount"]) for c in world.get("expenses", **OCT)["uzum"]}
        assert uzum["advertising"] == D(20_000)  # taxmin — Uzum yechgan summa emas
        # B4.24: reklamasi allaqachon yechilgan (bog'langan) Jarayondagi sotuvga taxmin qo'shilmaydi — bir marta.
        ((pending,),) = a.sql(
            "SELECT id FROM sale_items WHERE org_id = %s AND upper(status) = 'PROCESSING'",
            [world.org_id],
        )
        ad = world.expense(a, d(10, 16), "advertising", 3_000, sale_item_id=pending)
        try:
            once = world.get("pnl", **OCT)["statement"]
            assert once["uzum_estimated"] == {}
            assert money(once["uzum_expenses"]["advertising"]) == D(23_000)
        finally:
            a.sql("DELETE FROM mp_expenses WHERE id = %s", [ad])
    finally:
        a.sql("UPDATE sale_items SET issued_at = NULL WHERE id = %s", [world.ids["s_oct10"]])
    assert world.get("pnl", **OCT)["statement"] == before["statement"]


def test_processing_sale_leaves_when_canceled(world: World) -> None:
    """ADR-036: Jarayondagi sotuv bekor bo'lsa (Uzum qatorni 0 qilib beradi) — sinxrondan keyingi qayta hisobda
    tushum va foydadan o'zi chiqadi; Yakunlangan bo'lsa — "shundan jarayonda" dan chiqadi, summa o'zgarmaydi."""
    a = world.a
    before = world.get("pnl", **OCT)["statement"]

    def resync(status: str, amount: int, returns: int) -> dict[str, Any]:
        a.sql(
            "UPDATE sale_items SET status = %s, amount = %s, amount_returns = %s, commission = %s, "
            "logistics_fee = %s WHERE org_id = %s AND sku_id = %s "
            "AND (ordered_at AT TIME ZONE 'Asia/Tashkent')::date = %s",
            [
                status,
                amount,
                returns,
                40_000 * amount,
                5_000 * amount,
                a.org_id,
                world.ids["xa"],
                d(10, 15),
            ],
        )
        a.run(lambda conn: calc.request(conn, world.org_id, calc.Scope.SHOP, a.shop_id, d(10, 15)))
        assert a.recalc(datetime.now(UTC)).errors == {}
        return world.get("pnl", **OCT)["statement"]

    try:
        done = resync("TO_WITHDRAW", 1, 0)
        assert money(done["revenue"]) == money(before["revenue"]) and done["units_processing"] == 0
        canceled = resync("CANCELED", 0, 1)
        assert money(canceled["revenue"]) == money(before["revenue"]) - D(200_000)
        assert money(canceled["net_profit"]) < money(before["net_profit"])
        assert canceled["units_processing"] == 0 and canceled["units"] == before["units"] - 1
    finally:
        after = resync("PROCESSING", 1, 0)
    assert after == before


def test_recalculated_flag(world: World, db: dict[str, str]) -> None:
    assert world.get("pnl", **OCT)["recalculated"] == 0
    # Kech kelgan kargo (M9): P1 tannarxi o'zgaradi → oktabr sotuvlari "qayta hisoblandi".
    cargo = world.a.component(world.ids["p1"], "cargo", 1_000_000)
    world.a.run(lambda conn: calc.request(conn, world.org_id, calc.Scope.PURCHASE, world.ids["p1"]))
    world.a.recalc(datetime.now(UTC))
    try:
        body = world.get("pnl", **OCT)
        assert body["recalculated"] == 4  # 2, 5, 10 va 15-oktabr (Jarayonda ham)
        sale = next(
            s for s in world.get("sales", **OCT)["items"] if s["id"] == str(world.ids["s_oct2"])
        )
        assert sale["recalculated_at"] is not None and money(sale["previous_cogs"]) == D(200_000)
        assert money(sale["cogs"]) == D(220_000)
    finally:
        world.a.sql("DELETE FROM cost_components WHERE id = %s", [cargo])
        world.a.run(
            lambda conn: calc.request(conn, world.org_id, calc.Scope.PURCHASE, world.ids["p1"])
        )
        world.a.recalc(datetime.now(UTC))
        world.a.sql("UPDATE sale_costs SET changed_at = NULL, previous_cogs = NULL")


# --- Bosh sahifa va SKU jadvali ----------------------------------------------------------------------


def test_dashboard_equals_pnl_and_skus(world: World) -> None:
    dash = world.get("dashboard", **OCT)
    pnl = world.get("pnl", **OCT)
    skus = world.get("skus", **OCT)
    net = money(pnl["statement"]["net_profit"])
    assert money(dash["statement"]["net_profit"]) == net
    rows_net = sum(money(r["net_profit"]) for r in skus["items"])
    assert (
        rows_net + money(skus["unlinked"]["net_profit"]) + money(skus["unallocated"]["net_profit"])
        == net
    )
    assert sum(money(x["revenue"]) for x in dash["daily"]) == D(2_000_000)
    oct15 = next(x for x in dash["daily"] if x["day"] == "2026-10-15")
    assert money(oct15["revenue_processing"]) == D(200_000)
    assert money(oct15["revenue_done"]) + money(oct15["revenue_processing"]) == money(
        oct15["revenue"]
    )
    assert len(dash["daily"]) == 20 and dash["daily"][0]["day"] == "2026-10-01"
    assert money(dash["daily"][0]["revenue"]) == 0  # sotuvsiz kun ham bor


def test_dashboard_blocks(world: World) -> None:
    dash = world.get("dashboard", **OCT)
    periods = {p["key"]: p for p in dash["periods"]}
    assert set(periods) == {"today", "yesterday", "this_month", "last_month"}
    assert money(periods["today"]["revenue"]) == D(100_000) and periods["today"]["units"] == 1
    today = datetime.now(TASHKENT).date()
    assert periods["this_month"]["period"]["start"] == today.replace(day=1).isoformat()
    # M4 "Oy prognozi" — to'liq o'tgan kunlar bo'yicha (bugungi tugamagan kun kirmaydi): oy boshidan kechagacha bo'lgan
    # qiymat × oydagi kunlar / o'tgan to'liq kunlar; oyning 1-kuni — prognoz yo'q.
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    to_yesterday = money(periods["this_month"]["revenue"]) - money(periods["today"]["revenue"])
    expected = None if today.day == 1 else run_rate(to_yesterday, today.day - 1, days_in_month)
    got = dash["forecast"]["revenue"]
    assert (None if got is None else D(got)) == expected
    # KPI sarhisob (ADR-043): 4 guruh, har kartochkada joriy, oldingi, o'zgarish va trend.
    summary = dash["summary"]
    assert [g["key"] for g in summary["groups"]] == ["orders", "uzum", "returns", "average"]
    assert sum(len(g["cards"]) for g in summary["groups"]) == 24
    cards = {c["key"]: c for g in summary["groups"] for c in g["cards"]}
    assert summary["bucket"] == "day" and len(summary["points"]) == 20
    assert all(len(c["series"]) == 20 for c in cards.values())

    def val(key: str) -> D:
        return D(cards[key]["value"])

    # Sotilgan: 12 yakunlangan + 1 Jarayonda = 13; bekor (topshirilmagan) 1; qaytarish (amountReturns) 1 → yalpi 15.
    # F17: 1 / 15; F18: 1 / (13 + 1); F19: reklama 20 000 / 2 000 000.
    assert val("units") == 13 and val("cancel_units") == 1 and val("return_units") == 1
    assert val("cancel_share") == D("0.066667") and val("return_share") == D("0.071429")
    assert val("cancel_revenue") == D(200_000) and val("return_revenue") == D(200_000)
    assert val("gross_revenue") == val("revenue") + val("cancel_revenue") + val("return_revenue")
    assert val("drr") == D("0.010000")
    # F45: oktabrda 8 ta buyurtma (har sotuv — alohida buyurtma), shundan bekor qilingani sof emas.
    assert val("orders") == 8 and val("orders_net") == 7 and val("net_order_share") == D("0.875000")
    assert val("average_check") == (val("revenue") / 7).quantize(D("0.01"))
    assert val("units_per_order") == D("1.857143")  # 13 / 7
    # F46, F47: Uzum xarajatlari = komissiya + logistika + F9; Uzumdan keyin qoladi = tushum − F46.
    rows = {r["code"]: money(r["amount"]) for r in dash["rows"]}
    uzum = sum((v for k, v in rows.items() if k.startswith("uzum:")), D(0))
    assert val("uzum_costs") == -(rows["commission"] + rows["logistics"]) - uzum
    assert val("after_uzum") == val("revenue") - val("uzum_costs")
    assert val("net_profit") == money(dash["statement"]["net_profit"])
    # F49 (ADR-053): buyurtmadan sof foydagacha — bo'laklar yig'indisi = yalpi summa, birinchisi 100%.
    flow = {x["key"]: x for x in summary["flow"]}
    assert list(flow) == [
        "gross_revenue",
        "cancel_revenue",
        "return_revenue",
        "uzum_costs",
        "cogs",
        "own_expenses",
        "tax",
        "uncosted",
        "net_profit",
    ]
    assert D(flow["gross_revenue"]["value"]) == val("gross_revenue")
    assert D(flow["gross_revenue"]["share"]) == 1 and flow["cogs"]["formula"] == "F7"
    assert D(flow["uzum_costs"]["value"]) == val("uzum_costs")
    assert D(flow["cogs"]["value"]) == -rows["cogs"]
    assert D(flow["net_profit"]["value"]) == val("net_profit")
    assert sum(D(x["value"]) for x in summary["flow"][1:]) == val("gross_revenue")
    # Oldingi davr (11–30 sentabr): 1 buyurtma, 2 dona; o'zgarish — nisbiy, ulushlarda — punkt.
    assert D(cards["orders"]["previous"]) == 1 and D(cards["orders"]["change"]) == 7
    assert cards["cancel_share"]["previous"] == "0.000000"
    assert cards["cancel_share"]["change"] == "0.066667"
    assert cards["cancel_share"]["good"] == "down" and cards["revenue"]["good"] == "up"
    assert not any(c["warn"] for c in cards.values())  # chegara sozlanmagan
    # Trend nuqtalari yig'indisi davr qiymatiga teng (additiv kartochkalar).
    for key in ("revenue", "units", "orders", "cancel_units", "return_revenue"):
        assert sum(D(x) for x in cards[key]["series"]) == val(key)
    # ADR-037: kutilayotgan sof foyda (F16) — hisobot, davr chizig'i va kunlarda yakunlangan + kutilayotgan = jami.
    assert money(dash["expected"]["net_profit"]) == D(37_000)
    st = dash["statement"]
    assert money(st["net_profit_done"]) + money(st["net_profit_processing"]) == money(
        st["net_profit"]
    )
    for p in dash["periods"]:
        assert money(p["net_profit_done"]) + money(p["net_profit_processing"]) == money(
            p["net_profit"]
        )
    for x in dash["daily"]:
        assert money(x["net_profit_done"]) + money(x["net_profit_processing"]) == money(
            x["net_profit"]
        )
    oct15 = next(x for x in dash["daily"] if x["day"] == "2026-10-15")
    assert (
        money(oct15["net_profit_processing"]) == D(37_000) and money(oct15["net_profit_done"]) == 0
    )
    # F29: X — 100 000 × (80 + 5 + 2), Z — 50 000 × 40; yo'lda 20 × 120 000.
    kpis = dash["kpis"]
    assert money(kpis["frozen_money"]) == D(
        13_500_000
    )  # + o'z omborim: Chiroq 2 500 000, Lampa 300 000
    assert money(kpis["in_transit_value"]) == D(2_400_000)
    top = dash["top"]
    assert {x["sku_id"] for x in top} <= {str(world.ids["xa"]), str(world.ids["zb"])}
    assert top and all(money(x["net_profit"]) > 0 for x in top)
    nets = [money(x["net_profit"]) for x in top]
    assert nets == sorted(nets, reverse=True)
    assert top[0]["title"] is not None and top[0]["shop_id"] is not None
    att = dash["attention"]
    assert att["uncosted_lines"] == 2 and money(att["uncosted_revenue"]) == D(200_000)
    assert set(dash["meta"]["freshness"]) == {"orders", "expenses", "products", "snapshot"}


def test_skus_table(world: World) -> None:
    body = world.get("skus", **OCT)
    rows = {r["sku_id"]: r for r in body["items"]}
    # Lampa (avgust sotuvlari) — oktabrda sotuvsiz, jadvalda bor.
    assert set(rows) == {str(world.ids[k]) for k in ("xa", "ya", "zb", "lb")}
    assert rows[str(world.ids["lb"])]["units"] == 0
    xa = rows[str(world.ids["xa"])]
    assert xa["units"] == 7 and money(xa["revenue"]) == D(
        1_400_000
    )  # + 15-oktabr Jarayonda (ADR-036)
    assert money(xa["avg_price"]) == D(200_000)
    assert D(xa["commission_share"]) == D("0.2")
    assert money(xa["logistics_per_unit"]) == D(5_000)
    assert money(xa["cogs_per_unit"]) == D(100_000)
    assert money(xa["ads_per_unit"]) == D("2857.14")  # 20 000 / 7
    assert D(xa["return_share"]) == D("0.125000")  # 1 / (sotilgan 7 + 1), ADR-043
    assert D(xa["cancel_share"]) == D("0.111111")  # 1 / yalpi 9
    assert xa["stock"] == 85 and xa["abc"] in ("A", "B", "C") and xa["rank"] == "A"
    assert xa["label"] in ("profitable", "borderline", "loss")
    ya = rows[str(world.ids["ya"])]
    assert ya["label"] == "no_data" and ya["cogs_per_unit"] is None and ya["uncovered_lines"] == 1
    assert body["total"] == 4 and (body["page"], body["pages"]) == (1, 1)
    assert money(body["unlinked"]["revenue"]) == D(50_000)


def test_skus_search_sort_and_pages(world: World) -> None:
    for q in ("кружка", "KRUJKA", "oyinchoq", "O'yinchoq", "Oʼyinchoq", "4780001", "art-1"):
        found = world.get("skus", q=q, **OCT)["items"]
        assert len(found) == 1, q
    by_units = world.get("skus", sort="-units", **OCT)["items"]
    assert [r["units"] for r in by_units] == sorted((r["units"] for r in by_units), reverse=True)
    asc = world.get("skus", sort="title", **OCT)["items"]
    shown = [fold(r["title"] or r["product_title"]) for r in asc]
    assert shown == sorted(
        shown
    )  # ko'rinadigan nom, katta-kichik harf va kirill/lotindan qat'i nazar (B4.50)

    # "Zaxira kunlari": harakatsiz qoldiq (tezlik 0, qoldiq bor) — cheksiz zaxira; qoldiqsiz SKU doim oxirida.
    def kind(r: dict[str, Any]) -> str:
        return "known" if r["days_of_stock"] is not None else "idle" if r["stock"] > 0 else "empty"

    desc = world.get("skus", sort="-days_of_stock", **OCT)["items"]
    assert [kind(r) for r in desc] == ["idle", "known", "empty", "empty"]
    asc_days = world.get("skus", sort="days_of_stock", **OCT)["items"]
    assert [kind(r) for r in asc_days] == ["known", "idle", "empty", "empty"]
    first = world.get("skus", limit=2, **OCT)
    assert len(first["items"]) == 2 and (first["page"], first["pages"]) == (1, 2)
    rest = world.get("skus", limit=2, page=2, **OCT)
    assert len(rest["items"]) == 2 and (rest["page"], rest["pages"]) == (2, 2)
    ids = {r["sku_id"] for r in first["items"] + rest["items"]}
    assert len(ids) == 4
    assert world.call("skus", sort="nope", **OCT).status_code == 422
    assert world.call("skus", page="x", **OCT).status_code == 422
    margin = world.get("skus", sort="-margin", **OCT)["items"]
    assert margin[-1]["margin"] is None  # qiymatsiz oxirida


# --- Drill-down: sotuvlar va xarajatlar ------------------------------------------------------------


def test_sales_and_expenses_pages(world: World) -> None:
    """ADR-054: `page` rejimi — sahifalar ketma-ket va takrorsiz; `cursor` rejimi (drill-down) bilan bir xil qatorlar."""
    for route in ("sales", "expenses"):
        by_cursor: list[str] = []
        cursor = None
        while True:
            params: dict[str, Any] = {"limit": 2, **OCT}
            if cursor:
                params["cursor"] = cursor
            got = world.get(route, **params)
            by_cursor += [i["id"] for i in got["items"]]
            cursor = got["next_cursor"]
            if not cursor:
                break
        everything = world.get(route, limit=100, **OCT)
        assert [i["id"] for i in everything["items"]] == by_cursor
        total = everything["total"]
        assert total == len(by_cursor) and (everything["page"], everything["pages"]) == (1, 1)
        pages = -(-total // 2)
        seen: list[str] = []
        for n in range(1, pages + 1):
            got = world.get(route, limit=2, page=n, **OCT)
            assert (got["page"], got["pages"], got["total"]) == (n, pages, total)
            assert got["next_cursor"] is None  # sahifa rejimida kursor yo'q
            seen += [i["id"] for i in got["items"]]
        assert seen == by_cursor
        last = world.get(route, limit=2, page=999, **OCT)
        assert last["page"] == last["pages"] == pages
        assert world.call(route, page=0, **OCT).status_code == 422


def test_sales_drilldown_sums_match_pnl(world: World) -> None:
    pnl = world.get("pnl", **OCT)["statement"]
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        params = {"counted": "true", "limit": 2, **OCT}  # Yakunlangan + Jarayonda (ADR-036)
        if cursor:
            params["cursor"] = cursor
        page = world.get("sales", **params)
        items += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(items) == 7 and len({i["id"] for i in items}) == 7
    assert {i["group"] for i in items} == {"completed", "processing"}
    for key in ("revenue", "commission", "logistics"):
        assert sum(money(i[key]) for i in items) == money(pnl[key]), key
    assert sum(money(i["cogs"]) for i in items) == money(pnl["cogs"])
    assert [i["ordered_at"] for i in items] == sorted(
        (i["ordered_at"] for i in items), reverse=True
    )
    noitem = next(i for i in items if i["sku_id"] == str(world.ids["ya"]))
    assert noitem["cogs"] is None and noitem["gross_profit"] is None
    assert noitem["cost_flags"] == ["no_item"]
    oct2 = next(i for i in items if i["id"] == str(world.ids["s_oct2"]))
    assert money(oct2["payout"]) == D(310_000) and money(oct2["gross_profit"]) == D(110_000)


def test_sales_filters_and_summary(world: World) -> None:
    all_ = world.get("sales", **OCT)
    assert len(all_["items"]) == 8
    groups = {i["group"] for i in all_["items"]}
    assert groups == {"completed", "processing", "canceled"}
    assert all_["summary"] == {  # ADR-043: sotilgan = Yakunlangan + Jarayonda, yalpi = 13 + 1 + 1
        "units": 13,
        "canceled": 1,
        "returns": 1,
        "cancel_share": "0.066667",
        "return_share": "0.071429",
    }
    canceled = world.get("sales", group="canceled", **OCT)["items"]
    assert len(canceled) == 1 and canceled[0]["amount"] == 1
    xa = world.get("sales", sku=str(world.ids["xa"]), **OCT)
    assert len(xa["items"]) == 5 and xa["summary"]["units"] == 7  # + Jarayonda (ADR-043)
    unlinked = world.get("sales", unlinked=True, **OCT)
    assert [i["sku_title"] for i in unlinked["items"]] == ["Noma'lum"]
    assert world.get("sales", group="unknown", **OCT)["items"] == []
    shop_b = world.get("sales", shop=str(world.b.shop_id), **OCT)["items"]
    assert len(shop_b) == 1 and shop_b[0]["amount"] == 4


def test_expenses_match_pnl(world: World) -> None:
    pnl = world.get("pnl", **OCT)["statement"]
    body = world.get("expenses", **OCT)
    uzum = {c["category"]: money(c["amount"]) for c in body["uzum"]}
    assert uzum == {k: money(v) for k, v in pnl["uzum_expenses"].items()}
    assert money(body["uzum_total"]) == sum(uzum.values()) == D(180_000)
    own = {c["category"]: money(c["amount"]) for c in body["own"]}
    assert own == {k: money(v) for k, v in pnl["own_expenses"].items()}
    assert money(body["own_total"]) == D(450_000)
    assert [f["id"] for f in body["fines"]] == [str(world.ids["fine70"]), str(world.ids["fine50"])]
    assert body["by_month"][0]["month"] == "2026-10-01"
    assert len(body["items"]) == 7  # chiqarilgan 2 tasi ro'yxatda yo'q (``include_excluded`` siz)
    ids = {i["id"] for i in body["items"]}
    assert str(world.ids["excluded"]) not in ids
    comp = next(i for i in body["items"] if i["category"] == "compensation")
    assert money(comp["amount"]) == D(-10_000) and comp["in_pnl"] is True
    scopes = {o["category"]: o["scope"] for o in body["own_items"]}
    assert scopes == {"ijara": "org", "internet": "shop", "qadoq": "item"}
    ijara = next(o for o in body["own_items"] if o["category"] == "ijara")
    assert money(ijara["in_period"]) == D(200_000) and money(ijara["amount"]) == D(310_000)


def test_expenses_excluded_category_and_cursor(world: World) -> None:
    body = world.get("expenses", include_excluded=True, **OCT)
    rows = {i["id"]: i for i in body["items"]}
    assert rows[str(world.ids["excluded"])]["excluded"] == "status"
    assert rows[str(world.ids["excluded"])]["in_pnl"] is False
    logistics = next(i for i in body["items"] if i["category"] == "logistics")
    assert logistics["in_pnl"] is False
    fines = world.get("expenses", category="fine", **OCT)["items"]
    assert {f["id"] for f in fines} == {str(world.ids["fine50"]), str(world.ids["fine70"])}
    seen, cursor = [], None
    while True:
        params: dict[str, Any] = {"include_excluded": True, "limit": 3, **OCT}
        if cursor:
            params["cursor"] = cursor
        page = world.get("expenses", **params)
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(rows) and len(seen) == len(set(seen))
    b_only = world.get("expenses", shop=str(world.b.shop_id), **OCT)
    assert money(b_only["uzum_total"]) == D(8_000)
    assert {o["category"] for o in b_only["own_items"]} == {"ijara", "internet"}
    a_only = world.get("expenses", shop=str(world.a.shop_id), **OCT)
    assert {o["category"] for o in a_only["own_items"]} == {"ijara", "qadoq"}


# --- Ombor ----------------------------------------------------------------------------------------


def test_inventory(world: World) -> None:
    body = world.get("inventory", as_of=AS_OF.isoformat())
    rows = {r["sku_id"]: r for r in body["items"]}
    xa = rows[str(world.ids["xa"])]
    # F23 mustaqil (ADR-057 Q1): 60 kun orqaga, 14 ta savdodagi kun; 8-oktabr qoldiq 0, birinchi sotuv 20-sentabr;
    # yakuniy donalar 50 dan kam — yakunlanish ulushi noma'lum (Jarayondagi to'liq).
    sold = {
        d(9, 20): 2,
        d(10, 2): 2,
        d(10, 5): 1,
        d(10, 10): 3,
        d(10, 15): 1,
    }  # + Jarayonda (ADR-036)
    snaps = {d(10, i): i != 8 for i in range(1, 21)}
    days = [
        DayStat(AS_OF - timedelta(days=i), sold.get(AS_OF - timedelta(days=i), 0),
                1 if AS_OF - timedelta(days=i) == d(10, 5) else 0,
                snaps.get(AS_OF - timedelta(days=i)))
        for i in range(60)
    ]  # fmt: skip
    expected = velocity(sorted(days, key=lambda x: x.day), AS_OF, d(9, 20))
    assert D(xa["velocity"]["value"]) == expected.value
    assert xa["velocity"]["days_counted"] == expected.days_counted == 14
    assert xa["velocity"]["completion"] is None and xa["velocity"]["new_item"] is False
    assert (xa["stock"], xa["qty_defected"], xa["in_transit"]) == (85, 2, 20)
    # M10 joylar (ADR-061 §10): p3 — faqat buyurtma berilgan ("Yo'lda"; eski "Xitoyda" ham shu), p1 Uzumga yuborilgan.
    assert xa["locations"] == {
        "fbo": 80, "fbs": 5, "defected": 2, "pending": 0, "china": 0, "road": 20, "own": 0,
        "inbound": 0,
    }  # fmt: skip
    # F27 buyurtma sanasi = bugun + (hamma joydagi tovar zaxira kunlari − muddat 32 kun), kunga pastga yaxlitlanadi
    # (ADR-057 Q2: Uzumda 85 + Xitoyda 20 = 105).
    assert D(xa["days_of_stock_all"]) == (D(105) / expected.value).quantize(D("0.1"))
    slack = D(xa["days_of_stock_all"]) - 32
    assert xa["order_by"] == {
        "day": (AS_OF + timedelta(days=int(slack))).isoformat(),
        "overdue": False,
    }
    assert D(xa["days_of_stock"]) == (D(85) / expected.value).quantize(D("0.1"))
    assert xa["lead_time"]["stages"] == {
        "cargo": "13",
        "china": "2",
        "handover": "2",
        "prep": "8",
        "receive": "7",
    }
    assert D(xa["lead_time"]["total"]) == 32 and xa["status"] == StockStatus.GOOD.value
    assert money(xa["unit_cost"]) == D(100_000) and money(xa["stock_value"]) == D(8_500_000)
    assert xa["reorder"]["qty"] == 0 and xa["last_sale_on"] == "2026-10-15"  # Jarayondagi ham sotuv
    zb = rows[str(world.ids["zb"])]
    # Oxirgi sotuv 2-oktabr (14 kunlik oynadan tashqari): tezlik 0, qoldiq 40 — Harakatsiz (muddatsiz ham aniq).
    assert zb["lead_time"] is None and zb["reorder"] is None and zb["order_by"] is None
    # p2 qabul qilingan, Uzumga yuborilmagan — 50 dona o'z omborida (Uzumda 40 ta turibdi).
    assert zb["locations"]["own"] == 50 and zb["locations"]["china"] == zb["locations"]["road"] == 0
    assert zb["status"] == StockStatus.DEAD.value and zb["liquidity"] is None
    ya = rows[str(world.ids["ya"])]
    assert ya["status"] is None and ya["unit_cost"] is None  # qoldiq yo'q, sotuv oynadan tashqarida
    totals = body["totals"]
    assert {k: money(v) for k, v in totals["frozen_money"].items()} == {
        "china": D(0),
        "road": D(2_400_000),
        "own": D(2_800_000),  # Chiroq 50 × 50 000 + Lampa 10 × 30 000
        "fbo": D(10_000_000),
        "fbs": D(500_000),
        "defected": D(200_000),
        "inbound": D(0),
    }
    assert money(totals["frozen_total"]) == D(15_900_000)
    assert totals["units"] == {
        "china": 0, "road": 20, "own": 60, "fbo": 120, "fbs": 5, "defected": 2, "inbound": 0,
    }  # fmt: skip
    assert totals["statuses"] == {"dead": 1, "good": 1}
    # "Uzumga yuborish": zb ning omborida 50 dona bor, lekin tezlik 0 — signal yo'q; xa ning omborida tovar yo'q.
    assert totals["ship"] == 0 and xa["ship"] is None and zb["ship"] is None
    assert body["as_of"] == "2026-10-20" and body["total"] == 4  # lampa — qoldiqsiz
    order = [r["sku_id"] for r in body["items"]]
    assert order[0] == str(world.ids["xa"])  # holati borlari birinchi


def test_inventory_filters_and_warehouse_amounts(world: World) -> None:
    hidden = world.get("inventory", role="warehouse", as_of=AS_OF.isoformat())
    xa = next(r for r in hidden["items"] if r["sku_id"] == str(world.ids["xa"]))
    assert xa["unit_cost"] is None and xa["stock_value"] is None
    assert xa["reorder"]["budget"] is None and xa["stock"] == 85
    assert hidden["totals"]["frozen_money"] is None and hidden["totals"]["frozen_total"] is None
    shown = world.get("inventory", role="manager", as_of=AS_OF.isoformat())
    assert shown["totals"]["frozen_total"] is not None
    assert world.get("inventory", ship="true", as_of=AS_OF.isoformat())["items"] == []
    good = world.get("inventory", status="good", as_of=AS_OF.isoformat())["items"]
    assert [r["sku_id"] for r in good] == [str(world.ids["xa"])]
    b_only = world.get("inventory", shop=str(world.b.shop_id), as_of=AS_OF.isoformat())
    assert {r["sku_id"] for r in b_only["items"]} == {str(world.ids["zb"]), str(world.ids["lb"])}
    found = world.get("inventory", q="chiroq", as_of=AS_OF.isoformat())["items"]
    assert [r["sku_id"] for r in found] == [str(world.ids["zb"])]
    page = world.get("inventory", limit=1, as_of=AS_OF.isoformat())
    assert len(page["items"]) == 1 and (page["page"], page["pages"]) == (1, page["total"])
    last = world.get(
        "inventory", limit=1, page=999, as_of=AS_OF.isoformat()
    )  # oxirgisidan oshsa — oxirgisi
    assert last["page"] == last["pages"] == page["total"] and len(last["items"]) == 1
    assert world.call("inventory", page=0, as_of=AS_OF.isoformat()).status_code == 422
    assert world.call("inventory", limit=101, as_of=AS_OF.isoformat()).status_code == 422


# --- Ruxsat, ajratish, xatolar -----------------------------------------------------------------------

FINANCE = ["dashboard", "pnl", "skus", "sales", "expenses"]


@pytest.mark.parametrize("path", FINANCE)
def test_warehouse_has_no_finance(world: World, path: str) -> None:
    r = world.call(path, role="warehouse", **OCT)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"


@pytest.mark.parametrize("role", ["manager", "accountant"])
@pytest.mark.parametrize("path", [*FINANCE, "inventory"])
def test_finance_roles_can_read(world: World, role: str, path: str) -> None:
    assert world.call(path, role=role, **OCT).status_code == 200


@pytest.mark.parametrize("path", [*FINANCE, "inventory"])
def test_other_org_is_invisible(world: World, path: str) -> None:
    r = world.call(path, org=world.other, **OCT)
    assert r.status_code == 404 and r.json()["code"] == "org_not_found"


def test_unauthenticated(world: World) -> None:
    world.api.client.cookies.clear()
    r = world.api.client.get(f"/api/v1/orgs/{world.org_id}/pnl")
    assert r.status_code == 401


def test_bad_period(world: World) -> None:
    r = world.call("pnl", start="2026-10-20", end="2026-10-01")
    assert r.status_code == 422 and r.json()["code"] == "bad_period"
    r = world.call("pnl", start="2000-01-01", end="2026-10-01")
    assert r.status_code == 422 and r.json()["code"] == "bad_period"


def test_default_period_is_last_30_days(world: World) -> None:
    meta = world.get("pnl")["meta"]
    today = datetime.now(TASHKENT).date()
    assert meta["period"]["end"] == today.isoformat() and meta["period"]["days"] == 30


def test_freshness_reflects_sync_state(world: World) -> None:
    assert world.get("sales", **OCT)["meta"]["freshness"] == {"orders": None}
    moment = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
    for shop in (world.a.shop_id, world.b.shop_id):
        world.a.insert("sync_state", shop_id=shop, kind="orders", last_success_at=moment)
    try:
        fresh = world.get("sales", **OCT)["meta"]["freshness"]["orders"]
        assert datetime.fromisoformat(fresh) == moment
    finally:
        world.a.sql("DELETE FROM sync_state WHERE org_id = %s", [world.org_id])


# --- OpenAPI tiplari (03 §8, §13) -------------------------------------------------------------------


def test_openapi_snapshot_is_current() -> None:
    """``apps/api/openapi.json`` (frontend tiplari manbasi) kod bilan bir xil: farq bo'lsa
    ``uv run python -m upapi.openapi`` bilan yangilanadi."""
    from upapi.openapi import render

    path = Path(__file__).resolve().parents[1] / "openapi.json"
    assert path.read_text() == render(), "openapi.json eskirgan: uv run python -m upapi.openapi"
    spec = json.loads(path.read_text())
    for name in ("dashboard", "pnl", "skus", "sales", "expenses", "inventory"):
        assert f"/api/v1/orgs/{{org_id}}/{name}" in spec["paths"]


def test_openapi_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from upapi import openapi

    assert openapi.main(["--check"]) == 0
    target = tmp_path / "openapi.json"
    monkeypatch.setattr(openapi, "PATH", target)
    assert openapi.main(["--check"]) == 1  # fayl yo'q
    assert openapi.main([]) == 0 and openapi.main(["--check"]) == 0
    target.write_text("{}")
    assert openapi.main(["--check"]) == 1


# --- Tezlik (M4: 1 yil, 50 000 sotuv qatori — p95 < 700 ms) -------------------------------------------


LIMIT = 1.5  # soniya: CI'da regressiya chegarasi (maqsad 0,7 — docstring)


@pytest.mark.benchmark
def test_benchmark_dashboard_year(db: dict[str, str]) -> None:
    """1 yil, 50 000 sotuv qatori, 300 SKU (Zipf: ko'p sotuv bir nechta SKU'da) → ~24 000 (SKU × kun) katak,
    3 000 reklama xarajati (har biri kun tushumi ulushida SKU'larga). Bosh sahifa, P&L (SKU ko'rinishi) va SKU
    jadvali — HTTP orqali, 1 isitish + 10 so'rov.

    M4 maqsadi p95 < 700 ms (B4; staging serverida B8.4 yuklama testi bilan). B2.9 da o'lchangan (sandbox, 4 vCPU,
    mediana / eng sekini): bosh sahifa 0,78 / 0,93 s, P&L 0,60 / 0,81 s, SKU 0,68 / 0,81 s — maqsadga yetmagan,
    05 B4 ga yozilgan. Bu test — regressiya qo'riqchisi (CI runner tezligi o'zgaruvchan): ``LIMIT`` dan oshsa qizaradi."""
    import random
    import time

    import psycopg

    settings = sf.settings_for(db)
    account = create_account(db, settings, TOKEN, [A, B])
    shops = [account.shops[A], account.shops[B]]
    org = account.org_id
    start = date(2025, 10, 1)
    with psycopg.connect(db["admin"]) as conn, conn.cursor() as cur:
        skus = []
        for i in range(300):
            sku = uuid.uuid4()
            skus.append((sku, shops[i % 2]))
            cur.execute(
                "INSERT INTO mp_skus (id, org_id, shop_id, external_id, sku_code, qty_active) "
                "VALUES (%s, %s, %s, %s, %s, 10)",
                [sku, org, shops[i % 2], i, f"SKU {i}"],
            )
        rng = random.Random(1)
        weights = [1 / (i + 1) for i in range(300)]
        lines: dict[tuple[int, int], int] = {}
        for _ in range(50_000):
            key = (rng.choices(range(300), weights)[0], rng.randrange(365))
            lines[key] = lines.get(key, 0) + 1
        cur.executemany(
            "INSERT INTO daily_sku_metrics (org_id, shop_id, sku_id, day, revenue, units, commission, "
            "logistics, cogs, revenue_costed, payout_costed, lines, units_costed) "
            "VALUES (%s, %s, %s, %s, 100000 * %s, %s, 20000 * %s, 5000 * %s, 40000 * %s, 100000 * %s, "
            "75000 * %s, %s, %s)",
            [
                (org, skus[s][1], skus[s][0], start + timedelta(days=day), *[n] * 9)
                for (s, day), n in lines.items()
            ],
        )
        cur.executemany(
            "INSERT INTO mp_expenses (org_id, shop_id, external_id, category, type, amount, created_on) "
            "VALUES (%s, %s, %s, 'advertising', 'OUTCOME', 10000, %s)",
            [(org, shops[i % 2], i, at(start + timedelta(days=i % 365))) for i in range(3_000)],
        )
    year = {"start": start.isoformat(), "end": (start + timedelta(days=364)).isoformat()}
    with mp_api(db) as api:
        phone = api.login()
        user = api.admin("SELECT id FROM users WHERE phone = %s", [phone])[0][0]
        api.admin(
            "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, 'owner')", [org, user]
        )
        for path, extra in (("dashboard", {}), ("pnl", {"view": "sku"}), ("skus", {})):
            times = []
            for _ in range(11):
                t0 = time.perf_counter()
                r = api.client.get(f"/api/v1/orgs/{org}/{path}", params={**year, **extra})
                times.append(time.perf_counter() - t0)
                assert r.status_code == 200, r.text
            body = r.json()
            assert money(body["statement" if path != "skus" else "unlinked"]["revenue"]) >= 0
            if path == "skus":
                assert body["total"] == 300
            p95 = sorted(times[1:])[-1]
            assert p95 < LIMIT, (path, [round(t, 3) for t in times])


def test_forecast_basis_is_completed_days() -> None:
    """M4 "Oy prognozi": asos — oy boshidan kechagacha; bugungi tugamagan kun kirmaydi, 1-sanada prognoz yo'q."""
    from upapi.routes.dashboard import forecast_basis

    assert forecast_basis(date(2026, 11, 1)) is None
    assert forecast_basis(date(2026, 11, 2)) == Period(date(2026, 11, 1), date(2026, 11, 1))
    basis = forecast_basis(date(2026, 11, 11))
    assert basis is not None and basis.days == 10 and basis.end == date(2026, 11, 10)
    # Kuniga 1 mln sur'at, 30 kunlik oy: 10 to'liq kun → 30 mln (bugungi yarim kun natijaga ta'sir qilmaydi).
    assert run_rate(Decimal(10_000_000), basis.days, 30) == Decimal("30000000.00")


def test_summary_buckets() -> None:
    """ADR-043: trend nuqtalari — ≤ 62 kun kunlik, ≤ 366 kun 7 kunlik (davr boshidan), undan uzun — oylik."""
    from upapi.routes.dashboard import _buckets
    from upcore.metrics import Period

    kind, of = _buckets(Period(d(10, 1), d(10, 31)))
    assert kind == "day" and of(d(10, 7)) == d(10, 7)
    kind, of = _buckets(Period(d(7, 1), d(10, 31)))
    assert kind == "week" and of(d(7, 7)) == d(7, 1) and of(d(7, 8)) == d(7, 8)
    kind, of = _buckets(Period(date(2025, 1, 1), d(10, 31)))
    assert kind == "month" and of(d(10, 17)) == d(10, 1)


def test_dashboard_weekly_summary(world: World) -> None:
    dash = world.get("dashboard", start="2026-08-01", end="2026-10-20")
    summary = dash["summary"]
    assert summary["bucket"] == "week" and summary["points"][0] == "2026-08-01"
    cards = {c["key"]: c for g in summary["groups"] for c in g["cards"]}
    for key in ("revenue", "units", "orders"):
        assert sum(D(x) for x in cards[key]["series"]) == D(cards[key]["value"])

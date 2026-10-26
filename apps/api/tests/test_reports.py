"""B2.9 o'qish API'lari (haqiqiy PostgreSQL): dashboard, pnl, skus, sales, expenses, inventory.

Ma'lumot superuser bilan yoziladi, hosila jadvallar haqiqiy hisob ishi bilan quriladi (lotlar → ``sale_costs`` →
``daily_sku_metrics``). Asosiy tekshiruvlar — M5 qabul mezonlari: P&L sof foydasi = bosh sahifa = SKU jadvali
yig'indisi; ustunlar (oylar, do'konlar, SKU) yig'indisi = jami; drill-down yig'indisi = qator summasi; kunlik agregat
ustidagi P&L = sotuv qatorlaridan qurilgan P&L (``upcore``). Ruxsatlar va tashkilotlarni ajratish ham shu yerda.
"""

from __future__ import annotations

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
from upcore.expenses import ExpenseCategory
from upcore.inventory import DayStat, StockStatus, velocity
from upcore.metrics import TASHKENT, ManualExpense, Period, SaleLine, business_date
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
    assert money(s["revenue"]) == ref.revenue.amount == D(1_800_000)
    for key in ("commission", "logistics", "cogs", "tax", "net_profit", "expenses_deducted"):
        assert money(s[key]) == getattr(ref, key).amount, key
    assert s["units"] == ref.units == 12 and s["lines"] == ref.lines == 6
    assert s["covered_units"] == ref.covered_units == 10
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


def test_pnl_rows_and_previous(world: World) -> None:
    body = world.get("pnl", **OCT)
    rows = {r["code"]: r for r in body["rows"]}
    assert money(rows["revenue"]["amount"]) == D(1_800_000)
    assert money(rows["revenue"]["previous"]) == D(400_000)  # 20-sentabr, 2 dona
    assert money(rows["revenue"]["diff"]) == D(1_400_000)
    assert D(rows["revenue"]["share_of_revenue"]) == D(1)
    assert D(rows["revenue"]["change"]) == D("3.5")  # 1 400 000 / 400 000
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
    assert money(both["statement"]["revenue"]) == D(1_800_000)
    assert both["meta"]["shops"] == sorted([str(world.a.shop_id), str(world.b.shop_id)])


def test_pnl_pending_profit(world: World) -> None:
    body = world.get("pnl", **OCT)
    # 15-oktabr Jarayonda: 200 000 − 40 000 − 5 000 − tannarx 100 000 = 55 000; R — 50 donadan kam (noma'lum).
    assert money(body["pending"]["raw"]) == D(55_000)
    assert body["pending"]["amount"] is None and body["pending"]["rate"] is None
    assert [p["shop_id"] for p in body["pending_shops"]] == [str(world.a.shop_id)]


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
    assert sum(money(x["revenue"]) for x in dash["daily"]) == D(1_800_000)
    assert len(dash["daily"]) == 20 and dash["daily"][0]["day"] == "2026-10-01"
    assert money(dash["daily"][0]["revenue"]) == 0  # sotuvsiz kun ham bor


def test_dashboard_blocks(world: World) -> None:
    dash = world.get("dashboard", **OCT)
    periods = {p["key"]: p for p in dash["periods"]}
    assert set(periods) == {"today", "yesterday", "this_month", "last_month"}
    assert money(periods["today"]["revenue"]) == D(100_000) and periods["today"]["units"] == 1
    today = datetime.now(TASHKENT).date()
    assert periods["this_month"]["period"]["start"] == today.replace(day=1).isoformat()
    assert dash["forecast"]["revenue"] is not None
    kpis = dash["kpis"]
    # F17: bekor 1 / (yakunlangan 12 + 1); F18: qaytgan 1 / (12 + 1); F19: reklama 20 000 / 1 800 000.
    assert D(kpis["cancel_share"]) == D("0.076923") and D(kpis["return_share"]) == D("0.076923")
    assert D(kpis["drr"]) == D("0.011111")
    assert money(kpis["expected_profit"]["raw"]) == D(55_000)
    # F29: X — 100 000 × (80 + 5 + 2), Z — 50 000 × 40; yo'lda 20 × 120 000.
    assert money(kpis["frozen_money"]) == D(10_700_000)
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
    assert set(rows) == {str(world.ids[k]) for k in ("xa", "ya", "zb")}
    xa = rows[str(world.ids["xa"])]
    assert xa["units"] == 6 and money(xa["revenue"]) == D(1_200_000)
    assert money(xa["avg_price"]) == D(200_000)
    assert D(xa["commission_share"]) == D("0.2")
    assert money(xa["logistics_per_unit"]) == D(5_000)
    assert money(xa["cogs_per_unit"]) == D(100_000)
    assert money(xa["ads_per_unit"]) == D("3333.33")  # 20 000 / 6
    assert D(xa["return_share"]) == D("0.142857")  # 1 / (6 + 1)
    assert D(xa["cancel_share"]) == D("0.142857")
    assert xa["stock"] == 85 and xa["abc"] in ("A", "B", "C") and xa["rank"] == "A"
    assert xa["label"] in ("profitable", "borderline", "loss")
    ya = rows[str(world.ids["ya"])]
    assert ya["label"] == "no_data" and ya["cogs_per_unit"] is None and ya["uncovered_lines"] == 1
    assert body["total"] == 3 and body["next_cursor"] is None
    assert money(body["unlinked"]["revenue"]) == D(50_000)


def test_skus_search_sort_and_cursor(world: World) -> None:
    for q in ("кружка", "KRUJKA", "oyinchoq", "O'yinchoq", "Oʼyinchoq", "4780001", "art-1"):
        found = world.get("skus", q=q, **OCT)["items"]
        assert len(found) == 1, q
    by_units = world.get("skus", sort="-units", **OCT)["items"]
    assert [r["units"] for r in by_units] == sorted((r["units"] for r in by_units), reverse=True)
    asc = world.get("skus", sort="title", **OCT)["items"]
    assert [r["title"] for r in asc] == sorted(r["title"] for r in asc)
    first = world.get("skus", limit=2, **OCT)
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = world.get("skus", limit=2, cursor=first["next_cursor"], **OCT)
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    ids = {r["sku_id"] for r in first["items"] + rest["items"]}
    assert len(ids) == 3
    assert world.call("skus", sort="nope", **OCT).status_code == 422
    assert world.call("skus", cursor="!!", **OCT).status_code == 422
    margin = world.get("skus", sort="-margin", **OCT)["items"]
    assert margin[-1]["margin"] is None  # qiymatsiz oxirida


# --- Drill-down: sotuvlar va xarajatlar ------------------------------------------------------------


def test_sales_drilldown_sums_match_pnl(world: World) -> None:
    pnl = world.get("pnl", **OCT)["statement"]
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        params = {"group": "completed", "limit": 2, **OCT}
        if cursor:
            params["cursor"] = cursor
        page = world.get("sales", **params)
        items += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(items) == 6 and len({i["id"] for i in items}) == 6
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
    assert all_["summary"] == {
        "units": 12,
        "canceled": 1,
        "returns": 1,
        "cancel_share": "0.076923",
        "return_share": "0.076923",
    }
    canceled = world.get("sales", group="canceled", **OCT)["items"]
    assert len(canceled) == 1 and canceled[0]["amount"] == 1
    xa = world.get("sales", sku=str(world.ids["xa"]), **OCT)
    assert len(xa["items"]) == 5 and xa["summary"]["units"] == 6
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
    # F23 mustaqil: 56 kunlik oyna, 8-oktabr qoldiq 0, birinchi sotuv 20-sentabr.
    sold = {d(9, 20): 2, d(10, 2): 2, d(10, 5): 1, d(10, 10): 3}
    snaps = {d(10, i): i != 8 for i in range(1, 21)}
    days = [
        DayStat(AS_OF - timedelta(days=i), sold.get(AS_OF - timedelta(days=i), 0),
                1 if AS_OF - timedelta(days=i) == d(10, 5) else 0,
                snaps.get(AS_OF - timedelta(days=i)))
        for i in range(56)
    ]  # fmt: skip
    expected = velocity(sorted(days, key=lambda x: x.day), AS_OF, d(9, 20))
    assert D(xa["velocity"]["value"]) == expected.value
    assert xa["velocity"]["days_counted"] == expected.days_counted == 13
    assert (xa["stock"], xa["qty_defected"], xa["in_transit"]) == (85, 2, 20)
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
    assert xa["reorder"]["qty"] == 0 and xa["last_sale_on"] == "2026-10-10"
    zb = rows[str(world.ids["zb"])]
    # Oxirgi sotuv 2-oktabr (14 kunlik oynadan tashqari): tezlik 0, qoldiq 40 — Harakatsiz (muddatsiz ham aniq).
    assert zb["lead_time"] is None and zb["reorder"] is None
    assert zb["status"] == StockStatus.DEAD.value and zb["liquidity"] is None
    ya = rows[str(world.ids["ya"])]
    assert ya["status"] is None and ya["unit_cost"] is None  # qoldiq yo'q, sotuv oynadan tashqarida
    totals = body["totals"]
    assert {k: money(v) for k, v in totals["frozen_money"].items()} == {
        "fbo": D(10_000_000),
        "fbs": D(500_000),
        "defected": D(200_000),
        "in_transit": D(2_400_000),
    }
    assert money(totals["frozen_total"]) == D(13_100_000)
    assert totals["statuses"] == {"dead": 1, "good": 1}
    assert body["as_of"] == "2026-10-20" and body["total"] == 3
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
    good = world.get("inventory", status="good", as_of=AS_OF.isoformat())["items"]
    assert [r["sku_id"] for r in good] == [str(world.ids["xa"])]
    b_only = world.get("inventory", shop=str(world.b.shop_id), as_of=AS_OF.isoformat())
    assert [r["sku_id"] for r in b_only["items"]] == [str(world.ids["zb"])]
    found = world.get("inventory", q="chiroq", as_of=AS_OF.isoformat())["items"]
    assert [r["sku_id"] for r in found] == [str(world.ids["zb"])]
    page = world.get("inventory", limit=1, as_of=AS_OF.isoformat())
    assert len(page["items"]) == 1 and page["next_cursor"]


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

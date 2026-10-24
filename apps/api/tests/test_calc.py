"""B2.8 hisob ishlari (haqiqiy PostgreSQL): lotlar (F20), sotuv tannarxi (F21, F22), "qayta hisoblandi" belgisi,
kunlik agregat, qayta hisob navbati, inkremental = to'liq qayta qurish, sinxron va Procrastinate bilan bog'lanish."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import dbtools
import psycopg
import pytest
import sellerfake as sf
from procrastinate.testing import InMemoryConnector
from psycopg.types.json import Jsonb
from sellerfake import TOKEN, A, admin, create_account, runtime, seller
from sqlalchemy.ext.asyncio import AsyncConnection
from upapi import calc
from upapi.db.session import make_engine, org_transaction
from upapi.sync import engine as eng
from upapi.sync import jobs

D = Decimal
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 7, 0, tzinfo=UTC)  # Toshkent 12:00


@dataclass
class Org:
    db: dict[str, str]
    org_id: uuid.UUID
    shop_id: uuid.UUID
    _ext: int = 0

    def sql(self, query: str, params: list[Any] | None = None) -> Any:
        return admin(self.db, query, params)

    def insert(self, table: str, **values: Any) -> uuid.UUID:
        values.setdefault("id", uuid.uuid4())
        values["org_id"] = self.org_id
        cols = ", ".join(values)
        marks = ", ".join(["%s"] * len(values))
        with psycopg.connect(self.db["admin"]) as conn:
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))
        return values["id"]

    def item(self, name: str = "Tovar") -> tuple[uuid.UUID, uuid.UUID]:
        item = self.insert("items", name=name)
        self._ext += 1
        sku = self.insert(
            "mp_skus", shop_id=self.shop_id, external_id=self._ext, sku_code=name, item_id=item
        )
        return item, sku

    def purchase(self, received: date | None = None, **extra: Any) -> uuid.UUID:
        return self.insert("purchases", received_on=received, **extra)

    def line(
        self, purchase: uuid.UUID, item: uuid.UUID | None, qty: int, **extra: Any
    ) -> uuid.UUID:
        return self.insert(
            "purchase_lines",
            purchase_id=purchase,
            item_id=item,
            ordered_qty=qty,
            received_qty=extra.pop("received", qty),
            **extra,
        )

    def component(
        self, purchase: uuid.UUID, kind: str, amount: int | str, currency: str = "UZS", **extra: Any
    ) -> uuid.UUID:
        if "targets" in extra:
            extra["targets"] = Jsonb(extra["targets"])
        return self.insert(
            "cost_components",
            purchase_id=purchase,
            kind=kind,
            amount=D(amount),
            currency=currency,
            **extra,
        )

    def sale(
        self,
        sku: uuid.UUID | None,
        day: date,
        amount: int = 1,
        status: str = "TO_WITHDRAW",
        price: int = 200_000,
        **extra: Any,
    ) -> uuid.UUID:
        self._ext += 1
        return self.insert(
            "sale_items",
            shop_id=self.shop_id,
            external_id=extra.pop("external_id", self._ext),
            order_id=self._ext * 10,
            status=status,
            ordered_at=at(day),
            sell_price=D(price),
            amount=amount,
            commission=D(price * amount // 5),
            logistics_fee=D(5_000 * amount),
            sku_id=sku,
            **extra,
        )

    def run(self, fn: Callable[[AsyncConnection], Coroutine[Any, Any, Any]]) -> Any:
        async def main() -> Any:
            engine = make_engine(self.db["app"])
            try:
                async with org_transaction(engine, self.org_id) as conn:
                    return await fn(conn)
            finally:
                await engine.dispose()

        return asyncio.run(main())

    def request(
        self, scope: calc.Scope, ref: uuid.UUID | None = None, since: date | None = None
    ) -> None:
        self.run(lambda conn: calc.request(conn, self.org_id, scope, ref, since))

    def recalc(self, now: datetime = NOW) -> calc.CalcResult:
        async def main() -> calc.CalcResult:
            engine = make_engine(self.db["app"])
            try:
                return await calc.recalc_org(engine, self.org_id, now)
            finally:
                await engine.dispose()

        return asyncio.run(main())

    def costs(self) -> dict[uuid.UUID, Any]:
        rows = self.sql(
            "SELECT sale_item_id, cogs, unit_cost, flags, allocations, changed_at, previous_cogs, method "
            "FROM sale_costs WHERE org_id = %s",
            [self.org_id],
        )
        return {r[0]: r[1:] for r in rows}

    def metrics(self) -> dict[tuple[Any, date], tuple[Any, ...]]:
        rows = self.sql(
            "SELECT sku_id, day, revenue, units, commission, logistics, cogs, ads, returns, canceled, "
            "revenue_costed, payout_costed, cogs_estimated FROM daily_sku_metrics WHERE org_id = %s",
            [self.org_id],
        )
        return {(r[0], r[1]): r[2:] for r in rows}

    def queue(self) -> list[tuple[Any, ...]]:
        return self.sql(
            "SELECT kind, ref_id, since FROM recalc_queue WHERE org_id = %s ORDER BY kind",
            [self.org_id],
        )


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    """Alohida baza: kurslar (global ``fx_rates``) va tungi ish faqat shu modul ma'lumotini ko'radi."""
    with dbtools.migrated_database() as urls:
        yield urls


@pytest.fixture
def org(db: dict[str, str]) -> Org:
    account = create_account(db, sf.settings_for(db), TOKEN, [A])
    return Org(db, account.org_id, account.shops[A])


def d(month: int, day: int) -> date:
    return date(2026, month, day)


# --- Lotlar va FIFO ----------------------------------------------------------------------------------


def _two_lots(org: Org) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Tovar: P1 (1-sentabr, 10 dona × 120 000) va P2 (1-oktabr, 10 dona × 130 000, USD qo'lda kurs)."""
    item, sku = org.item()
    p1 = org.purchase(d(9, 1), ordered_on=d(8, 1))
    org.line(p1, item, 10)
    org.component(p1, "goods", 1_000_000)
    org.component(p1, "cargo", 200_000, allocation="weight")  # vazn yo'q → dona bo'yicha
    p2 = org.purchase(d(10, 1), ordered_on=d(9, 1))
    org.line(p2, item, 10)
    org.component(p2, "goods", 100, "USD", rate_mode="manual", rate=D(12_000))
    org.component(p2, "cargo", 100_000)
    return item, sku, p1, p2


def test_lots_sale_costs_and_metrics(org: Org) -> None:
    item, sku, p1, p2 = _two_lots(org)
    s1 = org.sale(sku, d(9, 10), 8)
    s2 = org.sale(sku, d(10, 5), 4, amount_returns=1)
    s3 = org.sale(sku, d(10, 6), 1, "PROCESSING")
    canceled = org.sale(sku, d(10, 6), 2, "CANCELED")
    _, other = org.item("Lotsiz")
    no_lots = org.sale(other, d(10, 6))
    unlinked = org.sale(None, d(10, 6), sku_title="Noma'lum")
    org.request(calc.Scope.PURCHASE)
    org.request(calc.Scope.SHOP, org.shop_id)

    result = org.recalc()
    assert result.status == "done" and result.errors == {}
    assert (result.lots, result.costs_written, result.costs_deleted) == (2, 5, 0)
    assert org.queue() == []

    lots = org.sql(
        "SELECT p.id, l.qty, l.total, l.unit_cost, l.ready_on, l.flags, l.item_id FROM lots l "
        "JOIN purchase_lines pl ON pl.id = l.purchase_line_id JOIN purchases p ON p.id = pl.purchase_id "
        "WHERE l.org_id = %s",
        [org.org_id],
    )
    by = {r[0]: r[1:] for r in lots}
    assert by[p1] == (10, D("1200000.00"), D("120000.000000"), d(9, 1), ["base_fallback"], item)
    assert by[p2] == (10, D("1300000.00"), D("130000.000000"), d(10, 1), [], item)

    costs = org.costs()
    assert set(costs) == {s1, s2, s3, no_lots, unlinked}  # bekor qilingan — yo'q
    assert costs[s1][:3] == (D("960000.00"), D("120000.000000"), ["base_fallback"])
    # FIFO: 2 dona P1 (120 000) + 2 dona P2 (130 000).
    assert costs[s2][0] == D("500000.00")
    assert [(a["qty"], a["unit"]) for a in costs[s2][3]] == [
        (2, "120000.000000"),
        (2, "130000.000000"),
    ]
    assert costs[s3][0] == D("130000.00")
    assert costs[no_lots][:3] == (None, None, ["no_lots"])
    assert costs[unlinked][:3] == (None, None, ["no_item"])
    assert all(
        c[4] is None and c[6] == "fifo" for c in costs.values()
    )  # birinchi hisob — belgi yo'q
    assert canceled not in costs

    metrics = org.metrics()
    oct6 = metrics[(sku, d(10, 6))]
    # Jarayonda va bekor qilingan: tushumda yo'q; bekor dona — 2.
    assert oct6 == (D(0), 0, D(0), D(0), D(0), D(0), 0, 2, D(0), D(0), D(0))
    oct5 = metrics[(sku, d(10, 5))]
    assert oct5 == (
        D("800000.00"),
        4,
        D("160000.00"),
        D("20000.00"),
        D("500000.00"),
        D(0),
        1,
        0,
        D("800000.00"),
        D("620000.00"),  # F6 tannarxi ma'lum qism
        D("500000.00"),  # P1 qismi "base_fallback" — taxminiy (F22)
    )
    assert metrics[(sku, d(9, 10))][4] == D("960000.00")
    assert metrics[(sku, d(9, 10))][10] == D("960000.00")  # base_fallback — taxminiy (F22)
    assert metrics[(None, d(10, 6))][0] == D("200000.00")  # bog'lanmagan sotuv tushumi yo'qolmaydi
    assert metrics[(None, d(10, 6))][8] == D(0)  # ...lekin tannarxsiz qism (F15)

    # Takror: navbat bo'sh — hech narsa qilinmaydi; to'liq qayta qurish — farq yo'q, yozuv yo'q.
    assert org.recalc().status == "idle"
    org.run(lambda conn: calc.request_full(conn, org.org_id))
    again = org.recalc()
    assert (again.costs_written, again.costs_deleted) == (0, 0)
    assert org.costs() == costs and org.metrics() == metrics


def test_late_cargo_marks_recalculated_and_cancel_removes(org: Org) -> None:
    _, sku, p1, _ = _two_lots(org)
    s1 = org.sale(sku, d(9, 10), 8)
    s2 = org.sale(sku, d(10, 5), 4)
    org.request(calc.Scope.PURCHASE)
    org.request(calc.Scope.SHOP, org.shop_id)
    org.recalc()

    # 20 kundan keyin kiritilgan bojxona (P1): o'tgan sotuvlar tannarxi qayta hisoblanadi.
    org.component(p1, "customs", 100_000)
    org.request(calc.Scope.PURCHASE, p1)
    later = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    result = org.recalc(later)
    assert result.costs_written == 2
    costs = org.costs()
    assert (
        costs[s1][0] == D("1040000.00") and costs[s1][4] == later and costs[s1][5] == D("960000.00")
    )
    assert costs[s2][0] == D("520000.00") and costs[s2][5] == D("500000.00")
    assert org.metrics()[(sku, d(9, 10))][4] == D("1040000.00")

    # Sotuv bekor bo'ldi (deep sinxron): tannarx qatori o'chadi, keyingi sotuv lotni egallaydi.
    org.sql("UPDATE sale_items SET status = 'CANCELED' WHERE id = %s", [s1])
    org.request(calc.Scope.SHOP, org.shop_id, d(9, 10))
    result = org.recalc(later)
    assert result.costs_deleted == 1
    costs = org.costs()
    assert s1 not in costs and costs[s2][0] == D("520000.00")  # 4 × 130 000 (P1 + bojxona)
    assert org.metrics()[(sku, d(9, 10))][7] == 8


def test_incremental_equals_full_rebuild(org: Org) -> None:
    _, sku, _, p2 = _two_lots(org)
    for i in range(12):
        org.sale(sku, d(9, 2 + 2 * i), 1 + i % 3, "PROCESSING" if i == 11 else "TO_WITHDRAW")
    org.insert(
        "stock_moves",
        item_id=org.sql("SELECT item_id FROM mp_skus WHERE id = %s", [sku])[0][0],
        kind="writeoff",
        qty=2,
        day=d(9, 15),
    )
    org.request(calc.Scope.PURCHASE)
    org.request(calc.Scope.SHOP, org.shop_id)
    org.recalc()
    org.component(p2, "packaging", 50_000)
    org.request(calc.Scope.PURCHASE, p2)
    org.sale(sku, d(10, 20), 3)
    org.request(calc.Scope.SHOP, org.shop_id, d(10, 20))
    org.recalc()

    def strip(costs: dict[uuid.UUID, Any]) -> dict[uuid.UUID, Any]:
        return {k: (v[0], v[1], v[2], v[3], v[6]) for k, v in costs.items()}

    incremental, metrics = strip(org.costs()), org.metrics()
    for table in ("sale_costs", "lots", "daily_sku_metrics"):
        org.sql(f"DELETE FROM {table} WHERE org_id = %s", [org.org_id])
    org.run(lambda conn: calc.request_full(conn, org.org_id))
    org.recalc()
    assert strip(org.costs()) == incremental and org.metrics() == metrics
    # Hisobdan chiqarilgan 2 dona ham lotdan olingan: oxirgi sotuvlar lot yetmagan qismda.
    assert sum(1 for v in incremental.values() if "lot_shortage" in v[2]) >= 1


def test_average_method(org: Org) -> None:
    org.sql("UPDATE orgs SET cost_method = 'average' WHERE id = %s", [org.org_id])
    _, sku, _, _ = _two_lots(org)
    sale = org.sale(sku, d(10, 5), 4)
    org.request(calc.Scope.PURCHASE)
    org.request(calc.Scope.SHOP, org.shop_id)
    org.recalc()
    cogs, unit, _, _, _, _, method = org.costs()[sale]
    assert method == "average" and cogs == D("500000.00") and unit == D("125000.000000")


# --- Kurslar va hisoblab bo'lmaydigan xarid ------------------------------------------------------------


def test_cbu_and_effective_rates_and_errors(org: Org) -> None:
    for day, rate in ((d(10, 2), "12500"), (d(10, 1), "12400")):
        org.sql(
            "INSERT INTO fx_rates (day, currency, source, rate) VALUES (%s, 'USD', 'cbu', %s) "
            "ON CONFLICT DO NOTHING",
            [day, D(rate)],
        )
    item, sku = org.item()
    p = org.purchase(d(10, 10), ordered_on=d(10, 1))
    a = org.line(p, item, 6, unit_price=D("10"), currency="USD")
    b = org.line(p, item, 4, unit_price=D("20"), currency="USD")
    # Tovar: 140 USD, CBU, to'lov 4-oktabr (shanba) → 2-oktabr kursi 12 500.
    org.component(p, "goods", 140, "USD", paid_on=d(10, 4), allocation="value")
    # Kargo: 1 000 CNY kartadan 1 800 000 so'm yechildi → effektiv kurs 1 800; faqat b qatoriga.
    org.component(
        p,
        "cargo",
        1000,
        "CNY",
        rate_mode="effective",
        charged_amount=D(1_800_000),
        charged_currency="UZS",
        targets={"lines": [str(b)]},
    )
    bad = org.purchase(d(10, 10))
    org.line(bad, item, 5)
    org.component(bad, "goods", 100, "CNY")  # CNY CBU kursi bazada yo'q
    org.request(calc.Scope.PURCHASE)
    result = org.recalc()
    assert set(result.errors) == {str(bad)} and "CNY" in result.errors[str(bad)]
    lots = dict(org.sql("SELECT purchase_line_id, total FROM lots WHERE org_id = %s", [org.org_id]))
    assert lots == {a: D("750000.00"), b: D("1000000.00") + D("1800000.00")}
    flags = org.sql("SELECT flags FROM lots WHERE purchase_line_id = %s", [a])[0][0]
    assert flags == ["cbu_rate"]
    assert sku  # SKU sotuvsiz — tovar lotlari tayyor


def test_manual_shares_missing_is_error(org: Org) -> None:
    item, _ = org.item()
    p = org.purchase(d(10, 1))
    org.line(p, item, 2)
    org.component(p, "goods", 1000, allocation="manual", targets={"shares": {}})
    org.request(calc.Scope.PURCHASE, p)
    result = org.recalc()
    assert list(result.errors) == [str(p)]
    assert org.sql("SELECT count(*) FROM lots WHERE org_id = %s", [org.org_id])[0][0] == 0


def test_incomplete_rates_are_errors_and_empty_purchases_skipped(org: Org) -> None:
    item, _ = org.item()
    manual = org.purchase(d(10, 1))
    org.line(manual, item, 2)
    org.component(manual, "goods", 10, "USD", rate_mode="manual")  # kurs kiritilmagan
    effective = org.purchase(d(10, 1))
    org.line(effective, item, 2)
    org.component(effective, "goods", 10, "USD", rate_mode="effective")  # yechilgan summa yo'q
    org.purchase(d(10, 1))  # qatorsiz qoralama
    partial = org.purchase(d(10, 1))
    ok = org.line(partial, item, 3)
    org.line(partial, item, 0, received=0)  # hali kelmagan qator — lot emas
    org.component(partial, "goods", 30_000)
    org.request(calc.Scope.PURCHASE)
    result = org.recalc()
    assert set(result.errors) == {str(manual), str(effective)}
    assert org.sql("SELECT purchase_line_id FROM lots WHERE org_id = %s", [org.org_id]) == [(ok,)]


# --- Reklama va kunlik agregat -------------------------------------------------------------------------


def test_ads_in_daily_metrics(org: Org) -> None:
    _, sku = org.item()
    org.sale(sku, d(10, 5), 1, external_id=9001)
    org.sale(None, d(10, 5), 1, external_id=9002)

    def ad(
        ext: int, amount: int, kind: str = "OUTCOME", item: int | None = None, **kw: Any
    ) -> None:
        org.insert(
            "mp_expenses",
            shop_id=org.shop_id,
            external_id=ext,
            category=kw.pop("category", "advertising"),
            type=kind,
            amount=D(amount),
            item_external_id=item,
            created_on=at(d(10, 5)),
            **kw,
        )

    ad(1, 10_000, item=9001)
    ad(2, 3_000, "INCOME", item=9001)
    ad(3, 4_000)  # bog'lanmagan
    ad(4, 99_000, item=9001, excluded="status")  # bekor — hisobga kirmaydi
    ad(5, 50_000, category="storage")  # reklama emas
    org.request(calc.Scope.METRICS, org.shop_id, d(10, 1))
    org.recalc()
    metrics = org.metrics()
    assert metrics[(sku, d(10, 5))][5] == D("7000.00")
    assert metrics[(None, d(10, 5))][5] == D("4000.00")
    assert org.sql("SELECT count(*) FROM sale_costs WHERE org_id = %s", [org.org_id])[0][0] == 0


# --- Navbat --------------------------------------------------------------------------------------------


def test_queue_merges_requests(org: Org) -> None:
    org.request(calc.Scope.SHOP, org.shop_id, d(10, 5))
    org.request(calc.Scope.SHOP, org.shop_id, d(10, 3))
    org.request(calc.Scope.SHOP, org.shop_id, d(10, 9))
    org.request(calc.Scope.METRICS, org.shop_id, d(10, 9))
    assert org.queue() == [("metrics", org.shop_id, d(10, 9)), ("shop", org.shop_id, d(10, 3))]
    org.request(calc.Scope.SHOP, org.shop_id)
    org.request(calc.Scope.SHOP, org.shop_id, d(10, 1))
    assert org.queue()[1] == ("shop", org.shop_id, None)
    org.request(calc.Scope.ITEM)
    org.request(calc.Scope.ITEM)
    assert [r[0] for r in org.queue()] == ["item", "metrics", "shop"]
    assert org.recalc().requests == 3
    assert org.queue() == []


def test_sync_writes_requests_and_job_runs_calc(db: dict[str, str]) -> None:
    """Sinxron sotuv/xarajat yozsa — shu tranzaksiyada so'rov; akkaunt ishi hisob ishini navbatga qo'yadi."""
    fake = seller()
    app = jobs.build_app(InMemoryConnector())
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        shop = account.shops[A]

        async def main(rt: eng.Runtime) -> list[Any]:
            async with app.open_async():
                await app.configure_task(jobs.ACCOUNT).defer_async(
                    org_id=str(account.org_id), account_id=str(account.account_id)
                )
                await app.run_worker_async(
                    queues=[jobs.QUEUE],
                    wait=False,
                    install_signal_handlers=False,
                    additional_context={"runtime": rt},
                )
                # Ishchi davriy ``tick`` ni ham bajaradi (boshqa akkauntlar ham) — shu tashkilotda bitta ish.
                queued = [
                    j["task_name"]
                    for j in app.connector.jobs.values()
                    if j["status"] == "todo" and j["args"].get("org_id") == str(account.org_id)
                ]
                assert queued == [jobs.CALC]
                assert await jobs.defer_calc(app, account.org_id) is False  # navbatda bitta
                kinds = admin(
                    db,
                    "SELECT kind, ref_id FROM recalc_queue WHERE org_id = %s ORDER BY kind",
                    [account.org_id],
                )
                assert kinds == [("metrics", shop), ("shop", shop)]
                await app.run_worker_async(
                    queues=jobs.QUEUES,
                    wait=False,
                    install_signal_handlers=False,
                    additional_context={"runtime": rt},
                )
                return [j["status"] for j in app.connector.jobs.values()]

        statuses = run(main)
    assert set(statuses) == {"succeeded"}
    assert admin(db, "SELECT count(*) FROM recalc_queue WHERE org_id = %s", [account.org_id]) == [
        (0,)
    ]
    # Soxta sotuvchida SKU'lar tovarga bog'lanmagan: tannarxsiz, lekin tushum kunlik agregatda bor.
    flags = admin(db, "SELECT DISTINCT flags FROM sale_costs WHERE org_id = %s", [account.org_id])
    assert flags == [(["no_item"],)]
    revenue = admin(
        db,
        "SELECT (SELECT sum(revenue) FROM daily_sku_metrics WHERE org_id = %(o)s), "
        "(SELECT sum(sell_price * amount) FROM sale_items WHERE org_id = %(o)s AND status IN ('TO_WITHDRAW', 'PARTIALLY_CANCELLED'))",
        {"o": account.org_id},
    )[0]
    assert revenue[0] == revenue[1] and revenue[0] > 0


def test_nightly_requests_full_rebuild(db: dict[str, str]) -> None:
    app = jobs.build_app(InMemoryConnector())
    with runtime(db, seller()) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])

        async def main(rt: eng.Runtime) -> int:
            async with app.open_async():
                await app.configure_task(jobs.CALC_NIGHTLY).defer_async(timestamp=0)
                await app.run_worker_async(
                    queues=jobs.QUEUES,
                    wait=False,
                    install_signal_handlers=False,
                    additional_context={"runtime": rt},
                )
                return sum(j["task_name"] == jobs.CALC for j in app.connector.jobs.values())

        assert run(main) >= 1
    assert admin(db, "SELECT count(*) FROM recalc_queue WHERE org_id = %s", [account.org_id]) == [
        (0,)
    ]


# --- Tezlik (03 §7) ------------------------------------------------------------------------------------


@pytest.mark.benchmark
def test_benchmark_10k_sales_item(org: Org) -> None:
    """10 000 sotuvli tovar: kech kiritilgan xarajatdan keyin qayta hisob (o'qish + F21 + 10 000 qator yozish +
    kunlik agregat). Dvigatelning o'zi < 1 s (``packages/core``); bazasi bilan — 3 s chegarasi (lokal ≈ 1 s)."""
    item, sku = org.item()
    p = org.purchase(d(1, 1))
    org.line(p, item, 20_000)
    org.component(p, "goods", 2_000_000_000)
    with psycopg.connect(org.db["admin"]) as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO sale_items (org_id, shop_id, external_id, order_id, status, ordered_at, "
            "sell_price, amount, sku_id) VALUES (%s, %s, %s, %s, 'TO_WITHDRAW', %s, 200000, 1, %s)",
            [
                (
                    org.org_id,
                    org.shop_id,
                    100_000 + i,
                    i,
                    at(date(2026, 1 + i % 9, 1 + i % 28)),
                    sku,
                )
                for i in range(10_000)
            ],
        )
    org.request(calc.Scope.PURCHASE)
    org.request(calc.Scope.SHOP, org.shop_id)
    org.recalc()
    org.component(p, "cargo", 20_000_000)
    org.request(calc.Scope.PURCHASE, p)
    start = time.perf_counter()
    result = org.recalc()
    assert time.perf_counter() - start < 3.0
    assert result.costs_written == 10_000

import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from upcore.expenses import ExpenseCategory, classify_expenses
from upcore.metrics import ManualExpense, Period, SaleLine, profit_summary
from upcore.money import Money, total
from upcore.pnl import (
    CellKey,
    ExpenseItem,
    OwnExpense,
    TaxBase,
    TaxRule,
    build_cells,
    compare,
    expense_items,
    pending_profit,
)

D = Decimal
C = ExpenseCategory
OCT = Period(date(2026, 10, 1), date(2026, 10, 31))


def d(n: int) -> date:
    return date(2026, 10, 1) + timedelta(days=n - 1)


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def sale(
    day: int,
    sku: str = "A",
    shop: str = "S1",
    price: int = 100_000,
    qty: int = 1,
    cost: int | None = 40_000,
    status: str = "TO_WITHDRAW",
) -> SaleLine:
    return SaleLine(
        sku,
        d(day),
        status,
        D(price),
        qty,
        D(price * qty // 5),
        D(5_000 * qty),
        unit_cost=None if cost is None else D(cost),
        shop=shop,
    )


def test_single_cell_matches_profit_summary() -> None:
    lines = [sale(3, qty=2), sale(3, price=50_000, cost=None)]
    exp = [ExpenseItem(d(3), "S1", C.STORAGE, uzs(30_000))]
    cells = build_cells(OCT, lines, exp, tax=TaxRule(D(4)))
    s = cells.statement()
    ref = profit_summary(lines, uzs(30_000), uzs(0), uzs(10_000))  # soliq 4% × 250 000
    assert s.revenue == ref.revenue and s.payout == ref.payout and s.cogs == ref.cogs
    assert s.tax == uzs(10_000)
    assert s.net_profit == ref.net_profit
    assert s.coverage == ref.coverage and s.uncovered_share == ref.uncovered_share
    assert s.margin == ref.margin and s.roi == ref.roi
    assert (
        s.uncovered_expenses == ref.uncovered_expenses
        and s.uncovered_payout == ref.uncovered_payout
    )
    assert s.lines == 2 and s.uncovered_lines == 1 and s.units == 3


def test_expense_allocation_rules() -> None:
    lines = [sale(1, "A", price=300_000), sale(1, "B", price=100_000), sale(2, "A", shop="S2")]
    exp = [
        ExpenseItem(d(1), "S1", C.ADVERTISING, uzs(40_000)),  # do'kon → A:B = 3:1
        ExpenseItem(d(1), "S1", C.ADVERTISING, uzs(7_000), sku="B"),  # SKU'ga bog'langan
        ExpenseItem(d(5), "S1", C.STORAGE, uzs(9_000)),  # sotuvsiz kun → taqsimlanmagan
        ExpenseItem(d(1), "S1", C.COMPENSATION, uzs(-4_000)),
        ExpenseItem(date(2026, 11, 1), "S1", C.FINE, uzs(1)),  # davrdan tashqari
    ]
    cells = build_cells(OCT, lines, exp)
    a = cells.items[CellKey(d(1), "S1", "A")]
    b = cells.items[CellKey(d(1), "S1", "B")]
    assert a.uzum_expenses == {C.ADVERTISING: uzs(30_000), C.COMPENSATION: uzs(-3_000)}
    assert b.uzum_expenses == {C.ADVERTISING: uzs(17_000), C.COMPENSATION: uzs(-1_000)}
    loose = cells.items[CellKey(d(5), "S1", None)]
    assert loose.uzum_expenses == {C.STORAGE: uzs(9_000)} and loose.net_profit == uzs(-9_000)
    assert CellKey(d(2), "S2", "A") in cells.items
    assert cells.statement().uzum_total == uzs(52_000)
    # ADR-026: taqsimlangan va to'g'ridan-to'g'ri xarajatlar alohida
    assert a.uzum_allocated == {C.ADVERTISING: uzs(30_000), C.COMPENSATION: uzs(-3_000)}
    assert b.uzum_allocated == {C.ADVERTISING: uzs(10_000), C.COMPENSATION: uzs(-1_000)}
    assert b.allocated_total == uzs(9_000) and b.direct_total == uzs(7_000)
    assert loose.allocated_total == uzs(0) and loose.direct_total == uzs(9_000)
    whole = cells.statement()
    assert whole.allocated_total == uzs(36_000) and whole.direct_total == uzs(16_000)


def test_own_expenses_amortized_and_scoped() -> None:
    lines = [sale(1, "A", "S1"), sale(1, "B", "S2", price=300_000)]
    rent = OwnExpense(ManualExpense(uzs(3_100_000), d(1), d(31)), "ijara")  # kuniga 100 000
    pack = OwnExpense(ManualExpense(uzs(500), d(1), d(1)), "qadoq", shop="S2")
    label = OwnExpense(ManualExpense(uzs(70), d(2), d(2)), "yorliq", shop="S1", sku="A")
    cells = build_cells(OCT, lines, own_expenses=[rent, pack, label])
    day1 = cells.by_day()[d(1)]
    assert day1.own_expenses == {"ijara": uzs(100_000), "qadoq": uzs(500)}
    assert cells.items[CellKey(d(1), "S1", "A")].own_expenses == {"ijara": uzs(25_000)}
    assert cells.items[CellKey(d(1), "S2", "B")].own_expenses == {
        "ijara": uzs(75_000),
        "qadoq": uzs(500),
    }
    assert cells.items[CellKey(d(2), "", None)].own_expenses == {"ijara": uzs(100_000)}
    assert cells.items[CellKey(d(2), "S1", "A")].own_expenses == {"yorliq": uzs(70)}
    assert cells.items[CellKey(d(2), "S1", "A")].own_allocated == {}
    assert cells.items[CellKey(d(1), "S2", "B")].own_allocated == {
        "ijara": uzs(75_000),
        "qadoq": uzs(500),
    }
    assert cells.items[CellKey(d(2), "", None)].own_allocated == {}
    assert cells.statement().own_expenses == {
        "ijara": uzs(3_100_000),
        "qadoq": uzs(500),
        "yorliq": uzs(70),
    }


def test_slices_sum_to_total() -> None:
    lines = [
        sale(1, "A"),
        sale(15, "B", cost=None),
        sale(31, "A", shop="S2", qty=3),
        sale(20, "C", status="PROCESSING"),
    ]
    exp = [
        ExpenseItem(d(15), "S1", C.FINE, uzs(12_345)),
        ExpenseItem(d(31), "S2", C.STORAGE, uzs(1_000)),
    ]
    own = [OwnExpense(ManualExpense(uzs(1_000), d(10), date(2026, 11, 9)), "ish haqi")]
    cells = build_cells(OCT, lines, exp, own, TaxRule(D(1), TaxBase.PAYOUT))
    whole = cells.statement()
    for view in (cells.by_day(), cells.by_shop(), cells.by_sku(), cells.by_month()):
        assert total([s.net_profit for s in view.values()], "UZS") == whole.net_profit
        assert total([s.revenue for s in view.values()], "UZS") == whole.revenue
    # 1 000 so'm 31 kunga (10-oktabr – 9-noyabr), oktabrda 22 kun: 1 000 × 22 / 31
    assert whole.own_expenses == {"ish haqi": uzs("709.68")}
    assert list(cells.by_sku()) == ["A", "B", None]
    assert whole.units == 5  # PROCESSING kirmaydi


def test_rows_and_compare() -> None:
    cur = build_cells(
        OCT, [sale(1), sale(2, cost=None)], [ExpenseItem(d(1), "S1", C.ADVERTISING, uzs(10_000))]
    ).statement()
    prev = build_cells(
        Period(date(2026, 9, 1), date(2026, 9, 30)),
        [SaleLine("A", date(2026, 9, 5), "TO_WITHDRAW", D(80_000), 1, unit_cost=D(1), shop="S1")],
        [ExpenseItem(date(2026, 9, 5), "S1", C.FINE, uzs(500))],
    ).statement()
    codes = [c for c, _ in cur.rows()]
    assert codes == [
        "revenue",
        "commission",
        "logistics",
        "payout",
        "cogs",
        "gross_profit",
        "uzum:advertising",
        "tax",
        "uncovered_payout",
        "uncovered_expenses",
        "net_profit",
    ]
    rows = {r.code: r for r in compare(cur, prev)}
    assert rows["revenue"].current == uzs(200_000) and rows["revenue"].previous == uzs(80_000)
    assert rows["revenue"].diff == uzs(120_000) and rows["revenue"].share_of_revenue == D(1)
    assert rows["uzum:fine"].current == uzs(0) and rows["uzum:fine"].previous == uzs(-500)
    assert rows["net_profit"].current == cur.net_profit
    assert "uncovered_payout" not in dict(prev.rows())


def test_expense_items_adapter() -> None:
    ms = int(datetime(2026, 10, 5, 6, 0, tzinfo=UTC).timestamp() * 1000)
    base = {"dateCreated": ms, "paymentPrice": 1000, "type": "OUTCOME"}
    records = classify_expenses(
        [
            {**base, "id": 1, "code": "Y000120", "externalId": "AD#11-1"},
            {**base, "id": 2, "code": "logistics-volume"},
            {**base, "id": 3, "code": "return-C000003", "type": "INCOME"},
        ]
    )
    items = expense_items(records, "S1", lambda r: {11: "SKU-11"}.get(r.item_id or 0))
    assert items == [
        ExpenseItem(d(5), "S1", C.ADVERTISING, uzs(1000), "SKU-11"),
        ExpenseItem(d(5), "S1", C.COMPENSATION, uzs(-1000), None),
    ]
    assert expense_items(records, "S1")[0].sku is None


def test_pending_profit() -> None:
    window = [sale(1, qty=90), sale(2, qty=10, status="CANCELED")]
    lines = [sale(3, status="PROCESSING"), sale(3), sale(3, status="PROCESSING", cost=None)]
    e = pending_profit(OCT, lines, window)
    assert e.rate == D("0.9") and e.raw == uzs(100_000 - 20_000 - 5_000 - 40_000)
    assert e.amount == uzs(31_500) and e.uncovered_lines == 1
    assert pending_profit(OCT, lines, window[:1], min_units=100).amount is None


# --- Xossalar va tezlik ----------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(1, 31),
            st.sampled_from(["A", "B", "C"]),
            st.sampled_from(["S1", "S2"]),
            st.integers(1, 10**6),
            st.booleans(),
        ),
        max_size=25,
    ),
    st.lists(
        st.tuples(
            st.integers(1, 31),
            st.sampled_from(["S1", "S2"]),
            st.integers(-(10**5), 10**6),
            st.sampled_from([None, "A"]),
        ),
        max_size=10,
    ),
    st.lists(st.tuples(st.integers(1, 31), st.integers(0, 40), st.integers(1, 10**7)), max_size=3),
)
def test_additivity_property(raw_sales: list, raw_exp: list, raw_own: list) -> None:
    lines = [
        sale(dd, sku, shop, price, cost=40_000 if known else None)
        for dd, sku, shop, price, known in raw_sales
    ]
    exp = [ExpenseItem(d(dd), shop, C.OTHER, uzs(a), sku) for dd, shop, a, sku in raw_exp]
    own = [
        OwnExpense(ManualExpense(uzs(a), d(dd), d(dd) + timedelta(days=n)), "x")
        for dd, n, a in raw_own
    ]
    cells = build_cells(OCT, lines, exp, own, TaxRule(D("1.5")))
    whole = cells.statement()
    for view in (cells.by_day(), cells.by_shop(), cells.by_sku()):
        assert total([s.net_profit for s in view.values()], "UZS") == whole.net_profit
    # Hamma xarajat yo yerda ayrilgan, yo tannarxsiz qismda — yo'qolmaydi.
    assert whole.expenses_deducted + whole.uncovered_expenses == whole.overhead
    assert whole.direct_total + whole.allocated_total + whole.tax == whole.overhead
    assert total([s.allocated_total for s in cells.items.values()], "UZS") == whole.allocated_total
    assert whole.uzum_total == total([e.amount for e in exp], "UZS")
    in_oct = total([own_expense_in_oct(o) for o in own], "UZS")
    assert whole.own_total == in_oct


def own_expense_in_oct(o: OwnExpense) -> Money:
    from upcore.metrics import own_expense_in_period

    return own_expense_in_period(o.expense, OCT)


@pytest.mark.benchmark
def test_year_50k_lines_fast() -> None:
    year = Period(date(2026, 1, 1), date(2026, 12, 31))
    lines = [
        SaleLine(
            f"SKU{i % 300}",
            year.start + timedelta(days=i % 365),
            "TO_WITHDRAW",
            D(100_000),
            1,
            D(20_000),
            D(5_000),
            unit_cost=D(40_000) if i % 7 else None,
            shop=f"S{i % 2}",
        )
        for i in range(50_000)
    ]
    exp = [
        ExpenseItem(year.start + timedelta(days=i % 365), f"S{i % 2}", C.ADVERTISING, uzs(10_000))
        for i in range(3_000)
    ]
    own = [OwnExpense(ManualExpense(uzs(12_000_000), year.start, year.end), "ijara")]
    start = time.perf_counter()
    cells = build_cells(year, lines, exp, own, TaxRule(D(1)))
    months = cells.by_month()
    assert time.perf_counter() - start < 5.0
    assert total([m.net_profit for m in months.values()], "UZS") == cells.statement().net_profit

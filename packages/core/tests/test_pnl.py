import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from upcore.expenses import ExpenseCategory, classify_expenses
from upcore.metrics import ManualExpense, Period, SaleLine, own_expense_in_period, profit_summary
from upcore.money import Money, total
from upcore.pnl import (
    CellKey,
    Cells,
    CellSales,
    ExpenseItem,
    OwnExpense,
    TaxBase,
    TaxRule,
    build_cells,
    compare,
    expense_items,
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
    logistics: int | None = None,
    issued: bool = False,
) -> SaleLine:
    return SaleLine(
        sku,
        d(day),
        status,
        D(price),
        qty,
        D(price * qty // 5),
        D(5_000 * qty if logistics is None else logistics),
        unit_cost=None if cost is None else D(cost),
        shop=shop,
        issued=issued,
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
    # F46, F47 (ADR-043): komissiya 50 000 + logistika 15 000 + saqlash 30 000; tushum 250 000.
    assert s.uzum_costs == uzs(95_000) and s.uzum_costs_share == D("0.38")
    assert s.after_uzum == uzs(155_000) == s.payout - s.uzum_total
    assert Cells(OCT, {}).statement().uzum_costs_share is None


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
    assert list(cells.by_sku()) == ["A", "B", "C", None]
    assert whole.units == 6  # ADR-036: Jarayondagi qator ham kiradi
    assert (whole.units_processing, whole.revenue_processing) == (1, uzs(100_000))


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
    # O'zgarish = farq / |oldingi| (ishorali): tushum 80 000 → 200 000 = +150%; jarima −500 → 0 = +100%
    # (xarajat yo'qolishi — yaxshi); oldingi nol bo'lsa yo'q.
    assert rows["revenue"].change == D("1.5")
    assert rows["uzum:fine"].change == D("1")
    assert rows["uzum:advertising"].change is None
    assert "uncovered_payout" not in dict(prev.rows())
    # Oldingi davrda sotuv yo'q (do'kon hali ulanmagan): faqat jarima bo'lsa ham foiz ma'nosiz — ko'rsatilmaydi.
    empty = build_cells(
        Period(date(2026, 9, 1), date(2026, 9, 30)),
        [],
        [ExpenseItem(date(2026, 9, 5), "S1", C.FINE, uzs(500))],
    ).statement()
    assert all(r.change is None for r in compare(cur, empty))


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


def fee_table(shop: str, sku: str) -> Money | None:
    """F40 tarifi (soxta): A — 4 000, B — tarif yo'q, qolgani — do'kon odatiy 6 000."""
    return {"A": uzs(4_000)}.get(sku) or (None if sku == "B" else uzs(6_000))


def test_processing_part_and_cash_split() -> None:
    """ADR-037: kutilayotgan qism — o'z sotuvlari, katak xarajatlarining tushum ulushi, o'z soliq summasi; yakunlangan = jami −
    kutilayotgan; sotuvsiz kun xarajati — yakunlangan qismda."""
    lines = [
        sale(1, "A", price=300_000),  # Yakunlangan
        sale(
            1, "A", price=100_000, status="PROCESSING", issued=True
        ),  # Jarayonda, logistika yozilgan
        sale(2, "A", price=200_000, status="PROCESSING", cost=None, issued=True),  # tannarxsiz
    ]
    exp = [
        ExpenseItem(
            d(1), "S1", C.ADVERTISING, uzs(40_000)
        ),  # A katagida: 3/4 yakunlangan, 1/4 kutilayotgan
        ExpenseItem(d(5), "S1", C.STORAGE, uzs(9_000)),  # sotuvsiz kun — yakunlangan
    ]
    own = [OwnExpense(ManualExpense(uzs(8_000), d(1), d(1)), "qadoq")]
    cells = build_cells(OCT, lines, exp, own, TaxRule(D(1)))
    cell = cells.items[CellKey(d(1), "S1", "A")]
    part = cell.processing
    assert part is not None and part.revenue == uzs(100_000) and part.units == 1
    assert part.uzum_expenses == {C.ADVERTISING: uzs(10_000)} and part.own_expenses == {
        "qadoq": uzs(2_000)
    }
    assert part.tax == uzs(1_000)  # o'z tushumidan (1%)
    # 100 000 − 20 000 − 5 000 − 40 000 − (10 000 + 2 000 + 1 000)
    assert part.net_profit == cell.net_profit_processing == uzs(22_000)
    assert cell.net_profit_done == cell.net_profit - uzs(22_000)
    assert cells.items[CellKey(d(5), "S1", None)].processing is None
    whole = cells.statement()
    assert whole.net_profit_done + whole.net_profit_processing == whole.net_profit
    assert whole.processing is not None and whole.processing.uncovered_lines == 1
    assert (whole.units_done, whole.lines_processing) == (1, 2)
    assert whole.revenue_done == uzs(300_000) and whole.revenue_processing == uzs(300_000)
    # Qatorlar: jami = yakunlangan + kutilayotgan; sotuvsiz kun saqlash xarajati to'liq yakunlangan qismda.
    rows = {r.code: r for r in compare(whole, build_cells(OCT, []).statement())}
    for r in rows.values():
        assert r.done + r.processing == r.current
    assert rows["uzum:storage"].processing == uzs(0) and rows["uzum:storage"].done == uzs(-9_000)
    assert rows["net_profit"].processing == whole.net_profit_processing
    assert rows["revenue"].processing == uzs(300_000)
    # Jarayondagi sotuvsiz hisobot — qism yo'q, yakunlangan = jami.
    done_only = build_cells(OCT, [sale(1)]).statement()
    assert done_only.processing is None and done_only.net_profit_processing == uzs(0)
    assert done_only.net_profit_done == done_only.net_profit and done_only.lines_processing == 0
    assert all(r.processing == uzs(0) for r in compare(done_only, done_only))


def test_expected_logistics_estimate() -> None:
    """F5 (ADR-037): Uzum logistikasini hali yozmagan Jarayondagi qator — F40 × dona (taxminiy); topshirilgan va 0 —
    taxminsiz (ADR-035); tarif noma'lum — taxmin yo'q, qatorlar sanaladi."""
    lines = [
        sale(3, "A", qty=2, status="PROCESSING", logistics=0),  # 2 × 4 000, tannarxi ma'lum
        sale(
            3, "C", status="PROCESSING", logistics=0, cost=None
        ),  # do'kon odatiy 6 000, tannarxsiz
        sale(3, "B", status="PROCESSING", logistics=0),  # tarif yo'q
        sale(
            3, "A", status="PROCESSING", logistics=0, issued=True
        ),  # topshirilgan, 0 — Uzum bergani
        sale(3, "A", logistics=0),  # Yakunlangan, 0 — Uzum bergani
    ]
    plain = build_cells(OCT, lines).statement()
    cells = build_cells(OCT, lines, logistics_fee=fee_table)
    s = cells.statement()
    assert s.logistics_estimated == uzs(8_000 + 6_000) and s.logistics == plain.logistics + uzs(
        14_000
    )
    assert (
        s.logistics_estimated_units,
        s.logistics_estimated_lines,
        s.logistics_missing_lines,
    ) == (3, 2, 1)
    assert s.gross_profit == plain.gross_profit - uzs(8_000)  # tannarxsiz qatorniki F8 ga kirmaydi
    assert s.payout == plain.payout - uzs(14_000)
    assert s.processing is not None and s.processing.logistics_estimated == uzs(14_000)
    assert s.net_profit_processing == plain.net_profit_processing - uzs(8_000)
    assert s.net_profit_done == plain.net_profit_done
    a = cells.items[CellKey(d(3), "S1", "A")]
    assert a.logistics_estimated == uzs(8_000) and a.logistics_estimated_units == 2
    assert cells.items[CellKey(d(3), "S1", "B")].logistics_missing_lines == 1
    # ADR-041: tarif funksiyasi berilmasa — taxmin o'chiq (Uzum logistikani buyurtma paytida yozadi, 0 — bepul).
    assert plain.logistics_estimated == uzs(0) and plain.logistics_missing_lines == 0


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
            st.sampled_from(["TO_WITHDRAW", "PROCESSING", "PROCESSING_DUE"]),
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
        sale(
            dd,
            sku,
            shop,
            price,
            cost=40_000 if known else None,
            status=status.removesuffix("_DUE"),
            logistics=0 if status.endswith("_DUE") else None,
        )
        for dd, sku, shop, price, known, status in raw_sales
    ]
    exp = [ExpenseItem(d(dd), shop, C.OTHER, uzs(a), sku) for dd, shop, a, sku in raw_exp]
    own = [
        OwnExpense(ManualExpense(uzs(a), d(dd), d(dd) + timedelta(days=n)), "x")
        for dd, n, a in raw_own
    ]
    cells = build_cells(OCT, lines, exp, own, TaxRule(D("1.5")), logistics_fee=fee_table)
    whole = cells.statement()
    for key in (lambda k: k.day, lambda k: k.sku):
        groups, combined = cells.by_and_total(key)
        assert combined == whole and groups == cells.by(key)
    assert cells.statements({"all": lambda _: True, "none": lambda _: False}) == {
        "all": whole,
        "none": build_cells(OCT, []).statement(),
    }
    assert cells.within(OCT).statement() == whole
    for view in (cells.by_day(), cells.by_shop(), cells.by_sku()):
        assert total([s.net_profit for s in view.values()], "UZS") == whole.net_profit
    # Hamma xarajat yo yerda ayrilgan, yo tannarxsiz qismda — yo'qolmaydi.
    assert whole.expenses_deducted + whole.uncovered_expenses == whole.overhead
    # ADR-037: yakunlangan + kutilayotgan = jami; kesimlar bo'yicha kutilayotgan qismlar yig'indisi = butun davrniki.
    assert whole.net_profit_done + whole.net_profit_processing == whole.net_profit
    for view in (cells.by_day(), cells.by_shop(), cells.by_sku()):
        parts = [s.net_profit_processing for s in view.values()]
        assert total(parts, "UZS") == whole.net_profit_processing
    assert whole.direct_total + whole.allocated_total + whole.tax == whole.overhead
    assert whole.uzum_direct + whole.uzum_allocated_total == whole.uzum_total
    assert whole.own_direct + whole.own_allocated_total == whole.own_total
    assert whole.uzum_allocated_total + whole.own_allocated_total == whole.allocated_total
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


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(1, 31),
            st.sampled_from(["A", "B"]),
            st.sampled_from(["S1", "S2"]),
            st.integers(1, 10**6),
            st.integers(1, 3),
            st.booleans(),
            st.sampled_from(["TO_WITHDRAW", "PROCESSING", "PROCESSING_DUE", "CANCELED"]),
        ),
        max_size=25,
    ),
    st.lists(
        st.tuples(st.integers(1, 31), st.sampled_from(["S1", "S2"]), st.integers(1, 10**6)),
        max_size=6,
    ),
)
def test_totals_input_matches_lines(raw_sales: list, raw_exp: list) -> None:
    """``daily_sku_metrics`` yig'indilari (``sale_totals``) qatorlar bilan bir xil kataklar beradi (B2.9), Jarayondagi
    qism va kutilayotgan logistika taxmini bilan (ADR-037)."""
    from upcore.metrics import sale_totals

    lines = [
        sale(
            dd,
            sku,
            shop,
            price,
            qty,
            cost=40_000 if known else None,
            status=status.removesuffix("_DUE"),
            logistics=0 if status.endswith("_DUE") else None,
        )
        for dd, sku, shop, price, qty, known, status in raw_sales
    ]
    groups: dict[CellKey, list[SaleLine]] = {}
    for line in lines:
        groups.setdefault(CellKey(line.order_date, line.shop, line.sku), []).append(line)
    totals = [(k, CellSales.of(sale_totals(v))) for k, v in groups.items()]
    exp = [ExpenseItem(d(dd), shop, C.STORAGE, uzs(a)) for dd, shop, a in raw_exp]
    by_lines = build_cells(OCT, lines, exp, tax=TaxRule(D(4)), logistics_fee=fee_table)
    by_totals = build_cells(OCT, [], exp, tax=TaxRule(D(4)), totals=totals, logistics_fee=fee_table)
    assert by_lines.items == by_totals.items


def test_totals_outside_period_ignored() -> None:
    from upcore.metrics import sale_totals

    lines = [sale(3), sale(4, status="CANCELED")]
    totals = [(CellKey(x.order_date, x.shop, x.sku), CellSales.of(sale_totals([x]))) for x in lines]
    cells = build_cells(Period(d(4), d(5)), [], totals=totals)
    assert cells.items == {}  # 3-kun davrdan tashqarida, 4-kunda faqat bekor


def test_unit_economics() -> None:
    from upcore.pnl import unit_economics

    lines = [sale(3, qty=2), sale(3, price=50_000, cost=None)]
    exp = [ExpenseItem(d(3), "S1", C.ADVERTISING, uzs(30_000), sku="A")]
    s = build_cells(OCT, lines, exp).statement()
    assert (s.units, s.covered_units) == (3, 2)
    u = unit_economics(s)
    assert u.avg_price == uzs("83333.33")  # 250 000 / 3
    assert u.commission_share == D("0.2")
    assert u.logistics_per_unit == uzs(5_000)
    assert u.cogs_per_unit == uzs(40_000)
    assert u.ads_per_unit == uzs(10_000) and u.acos == D("0.12")
    assert u.profit_per_unit == total([s.net_profit], "UZS") * D("0.5")
    empty = unit_economics(build_cells(OCT, []).statement())
    assert empty.avg_price is None and empty.cogs_per_unit is None and empty.acos is None


def test_direct_then_allocated_in_same_cell() -> None:
    """SKU'ga bog'langan xarajat avval kelsa ham, keyingi taqsimlangan qism alohida hisoblanadi (ADR-026)."""
    lines = [sale(1, "A")]
    exp = [
        ExpenseItem(d(1), "S1", C.FINE, uzs(5_000), sku="A"),
        ExpenseItem(d(1), "S1", C.FINE, uzs(7_000)),
    ]
    own = [
        OwnExpense(ManualExpense(uzs(3_000), d(1), d(1)), "qadoq", "S1", "A"),
        OwnExpense(ManualExpense(uzs(2_000), d(1), d(1)), "qadoq"),
    ]
    s = build_cells(OCT, lines, exp, own).items[CellKey(d(1), "S1", "A")]
    assert s.uzum_expenses == {C.FINE: uzs(12_000)} and s.uzum_allocated == {C.FINE: uzs(7_000)}
    assert s.own_expenses == {"qadoq": uzs(5_000)} and s.own_allocated == {"qadoq": uzs(2_000)}
    assert s.direct_total == uzs(8_000) and s.allocated_total == uzs(9_000)


def test_tax_rule_money_and_raw() -> None:
    rule = TaxRule(D("1.5"), TaxBase.PAYOUT)
    assert rule.on(uzs(100_000), uzs(70_001)) == uzs("1050.02")
    assert rule.amount_on(D(100_000), D(70_001)) == D("1050.02")


def test_expense_pinned_to_its_sale() -> None:
    """ADR-039 (07 Q10): buyurtmaga bog'liq reklama — o'sha sotuvning katagi va qismiga (tushum ulushida emas);
    taxminiy reklama (F42) — kutilayotgan qismga, "≈" sifatida sanaladi; bekor sotuvniki — yakunlangan qismda."""
    lines = [
        sale(1, "A", price=300_000),  # Yakunlangan
        sale(1, "A", price=100_000, status="PROCESSING", issued=True),
    ]
    exp = [
        ExpenseItem(
            d(1), "S1", C.ADVERTISING, uzs(8_000), sku="A", processing=True
        ),  # topshirilgan sotuvniki
        ExpenseItem(
            d(1), "S1", C.ADVERTISING, uzs(3_000), sku="A", processing=False
        ),  # yakunlangan sotuvniki
        ExpenseItem(
            d(1), "S1", C.ADVERTISING, uzs(5_000), sku="A", processing=True, estimated=True
        ),
        ExpenseItem(d(1), "S1", C.STORAGE, uzs(4_000)),  # katak xarajati — tushum ulushida (1/4)
        ExpenseItem(
            d(2), "S1", C.ADVERTISING, uzs(2_000), sku="B", processing=False
        ),  # bekor sotuv (tushum 0)
    ]
    cells = build_cells(OCT, lines, exp)
    cell = cells.items[CellKey(d(1), "S1", "A")]
    part = cell.processing
    assert part is not None
    assert part.uzum_expenses == {C.ADVERTISING: uzs(13_000), C.STORAGE: uzs(1_000)}
    assert cell.uzum_expenses == {C.ADVERTISING: uzs(16_000), C.STORAGE: uzs(4_000)}
    assert (
        cell.uzum_estimated == {C.ADVERTISING: uzs(5_000)}
        and part.uzum_estimated == cell.uzum_estimated
    )
    # Kutilayotgan: 100 000 − 20 000 − 5 000 − 40 000 − 14 000
    assert cell.net_profit_processing == uzs(21_000)
    canceled = cells.items[CellKey(d(2), "S1", "B")]
    assert canceled.processing is None and canceled.net_profit_done == uzs(-2_000)
    whole = cells.statement()
    assert whole.uzum_estimated_total == uzs(5_000)
    assert whole.net_profit_done + whole.net_profit_processing == whole.net_profit
    rows = {r.code: r for r in compare(whole, build_cells(OCT, []).statement())}
    assert rows["uzum:advertising"].processing == uzs(-13_000)
    assert rows["uzum:advertising"].done == uzs(-5_000)  # 3 000 + bekor sotuvniki 2 000


def test_storage_split_by_weights() -> None:
    """F43 (ADR-039): do'kon saqlash xarajati SKU'larga og'irlikda (qoldiq × narx) — sotuvi yo'q SKU ham oladi,
    to'g'ridan-to'g'ri (taqsimlangan emas); og'irlik yo'q — odatdagidek tushum ulushida."""
    lines = [sale(1, "A", price=100_000), sale(1, "B", price=300_000)]
    exp = [
        ExpenseItem(d(1), "S1", C.STORAGE, uzs(10_000), weights={"A": D(1), "C": D(4), "B": D(0)}),
        ExpenseItem(d(1), "S1", C.STORAGE, uzs(4_000), weights={}),  # og'irliksiz — tushum ulushida
    ]
    by_sku = build_cells(OCT, lines, exp).by_sku()
    assert by_sku["A"].uzum_expenses == {C.STORAGE: uzs(3_000)}  # 2 000 + 1 000
    assert by_sku["B"].uzum_expenses == {C.STORAGE: uzs(3_000)}  # 0 + 3 000
    assert by_sku["C"].uzum_expenses == {C.STORAGE: uzs(8_000)} and by_sku["C"].revenue == uzs(0)
    assert by_sku["C"].uzum_allocated == {} and by_sku["C"].net_profit == uzs(-8_000)
    assert by_sku["A"].uzum_allocated == {C.STORAGE: uzs(1_000)}


def test_own_expense_on_item_skus() -> None:
    """ADR-039: bir necha SKU'li tovarga bog'langan o'z xarajati — faqat shu SKU'larga (tushum ulushida; kunda sotuv
    bo'lmasa teng), do'konning boshqa SKU'lariga emas."""
    lines = [sale(1, "A", price=100_000), sale(1, "B", price=300_000), sale(1, "Z", price=500_000)]
    own = [
        OwnExpense(ManualExpense(uzs(8_000), d(1), d(2)), "kargo", skus=(("S1", "A"), ("S1", "B")))
    ]
    by_sku = build_cells(OCT, lines, own_expenses=own).by_sku()
    assert by_sku["A"].own_expenses == {
        "kargo": uzs(3_000)
    }  # 1-kun: 4 000 × 1/4 + 2-kun: 4 000 / 2
    assert by_sku["B"].own_expenses == {"kargo": uzs(5_000)}  # 3 000 + 2 000
    assert "Z" not in by_sku or by_sku["Z"].own_expenses == {}


def test_idle_expenses_in_done_part() -> None:
    """B4.22: sotuvsiz katak xarajati (sotilmagan tovar saqlashi, sotuvsiz kun) — yakunlangan qismda va alohida
    sanaladi: yakunlangan sotuv yo'q davrda yakunlangan sof foyda shu summaga teng (manfiy)."""
    lines = [sale(1, "A", price=100_000, status="PROCESSING", issued=True)]
    exp = [
        ExpenseItem(
            d(1), "S1", C.STORAGE, uzs(5_000), weights={"A": D(1), "B": D(4)}
        ),  # B — sotilmagan
        ExpenseItem(d(2), "S1", C.FINE, uzs(1_000)),  # sotuvsiz kun
    ]
    s = build_cells(OCT, lines, exp).statement()
    assert s.idle_expenses == uzs(5_000)  # B ning 4 000 + sotuvsiz kun 1 000
    # ADR-040: B saqlashi SKU'da qoladi, qismga — kun tushumining Jarayondagi ulushida (100%); yakunlangan qismda
    # faqat do'konda sotuv bo'lmagan kun xarajati.
    assert s.net_profit_done == uzs(-1_000) and s.units_done == 0
    assert s.processing is not None and s.processing.uzum_expenses[C.STORAGE] == uzs(5_000)


@settings(max_examples=300, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(1, 10),
            st.sampled_from(["A", "B", "C"]),
            st.sampled_from(["S1", "S2"]),
            st.integers(1, 10**6),
            st.integers(1, 3),
            st.sampled_from(["TO_WITHDRAW", "PROCESSING", "CANCELED"]),
        ),
        max_size=20,
    ),
    st.lists(
        st.tuples(
            st.integers(1, 10),
            st.sampled_from(["S1", "S2"]),
            st.sampled_from(list(C)),
            st.integers(-(10**5), 10**6),
            st.sampled_from(["shop", "sku_done", "sku_proc", "estimate", "weights"]),
            st.sampled_from(["A", "B", "C", "D"]),
        ),
        max_size=15,
    ),
    st.lists(
        st.tuples(
            st.integers(1, 10),
            st.integers(0, 5),
            st.integers(1, 10**6),
            st.sampled_from(["org", "shop", "sku", "item"]),
        ),
        max_size=4,
    ),
    st.sampled_from([D(0), D(1), D(4)]),
)
def test_conservation_every_cost_once(
    raw_sales: list, raw_exp: list, raw_own: list, rate: Decimal
) -> None:
    """Hisobning yuragi (B4.24 tekshiruvi): har qanday sotuv va xarajat to'plamida (bog'langan, taxminiy, og'irlikli,
    do'kon, tovar SKU'lari, sotuvsiz kun) sof foyda = tushum − komissiya − logistika − tannarx − davrdagi HAR BIR
    Uzum xarajati bir marta − o'z xarajatlari − soliq (hamma sotuv tannarxli — F15 = 100%). Xarajat ayirish tartibi
    (yalpi foydadan oldin yoki keyin) natijaga ta'sir qilmaydi; yakunlangan + kutilayotgan = jami; kesimlar yig'indisi
    = jami."""
    period = Period(d(1), d(10))
    lines = [
        sale(dd, sku, shop, price, qty, 40_000, status, issued=True)
        for dd, sku, shop, price, qty, status in raw_sales
    ]
    lines = [
        replace(x, amount=0, commission=D(0), logistics=D(0)) if x.status == "CANCELED" else x
        for x in lines
    ]
    exp = []
    for dd, shop, cat, amount, mode, sku in raw_exp:
        money = uzs(amount)
        if mode == "shop":
            exp.append(ExpenseItem(d(dd), shop, cat, money))
        elif mode == "weights":
            exp.append(ExpenseItem(d(dd), shop, cat, money, weights={sku: D(1), "Z": D(2)}))
        else:
            exp.append(
                ExpenseItem(
                    d(dd),
                    shop,
                    cat,
                    money,
                    sku=sku,
                    processing=mode != "sku_done",
                    estimated=mode == "estimate",
                )
            )
    own = []
    for dd, length, amount, scope in raw_own:
        m = ManualExpense(uzs(amount), d(dd), min(d(dd) + timedelta(days=length), d(10)))
        if scope == "org":
            own.append(OwnExpense(m, "ijara"))
        elif scope == "shop":
            own.append(OwnExpense(m, "ijara", "S1"))
        elif scope == "sku":
            own.append(OwnExpense(m, "qadoq", "S2", "B"))
        else:
            own.append(OwnExpense(m, "kargo", skus=(("S1", "A"), ("S2", "C"))))
    cells = build_cells(period, lines, exp, own, TaxRule(rate))
    s = cells.statement()
    live = [x for x in lines if x.status != "CANCELED"]
    revenue = sum((x.revenue for x in live), D(0))
    fees = sum((x.commission + x.logistics for x in live), D(0))
    cogs = sum((x.cogs or D(0) for x in live), D(0))
    uzum = sum((e.amount.amount for e in exp), D(0))
    own_total = sum((own_expense_in_period(o.expense, period).amount for o in own), D(0))
    assert s.revenue.amount == revenue and s.cogs.amount == cogs
    assert s.uzum_total.amount == uzum and s.own_total.amount == own_total
    assert s.net_profit.amount == revenue - fees - cogs - uzum - own_total - s.tax.amount
    # Ayirish tartibi: yalpi foyda (F8) dan keyin xarajatlar = tushumdan hammasini birga ayirish.
    assert s.gross_profit.amount - uzum - own_total - s.tax.amount == s.net_profit.amount
    assert s.net_profit_done + s.net_profit_processing == s.net_profit
    for view in (cells.by_sku(), cells.by_day(), cells.by_shop()):
        assert total([x.net_profit for x in view.values()], "UZS") == s.net_profit

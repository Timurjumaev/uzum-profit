from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.metrics import (
    ManualExpense,
    Period,
    SaleLine,
    StatusGroup,
    breakeven_price,
    business_date,
    cancel_share,
    cogs,
    commission,
    date_from_epoch_ms,
    drr,
    fixed_unit_cost,
    gross_profit,
    in_period,
    logistics,
    own_expense_in_period,
    own_expenses,
    payout,
    payout_mismatches,
    pending_sales,
    period_return_share,
    profit_summary,
    ratio,
    realization_rate,
    return_share,
    revenue,
    sale_totals,
    sku_acos,
    status_group,
    target_margin_price,
    uzum_expenses,
)
from upcore.money import Money, total

D = Decimal
DAY = date(2026, 10, 10)


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def line(
    status: str = "TO_WITHDRAW",
    price: int = 100_000,
    amount: int = 1,
    comm: int = 20_000,
    log: int = 5_000,
    cost: int | None = 40_000,
    sku: str = "A",
    day: date = DAY,
    seller_profit: int | None = None,
    returns: int = 0,
    estimated: bool = False,
) -> SaleLine:
    return SaleLine(
        sku=sku,
        order_date=day,
        status=status,
        sell_price=D(price),
        amount=amount,
        commission=D(comm),
        logistics=D(log),
        seller_profit=None if seller_profit is None else D(seller_profit),
        amount_returns=returns,
        unit_cost=None if cost is None else D(cost),
        estimated=estimated,
    )


# F1 -------------------------------------------------------------------------------------------


def test_business_date_tashkent() -> None:
    # 2026-10-09 19:30 UTC = 2026-10-10 00:30 Toshkent (UTC+5).
    assert business_date(datetime(2026, 10, 9, 19, 30, tzinfo=UTC)) == date(2026, 10, 10)
    assert business_date(datetime(2026, 10, 9, 18, 59, tzinfo=UTC)) == date(2026, 10, 9)
    plus3 = timezone(timedelta(hours=3))
    assert business_date(datetime(2026, 10, 9, 22, 0, tzinfo=plus3)) == date(2026, 10, 10)
    with pytest.raises(ValueError):
        business_date(datetime(2026, 10, 9, 12, 0))


def test_date_from_epoch_ms() -> None:
    ms = int(datetime(2026, 10, 9, 19, 30, tzinfo=UTC).timestamp() * 1000)
    assert date_from_epoch_ms(ms) == date(2026, 10, 10)


def test_period() -> None:
    p = Period(date(2026, 10, 1), date(2026, 10, 31))
    assert date(2026, 10, 1) in p and date(2026, 10, 31) in p
    assert date(2026, 11, 1) not in p and "2026-10-05" not in p
    assert p.days == 31
    assert p.previous() == Period(date(2026, 8, 31), date(2026, 9, 30))
    with pytest.raises(ValueError):
        Period(date(2026, 10, 2), date(2026, 10, 1))
    lines = [line(day=date(2026, 9, 30)), line(day=date(2026, 10, 1))]
    assert [x.order_date for x in in_period(lines, p)] == [date(2026, 10, 1)]


# F2 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "group"),
    [
        ("TO_WITHDRAW", StatusGroup.COMPLETED),
        ("PARTIALLY_CANCELLED", StatusGroup.COMPLETED),
        ("processing", StatusGroup.PROCESSING),
        ("CANCELED", StatusGroup.CANCELED),
        ("RETURNED_SOMETHING_NEW", StatusGroup.UNKNOWN),
    ],
)
def test_status_group(status: str, group: StatusGroup) -> None:
    assert status_group(status) is group


# F3–F8 ----------------------------------------------------------------------------------------

SAMPLE = [
    line(amount=2, comm=40_000, log=10_000),  # yakunlangan, 2 dona
    line("PARTIALLY_CANCELLED", price=50_000, comm=10_000, log=5_000, cost=None),
    line("PROCESSING"),  # ADR-036: Jarayondagi qator ham hisobga kiradi
    line("CANCELED", amount=3),
    line("SOMETHING_NEW"),
]


def test_f3_to_f8() -> None:
    assert revenue(SAMPLE) == uzs(350_000)
    assert commission(SAMPLE) == uzs(70_000)
    assert logistics(SAMPLE) == uzs(20_000)
    assert payout(SAMPLE) == uzs(260_000)
    assert cogs(SAMPLE) == uzs(120_000)  # tannarxsiz qator kirmaydi
    assert gross_profit(SAMPLE) == uzs(105_000)  # (300 000 − 60 000 − 15 000) − 120 000
    # Bekor va noma'lum holat hech qaysi hisobga kirmaydi.
    assert revenue([line("CANCELED"), line("SOMETHING_NEW")]).is_zero()


def test_payout_mismatches() -> None:
    ok = line(seller_profit=75_000)
    off_by_one = line(seller_profit=75_001)
    bad = line(seller_profit=74_000)
    assert payout_mismatches([ok, off_by_one, bad, line()]) == [bad]


def test_sale_totals() -> None:
    lines = [
        line(amount=2, comm=40_000, log=10_000, returns=1),
        line(cost=None, price=50_000, comm=10_000, log=5_000),
        line(estimated=True, cost=30_000),
        line("PROCESSING"),
        line("CANCELED", amount=3),
    ]
    t = sale_totals(lines)
    assert t.revenue == uzs(450_000) and t.units == 5  # Yakunlangan 4 + Jarayonda 1 (ADR-036)
    assert (t.units_processing, t.revenue_processing) == (1, uzs(100_000))
    assert (t.commission, t.logistics) == (uzs(90_000), uzs(25_000))
    assert t.cogs == uzs(150_000) and t.cogs_estimated == uzs(30_000)
    assert t.revenue_costed == uzs(400_000) and t.payout_costed == uzs(400_000 - 80_000 - 20_000)
    assert (t.returns, t.canceled) == (1, 3)  # F17/F18 — faqat Yakunlangan va Bekor
    assert t.payout_costed - t.cogs == gross_profit(lines)  # F8


@given(st.lists(st.tuples(st.integers(1, 5), st.integers(0, 3)), max_size=12))
def test_sale_totals_additive(rows: list[tuple[int, int]]) -> None:
    lines = [line(amount=a, day=DAY + timedelta(days=d)) for a, d in rows]
    whole = sale_totals(lines)
    parts = [
        sale_totals([x for x in lines if x.order_date == DAY + timedelta(days=d)]) for d in range(4)
    ]
    assert total([p.revenue for p in parts], "UZS") == whole.revenue == revenue(lines)
    assert total([p.cogs for p in parts], "UZS") == whole.cogs == cogs(lines)
    assert sum(p.units for p in parts) == whole.units


# F9–F10 ---------------------------------------------------------------------------------------


def test_uzum_expenses() -> None:
    assert uzum_expenses([uzs(30_000), uzs(5_000)], [uzs(2_000)]) == uzs(33_000)
    assert uzum_expenses([]) == uzs(0)


def test_own_expense_amortization() -> None:
    rent = ManualExpense(uzs(3_100_000), date(2026, 10, 1), date(2026, 10, 31))
    assert own_expense_in_period(rent, Period(date(2026, 10, 1), date(2026, 10, 10))) == uzs(
        1_000_000
    )
    assert own_expense_in_period(rent, Period(date(2026, 11, 1), date(2026, 11, 5))) == uzs(0)
    one_day = ManualExpense(uzs(500), DAY, DAY)
    assert own_expenses([rent, one_day], Period(DAY, DAY)) == uzs(100_500)
    with pytest.raises(ValueError):
        ManualExpense(uzs(1), DAY, DAY - timedelta(days=1))


def test_own_expense_months_sum_exactly() -> None:
    # 1 000 so'm 7 kunga: kunlik 142,857… — kunlar yig'indisi tiyinigacha 1 000.
    e = ManualExpense(uzs(1000), date(2026, 10, 1), date(2026, 10, 7))
    days = [
        own_expense_in_period(e, Period(d, d)) for d in (date(2026, 10, i) for i in range(1, 8))
    ]
    assert total(days, "UZS") == uzs(1000)


@given(
    st.integers(min_value=1, max_value=10**9),
    st.integers(min_value=1, max_value=400),
    st.lists(st.integers(min_value=1, max_value=60), min_size=1, max_size=20),
)
def test_own_expense_consecutive_periods_property(
    amount: int, length: int, cuts: list[int]
) -> None:
    start = date(2026, 1, 1)
    e = ManualExpense(uzs(amount), start, start + timedelta(days=length - 1))
    parts, cursor = [], start - timedelta(days=5)
    for c in [*cuts, 1000]:
        end = cursor + timedelta(days=c - 1)
        parts.append(own_expense_in_period(e, Period(cursor, end)))
        cursor = end + timedelta(days=1)
        if cursor > e.end:
            break
    assert total(parts, "UZS") == e.amount


# F12–F15 --------------------------------------------------------------------------------------


def test_profit_summary_full_coverage() -> None:
    s = profit_summary(
        [line(amount=2, comm=40_000, log=10_000)], uzs(20_000), uzs(10_000), uzs(2_000)
    )
    assert s.revenue == uzs(200_000) and s.payout == uzs(150_000) and s.cogs == uzs(80_000)
    assert s.coverage == D(1) and s.uncovered_share == D(0)
    assert s.net_profit == uzs(150_000 - 80_000 - 32_000)
    assert s.uncovered_lines == 0 and s.uncovered_expenses == uzs(0)
    assert s.margin == D("0.19")  # 38 000 / 200 000
    assert s.roi == D("0.475")  # 38 000 / 80 000


def test_profit_summary_partial_coverage() -> None:
    lines = [
        line(price=300_000, comm=0, log=0, cost=100_000),
        line(price=100_000, comm=0, log=0, cost=None),
    ]
    s = profit_summary(lines, uzs(40_000), uzs(0), uzs(0))
    assert s.coverage == D("0.75")
    assert s.expenses_deducted == uzs(30_000)  # 40 000 × 75%
    assert s.uncovered_expenses == uzs(10_000)
    assert s.net_profit == uzs(300_000 - 100_000 - 30_000)
    assert s.uncovered_revenue == uzs(100_000) and s.uncovered_payout == uzs(100_000)
    assert s.uncovered_lines == 1
    assert s.margin == ratio(170_000, 300_000)  # F13: maxraj — ma'lum qism tushumi (ADR-024)
    assert s.uncovered_share == D("0.25")


def test_profit_summary_no_sales() -> None:
    s = profit_summary([line("CANCELED")], uzs(5_000), uzs(1_000), uzs(0))
    assert s.coverage == D(1)
    assert s.net_profit == uzs(-6_000)
    assert s.margin is None and s.roi is None and s.uncovered_share == D(0)


def test_profit_summary_nothing_covered() -> None:
    s = profit_summary([line(cost=None)], uzs(1_000), uzs(0), uzs(0))
    assert s.coverage == D(0) and s.uncovered_share == D(1)
    assert s.margin is None  # tannarxi ma'lum tushum yo'q
    assert s.net_profit == uzs(0) and s.uncovered_expenses == uzs(1_000)


@given(
    st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=10**7),
            st.integers(min_value=1, max_value=50),
            st.one_of(st.none(), st.integers(min_value=0, max_value=10**7)),
        ),
        max_size=30,
    ),
    st.integers(min_value=0, max_value=10**8),
)
def test_profit_summary_reconciles(rows: list[tuple[int, int, int | None]], overhead: int) -> None:
    lines = [line(price=p, amount=a, comm=p * a // 10, log=1000, cost=c) for p, a, c in rows]
    s = profit_summary(lines, uzs(overhead), uzs(0), uzs(0))
    # Ayrilgan + tannarxsiz qism xarajatlari = to'liq xarajat; qamrov 0..1.
    assert s.expenses_deducted + s.uncovered_expenses == uzs(overhead)
    assert D(0) <= s.coverage <= D(1)
    assert s.net_profit + s.uncovered_payout - s.uncovered_expenses == s.payout - s.cogs - uzs(
        overhead
    )


# F16–F18 --------------------------------------------------------------------------------------


def test_realization_rate() -> None:
    window = [line(amount=45), line("CANCELED", amount=5), line("PROCESSING", amount=100)]
    assert realization_rate(window) == D("0.9")
    assert realization_rate(window[:1], min_units=50) is None
    assert realization_rate(window, min_units=51) is None


def test_pending_sales() -> None:
    pending = [
        line("PROCESSING", amount=2, comm=40_000, log=10_000),
        line("PROCESSING", cost=None),
        line(),
    ]
    e = pending_sales(pending, D("0.9"))
    assert e.units == 3 and e.revenue == uzs(300_000)
    assert e.profit == uzs(70_000)  # R summaga ko'paytirilmaydi (ADR-036) — faqat fakt
    assert e.rate == D("0.9") and e.uncovered_lines == 1
    assert pending_sales(pending, None).rate is None


def test_cancel_and_return_share() -> None:
    lines = [
        line(amount=8, returns=1),
        line("CANCELED", amount=2),
        line("PROCESSING", amount=5, returns=1),
    ]
    assert cancel_share(lines) == D("0.2")
    assert cancel_share([]) is None
    # Qaytgan — faqat Yakunlangan qatorlarnikidan: 1 / (8 + 1); Jarayondagi qator hisobga kirmaydi.
    assert period_return_share(lines) == D("0.111111")
    assert return_share(sold=95, returned=5) == D("0.05")
    assert return_share(0, 0) is None


def test_real_canceled_line_shape() -> None:
    """B2.11 (Temurning real ma'lumoti, 905 ta CANCELED qator): Uzum bekor qatorda ``amount`` = 0, ``commission``,
    ``logisticDeliveryFee``, ``sellerProfit`` = 0 beradi, bekor qilingan dona ``amountReturns`` da. Bekor dona F17 va
    F16 ga kiradi, F18 (qaytish) ga kirmaydi."""
    real = SaleLine(
        "A", date(2026, 10, 1), "CANCELED", D(92_000), 0, D(0), D(0), D(0), amount_returns=2
    )
    done = SaleLine("A", date(2026, 10, 1), "TO_WITHDRAW", D(92_000), 2, D(20_000), D(5_000))
    lines = [real, done]
    assert real.revenue == 0 and real.payout == 0
    assert cancel_share(lines) == D("0.5")  # 2 / (2 + 2)
    assert period_return_share(lines) == 0
    t = sale_totals(lines)
    assert (t.units, t.canceled, t.returns) == (2, 2, 0)
    assert payout_mismatches([real]) == []


# F19 ------------------------------------------------------------------------------------------


def test_drr() -> None:
    assert drr(uzs(15_000), uzs(100_000)) == D("0.15")
    assert drr(uzs(1), uzs(0)) is None


def test_sku_acos_distributes_unlinked_by_revenue() -> None:
    rows, rest = sku_acos(
        {"A": uzs(300_000), "B": uzs(100_000)},
        {"A": uzs(10_000), "C": uzs(5_000)},
        uzs(20_000),
    )
    assert rest == uzs(0)
    assert rows["A"].allocated == uzs(15_000) and rows["A"].total == uzs(25_000)
    assert rows["A"].acos == ratio(25_000, 300_000)
    assert rows["B"].allocated == uzs(5_000) and rows["B"].acos == D("0.05")
    assert rows["C"].allocated == uzs(0) and rows["C"].acos is None  # tushumsiz SKU
    assert total([r.total for r in rows.values()], "UZS") == uzs(35_000)


def test_sku_acos_without_distribution() -> None:
    rows, rest = sku_acos({"A": uzs(100)}, {}, uzs(50), distribute=False)
    assert rest == uzs(50) and rows["A"].allocated == uzs(0) and rows["A"].acos == D(0)
    rows, rest = sku_acos({"A": uzs(0)}, {}, uzs(50))
    assert rest == uzs(50)
    rows, rest = sku_acos({}, {}, uzs(50))
    assert rows == {} and rest == uzs(50)


# F35–F36 --------------------------------------------------------------------------------------


def test_breakeven_and_target_price() -> None:
    fixed = fixed_unit_cost(uzs(40_000), uzs(5_250), uzs(750))
    assert fixed == uzs(46_000)
    # ulush = 20 + 4 + 6 = 30% → 46 000 / 0,7
    assert breakeven_price(fixed, 20, 4, 6) == uzs("65714.29")
    assert target_margin_price(fixed, 10, 20, 4, 6) == uzs("76666.67")
    assert breakeven_price(fixed, 60, 25, 15) is None
    assert target_margin_price(fixed, 50, 50) is None


@given(
    st.integers(min_value=1, max_value=10**7),
    st.decimals(min_value=0, max_value=99, places=2),
)
def test_breakeven_price_covers_share(fixed_amount: int, share: Decimal) -> None:
    price = breakeven_price(uzs(fixed_amount), share)
    assert price is not None
    # narx − ulush = qat'iy xarajat (yaxlitlash 1 tiyingacha)
    leftover = price.amount * (1 - share / 100)
    assert abs(leftover - fixed_amount) <= D("0.01")


# --- B2.9: o'qish API'lari uchun yordamchilar ------------------------------------------------


def test_statuses_by_group() -> None:
    from upcore.metrics import statuses

    assert statuses(StatusGroup.COMPLETED) == {"TO_WITHDRAW", "PARTIALLY_CANCELLED"}
    assert statuses(StatusGroup.PROCESSING) == {"PROCESSING"}
    assert statuses(StatusGroup.UNKNOWN) == frozenset()


def test_sale_totals_counts_lines() -> None:
    from upcore.metrics import sale_totals

    t = sale_totals(
        [
            SaleLine("A", date(2026, 10, 1), "TO_WITHDRAW", Decimal(100), 2, unit_cost=Decimal(1)),
            SaleLine("A", date(2026, 10, 1), "TO_WITHDRAW", Decimal(100), 1),
            SaleLine("A", date(2026, 10, 1), "CANCELED", Decimal(100), 1),
        ]
    )
    assert (t.lines, t.uncovered_lines, t.units, t.units_costed, t.canceled) == (2, 1, 3, 2, 1)


def test_unit_rates_match_line_rates() -> None:
    from upcore.metrics import cancel_rate, realization_rate_units

    lines = [
        SaleLine("A", date(2026, 10, 1), "TO_WITHDRAW", Decimal(1), 30),
        SaleLine("A", date(2026, 10, 1), "CANCELED", Decimal(1), 30),
    ]
    assert cancel_rate(30, 30) == cancel_share(lines) == Decimal("0.5")
    assert realization_rate_units(30, 30) == realization_rate(lines) == Decimal("0.5")
    assert realization_rate_units(30, 19) is None  # 49 < 50
    assert cancel_rate(0, 0) is None


def test_run_rate() -> None:
    from upcore.metrics import run_rate

    assert run_rate(Decimal("1000000.00"), 10, 31) == Decimal("3100000.00")
    assert run_rate(7, 3, 31) == Decimal("72.33")
    assert run_rate(1, 0, 31) is None


def test_profit_label() -> None:
    from upcore.metrics import ProfitLabel, profit_label

    m = Money.of
    assert profit_label(m(-1, "UZS"), Decimal("-0.1")) is ProfitLabel.LOSS
    assert profit_label(m(-1, "UZS"), None) is ProfitLabel.LOSS  # sotuvsiz reklama
    assert profit_label(m(0, "UZS"), None) is ProfitLabel.NO_DATA
    assert profit_label(m(10, "UZS"), Decimal("0.049")) is ProfitLabel.BORDERLINE
    assert profit_label(m(10, "UZS"), Decimal("0.05")) is ProfitLabel.PROFITABLE


def test_line_gross_profit() -> None:
    line = SaleLine(
        "A", date(2026, 10, 1), "TO_WITHDRAW", Decimal(100), 2, Decimal(20), Decimal(10)
    )
    assert line.gross_profit is None
    costed = SaleLine(
        "A",
        date(2026, 10, 1),
        "TO_WITHDRAW",
        Decimal(100),
        2,
        Decimal(20),
        Decimal(10),
        unit_cost=Decimal(50),
    )
    assert costed.gross_profit == Decimal(70)  # 200 − 20 − 10 − 100


def test_late_cancel_share() -> None:
    """F17 qismi: topshirilgandan keyin bekor ulushi (Bekor dona ichida)."""
    from upcore.metrics import late_cancel_share

    assert late_cancel_share(40, 10) == Decimal("0.25")
    assert late_cancel_share(5, 5) == Decimal("1")
    assert late_cancel_share(0, 0) is None

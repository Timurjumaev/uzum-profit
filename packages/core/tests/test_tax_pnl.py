"""F11 (ADR-058) hisob varag'ida: bir necha foizli qator, qat'iy qator (F10 mexanizmi bilan) va "Soliq" ostidagi qatorlar."""

from datetime import date
from decimal import Decimal

from upcore.metrics import Period, SaleLine
from upcore.money import Money
from upcore.pnl import TaxBase, TaxRule, build_cells
from upcore.tax import (
    SEED_AMOUNTS,
    LineKind,
    TaxLine,
    TaxProfile,
    TaxRegime,
    amount_on,
    daily_rules,
    fixed_expenses,
)

D = Decimal
OCT = Period(date(2026, 10, 1), date(2026, 10, 31))

PERCENT = TaxLine("Aylanmadan soliq", LineKind.PERCENT, rate_pct=D(1))
PAYOUT = TaxLine("Qo'shimcha", LineKind.PERCENT, rate_pct=D(2), base=TaxBase.PAYOUT)
SOCIAL = TaxLine("Ijtimoiy soliq", LineKind.FIXED, bhm_count=D(1))


def bhm(day: date) -> D | None:
    return amount_on(SEED_AMOUNTS, "bhm", day)


def sale(day: int, price: int = 100_000, qty: int = 1) -> SaleLine:
    return SaleLine(
        "A",
        date(2026, 10, day),
        "TO_WITHDRAW",
        D(price),
        qty,
        D(price * qty // 5),
        D(5_000 * qty),
        unit_cost=D(40_000),
        shop="S1",
    )


LINES = [sale(1), sale(2, qty=2), sale(10), sale(10, price=250_000), sale(25, qty=3), sale(31)]


def stmt(profiles: list[TaxProfile] | None, with_fixed: bool = True):  # type: ignore[no-untyped-def]
    own = fixed_expenses(profiles, bhm, OCT.start, OCT.end)[0] if profiles and with_fixed else []
    tax = daily_rules(profiles) if profiles else None
    return build_cells(OCT, LINES, [], own, tax=tax).statement()


def test_legacy_profile_equals_single_rule() -> None:
    legacy = [TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, D(4))]
    ref = build_cells(OCT, LINES, [], tax=TaxRule(D(4))).statement()
    s = stmt(legacy)
    assert s.tax == ref.tax and s.net_profit == ref.net_profit and s.tax != Money.zero("UZS")
    assert not [
        code for code, _ in s.rows() if code.startswith("tax:")
    ]  # bitta qator — tarqatma yo'q


def test_two_percent_lines_sum_and_breakdown() -> None:
    p = [TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(PERCENT, PAYOUT))]
    one = build_cells(OCT, LINES, [], tax=TaxRule(D(1))).statement()
    two = build_cells(OCT, LINES, [], tax=TaxRule(D(2), TaxBase.PAYOUT)).statement()
    base = build_cells(OCT, LINES, []).statement()
    s = stmt(p, with_fixed=False)
    assert s.tax_lines == {"Aylanmadan soliq": one.tax, "Qo'shimcha": two.tax}
    assert s.tax == one.tax + two.tax
    assert s.net_profit == base.net_profit - s.tax  # hamma sotuv tannarxli: qamrov 100%
    codes = [code for code, _ in s.rows()]
    assert codes[codes.index("tax") + 1 : codes.index("tax") + 3] == [
        "tax:Aylanmadan soliq",
        "tax:Qo'shimcha",
    ]
    rows = dict(s.rows())
    assert rows["tax"] == -s.tax and rows["tax:Qo'shimcha"] == -two.tax


def test_fixed_line_goes_through_own_expense_but_shows_as_tax() -> None:
    p = [TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(PERCENT, SOCIAL))]
    base = build_cells(OCT, LINES, []).statement()
    percent_only = build_cells(OCT, LINES, [], tax=TaxRule(D(1))).statement()
    s = stmt(p)
    assert s.tax_lines["Ijtimoiy soliq"] == Money.of(440_000, "UZS")  # oktabr: 1 × BHM, aniq
    assert s.tax_lines["Aylanmadan soliq"] == percent_only.tax
    assert s.tax == percent_only.tax + Money.of(440_000, "UZS")
    assert "tax:Ijtimoiy soliq" not in s.own_expenses and s.own_total == base.own_total
    assert s.net_profit == base.net_profit - s.tax
    assert s.overhead == base.overhead + s.tax
    assert s.direct_total == base.direct_total  # soliq to'g'ridan-to'g'ri xarajat emas


def test_fixed_tax_accrues_without_sales_and_columns_sum() -> None:
    p = [TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(SOCIAL,))]
    own = fixed_expenses(p, bhm, OCT.start, OCT.end)[0]
    cells = build_cells(OCT, [sale(5)], [], own, tax=daily_rules(p))
    whole = cells.statement()
    assert whole.tax_lines == {"Ijtimoiy soliq": Money.of(440_000, "UZS")}
    groups, total = cells.by_and_total(lambda k: k.day)
    assert sum((g.tax for g in groups.values()), Money.zero("UZS")) == total.tax == whole.tax
    # Sotuv bo'lmagan kunlardagi qism ham hisobda (tashkilot darajasida), bitta kun oralig'i kam bo'lmaydi.
    assert len(groups) == 31


def test_fixed_expenses_missing_bhm_flag() -> None:
    p = [TaxProfile(date(2025, 1, 1), TaxRegime.TURNOVER, lines=(SOCIAL,))]
    items, missing = fixed_expenses(p, bhm, date(2025, 7, 29), date(2025, 8, 2))
    assert missing is True  # 29–31 iyul: BHM noma'lum
    assert len(items) == 2  # 1–2 avgust: BHM 412 000
    items, missing = fixed_expenses(p, bhm, date(2026, 10, 1), date(2026, 10, 3))
    assert missing is False and len(items) == 3


def test_daily_rules_follow_profile_dates() -> None:
    p = [
        TaxProfile(date(2026, 1, 1), TaxRegime.TURNOVER, lines=(PERCENT,)),
        TaxProfile(date(2026, 10, 16), TaxRegime.TURNOVER, lines=(PERCENT, PAYOUT)),
    ]
    rules = daily_rules(p)
    assert [name for name, _ in rules(date(2026, 10, 15))] == ["Aylanmadan soliq"]
    assert [name for name, _ in rules(date(2026, 10, 16))] == ["Aylanmadan soliq", "Qo'shimcha"]
    assert rules(date(2025, 12, 31)) == ()
    # Aralash davr: har kun o'z profili bo'yicha.
    s = build_cells(OCT, LINES, [], tax=rules).statement()
    assert set(s.tax_lines) == {"Aylanmadan soliq", "Qo'shimcha"}
    assert s.tax == sum(s.tax_lines.values(), Money.zero("UZS"))

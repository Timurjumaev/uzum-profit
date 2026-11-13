import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from upcore.fx import FxRate, RateSource, effective_fx_rate, manual_rate
from upcore.money import Currency, Money, total
from upcore.purchasing import (
    DATED_STAGES,
    INFO_FLAGS,
    SHIPMENT_KINDS,
    AllocationBase,
    ComponentKind,
    CostComponent,
    Flag,
    LotCost,
    Purchase,
    PurchaseError,
    PurchaseLine,
    Stage,
    SupplyState,
    average_unit_cost,
    box_shares,
    compute_lots,
    compute_shipment_lots,
    current_stage,
    default_base,
    purchase_total,
    residual_goods,
    split_by_purchase,
    stage_days,
    supply_path,
    supply_state,
    timeline,
    transit_days,
)

D = Decimal
K = ComponentKind
B = AllocationBase
DAY = date(2026, 9, 1)
CNY = FxRate(DAY, Currency.CNY, D("1790"), RateSource.MANUAL)
USD = FxRate(DAY, Currency.USD, D("12650"), RateSource.MANUAL)


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def by_id(lots: list[LotCost]) -> dict[str, LotCost]:
    return {lot.line_id: lot for lot in lots}


def test_shipment_kinds_exclude_purchase_level_costs() -> None:
    """ADR-049: tovar, Xitoy ichki yetkazish va agent komissiyasi har xaridniki; kargoga qolganlari yoziladi."""
    purchase_level = {ComponentKind.GOODS, ComponentKind.CN_DELIVERY, ComponentKind.AGENT_FEE}
    assert not (SHIPMENT_KINDS & purchase_level)
    assert SHIPMENT_KINDS | purchase_level == set(
        ComponentKind
    )  # yangi tur qo'shilsa — qaysi tomonga tegishli ekani hal qilinadi


def test_goods_cargo_extras_basic() -> None:
    lines = (
        PurchaseLine("a", 100, 100, unit_weight=D("0.2")),
        PurchaseLine("b", 50, 50, unit_weight=D("0.6")),
    )
    p = Purchase(
        "p1",
        lines,
        (
            CostComponent(K.GOODS, Money.of(1500, "CNY"), CNY),  # dona bo'yicha
            CostComponent(K.CARGO, Money.of(100, "USD"), USD, B.WEIGHT),  # 20 kg / 30 kg
            CostComponent(K.PACKAGING, uzs(150_000)),
        ),
        received_date=date(2026, 9, 20),
    )
    lots = by_id(compute_lots(p))
    a, b = lots["a"], lots["b"]
    assert a.breakdown[K.GOODS] == uzs(1_790_000) and b.breakdown[K.GOODS] == uzs(895_000)
    assert a.breakdown[K.CARGO] == uzs(506_000) and b.breakdown[K.CARGO] == uzs(759_000)
    assert a.breakdown[K.PACKAGING] == uzs(100_000) and b.breakdown[K.PACKAGING] == uzs(50_000)
    assert a.unit_cost == uzs(23_960) and b.unit_cost == uzs(34_080)
    assert a.flags == frozenset() and not a.estimated
    assert purchase_total(p) == a.total + b.total == uzs(4_100_000)
    assert average_unit_cost(list(lots.values())) == uzs("27333.33")
    assert average_unit_cost([]) is None
    assert p.ready_date == date(2026, 9, 20)


def test_flags_cargo_missing_not_received_cbu() -> None:
    cbu = FxRate(DAY, Currency.CNY, D("1790"))
    p = Purchase(
        "p", (PurchaseLine("a", 10),), (CostComponent(K.GOODS, Money.of(100, "CNY"), cbu),)
    )
    (lot,) = compute_lots(p)
    assert lot.flags == {Flag.CARGO_MISSING, Flag.NOT_RECEIVED, Flag.CBU_RATE}
    assert lot.estimated and lot.qty == 10
    assert p.ready_date is None  # yo'lda


def test_cbu_rate_alone_is_not_estimated_and_later_stage_makes_ready() -> None:
    # ADR-057 Q6 (audit K8, K9): Markaziy bank kursi — izoh, taxmin emas; qabul belgilanmagan, lekin "Uzumga yuborildi"
    # sanasi bor xarid — tovar qo'lda bo'lgan, "yo'lda" emas.
    cbu = FxRate(DAY, Currency.CNY, D("1790"))
    p = Purchase(
        "p",
        (PurchaseLine("a", 10, 10),),
        (
            CostComponent(K.GOODS, Money.of(100, "CNY"), cbu),
            CostComponent(K.CARGO, uzs(10_000)),
        ),
        later_date=date(2026, 9, 25),
    )
    (lot,) = compute_lots(p)
    assert lot.flags == {Flag.CBU_RATE} and not lot.estimated
    assert p.ready_date == date(2026, 9, 25)
    assert Purchase("q", (), received_date=date(2026, 9, 1), later_date=DAY).ready_date == date(
        2026, 9, 1
    )  # qabul sanasi ustun


def test_market_rate_is_flagged_not_cbu() -> None:
    """Zaxira bozor kursi (ADR-045) lotda `market_rate` belgisi bilan — rasmiy CBU deb ko'rsatilmaydi."""
    market = FxRate(DAY, Currency.CNY, D("1650"), RateSource.MARKET)
    p = Purchase(
        "p", (PurchaseLine("a", 10),), (CostComponent(K.GOODS, Money.of(100, "CNY"), market),)
    )
    (lot,) = compute_lots(p)
    assert Flag.MARKET_RATE in lot.flags and Flag.CBU_RATE not in lot.flags and lot.estimated


def test_partial_receipt_uses_received_qty() -> None:
    p = Purchase(
        "p",
        (PurchaseLine("a", 100, 80), PurchaseLine("b", 20, 0)),
        (CostComponent(K.GOODS, uzs(800_000)), CostComponent(K.CARGO, uzs(0))),
    )
    lots = by_id(compute_lots(p))
    assert lots["a"].unit_cost == uzs(10_000) and lots["a"].total == uzs(800_000)
    assert lots["b"].unit_cost is None and lots["b"].total == uzs(0)
    assert lots["a"].flags == frozenset()


def test_weight_missing_falls_back_to_units() -> None:
    p = Purchase(
        "p",
        (PurchaseLine("a", 1, 1, unit_weight=D(1)), PurchaseLine("b", 3, 3)),
        (CostComponent(K.CARGO, uzs(400), base=B.WEIGHT),),
    )
    lots = by_id(compute_lots(p))
    assert lots["a"].total == uzs(100) and lots["b"].total == uzs(300)
    assert Flag.BASE_FALLBACK in lots["a"].flags


def test_volume_value_manual_and_line_targets() -> None:
    lines = (
        PurchaseLine("a", 10, 10, Money.of(5, "CNY"), unit_volume=D("0.01")),
        PurchaseLine("b", 10, 10, Money.of(15, "CNY"), unit_volume=D("0.03")),
        PurchaseLine("c", 10, 10),
    )
    p = Purchase(
        "p",
        lines,
        (
            CostComponent(K.CARGO, uzs(1000), base=B.VOLUME, line_ids=("a", "b")),
            CostComponent(K.CUSTOMS, uzs(2000), base=B.VALUE, line_ids=("a", "b")),
            CostComponent(
                K.LABELING, uzs(90), base=B.MANUAL, manual_shares={"a": D(1), "b": D(1), "c": D(1)}
            ),
        ),
        goods_rate=CNY,
    )
    lots = by_id(compute_lots(p))
    assert lots["a"].breakdown[K.CARGO] == uzs(250) and lots["b"].breakdown[K.CARGO] == uzs(750)
    assert lots["a"].breakdown[K.CUSTOMS] == uzs(500) and lots["b"].breakdown[K.CUSTOMS] == uzs(
        1500
    )
    assert K.CARGO not in lots["c"].breakdown
    assert all(lot.breakdown[K.LABELING] == uzs(30) for lot in lots.values())


def test_value_base_without_prices_falls_back() -> None:
    p = Purchase(
        "p",
        (PurchaseLine("a", 1, 1), PurchaseLine("b", 1, 1)),
        (CostComponent(K.CUSTOMS, uzs(10), base=B.VALUE),),
    )
    lots = by_id(compute_lots(p))
    assert lots["a"].total == uzs(5) and Flag.BASE_FALLBACK in lots["a"].flags


def test_effective_rate_component() -> None:
    rate = effective_fx_rate(DAY, Money.of(1000, "CNY"), Money.of("142.50", "USD"), USD)
    p = Purchase(
        "p",
        (PurchaseLine("a", 1000, 1000),),
        (CostComponent(K.GOODS, Money.of(1000, "CNY"), rate), CostComponent(K.CARGO, uzs(0))),
    )
    (lot,) = compute_lots(p)
    assert lot.total == uzs("1802625.00") and lot.unit_cost == uzs("1802.63")
    assert lot.flags == frozenset()  # effektiv kurs — CBU belgisi yo'q


def test_errors() -> None:
    with pytest.raises(PurchaseError):
        PurchaseLine("a", -1)
    with pytest.raises(PurchaseError):
        PurchaseLine("a", 1, -1)
    with pytest.raises(PurchaseError):
        compute_lots(Purchase("p", (PurchaseLine("a", 1), PurchaseLine("a", 2))))
    with pytest.raises(PurchaseError):
        compute_lots(
            Purchase(
                "p", (PurchaseLine("a", 1),), (CostComponent(K.OTHER, uzs(1), line_ids=("x",)),)
            )
        )
    with pytest.raises(PurchaseError):
        compute_lots(Purchase("p", (PurchaseLine("a", 1, 0),), (CostComponent(K.OTHER, uzs(1)),)))
    with pytest.raises(PurchaseError):
        compute_lots(
            Purchase(
                "p",
                (PurchaseLine("a", 1), PurchaseLine("b", 1)),
                (CostComponent(K.OTHER, uzs(1), base=B.MANUAL, manual_shares={"a": D(1)}),),
            )
        )


def test_residual_goods() -> None:
    lines = [
        PurchaseLine("a", 10, unit_price=Money.of(20, "CNY")),
        PurchaseLine("b", 5),
        PurchaseLine("c", 5),
    ]
    rest, ids = residual_goods(Money.of(500, "CNY"), lines)
    assert rest == Money.of(300, "CNY") and ids == ("b", "c")
    rest, _ = residual_goods(Money.of(100, "CNY"), lines)
    assert rest == Money.of(0, "CNY")


# --- Legacy bilan solishtirish (B1.4 qabul mezoni: o'rtacha usulda bir xil) ---------------------

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from uzum_profit.costs import compute_batch  # noqa: E402


def legacy_as_purchase(batch: dict) -> Purchase:
    """Legacy partiyasi → yangi model: tovar (narxli qatorlar + qoldiq dona bo'yicha), kargo va qo'shimchalar dona bo'yicha."""
    cny = manual_rate(DAY, "CNY", str(batch["cny_rate"]))
    usd = manual_rate(DAY, "USD", str(batch["usd_rate"]))
    lines = tuple(
        PurchaseLine(
            str(i),
            ln["qty"],
            ln["qty"],
            None if ln["cny_unit"] is None else Money.of(str(ln["cny_unit"]), "CNY"),
        )
        for i, ln in enumerate(batch["lines"])
    )
    rest, unpriced = residual_goods(Money.of(str(batch["goods_cny"]), "CNY"), lines)
    comps = [
        CostComponent(K.GOODS, ln.unit_price * ln.qty, cny, line_ids=(ln.id,))
        for ln in lines
        if ln.unit_price is not None
    ]
    if unpriced:
        comps.append(CostComponent(K.GOODS, rest, cny, line_ids=unpriced))
    comps.append(CostComponent(K.CARGO, Money.of(str(batch["cargo_usd"]), "USD"), usd))
    comps += [CostComponent(K.OTHER, uzs(str(e["amount"]))) for e in batch["extras"]]
    return Purchase("legacy", lines, tuple(comps))


LEGACY_BATCHES = [
    {
        "goods_cny": 5230.5,
        "cny_rate": 1792.29,
        "cargo_usd": 187.4,
        "usd_rate": 12701.5,
        "lines": [
            {"sku": "A-1", "qty": 120, "cny_unit": 12.5},
            {"sku": "B-2", "qty": 75, "cny_unit": None},
            {"sku": None, "label": "yangi", "qty": 33, "cny_unit": None},
        ],
        "extras": [{"amount": 85000}, {"amount": 12345.67}],
    },
    {
        "goods_cny": 999,
        "cny_rate": 1785,
        "cargo_usd": 0,
        "usd_rate": 12650,
        "lines": [{"sku": "X", "qty": 7, "cny_unit": None}],
        "extras": [],
    },
]


@pytest.mark.parametrize("batch", LEGACY_BATCHES)
def test_matches_legacy_average_unit_cost(batch: dict) -> None:
    legacy = compute_batch(batch)
    lots = compute_lots(legacy_as_purchase(batch))
    for old, new in zip(legacy, lots, strict=True):
        assert new.unit_cost is not None
        assert abs(new.unit_cost.amount - D(str(old["unit_cost"]))) <= D("0.01"), (old, new)
    old_total = sum(r["qty"] * r["unit_cost"] for r in legacy)
    new_total = total([lot.total for lot in lots], "UZS").amount
    assert abs(new_total - D(str(old_total))) <= D("0.02")


# --- Xossalar --------------------------------------------------------------------------------


@given(
    st.lists(
        st.tuples(st.integers(0, 500), st.one_of(st.none(), st.decimals(0, 50, places=3))),
        min_size=1,
        max_size=15,
    ).filter(lambda rows: any(q > 0 for q, _ in rows)),
    st.integers(1, 10**9),
    st.sampled_from([B.UNITS, B.WEIGHT]),
)
def test_allocation_sums_exactly(
    rows: list[tuple[int, Decimal | None]], amount: int, base: AllocationBase
) -> None:
    lines = tuple(PurchaseLine(str(i), q, q, unit_weight=w) for i, (q, w) in enumerate(rows))
    p = Purchase("p", lines, (CostComponent(K.CARGO, uzs(amount), base=base),))
    lots = compute_lots(p)
    assert total([lot.total for lot in lots], "UZS") == uzs(amount)
    for lot in lots:
        if lot.qty == 0:
            assert lot.total == uzs(0) and lot.unit_cost is None


# --- Partiya yo'li (M9, 04 §6.2) -------------------------------------------------------------

S = Stage


def oct_(day: int) -> date:
    return date(2026, 10, day)


def test_default_base_cargo_weight_goods_value_rest_units() -> None:
    assert default_base(K.CARGO) is B.WEIGHT
    assert default_base(K.GOODS) is B.VALUE
    assert {default_base(k) for k in K if k not in (K.CARGO, K.GOODS)} == {B.UNITS}


def test_current_stage_is_latest_dated() -> None:
    assert current_stage({}) is S.DRAFT
    assert current_stage({S.ORDERED: oct_(2), S.SHIPPED: oct_(12)}) is S.SHIPPED  # oraliq ixtiyoriy
    assert current_stage({s: oct_(1) for s in DATED_STAGES}) is S.CLOSED


def test_stage_days_prep_from_paid_or_ordered() -> None:
    dates = {S.ORDERED: oct_(1), S.PAID: oct_(3), S.CN_WAREHOUSE: oct_(9), S.SHIPPED: oct_(12)}
    assert stage_days(dates) == {"prep": 6, "china": 3}
    assert stage_days({S.ORDERED: oct_(1), S.CN_WAREHOUSE: oct_(9)}) == {"prep": 8}
    assert (
        stage_days({S.SHIPPED: oct_(12), S.ARRIVED: oct_(10)}) == {}
    )  # tartib buzilgan — o'rganilmaydi


def test_timeline_mockup() -> None:
    """04 §6.2: Buyurtma ● To'landi ● Xitoy ombori ● Yo'lda ◐ (11 kun) — Toshkent kutilmoqda ~28.10."""
    dates = {S.ORDERED: oct_(2), S.PAID: oct_(3), S.CN_WAREHOUSE: oct_(9), S.SHIPPED: oct_(12)}
    marks = timeline(dates, oct_(23), {"cargo": D("15.5")})
    states = {m.stage: m.state for m in marks}
    assert [states[s] for s in DATED_STAGES] == ["done"] * 3 + ["current"] + ["upcoming"] * 4
    cur = next(m for m in marks if m.state == "current")
    assert (cur.on, cur.days, cur.expected, cur.delayed) == (oct_(12), 11, oct_(28), False)
    late = next(m for m in timeline(dates, oct_(29), {"cargo": D(16)}) if m.state == "current")
    assert late.expected == oct_(28) and late.delayed


def test_timeline_without_history_has_no_expected_and_closed_is_done() -> None:
    cur = next(m for m in timeline({S.ORDERED: oct_(2)}, oct_(5)) if m.state == "current")
    assert cur.expected is None and not cur.delayed and cur.days == 3
    skipped = timeline({S.ORDERED: oct_(2), S.RECEIVED: oct_(20)}, oct_(25))
    assert {m.stage: (m.state, m.on) for m in skipped}[S.PAID] == (
        "done",
        None,
    )  # o'tkazib yuborilgan
    closed = timeline({S.ORDERED: oct_(2), S.CLOSED: oct_(30)}, oct_(31))
    assert all(m.state == "done" for m in closed)
    draft = timeline({}, oct_(5), {"prep": D(5)})
    assert all(m.state == "upcoming" for m in draft)


# --- Kargo: bitta kargo — ko'p xarid (ADR-046) ---------------------------------------------------------------------


def _weighed(pid: str, *lines: tuple[str, int, str], **extra: object) -> Purchase:
    """Xarid: (qator id, dona, dona vazni kg) — hammasi qabul qilingan."""
    return Purchase(
        pid,
        tuple(PurchaseLine(lid, q, q, unit_weight=D(w)) for lid, q, w in lines),
        **extra,  # type: ignore[arg-type]
    )


def test_shipment_cargo_is_split_across_all_purchases_by_weight() -> None:
    """10 xil bazadagi tovar bitta presslangan kargoda (Temur): bitta kargo narxi hamma xaridlarning tovarlariga vazn
    bo'yicha bo'linadi; yig'indi tiyinigacha kargo summasiga teng; xarid ichidagi komponentlar o'z qatorlarida."""
    a = _weighed(
        "A",
        ("a1", 100, "0.5"),
        ("a2", 40, "1"),
        components=(CostComponent(K.GOODS, Money.of(1000, "CNY"), CNY),),
    )
    b = _weighed("B", ("b1", 200, "0.2"))
    cargo = CostComponent(K.CARGO, uzs(2_430_000), base=B.WEIGHT)
    lots = compute_shipment_lots([a, b], [cargo])
    # Vazn: a1 50, a2 40, b1 40 → jami 130 kg.
    by = {lot.line_id: lot for rows in lots.values() for lot in rows}
    assert by["a1"].breakdown[K.CARGO] == uzs("934615.38")
    assert by["a2"].breakdown[K.CARGO] + by["b1"].breakdown[K.CARGO] + by["a1"].breakdown[
        K.CARGO
    ] == uzs(2_430_000)
    assert total([lot.breakdown[K.CARGO] for lot in by.values()], Currency.UZS) == uzs(2_430_000)
    # Xarid ichidagi tovar komponenti kargo bilan qo'shiladi, boshqa xaridga tegmaydi.
    assert by["a1"].breakdown[K.GOODS] + by["a2"].breakdown[K.GOODS] == uzs(1_790_000)
    assert K.GOODS not in by["b1"].breakdown
    assert by["b1"].unit_cost == Money(by["b1"].total.amount / 200, Currency.UZS)
    assert all(Flag.CARGO_MISSING not in lot.flags for lot in by.values())


def test_shipment_without_components_equals_plain_purchases() -> None:
    a = _weighed("A", ("a1", 10, "1"), components=(CostComponent(K.CARGO, uzs(1000)),))
    b = _weighed("B", ("b1", 5, "1"))
    lots = compute_shipment_lots([a, b], [])
    assert lots["A"] == compute_lots(a) and lots["B"] == compute_lots(b)
    assert Flag.CARGO_MISSING in lots["B"][0].flags  # kargo kiritilmagan — avvalgidek


def test_shipment_cargo_missing_flag_only_when_neither_has_cargo() -> None:
    a, b = _weighed("A", ("a1", 10, "1")), _weighed("B", ("b1", 5, "1"))
    customs = CostComponent(K.CUSTOMS, uzs(900))
    lots = compute_shipment_lots([a, b], [customs])
    assert all(Flag.CARGO_MISSING in lot.flags for rows in lots.values() for lot in rows)
    lots = compute_shipment_lots([a, b], [customs, CostComponent(K.CARGO, uzs(300))])
    assert all(Flag.CARGO_MISSING not in lot.flags for rows in lots.values() for lot in rows)


def test_shipment_value_base_uses_each_purchases_own_rate() -> None:
    cny = Purchase(
        "A",
        (PurchaseLine("a1", 10, 10, unit_price=Money.of(10, "CNY")),),
        goods_rate=CNY,  # 1790
    )
    usd = Purchase(
        "B",
        (PurchaseLine("b1", 10, 10, unit_price=Money.of(1, "USD")),),
        goods_rate=USD,  # 12650
    )
    lots = compute_shipment_lots([cny, usd], [CostComponent(K.CARGO, uzs(10_000), base=B.VALUE)])
    # Qiymat: a1 = 179 000, b1 = 126 500 so'm.
    shares = {lot.line_id: lot.breakdown[K.CARGO] for rows in lots.values() for lot in rows}
    assert shares["a1"] + shares["b1"] == uzs(10_000)
    assert shares["a1"] > shares["b1"]


def test_shipment_weight_missing_in_one_line_falls_back_to_units_and_flags() -> None:
    a = _weighed("A", ("a1", 10, "1"))
    b = Purchase("B", (PurchaseLine("b1", 30, 30),))  # vazni yo'q
    lots = compute_shipment_lots([a, b], [CostComponent(K.CARGO, uzs(4000), base=B.WEIGHT)])
    shares = {lot.line_id: lot.breakdown[K.CARGO] for rows in lots.values() for lot in rows}
    assert shares == {"a1": uzs(1000), "b1": uzs(3000)}  # dona bo'yicha
    assert all(Flag.BASE_FALLBACK in lot.flags for rows in lots.values() for lot in rows)


def test_shipment_component_can_target_specific_lines_of_different_purchases() -> None:
    a, b = _weighed("A", ("a1", 10, "1"), ("a2", 10, "1")), _weighed("B", ("b1", 10, "1"))
    cargo = CostComponent(K.CARGO, uzs(3000), line_ids=("a1", "b1"))
    lots = compute_shipment_lots([a, b], [cargo])
    shares = {lot.line_id: lot.breakdown.get(K.CARGO) for rows in lots.values() for lot in rows}
    assert shares == {"a1": uzs(1500), "a2": None, "b1": uzs(1500)}
    with pytest.raises(PurchaseError):
        compute_shipment_lots([a, b], [CostComponent(K.CARGO, uzs(1), line_ids=("zzz",))])


def test_shipment_duplicate_line_ids_rejected() -> None:
    with pytest.raises(PurchaseError):
        compute_shipment_lots([_weighed("A", ("x", 1, "1")), _weighed("B", ("x", 1, "1"))], [])


@given(
    amount=st.integers(min_value=1, max_value=10**9),
    qtys=st.lists(st.integers(min_value=1, max_value=500), min_size=2, max_size=12),
    weights=st.lists(st.integers(min_value=1, max_value=900), min_size=12, max_size=12),
    split=st.integers(min_value=1, max_value=11),
)
def test_shipment_shares_always_sum_to_cargo_amount(
    amount: int, qtys: list[int], weights: list[int], split: int
) -> None:
    """Xossa: qanday xaridlarga bo'linmasin, kargo ulushlari yig'indisi kargo summasiga tiyinigacha teng."""
    rows = [(f"l{i}", q, str(D(weights[i]) / 100)) for i, q in enumerate(qtys)]
    cut = min(split, len(rows) - 1)
    purchases = [_weighed("A", *rows[:cut]), _weighed("B", *rows[cut:])]
    lots = compute_shipment_lots(purchases, [CostComponent(K.CARGO, uzs(amount), base=B.WEIGHT)])
    shares = [lot.breakdown[K.CARGO] for rs in lots.values() for lot in rs]
    assert total(shares, Currency.UZS) == uzs(amount)


# --- Ta'minot qayta loyihasi (ADR-061): qator summasi, sog' dona, qaytarilgan summa, qadoq, kodli quti ---


def _uzs(value: str | int) -> Money:
    return Money(Decimal(value), Currency.UZS)


def test_line_sum_splits_total_paid_proportionally() -> None:
    """F20 (ADR-061 §2): jami 800 = qatorlar 700 + 80 + farq 20 — farq qator summasiga mutanosib."""
    p = Purchase(
        "p",
        (
            PurchaseLine("a", 50, line_sum=Decimal(700)),
            PurchaseLine("b", 30, line_sum=Decimal(80)),
        ),
        (CostComponent(ComponentKind.GOODS, _uzs(780_000 + 20_000), base=AllocationBase.LINE_SUM),),
        on_hand=True,
    )
    lots = {x.line_id: x for x in compute_lots(p)}
    assert lots["a"].total + lots["b"].total == _uzs(800_000)
    assert lots["a"].total == _uzs("717948.72")
    assert Flag.NO_LINE_SUMS not in lots["a"].flags
    assert Flag.CARGO_MISSING not in lots["a"].flags  # "Tovar qo'limda" — kargo kutilmaydi


def test_line_sum_missing_falls_back_to_units_as_info() -> None:
    p = Purchase(
        "p",
        (PurchaseLine("a", 30), PurchaseLine("b", 10)),
        (CostComponent(ComponentKind.GOODS, _uzs(400), base=AllocationBase.LINE_SUM),),
    )
    lots = {x.line_id: x for x in compute_lots(p)}
    assert lots["a"].total == _uzs(300)
    assert Flag.NO_LINE_SUMS in lots["a"].flags
    assert Flag.NO_LINE_SUMS in INFO_FLAGS  # eslatma, taxminiy emas
    single = Purchase(
        "p",
        (PurchaseLine("a", 30),),
        (CostComponent(ComponentKind.GOODS, _uzs(400), base=AllocationBase.LINE_SUM),),
    )
    assert Flag.NO_LINE_SUMS not in compute_lots(single)[0].flags


def test_counting_spreads_all_costs_over_good_units() -> None:
    """F20 (ADR-061 §6): 100 buyurtma, 97 keldi, 2 brak → hamma chiqim 95 sog' donaga."""
    p = Purchase(
        "p",
        (PurchaseLine("a", 100, received_qty=97, defect_qty=2),),
        (
            CostComponent(ComponentKind.GOODS, _uzs(950_000), base=AllocationBase.LINE_SUM),
            CostComponent(ComponentKind.CARGO, _uzs(95_000)),
        ),
    )
    (lot,) = compute_lots(p)
    assert lot.qty == 95
    assert lot.total == _uzs(1_045_000)
    assert lot.unit_cost == _uzs(11_000)


def test_fully_defective_line_passes_its_cost_to_good_lines() -> None:
    p = Purchase(
        "p",
        (
            PurchaseLine("a", 10, received_qty=10, defect_qty=10),
            PurchaseLine("b", 10, received_qty=10),
        ),
        (CostComponent(ComponentKind.GOODS, _uzs(200), base=AllocationBase.LINE_SUM),),
    )
    lots = {x.line_id: x for x in compute_lots(p)}
    assert lots["a"].qty == 0 and lots["a"].unit_cost is None
    assert lots["b"].total == _uzs(200)


def test_defect_more_than_arrived_is_rejected() -> None:
    with pytest.raises(PurchaseError):
        PurchaseLine("a", 10, received_qty=5, defect_qty=6)


def test_supplier_refund_reduces_goods() -> None:
    p = Purchase(
        "p",
        (
            PurchaseLine("a", 50, received_qty=45, line_sum=Decimal(700)),
            PurchaseLine("b", 30, received_qty=30, line_sum=Decimal(80)),
        ),
        (CostComponent(ComponentKind.GOODS, _uzs(780_000), base=AllocationBase.LINE_SUM),),
        refund=_uzs(78_000),
    )
    lots = {x.line_id: x for x in compute_lots(p)}
    assert lots["a"].total + lots["b"].total == _uzs(702_000)
    assert lots["a"].breakdown[ComponentKind.GOODS] == _uzs(630_000)
    with pytest.raises(PurchaseError):
        compute_lots(
            Purchase("p", p.lines, p.components, refund=_uzs(900_000)),
        )


def test_pack_unit_cost_added_per_good_unit() -> None:
    p = Purchase(
        "p",
        (PurchaseLine("a", 10, received_qty=10, defect_qty=1, pack_unit_cost=_uzs(500)),),
        (CostComponent(ComponentKind.GOODS, _uzs(90_000)),),
    )
    (lot,) = compute_lots(p)
    assert lot.breakdown[ComponentKind.PACKAGING] == _uzs(4_500)
    assert lot.unit_cost == _uzs(10_500)


def test_split_by_purchase_units_and_fixed_shares() -> None:
    """ADR-061 §3: quti 30 — A 20 dona, B 10 dona → 20 / 10; A ga qo'lda 12 yozilsa qolgan 18 B va C ga dona bo'yicha."""
    a = Purchase("A", (PurchaseLine("a1", 12), PurchaseLine("a2", 8)))
    b = Purchase("B", (PurchaseLine("b1", 10),))
    c = Purchase("C", (PurchaseLine("c1", 5, received_qty=5),))
    box = CostComponent(ComponentKind.CARGO, _uzs(30))
    parts = split_by_purchase(box, [a, b], {})
    lots = compute_shipment_lots([a, b], parts)
    assert sum((x.total for x in lots["A"]), _uzs(0)) == _uzs(20)
    assert lots["B"][0].total == _uzs(10)

    parts = split_by_purchase(box, [a, b, c], {"A": Decimal(12)})
    lots = compute_shipment_lots([a, b, c], parts)
    assert sum((x.total for x in lots["A"]), _uzs(0)) == _uzs(12)
    assert lots["B"][0].total == _uzs(12) and lots["C"][0].total == _uzs(6)
    assert Flag.CARGO_MISSING not in lots["C"][0].flags

    with pytest.raises(PurchaseError):
        split_by_purchase(box, [a, b], {"A": Decimal(31)})
    with pytest.raises(PurchaseError):
        split_by_purchase(box, [a, b], {"A": Decimal(10), "B": Decimal(10)})
    with pytest.raises(PurchaseError):
        split_by_purchase(box, [a, b], {"X": Decimal(1)})


@given(
    qtys=st.lists(st.integers(min_value=1, max_value=500), min_size=1, max_size=6),
    amount=st.integers(min_value=1, max_value=10**9),
    fixed_share=st.integers(min_value=0, max_value=100),
)
def test_split_by_purchase_sums_exactly(qtys: list[int], amount: int, fixed_share: int) -> None:
    """Xossa (M9 qabul mezoni 3): kodli qutida ulushlar yig'indisi summaga tiyinigacha teng."""
    purchases = [Purchase(f"p{i}", (PurchaseLine(f"l{i}", q),)) for i, q in enumerate(qtys)]
    fixed = {}
    if len(purchases) > 1:
        fixed = {"p0": Decimal(amount * fixed_share // 100)}
    box = CostComponent(ComponentKind.CARGO, _uzs(amount))
    lots = compute_shipment_lots(purchases, split_by_purchase(box, purchases, fixed))
    assert sum((x.total for ls in lots.values() for x in ls), _uzs(0)) == _uzs(amount)


# --- Uch holat (ADR-061 §1, §11) ---


@pytest.mark.parametrize(
    ("stage", "state"),
    [
        (None, SupplyState.IN_TRANSIT),
        (Stage.ORDERED, SupplyState.IN_TRANSIT),
        (Stage.PAID, SupplyState.IN_TRANSIT),
        (Stage.CN_WAREHOUSE, SupplyState.IN_TRANSIT),
        (Stage.SHIPPED, SupplyState.IN_TRANSIT),
        (Stage.ARRIVED, SupplyState.IN_TRANSIT),
        (Stage.RECEIVED, SupplyState.IN_STOCK),
        (Stage.SENT_TO_UZUM, SupplyState.AT_UZUM),
        (Stage.CLOSED, SupplyState.AT_UZUM),
    ],
)
def test_supply_state_from_old_stages(stage: Stage | None, state: SupplyState) -> None:
    """ADR-061 §11: eski bosqich → yangi holat."""
    dates = {} if stage is None else {stage: date(2026, 10, 5)}
    assert supply_state(dates) is state


def test_supply_path_in_transit_expected_and_delay() -> None:
    dates = {Stage.ORDERED: date(2026, 10, 1)}
    path = supply_path(dates, date(2026, 10, 12), Decimal("20.5"))
    assert [m.mark for m in path] == ["current", "upcoming", "upcoming"]
    assert path[0].days == 11 and path[0].expected == date(2026, 10, 22) and not path[0].delayed
    assert supply_path(dates, date(2026, 10, 23), Decimal("20.5"))[0].delayed
    unknown = supply_path(dates, date(2026, 10, 12))
    assert unknown[0].expected is None and not unknown[0].delayed
    undated = supply_path({}, date(2026, 10, 12), Decimal(5), started=date(2026, 10, 10))
    assert undated[0].on == date(2026, 10, 10) and undated[0].days == 2
    assert supply_path({}, date(2026, 10, 12))[0].days is None


def test_supply_path_counted_and_sent() -> None:
    dates = {Stage.PAID: date(2026, 10, 2), Stage.RECEIVED: date(2026, 10, 20)}
    path = supply_path(dates, date(2026, 10, 25))
    assert [(m.state, m.mark, m.on) for m in path] == [
        (SupplyState.IN_TRANSIT, "done", date(2026, 10, 2)),
        (SupplyState.IN_STOCK, "current", date(2026, 10, 20)),
        (SupplyState.AT_UZUM, "upcoming", None),
    ]
    assert transit_days(dates) == 18
    sent = supply_path({**dates, Stage.CLOSED: date(2026, 10, 28)}, date(2026, 11, 1))
    assert [m.mark for m in sent] == ["done", "done", "current"]
    assert sent[2].on == date(2026, 10, 28)
    assert transit_days({Stage.ORDERED: date(2026, 10, 5)}) is None
    assert (
        transit_days({Stage.ORDERED: date(2026, 10, 5), Stage.RECEIVED: date(2026, 10, 1)}) is None
    )


# --- Kodli quti ulushlari (ADR-061 §3, TM3) ------------------------------------------------------


def test_box_shares_by_units_and_fixed() -> None:
    usd = lambda x: Money(D(x), Currency.USD)  # noqa: E731
    shares = box_shares(usd("100"), {"a": 30, "b": 60, "c": 10}, {})
    assert shares == {"a": usd("30.00"), "b": usd("60.00"), "c": usd("10.00")}
    # "b" qo'lda 50: qolgan 50 — a va c ga dona bo'yicha (30 : 10).
    shares = box_shares(usd("100"), {"a": 30, "b": 60, "c": 10}, {"b": D("50")})
    assert shares == {"a": usd("37.50"), "b": usd("50"), "c": usd("12.50")}
    # Hammasi qo'lda va yig'indi teng — xato yo'q; qoldiqni oladigan xarid yo'q va qoldiq 0.
    assert box_shares(usd("10"), {"a": 1, "b": 1}, {"a": D("4"), "b": D("6")})["b"] == usd("6")
    # Dona 0 bo'lgan xarid qoldig'i 0 bo'lsa — 0.
    assert box_shares(usd("10"), {"a": 1, "b": 0}, {"a": D("10")})["b"] == usd("0")


@pytest.mark.parametrize(
    ("units", "fixed", "message"),
    [
        ({}, {}, "kamida bitta"),
        ({"a": 1}, {"x": D("1")}, "qutida yo'q"),
        ({"a": 1, "b": 1}, {"a": D("-1")}, "manfiy"),
        ({"a": 1, "b": 1}, {"a": D("11")}, "summadan ko'p"),
        ({"a": 1, "b": 1}, {"a": D("4"), "b": D("5")}, "teng emas"),
        ({"a": 1, "b": 0}, {"a": D("4")}, "teng emas"),
    ],
)
def test_box_shares_errors(units: dict[str, int], fixed: dict[str, D], message: str) -> None:
    with pytest.raises(PurchaseError, match=message):
        box_shares(Money(D("10"), Currency.USD), units, fixed)


@given(
    st.lists(st.integers(min_value=1, max_value=500), min_size=1, max_size=8),
    st.decimals(min_value=D("0.01"), max_value=D("99999"), places=2),
)
def test_box_shares_sum_equals_amount(units: list[int], amount: D) -> None:
    money = Money(amount, Currency.USD)
    shares = box_shares(money, {str(i): u for i, u in enumerate(units)}, {})
    assert total(list(shares.values()), Currency.USD) == money


def test_new_cost_kinds_go_to_shipments() -> None:
    assert K.TRANSFER_FEE in SHIPMENT_KINDS and K.LOCAL_DELIVERY in SHIPMENT_KINDS

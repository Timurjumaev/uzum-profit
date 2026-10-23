import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from upcore.costing import (
    CostFlag,
    CostingError,
    CostMethod,
    Lot,
    Return,
    Sale,
    WriteOff,
    compute_costs,
    lots_from_purchase,
)
from upcore.money import Money
from upcore.purchasing import (
    ComponentKind,
    CostComponent,
    Flag,
    Purchase,
    PurchaseLine,
    compute_lots,
)

D = Decimal
FIFO, AVG = CostMethod.FIFO, CostMethod.AVERAGE


def d(n: int) -> date:
    return date(2026, 10, 1) + timedelta(days=n)


def uzs(x: int | str) -> Money:
    return Money.of(x, "UZS")


def lot(
    lid: str,
    day: int | None,
    qty: int,
    unit: int,
    flags: frozenset[Flag] = frozenset(),
    seq: int = 0,
) -> Lot:
    return Lot(lid, None if day is None else d(day), qty, uzs(unit * qty), flags, seq)


LOTS = [lot("L1", 0, 10, 100), lot("L2", 5, 10, 200)]


def test_fifo_basic() -> None:
    r = compute_costs(LOTS, [Sale("s1", d(1), 4), Sale("s2", d(6), 10)])
    assert r.sales["s1"].cost == uzs(400) and r.sales["s1"].flags == frozenset()
    s2 = r.sales["s2"]
    assert s2.cost == uzs(6 * 100 + 4 * 200) and s2.unit_cost == uzs(140)
    assert [(a.lot_id, a.qty) for a in s2.allocations] == [("L1", 6), ("L2", 4)]
    assert r.remaining == {"L1": 0, "L2": 6} and r.remaining_value == uzs(1200)


def test_average_basic() -> None:
    r = compute_costs(LOTS, [Sale("s1", d(1), 4), Sale("s2", d(6), 10)], AVG)
    assert r.sales["s1"].cost == uzs(400)
    # 6 × 100 + 10 × 200 = 2600 / 16 = 162,5
    assert r.sales["s2"].cost == uzs(1625) and r.remaining_value == uzs(975)
    assert r.remaining == {"L1": 0, "L2": 6}


def test_lot_not_ready_yet_is_early_sale() -> None:
    r = compute_costs(LOTS, [Sale("s", d(3), 12)])
    s = r.sales["s"]
    assert s.cost == uzs(10 * 100 + 2 * 200)
    assert CostFlag.EARLY_SALE in s.flags


def test_sale_before_first_lot() -> None:
    r = compute_costs([lot("L", 5, 10, 300)], [Sale("s", d(1), 2)])
    assert r.sales["s"].cost == uzs(600) and CostFlag.EARLY_SALE in r.sales["s"].flags
    assert r.remaining == {"L": 8}


def test_transit_lot_used_last_and_flagged() -> None:
    lots = [lot("ready", 0, 2, 100), lot("t2", None, 5, 400, seq=2), lot("t1", None, 5, 300, seq=1)]
    r = compute_costs(lots, [Sale("s", d(1), 4)])
    s = r.sales["s"]
    assert [(a.lot_id, a.qty) for a in s.allocations] == [("ready", 2), ("t1", 2)]
    assert CostFlag.NOT_RECEIVED_MARKED in s.flags
    assert r.remaining == {"ready": 0, "t1": 3, "t2": 5}
    assert r.remaining_value == uzs(3 * 300 + 5 * 400)


def test_shortage_uses_last_price() -> None:
    lots = [lot("L", 0, 3, 100, frozenset({Flag.CARGO_MISSING}))]
    r = compute_costs(lots, [Sale("s1", d(1), 5), Sale("s2", d(2), 1)])
    s1 = r.sales["s1"]
    assert s1.cost == uzs(500)
    assert s1.flags == {CostFlag.LOT_SHORTAGE, Flag.CARGO_MISSING}
    assert s1.allocations[-1].lot_id is None and s1.allocations[-1].qty == 2
    assert r.sales["s2"].cost == uzs(100) and CostFlag.LOT_SHORTAGE in r.sales["s2"].flags


def test_no_lots_no_cost() -> None:
    r = compute_costs([], [Sale("s", d(1), 1)])
    assert r.sales["s"].cost is None and r.sales["s"].unit_cost is None
    assert r.remaining_value == uzs(0)


def test_writeoff_consumes_but_is_separate() -> None:
    r = compute_costs(LOTS, [WriteOff("w", d(1), 3), Sale("s", d(2), 8)])
    assert r.writeoffs["w"].cost == uzs(300) and "w" not in r.sales
    assert r.sales["s"].cost == uzs(7 * 100 + 1 * 200)


def test_lot_flags_inherited() -> None:
    lots = [lot("L", 0, 5, 100, frozenset({Flag.CBU_RATE}))]
    assert compute_costs(lots, [Sale("s", d(1), 1)]).sales["s"].flags == {Flag.CBU_RATE}


def test_return_goes_back_to_same_lot_and_price() -> None:
    events = [Sale("s1", d(1), 12), Return("r1", d(7), 3, "s1"), Sale("s2", d(8), 5)]
    r = compute_costs(LOTS, events)
    assert r.sales["s1"].cost == uzs(1000 + 400)
    ret = r.returns["r1"]
    assert ret.cost == uzs(2 * 200 + 1 * 100) and ret.qty == 3  # oxirgi olingan lotdan boshlab
    # L1 da 1 dona (100), L2 da 10 dona → s2: 1 × 100 + 4 × 200
    assert r.sales["s2"].cost == uzs(900)


def test_return_average_uses_sale_price() -> None:
    events = [Sale("s1", d(6), 4), Return("r1", d(7), 2, "s1")]
    r = compute_costs(LOTS, events, AVG)
    assert r.sales["s1"].cost == uzs(600)  # o'rtacha 150
    assert r.returns["r1"].cost == uzs(300)
    assert r.remaining_value == uzs(3000 - 600 + 300)


def test_return_over_and_unmatched() -> None:
    events = [
        Sale("s1", d(1), 2),
        Return("r1", d(2), 1, "s1"),
        Return("r2", d(3), 5, "s1"),
        Return("r3", d(3), 1, "nope"),
    ]
    r = compute_costs(LOTS, events)
    assert r.returns["r1"].qty == 1 and r.returns["r1"].cost == uzs(100)
    assert r.returns["r2"].qty == 1 and CostFlag.RETURN_UNMATCHED in r.returns["r2"].flags
    assert r.returns["r3"].cost is None and CostFlag.RETURN_UNMATCHED in r.returns["r3"].flags
    assert r.remaining["L1"] == 10


def test_return_of_shortage_part_creates_layer() -> None:
    events = [Sale("s", d(1), 4), Return("r", d(2), 2, "s"), Sale("s2", d(3), 2)]
    r = compute_costs([lot("L", 0, 2, 100)], events)
    assert r.returns["r"].cost == uzs(200)
    assert r.sales["s2"].cost == uzs(200) and CostFlag.LOT_SHORTAGE not in r.sales["s2"].flags


def test_same_day_order_receipt_return_before_sale() -> None:
    lots = [lot("L1", 0, 1, 100), lot("L2", 2, 1, 500)]
    events = [Sale("s1", d(1), 1), Sale("s2", d(2), 1), Return("r", d(2), 1, "s1")]
    r = compute_costs(lots, events)
    # 2-kun: L2 kiradi, qaytish L1 ga, keyin s2 FIFO bo'yicha L1 dan
    assert r.sales["s2"].cost == uzs(100) and r.remaining == {"L1": 0, "L2": 1}


def test_validation() -> None:
    with pytest.raises(CostingError):
        Lot("x", d(0), 0, uzs(0))
    with pytest.raises(CostingError):
        compute_costs([lot("a", 0, 1, 1), lot("a", 1, 1, 1)], [])
    with pytest.raises(CostingError):
        compute_costs([], [Sale("s", d(0), 0)])


def test_lots_from_purchase() -> None:
    p = Purchase(
        "P7",
        (PurchaseLine("a", 10, 10), PurchaseLine("b", 5, 0), PurchaseLine("c", 4, 4)),
        (CostComponent(ComponentKind.GOODS, uzs(1400)), CostComponent(ComponentKind.CARGO, uzs(0))),
        order_date=d(0),
        received_date=d(9),
    )
    by_item = lots_from_purchase(p, compute_lots(p), {"a": "item1", "b": "item1"})
    (only,) = by_item["item1"]  # b — 0 dona, c — tovarga bog'lanmagan
    assert only.id == "P7:a" and only.ready == d(9) and only.qty == 10 and only.unit == D(100)
    assert only.seq == d(0).toordinal()
    no_date = Purchase("P8", (PurchaseLine("a", 1),), (CostComponent(ComponentKind.GOODS, uzs(5)),))
    (l8,) = lots_from_purchase(no_date, compute_lots(no_date), {"a": "x"})["x"]
    assert l8.ready is None and l8.seq == 0 and Flag.NOT_RECEIVED in l8.flags


# --- Xossalar --------------------------------------------------------------------------------

lot_st = st.tuples(
    st.one_of(st.none(), st.integers(0, 30)), st.integers(1, 50), st.integers(1, 10_000)
)
event_st = st.tuples(st.sampled_from(["s", "w", "r"]), st.integers(0, 40), st.integers(1, 20))


def build(raw_lots: list, raw_events: list) -> tuple[list[Lot], list]:
    lots = [
        Lot(f"L{i}", None if dd is None else d(dd), q, uzs(u * q), seq=i)
        for i, (dd, q, u) in enumerate(raw_lots)
    ]
    events: list = []
    sale_ids: list[str] = []
    for i, (kind, dd, q) in enumerate(raw_events):
        if kind == "s":
            events.append(Sale(f"s{i}", d(dd), q))
            sale_ids.append(f"s{i}")
        elif kind == "w":
            events.append(WriteOff(f"w{i}", d(dd), q))
        elif sale_ids:
            events.append(Return(f"r{i}", d(dd), q, sale_ids[i % len(sale_ids)]))
    return lots, events


@settings(max_examples=150)
@given(st.lists(lot_st, max_size=6), st.lists(event_st, max_size=25), st.sampled_from([FIFO, AVG]))
def test_conservation_and_determinism(raw_lots: list, raw_events: list, method: CostMethod) -> None:
    lots, events = build(raw_lots, raw_events)
    r = compute_costs(lots, events, method)
    assert (
        compute_costs(list(reversed(lots)), list(reversed(events)), method) == r
    )  # tartibga bog'liq emas
    out = [o for o in [*r.sales.values(), *r.writeoffs.values()] if o.cost is not None]
    shortage = sum((a.unit * a.qty for o in out for a in o.allocations if a.lot_id is None), D(0))
    spent = sum((o.cost.amount for o in out if o.cost), D(0))
    back = sum((x.cost.amount for x in r.returns.values() if x.cost), D(0))
    lots_value = sum((x.total.amount for x in lots), D(0))
    # Lotlar qiymati + lot yetmagan qism = chiqimlar − qaytishlar + qoldiq (har chiqim 1 tiyingacha yaxlitlangan)
    tolerance = D("0.01") * (len(out) + len(r.returns) + 1)
    assert abs(lots_value + shortage - (spent - back + r.remaining_value.amount)) <= tolerance
    assert all(v >= 0 for v in r.remaining.values())


@given(st.integers(1, 100), st.integers(1, 10_000), st.lists(st.integers(1, 5), max_size=20))
def test_single_lot_fifo_equals_average(qty: int, unit: int, sales: list[int]) -> None:
    lots = [Lot("L", d(0), qty, uzs(unit * qty))]
    events = [Sale(f"s{i}", d(1 + i), q) for i, q in enumerate(sales)]
    fifo, avg = compute_costs(lots, events, FIFO), compute_costs(lots, events, AVG)
    assert {k: v.cost for k, v in fifo.sales.items()} == {k: v.cost for k, v in avg.sales.items()}


def test_benchmark_10k_sales_under_1s() -> None:
    lots = [Lot(f"L{i}", d(i * 3), 500, uzs(1000 * 500 + i)) for i in range(25)]
    events = [Sale(f"s{i:05d}", d(i % 90), 1) for i in range(10_000)]
    start = time.perf_counter()
    r = compute_costs(lots, events)
    assert time.perf_counter() - start < 1.0
    assert len(r.sales) == 10_000

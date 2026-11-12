import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from upcore.costing import (
    OPENING_LOT,
    CostFlag,
    CostingError,
    CostMethod,
    Lot,
    Opening,
    PricePoint,
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
    assert r.sales["s"].flags == {CostFlag.NO_LOTS}
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


@pytest.mark.benchmark
def test_benchmark_10k_sales_under_1s() -> None:
    lots = [Lot(f"L{i}", d(i * 3), 500, uzs(1000 * 500 + i)) for i in range(25)]
    events = [Sale(f"s{i:05d}", d(i % 90), 1) for i in range(10_000)]
    start = time.perf_counter()
    r = compute_costs(lots, events)
    assert time.perf_counter() - start < 1.0
    assert len(r.sales) == 10_000


# --- F41: boshlang'ich holat (ADR-033) ------------------------------------------------------------


def opening(start: int, qty: int, *prices: tuple[int | None, int]) -> Opening:
    return Opening(
        d(start), qty, tuple(PricePoint(None if f is None else d(f), uzs(u)) for f, u in prices)
    )


def test_opening_history_does_not_eat_lots() -> None:
    """Muammo (hozirgi xatti-harakat): eski sotuvlar oxirgi partiyani yeydi; boshlang'ich holat bilan — yo'q."""
    lots = [lot("New", 10, 200, 13000)]
    old = [Sale(f"o{i}", d(i), 10) for i in range(10)]  # 100 dona boshlashdan oldin
    new = [Sale(f"n{i}", d(11 + i), 6) for i in range(25)]  # 150 dona boshlashdan keyin
    before = compute_costs(lots, old + new)
    assert before.remaining == {"New": 0}  # haqiqatda 170 + boshlang'ich qoldiq

    r = compute_costs(lots, old + new, FIFO, opening(10, 120, (None, 12000)))
    for i in range(10):
        out = r.sales[f"o{i}"]
        assert out.cost == uzs(10 * 12000) and out.flags == {CostFlag.HISTORICAL}
        assert out.allocations[0].lot_id is None
    took: dict[str | None, int] = {}
    for i in range(25):
        assert r.sales[f"n{i}"].flags == frozenset()
        for a in r.sales[f"n{i}"].allocations:
            took[a.lot_id] = took.get(a.lot_id, 0) + a.qty
    assert took == {OPENING_LOT: 120, "New": 30}
    assert sum((r.sales[f"n{i}"].cost.amount for i in range(25)), D(0)) == 120 * 12000 + 30 * 13000  # type: ignore[union-attr]
    assert r.remaining == {OPENING_LOT: 0, "New": 170} and r.remaining_value == uzs(170 * 13000)


def test_opening_average_blends_with_new_lot() -> None:
    r = compute_costs(
        [lot("New", 5, 200, 13000)],
        [Sale("a", d(1), 100), Sale("b", d(6), 10)],
        AVG,
        opening(0, 120, (None, 12000)),
    )
    # 1–4: boshlang'ich qoldiqdan 100; 5-kuni 20 × 12 000 + 200 × 13 000 = 2 840 000 / 220
    assert r.sales["a"].cost == uzs(100 * 12000)
    assert r.sales["b"].cost is not None
    assert r.sales["b"].unit_cost == Money(D(2840000) / 220, r.sales["b"].cost.currency)


def test_opening_price_periods() -> None:
    o = opening(20, 5, (None, 8000), (10, 10000), (15, 11000))
    assert o.price_on(d(0)) == uzs(8000) and o.price_on(d(12)) == uzs(10000)
    assert o.price_on(d(30)) == uzs(11000)
    lot_ = o.lot()
    assert lot_ is not None and lot_.id == OPENING_LOT and lot_.total == uzs(5 * 11000)
    # Birinchi narx sanasidan oldingi kun — eng birinchi narx.
    assert opening(20, 1, (10, 9000)).price_on(d(0)) == uzs(9000)
    assert opening(20, 1).price_on(d(0)) is None and opening(20, 1).lot() is None
    assert opening(20, 0, (None, 5)).lot() is None


def test_opening_first_before_same_day_lots_and_supersedes_older() -> None:
    lots = [lot("Old", 2, 50, 9000), lot("Same", 10, 10, 15000), lot("Road", None, 5, 16000)]
    r = compute_costs(lots, [Sale("s", d(10), 3)], FIFO, opening(10, 3, (None, 12000)))
    assert [(a.lot_id, a.qty) for a in r.sales["s"].allocations] == [(OPENING_LOT, 3)]
    assert r.superseded == {"Old"} and "Old" not in r.remaining
    assert r.remaining["Same"] == 10 and r.remaining["Road"] == 5


def test_opening_without_price() -> None:
    r = compute_costs(
        [lot("L", 5, 10, 100)],
        [Sale("h", d(1), 2), Sale("n", d(6), 1), WriteOff("w", d(1), 1)],
        FIFO,
        opening(3, 4),
    )
    assert r.sales["h"].cost is None and r.sales["h"].flags == {CostFlag.HISTORICAL}
    assert r.writeoffs["w"].cost is None
    # Narx yo'q — boshlang'ich qoldiq loti yaratilmaydi, keyingi sotuv partiyadan.
    assert r.sales["n"].allocations[0].lot_id == "L"


def test_opening_returns() -> None:
    o = opening(5, 2, (None, 1000))
    r = compute_costs(
        [], [Sale("h", d(1), 3), Return("rh", d(2), 1, "h"), Return("rx", d(2), 1, "zz")], FIFO, o
    )
    assert r.returns["rh"].cost == uzs(1000) and r.returns["rh"].flags == {CostFlag.HISTORICAL}
    assert r.returns["rx"].cost is None and r.returns["rx"].flags == {CostFlag.RETURN_UNMATCHED}
    # Sotilganidan ko'p qaytish (tarixiy, keyin yana boshlashdan keyin) — manfiy dona yo'q (hypothesis topgan).
    r3 = compute_costs(
        [], [Sale("h", d(1), 1), Return("a", d(2), 2, "h"), Return("b", d(6), 1, "h")], FIFO, o
    )
    assert r3.returns["a"].qty == 1 and CostFlag.RETURN_UNMATCHED in r3.returns["a"].flags
    assert r3.returns["b"].qty == 0 and r3.remaining == {OPENING_LOT: 2}
    # Boshlashdan keyin qaytgan tarixiy sotuv — qoldiqqa qaytadi (tovar haqiqatda qaytdi).
    r2 = compute_costs(
        [], [Sale("h", d(1), 3), Return("rh", d(6), 1, "h"), Sale("n", d(7), 3)], FIFO, o
    )
    assert r2.sales["n"].cost == uzs(3000) and r2.sales["n"].flags == frozenset()


def test_opening_validation() -> None:
    with pytest.raises(CostingError):
        Opening(d(0), -1)
    with pytest.raises(CostingError):
        compute_costs([lot(OPENING_LOT, 0, 1, 1)], [])


@settings(max_examples=150)
@given(
    st.lists(lot_st, max_size=6),
    st.lists(event_st, max_size=25),
    st.sampled_from([FIFO, AVG]),
    st.integers(0, 30),
    st.integers(0, 50),
    st.booleans(),
    st.none() | st.integers(0, 40),
)
def test_opening_conserves_units(
    raw_lots: list,
    raw_events: list,
    method: CostMethod,
    start: int,
    qty: int,
    is_fbo: bool,
    supplied: int | None,
) -> None:
    """Boshlashdan keyin lotlardan chiqqan + qoldiq = boshlang'ich qoldiq + ishlatilgan lotlar; tarix lotga tegmaydi
    (ADR-051: FBO va postavka sanasining har qanday holatida ham)."""
    lots, events = build(raw_lots, raw_events)
    base = opening(start, qty, (None, 100))
    o = Opening(
        base.start, base.qty, base.prices, is_fbo, None if supplied is None else d(supplied)
    )
    r = compute_costs(lots, events, method, o)
    assert compute_costs(list(reversed(lots)), list(reversed(events)), method, o) == r
    used = sum(x.qty for x in lots if x.id not in r.superseded)
    out = [*r.sales.values(), *r.writeoffs.values()]
    taken = sum(a.qty for x in out for a in x.allocations if a.lot_id is not None)
    back = sum(
        min(e.qty, r.sales[e.sale_id].qty)
        for e in events
        if isinstance(e, Return) and e.day >= o.start and e.sale_id in r.sales
    )
    assert taken + sum(r.remaining.values()) <= qty + used + back
    assert all(x.flags == {CostFlag.HISTORICAL} for x in out if x.day < o.start)


def test_opening_price_without_stock_or_lots_is_estimated_not_missing() -> None:
    """Narx yozilgan, lekin qoldiq 0 va partiya yo'q: boshlashdan keyingi sotuv tannarxsiz qolmaydi — o'sha kundagi
    sotuvchi kiritgan narx; bu aniq tannarx — taxminiy belgisi yo'q."""
    o = opening(10, 0, (None, 8000), (15, 9000))
    r = compute_costs([], [Sale("a", d(12), 2), Sale("b", d(20), 3)], FIFO, o)
    assert r.sales["a"].cost == uzs(2 * 8000) and r.sales["a"].flags == frozenset()
    assert r.sales["b"].cost == uzs(3 * 9000) and r.sales["b"].flags == frozenset()
    # Narx ham yo'q — avvalgidek tannarx yo'q.
    r = compute_costs([], [Sale("c", d(12), 1)], FIFO, opening(10, 0))
    assert r.sales["c"].cost is None and r.sales["c"].flags == {CostFlag.NO_LOTS}


def test_opening_stock_exhausted_without_new_supply_is_old_goods() -> None:
    """ADR-051: boshlang'ich qoldiq (2 dona) tugadi, boshlashdan keyin postavka yo'q — yetmagan qism qaytgan eski tovar
    (boshlashdan oldingi bekor buyurtmalar): sotuv kunidagi kiritilgan narxda, belgisiz. Postavka ma'lumoti bo'lmagan
    (FBO'siz) tovarda ham shunday: partiya tugagach — boshlang'ich narx."""
    o = opening(10, 2, (None, 8000), (15, 9000))
    r = compute_costs([], [Sale("a", d(12), 5), Sale("b", d(20), 2)], FIFO, o)
    assert r.sales["a"].cost == uzs(2 * 8000 + 3 * 8000) and r.sales["a"].flags == frozenset()
    assert (
        r.sales["b"].cost == uzs(2 * 9000) and r.sales["b"].flags == frozenset()
    )  # 15-kundan yangi narx
    real = compute_costs([lot("L", 11, 3, 9000)], [Sale("c", d(12), 8)], FIFO, o)
    assert real.sales["c"].cost == uzs(2 * 8000 + 3 * 9000 + 3 * 8000)
    assert real.sales["c"].flags == frozenset()


def fbo(o: Opening, supplied: int | None = None) -> Opening:
    return Opening(
        o.start, o.qty, o.prices, fbo=True, supplied_on=None if supplied is None else d(supplied)
    )


def test_temur_returned_old_goods_after_start() -> None:
    """ADR-051, Temur holati (BYDURII-GUBKA-БЕЛЫЙ, 2026-11-05): boshlang'ich qoldiq 4 dona (3 600), boshlashdan keyin postavka
    yo'q, 9 dona sotildi — 6 tasi oktabrdagi bekor buyurtmalardan qaytgan. Hammasi 3 600 da, "Taxminiy"siz."""
    o = fbo(opening(1, 4, (None, 3600)))
    r = compute_costs([], [Sale(f"s{i}", d(1 + i // 3), 1) for i in range(9)], FIFO, o)
    assert all(x.cost == uzs(3600) and x.flags == frozenset() for x in r.sales.values())


def test_no_new_supply_does_not_touch_transit_or_later_lots() -> None:
    """ADR-051: FBO tovari, postavka yo'q — yo'ldagi (sanasiz) va keyinroq tayyor bo'ladigan partiya Uzumda yo'q: qoldiq
    tugagach sotuv ular hisobidan emas ("yo'ldan olindi" / "erta sotuv" emas), boshlang'ich narxda; partiyalar butun qoladi."""
    lots = [lot("T", None, 10, 9000), lot("P", 30, 10, 9500)]
    o = fbo(opening(10, 1, (None, 8000)))
    r = compute_costs(lots, [Sale("a", d(12), 3)], FIFO, o)
    assert r.sales["a"].cost == uzs(3 * 8000) and r.sales["a"].flags == frozenset()
    assert r.remaining["T"] == 10 and r.remaining["P"] == 10
    # Postavka 20-kuni bo'ldi: 25-kungi sotuv avvalgidek keyingi partiyadan ("erta sotuv").
    r = compute_costs(lots, [Sale("b", d(25), 3)], FIFO, fbo(opening(10, 1, (None, 8000)), 20))
    assert CostFlag.EARLY_SALE in r.sales["b"].flags


def test_supply_with_lot_extra_units_at_lot_price_without_flag() -> None:
    """ADR-051 (Temur): postavka bo'lgan va partiya kiritilgan, lekin sotuv qoldiq + partiyadan ko'p (qaytgan eski tovar
    aralashgan — Uzum qaytish sanasini bermaydi, ajratib bo'lmaydi): ortiqcha dona oxirgi partiya narxida, "yetmadi"
    belgisisiz; partiyaning o'z belgisi (kargo kiritilmagan) qoladi."""
    o = fbo(opening(10, 2, (None, 8000)), 11)
    r = compute_costs([lot("L", 11, 3, 9000)], [Sale("a", d(12), 8)], FIFO, o)
    assert r.sales["a"].cost == uzs(2 * 8000 + 3 * 9000 + 3 * 9000)
    assert r.sales["a"].flags == frozenset()
    flagged = lot("L", 11, 3, 9000, frozenset({Flag.CARGO_MISSING}))
    r = compute_costs([flagged], [Sale("a", d(12), 8)], FIFO, o)
    assert r.sales["a"].flags == {Flag.CARGO_MISSING}


def test_supply_without_lot_is_flagged() -> None:
    """ADR-051: boshlashdan keyin postavka bo'lgan, partiya kiritilmagan — yangi tovar narxi noma'lum: boshlang'ich narx,
    "postavka bor, partiya kiritilmagan" belgisi (sotuvchi partiyani kiritsa yo'qoladi). Postavkadan oldingi sotuv — eski
    tovar, belgisiz."""
    o = fbo(opening(10, 1, (None, 8000)), 15)
    r = compute_costs([], [Sale("a", d(12), 2), Sale("b", d(16), 2)], FIFO, o)
    assert r.sales["a"].cost == uzs(2 * 8000) and r.sales["a"].flags == frozenset()
    assert r.sales["b"].cost == uzs(2 * 8000) and r.sales["b"].flags == {CostFlag.SUPPLY_NO_LOT}


def test_no_opening_shortage_unchanged() -> None:
    """Boshlang'ich holat yo'q (sana berilmagan): lotlar tugasa — avvalgidek "lot yetmadi"."""
    r = compute_costs([lot("L", 1, 3, 9000)], [Sale("a", d(2), 5)], FIFO)
    assert r.sales["a"].flags == {CostFlag.LOT_SHORTAGE}


def test_is_estimated_ignores_exact_flags() -> None:
    # ADR-057 Q6, ADR-051: Markaziy bank kursi va tarixiy narx — aniq; boshqa belgi — taxminiy
    from upcore.costing import is_estimated

    assert not is_estimated([]) and not is_estimated(None)
    assert not is_estimated(["cbu_rate"]) and not is_estimated(["historical", "cbu_rate"])
    assert is_estimated(["cbu_rate", "cargo_missing"]) and is_estimated(["lot_shortage"])

"""B4.9: legacy partiyasini ko'chirish qoidasi (``upcore.legacy``) — haqiqiy legacy kodi bilan bir xil natija."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from upcore.fx import RateSource
from upcore.legacy import (
    LegacyBatch,
    LegacyExtra,
    LegacyLine,
    decimal_of,
    legacy_unit_costs,
    to_purchase,
    tolerance,
    worst_difference,
)
from upcore.purchasing import AllocationBase, ComponentKind, Flag, compute_lots

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from uzum_profit import costs as legacy_costs

D = Decimal
DAY = date(2026, 8, 1)


def batch(**kw: object) -> LegacyBatch:
    base: dict[str, object] = {
        "id": 7,
        "shop_id": 106121,
        "day": DAY,
        "goods_cny": D("1000"),
        "cny_rate": D("1750"),
        "cargo_usd": D("50"),
        "usd_rate": D("12600"),
        "lines": (LegacyLine(1, 10, "A-1"), LegacyLine(2, 30, None, "Yangi qalpoq")),
    }
    base.update(kw)
    return LegacyBatch(**base)  # type: ignore[arg-type]


def as_dict(b: LegacyBatch) -> dict[str, object]:
    """Legacy ``load_batches`` lug'ati (float) — haqiqiy ``uzum_profit.costs`` bilan hisoblash uchun."""

    def f(x: Decimal | None) -> float | None:
        return None if x is None else float(x)

    return {
        "id": b.id,
        "date": b.day.isoformat(),
        "cargo_date": b.cargo_day.isoformat() if b.cargo_day else None,
        "goods_cny": f(b.goods_cny),
        "cny_rate": f(b.cny_rate),
        "cargo_usd": f(b.cargo_usd),
        "usd_rate": f(b.usd_rate),
        "lines": [
            {"id": x.id, "sku": x.sku, "label": x.label, "qty": x.qty, "cny_unit": f(x.cny_unit)}
            for x in b.lines
        ],
        "extras": [{"id": e.id, "name": e.name, "amount": float(e.amount)} for e in b.extras],
    }


def new_costs(b: LegacyBatch) -> list[Decimal | None]:
    lots = compute_lots(to_purchase(b).purchase)
    return [None if x.unit_cost is None else x.unit_cost.amount for x in lots]


def test_simple_batch_matches_legacy() -> None:
    b = batch(extras=(LegacyExtra(1, "Qadoq", D("40000")),))
    old = legacy_unit_costs(b)
    # tovar 1000 CNY / 40 dona × 1750 = 43 750; kargo 50 × 12 600 / 40 = 15 750; qo'shimcha 1 000
    assert old == [D("60500"), D("60500")]
    assert new_costs(b) == old
    assert [D(str(r["unit_cost"])) for r in legacy_costs.compute_batch(as_dict(b))] == old


def test_rule_components_and_dates() -> None:
    b = batch(
        cargo_day=date(2026, 8, 20),
        lines=(LegacyLine(1, 10, "A-1", cny_unit=D("12.5")), LegacyLine(2, 30, "B-2")),
        extras=(LegacyExtra(1, "Yo'l", D("30000")), LegacyExtra(2, "Bo'sh", D(0))),
    )
    m = to_purchase(b)
    p = m.purchase
    assert m.warnings == ()
    assert p.id == "B7" and p.order_date == DAY and p.cargo_paid_date == date(2026, 8, 20)
    assert p.ready_date == date(2026, 8, 20)
    kinds = [(c.kind, c.amount.amount, c.line_ids) for c in p.components]
    assert kinds == [
        (ComponentKind.GOODS, D("125.0"), ("1",)),  # narxli qator — o'z narxida
        (ComponentKind.GOODS, D("875.0"), ("2",)),  # qolgani narxsiz qatorlarga
        (ComponentKind.CARGO, D("50"), None),
        (ComponentKind.OTHER, D("30000"), None),  # 0 so'mli qo'shimcha o'tkazib yuboriladi
    ]
    assert all(c.base is AllocationBase.UNITS for c in p.components)  # legacy — dona bo'yicha
    assert {c.rate.source for c in p.components if c.rate} == {RateSource.MANUAL}
    cargo = next(c for c in p.components if c.kind is ComponentKind.CARGO)
    assert cargo.rate is not None and cargo.rate.day == date(2026, 8, 20)
    lots = compute_lots(p)
    assert all(not x.flags for x in lots)  # qabul qilingan, kargo bor, qo'lda kurs — taxminiy emas
    assert worst_difference(legacy_unit_costs(b), new_costs(b)) <= D("0.01")


def test_ready_date_and_cargo_states() -> None:
    assert (
        batch(cargo_day=date(2026, 7, 1)).ready_date == DAY
    )  # kargo sanasi buyurtmadan oldin emas
    assert batch(cargo_day=None).ready_date == DAY  # kargo bor, sanasi yo'q — buyurtma sanasi
    on_road = batch(cargo_usd=None)
    assert on_road.ready_date is None and not on_road.cargo_entered
    p = to_purchase(on_road).purchase
    assert p.cargo_paid_date is None
    assert all(Flag.CARGO_MISSING in x.flags for x in compute_lots(p))
    # 0 — "kargo yo'q": komponent bor (belgisiz), kurs bo'lmasa ham
    free = to_purchase(batch(cargo_usd=D(0), usd_rate=None))
    assert free.warnings == ()
    assert free.purchase.cargo_paid_date == DAY
    assert all(Flag.CARGO_MISSING not in x.flags for x in compute_lots(free.purchase))


def test_missing_rates_warn_and_skip() -> None:
    m = to_purchase(batch(cny_rate=None, usd_rate=None))
    assert [c.kind for c in m.purchase.components] == []
    assert len(m.warnings) == 2 and "CNY" in m.warnings[0] and "USD" in m.warnings[1]
    b = batch(cny_rate=None, usd_rate=None)
    assert new_costs(b) == [D(0), D(0)] == legacy_unit_costs(b)  # legacy ham 0 deb oladi
    assert to_purchase(batch(cny_rate=None, goods_cny=None)).warnings == ()


def test_all_priced_ignores_total_and_overpriced_lines() -> None:
    # Hamma qator narxli — umumiy summa e'tiborga olinmaydi (legacy kabi)
    b = batch(lines=(LegacyLine(1, 2, "A", cny_unit=D(10)), LegacyLine(2, 3, "B", cny_unit=D(20))))
    assert [c.line_ids for c in to_purchase(b).purchase.components][:2] == [("1",), ("2",)]
    assert new_costs(b) == legacy_unit_costs(b)
    # Narxli qatorlar yig'indisi umumiydan katta — narxsizga 0
    over = batch(lines=(LegacyLine(1, 10, "A", cny_unit=D(200)), LegacyLine(2, 5, "B")))
    assert legacy_unit_costs(over)[1] == D(50 * 12600) / 15
    assert new_costs(over) == legacy_unit_costs(over)


def test_no_lines_and_zero_qty() -> None:
    empty = to_purchase(batch(lines=()))
    assert legacy_unit_costs(batch(lines=())) == []
    goods = [c for c in empty.purchase.components if c.kind is ComponentKind.GOODS]
    assert goods[0].line_ids is None and goods[0].amount.amount == D(
        1000
    )  # qatorlar keyin qo'shilsa ham
    assert "qatorlar yo'q" in empty.warnings[0]
    zero = to_purchase(batch(lines=(LegacyLine(1, 0, "A"),)))
    assert "dona 0" in zero.warnings[-1]
    assert legacy_unit_costs(batch(lines=(LegacyLine(1, 0, "A"),))) == []


def test_decimal_of_and_tolerance() -> None:
    assert decimal_of(None) is None and decimal_of("") is None
    assert decimal_of(0.1) == D("0.1")  # float ikkilik xatosisiz
    assert decimal_of("12,5") == D("12.5") and decimal_of(7) == D(7)
    assert tolerance(0, 3, 3) == D("0.01")
    assert tolerance(100, 2, 2) == D("0.01")
    assert tolerance(1, 5, 3) == D("0.075")
    assert worst_difference([D(1), D(2)], [D("1.5"), None]) == D(2)
    assert worst_difference([], []) == D(0)


money = st.decimals(min_value=D(0), max_value=D(100_000), places=2)
rate = st.decimals(min_value=D(1), max_value=D(20_000), places=4)


@st.composite
def batches(draw: st.DrawFn) -> LegacyBatch:
    n = draw(st.integers(1, 6))
    lines = tuple(
        LegacyLine(
            i + 1,
            draw(st.integers(0, 500)),
            f"S-{i}",
            None,
            draw(st.none() | st.decimals(min_value=D(0), max_value=D(500), places=2)),
        )
        for i in range(n)
    )
    extras = tuple(LegacyExtra(i + 1, "x", draw(money)) for i in range(draw(st.integers(0, 3))))
    return batch(
        goods_cny=draw(st.none() | money),
        cny_rate=draw(st.none() | rate),
        cargo_usd=draw(st.none() | money),
        usd_rate=draw(st.none() | rate),
        lines=lines,
        extras=extras,
    )


@settings(max_examples=300, deadline=None)
@given(batches())
def test_property_matches_real_legacy_code(b: LegacyBatch) -> None:
    """M9 qabul mezoni: ko'chirilgan har partiyaning birlik tannarxi legacy bilan bir xil (yaxlitlash qoldig'igacha)."""
    old_real = legacy_costs.compute_batch(as_dict(b))
    old = legacy_unit_costs(b)
    assert len(old) == len(old_real)
    for mine, real in zip(old, old_real, strict=True):
        assert abs(mine - D(repr(real["unit_cost"]))) < D("0.0001")  # Decimal ↔ float formula
    if not old:
        return
    model = to_purchase(b).purchase
    new = new_costs(b)
    active = sum(x.qty > 0 for x in b.lines)
    for x, o, n in zip(b.lines, old, new, strict=True):
        if x.qty == 0:
            assert n is None
            continue
        assert n is not None
        assert abs(n - o) <= tolerance(x.qty, active, len(model.components)), (x, o, n)


def test_negative_extra_is_subtracted() -> None:
    # Legacy'da manfiy qo'shimcha (masalan qaytim) ham summaga qo'shiladi — yangi hisob ham ayiradi.
    b = batch(extras=(LegacyExtra(1, "Qaytim", D("-4000")),))
    assert new_costs(b) == legacy_unit_costs(b) == [D("59400"), D("59400")]

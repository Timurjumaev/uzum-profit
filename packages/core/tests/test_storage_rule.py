"""F43 (ADR-040): Uzum pullik saqlash qoidasi."""

from datetime import date
from decimal import Decimal


def test_storage_rule_and_paid_storage() -> None:
    """F43 (ADR-040): Uzum qoidasi — aylanma (15 kunlik o'rtacha qoldiq / o'rtacha kunlik sotuv) 60 kundan oshsa
    pullik; yangi SKU (30 kun) bepul; sotuvsiz qoldiq — pullik."""
    from upcore.tariffs import paid_storage, storage_rule, storage_turnover

    rule = storage_rule(date(2026, 11, 2))
    assert rule is not None and (rule.window_days, rule.free_turnover_days, rule.new_free_days) == (
        15,
        60,
        30,
    )
    assert storage_rule(date(2026, 1, 1)) is None
    assert storage_turnover(Decimal(40), 10, 15) == Decimal(60)
    assert storage_turnover(Decimal(40), 0, 15) is None
    day, old = date(2026, 11, 2), date(2026, 8, 1)
    assert not paid_storage(Decimal(40), 10, old, day, rule)  # 60 kun — bepul
    assert paid_storage(Decimal(41), 10, old, day, rule)  # 61,5 kun — pullik
    assert paid_storage(Decimal(3), 0, None, day, rule)  # sotuvsiz, birinchi kuni noma'lum
    assert not paid_storage(Decimal(3), 0, date(2026, 10, 20), day, rule)  # yangi SKU
    assert not paid_storage(Decimal(0), 0, old, day, rule)

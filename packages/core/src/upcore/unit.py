"""M6 unit kalkulyator: bir dona uchun narx → foyda, zararsizlik narxi (F35), maqsadli marja narxi (F36).

Narx ``p`` dagi foyda/dona = p × (1 − ulush/100) − qat'iy; F35 va F36 shu tenglamaning ildizi (foyda 0 yoki p × m/100).
Ulush = komissiya% + soliq% + reklama%; qat'iy = tannarx + logistika + qadoq (F35). Logistika va komissiya — me'yoriy
(bonussiz) tariflar bilan beriladi (F40, ADR-031): kalkulyator bonus davrini narx qarori uchun hisobga olmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from upcore.metrics import breakeven_price, fixed_unit_cost, ratio, target_margin_price
from upcore.money import DecimalLike, Money, to_decimal


@dataclass(frozen=True, slots=True)
class UnitCalc:
    """Kalkulyator natijasi (bir dona). ``None`` — hisoblab bo'lmaydi (ulush ≥ 100% yoki narx 0)."""

    price: Money
    fixed: Money  # F35: tannarx + logistika + qadoq
    share_pct: Decimal  # komissiya% + soliq% + reklama%
    commission: Money
    tax: Money
    ads: Money
    profit: Money  # narxdagi foyda/dona
    margin: Decimal | None  # foyda / narx (F13 ma'nosida)
    roi: Decimal | None  # foyda / tannarx (F14 ma'nosida)
    breakeven: Money | None  # F35
    target_price: Money | None  # F36 (maqsadli marja berilgan bo'lsa)


def unit_calc(
    price: Money,
    unit_cost: Money,
    logistics: Money,
    packaging: Money,
    commission_pct: DecimalLike,
    tax_pct: DecimalLike = 0,
    ads_pct: DecimalLike = 0,
    target_margin_pct: DecimalLike | None = None,
) -> UnitCalc:
    """Bir dona iqtisodi ``price`` narxda; F35 va F36 shu qat'iy xarajat va ulushdan."""
    commission_pct, tax_pct, ads_pct = (to_decimal(x) for x in (commission_pct, tax_pct, ads_pct))
    fixed = fixed_unit_cost(unit_cost, logistics, packaging)
    commission, tax, ads = (price * (x / 100) for x in (commission_pct, tax_pct, ads_pct))
    profit = price - fixed - commission - tax - ads
    return UnitCalc(
        price=price,
        fixed=fixed,
        share_pct=commission_pct + tax_pct + ads_pct,
        commission=commission,
        tax=tax,
        ads=ads,
        profit=profit,
        margin=ratio(profit.amount, price.amount),
        roi=ratio(profit.amount, unit_cost.amount),
        breakeven=breakeven_price(fixed, commission_pct, tax_pct, ads_pct),
        target_price=(
            None
            if target_margin_pct is None
            else target_margin_price(fixed, target_margin_pct, commission_pct, tax_pct, ads_pct)
        ),
    )

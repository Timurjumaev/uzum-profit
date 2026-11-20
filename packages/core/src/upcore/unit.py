"""M6 unit kalkulyator: bir dona uchun narx → foyda, zararsizlik narxi (F35), maqsadli marja narxi (F36).

Narx ``p`` dagi foyda/dona = p × (1 − ulush/100) − qat'iy; F35 va F36 shu tenglamaning ildizi (foyda 0 yoki p × m/100).
Ulush = komissiya% + soliq% + reklama%; qat'iy = tannarx + logistika + qadoq (F35). Logistika — standart tarif (F40:
oxirgi pullik logistika, logistikasi 0 qatorlar hisobga olinmaydi).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from upcore.metrics import breakeven_price, fixed_unit_cost, ratio, target_margin_price
from upcore.money import Currency, DecimalLike, Money, quantize, to_decimal

UZS = Currency.UZS


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


# --- M13 Kalkulyator: xariddan oldingi tannarx ------------------------------------------------------------------------


class CargoBasis(StrEnum):
    """Kargo narxi nimaga ko'ra olingan (``landed_unit_cost``)."""

    WEIGHT = "weight"  # $/kg × dona vazni
    VOLUME = "volume"  # $/m³ × dona hajmi


@dataclass(frozen=True, slots=True)
class Landed:
    """Bir donaning xariddan oldingi tannarxi (so'm): tovar (1688), Xitoy ichki yetkazish, kargo, qo'shimcha."""

    goods: Money
    china: Money
    cargo: Money
    extra: Money
    cargo_basis: CargoBasis | None  # kargo hisoblanmagan bo'lsa ``None``

    @property
    def unit_cost(self) -> Money:
        return self.goods + self.china + self.cargo + self.extra


def landed_unit_cost(
    *,
    price_cny: DecimalLike,
    qty: int,
    cny_rate: DecimalLike,
    china_cny_total: DecimalLike = 0,
    weight_kg: DecimalLike | None = None,
    volume_m3: DecimalLike | None = None,
    cargo_usd_per_kg: DecimalLike | None = None,
    cargo_usd_per_m3: DecimalLike | None = None,
    usd_rate: DecimalLike | None = None,
    extra_uzs: DecimalLike = 0,
) -> Landed:
    """M13. Xariddan oldingi birlik tannarx = 1688 narxi × kurs + Xitoy ichki yetkazish / dona × kurs + kargo + qo'shimcha.

    Kargo — bir dona uchun: ``$/kg × vazn`` va/yoki ``$/m³ × hajm`` (so'mga ``usd_rate`` bilan). Ikkala narx ham berilsa
    — kattasi (kargo kompaniyalari vazn yoki hajm bo'yicha qaysi biri qimmat bo'lsa shuni oladi). Narx berilgan, lekin
    unga mos o'lcham (vazn / hajm) berilmagan bo'lsa — o'sha usul hisobga olinmaydi (taxmin qilinmaydi); kargo narxi
    yo'q — kargo 0. Kurs manbasi (CBU / qo'lda) — chaqiruvchida (tamoyil 9)."""
    if qty < 1:
        raise ValueError("dona soni kamida 1 bo'lishi kerak")
    n = Decimal(qty)
    cny = to_decimal(cny_rate)
    goods = to_decimal(price_cny) * cny
    china = to_decimal(china_cny_total) / n * cny
    options: list[tuple[CargoBasis, Decimal]] = []
    if cargo_usd_per_kg is not None and weight_kg is not None and usd_rate is not None:
        options.append(
            (
                CargoBasis.WEIGHT,
                to_decimal(cargo_usd_per_kg) * to_decimal(weight_kg) * to_decimal(usd_rate),
            )
        )
    if cargo_usd_per_m3 is not None and volume_m3 is not None and usd_rate is not None:
        options.append(
            (
                CargoBasis.VOLUME,
                to_decimal(cargo_usd_per_m3) * to_decimal(volume_m3) * to_decimal(usd_rate),
            )
        )
    basis, cargo = max(options, key=lambda o: o[1]) if options else (None, Decimal(0))
    places = UZS.places
    return Landed(
        goods=Money(quantize(goods, places), UZS),
        china=Money(quantize(china, places), UZS),
        cargo=Money(quantize(cargo, places), UZS),
        extra=Money(quantize(to_decimal(extra_uzs), places), UZS),
        cargo_basis=basis,
    )

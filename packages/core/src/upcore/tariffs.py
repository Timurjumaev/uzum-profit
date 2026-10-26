"""Uzum logistika tarifi — F37, standart tarif bo'yicha foyda va bepul davrlar — F40.

Tariflar biznes ma'lumoti (ADR-015): ishlash vaqtida bazadagi ``ref_logistics_tariffs`` dan, sana bo'yicha.
``SEED_LOGISTICS`` — boshlang'ich yozuv (08-tadqiqot.md §5, 01.06.2026 dan).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from upcore.metrics import Period, SaleLine, StatusGroup, completed
from upcore.money import Currency, Money

UZS = Currency.UZS


@dataclass(frozen=True, slots=True)
class LogisticsTariff:
    """F37 tarifi: ``valid_from`` sanasidan amal qiladi."""

    valid_from: date
    base_fee: Money  # ≤ 1 l
    per_liter: Money  # har qo'shimcha litr
    max_fee: Money
    no_dims_fee: Money  # o'lcham kiritilmagan
    sim_fee: Money  # SIM-karta
    base_liters: int = 1


SEED_LOGISTICS: tuple[LogisticsTariff, ...] = (
    LogisticsTariff(
        valid_from=date(2026, 6, 1),
        base_fee=Money.of(5250, UZS),
        per_liter=Money.of(250, UZS),
        max_fee=Money.of(50_000, UZS),
        no_dims_fee=Money.of(50_000, UZS),
        sim_fee=Money.of(20_000, UZS),
    ),
)


class TariffError(ValueError):
    """Sana uchun tarif yo'q."""


def tariff_on(tariffs: Iterable[LogisticsTariff], day: date) -> LogisticsTariff:
    """Sanada amaldagi tarif (``valid_from <= day`` bo'lgan eng oxirgisi)."""
    best = None
    for t in tariffs:
        if t.valid_from <= day and (best is None or t.valid_from > best.valid_from):
            best = t
    if best is None:
        raise TariffError(f"{day.isoformat()} uchun logistika tarifi yo'q")
    return best


def liters(length_mm: int, width_mm: int, height_mm: int) -> int:
    """F37. Hajm (l) = uzunlik × eni × balandlik (mm) / 1 000 000, butun songa yaxlitlanadi."""
    raw = Decimal(length_mm * width_mm * height_mm) / 1_000_000
    return int(raw.to_integral_value(rounding=ROUND_HALF_UP))


def logistics_fee(
    tariff: LogisticsTariff,
    dims_mm: tuple[int, int, int] | None,
    is_sim: bool = False,
) -> Money:
    """F37. Bir dona uchun Uzum logistikasi.

    ≤ 1 l: asosiy; har qo'shimcha litr +250; maksimal 50 000; o'lcham yo'q: 50 000; SIM-karta: 20 000.
    Qaytishda qaytariladi (``return-logistics-volume`` xarajati, B1.3)."""
    if is_sim:
        return tariff.sim_fee
    if dims_mm is None or min(dims_mm) <= 0:
        return tariff.no_dims_fee
    extra = max(0, liters(*dims_mm) - tariff.base_liters)
    return min(tariff.base_fee + tariff.per_liter * extra, tariff.max_fee)


# --- F40 ------------------------------------------------------------------------------------


FREE_SHARE = Decimal(
    "0.9"
)  # F40: kunlik Yakunlangan qatorlarning shu ulushida logistika 0 — bepul kun


def paid_unit_fee(logistics: Decimal, amount: int) -> Money:
    """F40: pullik qatorning bir dona logistikasi (so'm, tiyinga yaxlitlangan)."""
    return Money(logistics / amount, UZS)


def last_paid_logistics(lines: Iterable[SaleLine]) -> dict[str, Money]:
    """F40 uchun: har SKU'ning oxirgi pullik logistikasi (bir dona uchun, buyurtma sanasi bo'yicha)."""
    best: dict[str, tuple[date, Money]] = {}
    for line in completed(lines):
        if line.logistics > 0 and line.amount > 0:
            per_unit = paid_unit_fee(line.logistics, line.amount)
            if line.sku not in best or line.order_date >= best[line.sku][0]:
                best[line.sku] = (line.order_date, per_unit)
    return {sku: fee for sku, (_, fee) in best.items()}


def with_standard_logistics(
    lines: Iterable[SaleLine],
    fee_of: Callable[[SaleLine], Money | None],
    free_days: Iterable[date] | None = None,
) -> list[SaleLine]:
    """F40. Logistikasi 0 bo'lgan Yakunlangan sotuvlarga standart tarif (bir dona × ``amount``) qo'shiladi.

    ``fee_of`` — F37 yoki SKU'ning oxirgi pullik logistikasi; ``None`` qaytarsa qator o'zgarmaydi.
    ``free_days`` berilsa, faqat shu (tasdiqlangan bepul) kunlardagi qatorlar. Natija P&L'ga beriladi —
    "standart tarif bo'yicha foyda" qatori."""
    days = None if free_days is None else set(free_days)
    result = []
    for line in lines:
        if (
            line.logistics == 0
            and line.group is StatusGroup.COMPLETED
            and (days is None or line.order_date in days)
        ):
            fee = fee_of(line)
            if fee is not None:
                line = replace(line, logistics=fee.amount * line.amount)
        result.append(line)
    return result


def detect_free_days(lines: Iterable[SaleLine], threshold: Decimal = FREE_SHARE) -> list[date]:
    """F40. Bepul logistika kunlari: kunlik Yakunlangan sotuv qatorlarining ≥ 90% ida logistika 0.

    Natija — taklif; admin jadvalida tasdiqlanadi (``free_logistics_periods``)."""
    per_day: dict[date, list[int]] = {}
    for line in completed(lines):
        counts = per_day.setdefault(line.order_date, [0, 0])
        counts[0] += 1
        counts[1] += 1 if line.logistics == 0 else 0
    return sorted(d for d, (n, free) in per_day.items() if is_free_day(n, free, threshold))


def is_free_day(lines: int, free_lines: int, threshold: Decimal = FREE_SHARE) -> bool:
    """F40: kun bepul — Yakunlangan qatorlarning ≥ 90% ida logistika 0 (qator yo'q kun — bepul emas)."""
    return lines > 0 and Decimal(free_lines) / lines >= threshold


def typical_fee(counts: Mapping[Decimal, int]) -> Money | None:
    """F40 zaxira tarifi: do'konning eng ko'p uchraydigan bir dona pullik logistikasi (legacy ``std_fee_map``);
    teng bo'lsa — kattasi (foyda oshirib ko'rsatilmasin). Pullik qator yo'q — ``None``."""
    if not counts:
        return None
    fee, _ = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return Money(fee, UZS)


def standard_fee_of(
    last_by_sku: Mapping[str, Money], typical_by_shop: Mapping[str, Money]
) -> Callable[[str, str], Money | None]:
    """F40 standart tarifi (bir dona): SKU'ning oxirgi pullik logistikasi, bo'lmasa do'konning odatiy tarifi
    (``typical_fee``). F37 hajm bo'yicha tarif SKU o'lchamlari bazada bo'lgandan keyin (hozir yo'q) — o'lchamsiz
    F37 (50 000) foydani haddan tashqari kamaytirardi. Ikkalasi ham yo'q — ``None`` (qator "tarifi noma'lum")."""

    def fee(shop: str, sku: str) -> Money | None:
        return last_by_sku.get(sku) or typical_by_shop.get(shop)

    return fee


def to_periods(days: Sequence[date]) -> list[Period]:
    """Ketma-ket kunlarni davrlarga birlashtiradi (bepul davrlar jadvali uchun)."""
    result: list[Period] = []
    for d in sorted(set(days)):
        if result and result[-1].end + timedelta(days=1) == d:
            result[-1] = Period(result[-1].start, d)
        else:
            result.append(Period(d, d))
    return result

"""Uzum logistika tarifi — F37; kalkulyator uchun standart logistika/dona — F40 (ADR-035).

Tariflar biznes ma'lumoti (ADR-015): ishlash vaqtida bazadagi ``ref_logistics_tariffs`` dan, sana bo'yicha.
``SEED_LOGISTICS`` — boshlang'ich yozuv (08-tadqiqot.md §5, 01.06.2026 dan).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from upcore.metrics import SaleLine, completed
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


def paid_unit_fee(logistics: Decimal, amount: int) -> Money:
    """F40: pullik qatorning bir dona logistikasi (so'm, tiyinga yaxlitlangan)."""
    return Money(logistics / amount, UZS)


def last_paid_logistics(lines: Iterable[SaleLine]) -> dict[str, Money]:
    """F40: har SKU'ning oxirgi pullik (logistika > 0) Yakunlangan sotuvi bo'yicha bir dona logistika."""
    best: dict[str, tuple[date, Money]] = {}
    for line in completed(lines):
        if line.logistics > 0 and line.amount > 0:
            per_unit = paid_unit_fee(line.logistics, line.amount)
            if line.sku not in best or line.order_date >= best[line.sku][0]:
                best[line.sku] = (line.order_date, per_unit)
    return {sku: fee for sku, (_, fee) in best.items()}


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
    (``typical_fee``). Logistikasi 0 qatorlar (sababi qanday bo'lmasin) hisobga olinmaydi. F37 hajm bo'yicha tarif
    SKU o'lchamlari bazada bo'lgandan keyin (hozir yo'q) — o'lchamsiz F37 (50 000) foydani haddan tashqari
    kamaytirardi. Ikkalasi ham yo'q — ``None`` (qator "tarifi noma'lum")."""

    def fee(shop: str, sku: str) -> Money | None:
        return last_by_sku.get(sku) or typical_by_shop.get(shop)

    return fee


# --- F43: Uzum pullik saqlash qoidasi (ADR-040) -------------------------------------------------


@dataclass(frozen=True, slots=True)
class StorageRule:
    """Uzum FBO saqlash qoidasi (Uzum qo'llanmasi, Temur, 2026-11-03; tariflar 01.06.2026 dan): aylanma = oxirgi
    ``window_days`` kundagi o'rtacha qoldiq / shu kunlardagi o'rtacha kunlik sotuv; ``free_turnover_days`` gacha —
    bepul, oshsa — pullik (SKU ``paidStoragePriceItem`` = litr × kunlik tarif); yangi SKU dastlabki
    ``new_free_days`` kun bepul (ba'zi toifalarda 60 — hozircha farqlanmaydi)."""

    valid_from: date
    window_days: int = 15
    free_turnover_days: int = 60
    new_free_days: int = 30


SEED_STORAGE_RULES: tuple[StorageRule, ...] = (StorageRule(valid_from=date(2026, 6, 1)),)


def storage_rule(
    day: date, rules: Iterable[StorageRule] = SEED_STORAGE_RULES
) -> StorageRule | None:
    """F43: kunga amal qiladigan qoida (eng oxirgi ``valid_from ≤ day``); yo'q — ``None``."""
    valid = [r for r in rules if r.valid_from <= day]
    return max(valid, key=lambda r: r.valid_from) if valid else None


def storage_turnover(avg_stock: Decimal, sold_units: int, window_days: int) -> Decimal | None:
    """F43: aylanma (kun) = o'rtacha qoldiq / (sotilgan dona / ``window_days``); sotuv yo'q — ``None`` (cheksiz)."""
    if sold_units <= 0:
        return None
    return avg_stock * window_days / sold_units


def paid_storage(
    avg_stock: Decimal, sold_units: int, first_day: date | None, day: date, rule: StorageRule
) -> bool:
    """F43: SKU shu kuni pullik saqlashdami — qoldiq bor, yangi emas (``first_day`` — birinchi postavka yoki sotuv;
    noma'lum — yangi emas deb) va aylanma ``free_turnover_days`` dan oshgan (sotuvsiz — oshgan)."""
    if avg_stock <= 0:
        return False
    if first_day is not None and (day - first_day).days < rule.new_free_days:
        return False
    turnover = storage_turnover(avg_stock, sold_units, rule.window_days)
    return turnover is None or turnover > rule.free_turnover_days

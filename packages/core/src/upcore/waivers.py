"""Uzum bonuslari (ADR-031): vaqtinchalik bepul xarajat davrlari — **ma'lumot**, qoida emas.

Uzum ba'zan (masalan, nosozlik uchun kompensatsiya) ma'lum muddatga logistika, saqlash va boshqa xarajatlarni bepul
qiladi. Bunday davr bazada yoziladi (``fee_waivers``): do'kon yoki hammasi, sanalar, bepul turlar, sabab. Hech qanday
sana yoki tur kodda qotirilmaydi (ADR-015); Uzum keyin boshqa turdagi bonus bersa — yangi yozuv.

- Haqiqiy foyda (F3–F16) bonusdan **o'zgarmaydi**: Uzum olmagan xarajat 0 bo'lib qoladi, o'ylab topilgan summa
  qo'shilmaydi. Bonus faqat belgilash (buyurtma "bonus davri"da) va me'yoriy baho (F40, B4.3) uchun.
- Tizim **taklif** qiladi: do'kon × kun bo'yicha Yakunlangan qatorlarning ≥ 90% ida logistika 0 (F40,
  ``upcore.tariffs.is_free_day``) — mavjud yozuvlar (faol yoki rad etilgan) qoplamagan kunlar davrlarga
  birlashtiriladi. Taklif foydalanuvchi tasdiqlamaguncha hech narsaga ta'sir qilmaydi.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from upcore.expenses import ExpenseCategory
from upcore.metrics import Period
from upcore.money import Money, total
from upcore.tariffs import to_periods

SALE_LOGISTICS = "sale_logistics"  # sotuv qatoridagi logistika (F5)
MAX_DAYS = 366


def waiver_kinds() -> list[str]:
    """Bepul bo'lishi mumkin bo'lgan xarajat turlari: sotuv logistikasi (F5) va P&L'ga kiradigan Uzum xarajatlari
    (F9; kompensatsiya — kirim, bepul bo'lmaydi). Yangi Uzum toifasi ``ExpenseCategory`` ga qo'shilsa — shu yerda ham."""
    return [SALE_LOGISTICS] + [
        c.value for c in ExpenseCategory if c.in_pnl and c is not ExpenseCategory.COMPENSATION
    ]


class WaiverError(ValueError):
    """Bonus davri noto'g'ri: ``code`` — API xato kodi."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def check(start: date, end: date, kinds: Iterable[str]) -> list[str]:
    """Davr va turlarni tekshiradi; tartiblangan, takrorsiz turlar ro'yxatini qaytaradi."""
    if end < start:
        raise WaiverError("bad_period", "Davr oxiri boshidan oldin")
    if (end - start).days + 1 > MAX_DAYS:
        raise WaiverError("bad_period", f"Bonus davri {MAX_DAYS} kundan uzun")
    allowed = waiver_kinds()
    chosen = set(kinds)
    if not chosen:
        raise WaiverError("bad_kinds", "Kamida bitta bepul xarajat turi tanlanadi")
    unknown = chosen - set(allowed)
    if unknown:
        raise WaiverError("bad_kinds", f"Noma'lum tur: {', '.join(sorted(unknown))}")
    return [k for k in allowed if k in chosen]


@dataclass(frozen=True, slots=True)
class FeeWaiver:
    """Bonus davri: ``shop`` ``None`` — tashkilotning hamma do'koni; ``dismissed`` — rad etilgan taklif (faqat shu
    kunlar qayta taklif qilinmasligi uchun, boshqa hech narsaga ta'sir qilmaydi)."""

    id: str
    shop: str | None
    start: date
    end: date
    kinds: frozenset[str]
    reason: str = ""
    dismissed: bool = False

    def covers(self, shop: str, day: date) -> bool:
        return (self.shop is None or self.shop == shop) and self.start <= day <= self.end

    def overlaps(self, period: Period, shops: frozenset[str] | None = None) -> bool:
        """Davr (va tanlangan do'konlar) bilan kesishadimi; ``shops`` ``None`` — hamma do'kon."""
        shop_ok = shops is None or self.shop is None or self.shop in shops
        return shop_ok and self.start <= period.end and self.end >= period.start


def active(waivers: Iterable[FeeWaiver]) -> list[FeeWaiver]:
    return [w for w in waivers if not w.dismissed]


def waiver_for(waivers: Iterable[FeeWaiver], shop: str, day: date) -> FeeWaiver | None:
    """Buyurtma (do'kon, sana) qaysi faol bonus davriga tushadi — eng erta boshlangani (teng bo'lsa id bo'yicha)."""
    found = [w for w in active(waivers) if w.covers(shop, day)]
    return min(found, key=lambda w: (w.start, w.id)) if found else None


@dataclass(frozen=True, slots=True)
class Suggestion:
    """Taklif: do'konda logistika olinmagan kunlar davri (tasdiqlanmagan)."""

    shop: str
    period: Period
    kinds: tuple[str, ...] = (SALE_LOGISTICS,)


def suggestions(
    free_days: Mapping[str, Iterable[date]], waivers: Iterable[FeeWaiver]
) -> list[Suggestion]:
    """Aniqlangan bepul kunlardan takliflar: shu do'konni qoplaydigan har qanday yozuv (faol yoki rad etilgan)
    kunlari chiqariladi, qolgani ketma-ket davrlarga birlashadi. Tartib: do'kon, sana."""
    known = list(waivers)
    out: list[Suggestion] = []
    for shop in sorted(free_days):
        days = [d for d in free_days[shop] if not any(w.covers(shop, d) for w in known)]
        out += [Suggestion(shop, p) for p in to_periods(days)]
    return out


# --- F40: me'yoriy (bonussiz) foyda/dona -----------------------------------------------------

STORAGE = "storage"  # saqlash: SKU ``storage_price`` × qoldiq-kunlar (baholovchisi bor tur)


class NormativeState(StrEnum):
    NONE = "none"  # bonus SKU'ga ta'sir qilmagan — me'yoriy foyda = haqiqiy foyda
    ADJUSTED = "adjusted"  # bonus bilan tejalgan xarajat me'yoriy qiymat bilan ayirildi
    UNAVAILABLE = "unavailable"  # bonus ta'sir qilgan, lekin me'yoriy baho yo'q (tamoyil 9: taxmin yashirilmaydi)


@dataclass(frozen=True, slots=True)
class Normative:
    """F40 natijasi bitta SKU uchun: ``missing`` — bonus ta'sir qilgan, baholovchisi yo'q xarajat turlari."""

    state: NormativeState
    profit_per_unit: Money | None
    saved_per_unit: Money | None
    missing: tuple[str, ...] = ()


def logistics_saving(covered_units: int, fee: Money | None) -> Money | None:
    """F40: bonus davrida logistikasi 0 bo'lgan (tannarxi ma'lum) dona × me'yoriy bir dona logistika;
    tarif noma'lum — ``None`` (baho yo'q)."""
    return None if fee is None else fee * covered_units


def storage_saving(storage_price: Money | None, stock_days: int) -> Money | None:
    """F40: bonus kunlarida omborda turgan dona-kunlar × SKU ``storage_price``; narx noma'lum — ``None``."""
    return None if storage_price is None else storage_price * stock_days


def normative_profit(
    profit_per_unit: Money | None, covered_units: int, savings: Mapping[str, Money | None]
) -> Normative:
    """F40. Me'yoriy foyda/dona = foyda/dona − Σ bonus bilan tejalgan xarajatning me'yoriy qiymati / tannarxi ma'lum
    dona. ``savings`` — bonus ta'sir qilgan turlar (tur → me'yoriy qiymat yoki ``None``); bo'sh — bonus ta'sir
    qilmagan. Birorta tur baholanmagan bo'lsa natija yo'q (``UNAVAILABLE``), qisman baho berilmaydi."""
    if not savings:
        return Normative(NormativeState.NONE, profit_per_unit, None)
    missing = tuple(sorted(k for k, v in savings.items() if v is None))
    if missing or profit_per_unit is None or covered_units <= 0:
        return Normative(NormativeState.UNAVAILABLE, None, None, missing)
    saved = total([v for v in savings.values() if v is not None], profit_per_unit.currency)
    per_unit = Money(saved.amount / covered_units, saved.currency)
    return Normative(NormativeState.ADJUSTED, profit_per_unit - per_unit, per_unit)

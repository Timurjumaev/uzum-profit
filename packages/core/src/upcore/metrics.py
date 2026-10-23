"""Asosiy metrikalar F1–F19, F35–F36 (02-funksiyalar.md, "Formulalar lug'ati").

Kirish — tayyor faktlar: sotuv qatorlari (``SaleLine``), toifalangan xarajat summalari, soliq summasi.
Xarajat kodlarini toifalash (F9 manbasi) — ``upcore.expenses`` (B1.3), sotuv birlik tannarxi (F21) —
lot dvigateli (B1.5), soliq summasi (F11) — ``upcore.tax`` (B1.8). Bu modul ularni faqat yig'adi.

Nisbatlar (marja, ROI, ulushlar) — kasr ``Decimal`` (0,125 = 12,5%), 6 xona; maxraj nol bo'lsa ``None``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from upcore.money import Currency, DecimalLike, Money, allocate, quantize, to_decimal, total

TASHKENT = ZoneInfo("Asia/Tashkent")
RATIO_PLACES = 6
UZS = Currency.UZS


def ratio(numerator: DecimalLike, denominator: DecimalLike) -> Decimal | None:
    """Kasr nisbat, 6 xona; maxraj nol bo'lsa ``None`` (raqam o'ylab topilmaydi)."""
    d = to_decimal(denominator)
    if d == 0:
        return None
    return quantize(to_decimal(numerator) / d, RATIO_PLACES)


def _uzs(amount: DecimalLike) -> Money:
    return Money(to_decimal(amount), UZS)


# --- F1. Davr -------------------------------------------------------------------------------


def business_date(moment: datetime) -> date:
    """F1. Biznes sanasi — vaqtning Toshkent sanasi. Vaqt mintaqasisiz ``datetime`` qabul qilinmaydi."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("vaqt mintaqasi ko'rsatilmagan datetime")
    return moment.astimezone(TASHKENT).date()


def date_from_epoch_ms(epoch_ms: int) -> date:
    """F1. Uzum ``date`` maydoni (epoch millisekund, UTC) → Toshkent sanasi."""
    return business_date(datetime.fromtimestamp(epoch_ms / 1000, tz=UTC))


@dataclass(frozen=True, slots=True)
class Period:
    """F1. Yopiq sana oralig'i [start; end] — Toshkent kunlari, ikkala chekka ham kiradi."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"davr oxiri boshidan oldin: {self.start} > {self.end}")

    def __contains__(self, day: object) -> bool:
        return isinstance(day, date) and self.start <= day <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> Period:
        """Oldingi xuddi shu uzunlikdagi davr (solishtirish uchun)."""
        end = self.start - timedelta(days=1)
        return Period(end - timedelta(days=self.days - 1), end)


# --- F2. Holatlar ---------------------------------------------------------------------------


class StatusGroup(StrEnum):
    """F2. Sotuv qatori holat guruhlari."""

    COMPLETED = "completed"  # Yakunlangan: TO_WITHDRAW, PARTIALLY_CANCELLED (qolgan amount)
    PROCESSING = "processing"  # Jarayonda
    CANCELED = "canceled"  # Bekor
    UNKNOWN = "unknown"  # Uzum yangi holat qo'shsa — hech qaysi hisobga kirmaydi, log qilinadi


_STATUS_GROUPS = {
    "TO_WITHDRAW": StatusGroup.COMPLETED,
    "PARTIALLY_CANCELLED": StatusGroup.COMPLETED,
    "PROCESSING": StatusGroup.PROCESSING,
    "CANCELED": StatusGroup.CANCELED,
}


def status_group(status: str) -> StatusGroup:
    """F2. Uzum holati → guruh. ``PARTIALLY_CANCELLED`` ning qolgan ``amount`` i yakunlangan hisoblanadi."""
    return _STATUS_GROUPS.get(status.strip().upper(), StatusGroup.UNKNOWN)


@dataclass(frozen=True, slots=True)
class SaleLine:
    """``finance/orders`` qatori (so'mda). ``commission`` va ``logistics`` — qator bo'yicha jami.

    ``unit_cost`` — F21 dan sotuvning birlik tannarxi; noma'lum bo'lsa ``None``.
    """

    sku: str
    order_date: date
    status: str
    sell_price: Decimal
    amount: int
    commission: Decimal = Decimal(0)
    logistics: Decimal = Decimal(0)
    seller_profit: Decimal | None = None
    amount_returns: int = 0
    unit_cost: Decimal | None = None

    @property
    def group(self) -> StatusGroup:
        return status_group(self.status)

    @property
    def revenue(self) -> Decimal:
        return to_decimal(self.sell_price) * self.amount

    @property
    def payout(self) -> Decimal:
        """F6 qator bo'yicha: tushum − komissiya − logistika."""
        return self.revenue - to_decimal(self.commission) - to_decimal(self.logistics)

    @property
    def cogs(self) -> Decimal | None:
        """F7 qator bo'yicha; tannarx noma'lum bo'lsa ``None``."""
        return None if self.unit_cost is None else to_decimal(self.unit_cost) * self.amount


def _in_group(lines: Iterable[SaleLine], group: StatusGroup) -> list[SaleLine]:
    return [line for line in lines if line.group is group]


def completed(lines: Iterable[SaleLine]) -> list[SaleLine]:
    """F2. Yakunlangan qatorlar."""
    return _in_group(lines, StatusGroup.COMPLETED)


def in_period(lines: Iterable[SaleLine], period: Period) -> list[SaleLine]:
    """F1. Buyurtma sanasi davrga tushgan qatorlar."""
    return [line for line in lines if line.order_date in period]


# --- F3–F8 ----------------------------------------------------------------------------------


def revenue(lines: Iterable[SaleLine]) -> Money:
    """F3. Tushum = Σ ``sellPrice`` × ``amount`` (Yakunlangan)."""
    return _uzs(sum((line.revenue for line in completed(lines)), Decimal(0)))


def commission(lines: Iterable[SaleLine]) -> Money:
    """F4. Uzum komissiyasi = Σ ``commission`` (Yakunlangan)."""
    return _uzs(sum((to_decimal(line.commission) for line in completed(lines)), Decimal(0)))


def logistics(lines: Iterable[SaleLine]) -> Money:
    """F5. Logistika = Σ ``logisticDeliveryFee`` (Yakunlangan)."""
    return _uzs(sum((to_decimal(line.logistics) for line in completed(lines)), Decimal(0)))


def payout(lines: Iterable[SaleLine]) -> Money:
    """F6. Uzum to'lovi = F3 − F4 − F5."""
    items = completed(lines)
    return revenue(items) - commission(items) - logistics(items)


def payout_mismatches(lines: Iterable[SaleLine], tolerance: DecimalLike = 1) -> list[SaleLine]:
    """F6 tekshiruvi: ``sellerProfit`` hisobdan ``tolerance`` so'mdan ko'p farq qilgan qatorlar (log uchun)."""
    tol = to_decimal(tolerance)
    return [
        line
        for line in completed(lines)
        if line.seller_profit is not None
        and abs(to_decimal(line.seller_profit) - line.payout) > tol
    ]


def cogs(lines: Iterable[SaleLine]) -> Money:
    """F7. Tannarx = Σ birlik tannarx (F21) × ``amount`` (Yakunlangan, tannarxi ma'lum qatorlar)."""
    known = (line.cogs for line in completed(lines))
    return _uzs(sum((c for c in known if c is not None), Decimal(0)))


def gross_profit(lines: Iterable[SaleLine]) -> Money:
    """F8. Yalpi foyda = F6 − F7 (tannarxi ma'lum qatorlar bo'yicha; qamrov — F15)."""
    covered = [line for line in completed(lines) if line.unit_cost is not None]
    return payout(covered) - cogs(covered)


# --- F9–F10 ---------------------------------------------------------------------------------


def uzum_expenses(charges: Iterable[Money], compensations: Iterable[Money] = ()) -> Money:
    """F9. Uzum xarajatlari = toifalangan xarajatlar yig'indisi − kompensatsiyalar.

    Summalar musbat (``abs(paymentPrice)``), toifa va filtrlar (status, dublikat, BALANCE_CORRECTION) —
    ``upcore.expenses`` (B1.3) da.
    """
    return total(list(charges), UZS) - total(list(compensations), UZS)


@dataclass(frozen=True, slots=True)
class ManualExpense:
    """O'z xarajati: ``amount`` [start; end] kunlariga teng taqsimlanadi (bir kunlik bo'lsa start = end)."""

    amount: Money
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("xarajat davri oxiri boshidan oldin")


def own_expense_in_period(expense: ManualExpense, period: Period) -> Money:
    """F10. O'z xarajatining davrga to'g'ri keladigan qismi (kunlik teng taqsimot).

    Kumulyativ yaxlitlash: qism = round(S × oxirgi kun / N) − round(S × birinchi kun / N), shuning uchun
    ketma-ket davrlar (masalan, oylar) qismlarining yig'indisi xarajat summasiga tiyinigacha teng.
    """
    total_days = (expense.end - expense.start).days + 1
    first = max(period.start, expense.start)
    last = min(period.end, expense.end)
    if last < first:
        return Money.zero(expense.amount.currency)
    before = (first - expense.start).days
    through = (last - expense.start).days + 1
    s, cur = expense.amount.amount, expense.amount.currency
    return Money(s * through / total_days, cur) - Money(s * before / total_days, cur)


def own_expenses(expenses: Iterable[ManualExpense], period: Period) -> Money:
    """F10. Davrdagi o'z xarajatlari yig'indisi (so'mda kiritilgan xarajatlar)."""
    return total([own_expense_in_period(e, period) for e in expenses], UZS)


# --- F12–F15 --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProfitSummary:
    """Hisob varag'i: F3 → F12, F13–F15. Qamrov < 100% bo'lsa "tannarxsiz qism" alohida."""

    revenue: Money  # F3
    commission: Money  # F4
    logistics: Money  # F5
    payout: Money  # F6
    cogs: Money  # F7
    gross_profit: Money  # F8 (tannarxi ma'lum qism)
    uzum_expenses: Money  # F9 (to'liq)
    own_expenses: Money  # F10 (to'liq)
    tax: Money  # F11 (to'liq)
    coverage: Decimal  # F15, 0..1
    expenses_deducted: Money  # (F9 + F10 + F11) × qamrov
    net_profit: Money  # F12
    uncovered_revenue: Money  # tannarxsiz qism tushumi
    uncovered_payout: Money  # tannarxsiz qism Uzum to'lovi
    uncovered_expenses: Money  # tannarxsiz qismga to'g'ri keladigan xarajatlar
    uncovered_lines: int

    @property
    def margin(self) -> Decimal | None:
        """F13. Marja = F12 / F3."""
        return ratio(self.net_profit.amount, self.revenue.amount)

    @property
    def roi(self) -> Decimal | None:
        """F14. ROI = F12 / F7."""
        return ratio(self.net_profit.amount, self.cogs.amount)


def profit_summary(
    lines: Iterable[SaleLine],
    uzum_expenses: Money,
    own_expenses: Money,
    tax: Money,
) -> ProfitSummary:
    """F12 sof foyda va F15 tannarx qamrovi.

    Qamrov = tannarxi ma'lum qatorlar tushumi / F3. Sof foyda = (ma'lum qism F6 − F7) − (F9 + F10 + F11) ×
    qamrov; qolgan xarajatlar va tannarxsiz qatorlar "tannarxsiz qism"da ko'rsatiladi (legacy hamma
    xarajatni ayirib foydani kam ko'rsatardi). Tushum nol bo'lsa qamrov 1 — xarajatlar to'liq ayriladi.
    """
    done = completed(lines)
    covered = [line for line in done if line.unit_cost is not None]
    uncovered = [line for line in done if line.unit_cost is None]
    rev, covered_rev = revenue(done), revenue(covered)
    share = ratio(covered_rev.amount, rev.amount)
    overhead = uzum_expenses + own_expenses + tax
    if share is None:
        coverage, deducted = Decimal(1), overhead
    else:
        # Ayriladigan qism aniq nisbatdan (yaxlitlangan qamrovdan emas) hisoblanadi.
        coverage = share
        deducted = Money(overhead.amount * covered_rev.amount / rev.amount, UZS)
    gross = gross_profit(covered)
    return ProfitSummary(
        revenue=rev,
        commission=commission(done),
        logistics=logistics(done),
        payout=payout(done),
        cogs=cogs(covered),
        gross_profit=gross,
        uzum_expenses=uzum_expenses,
        own_expenses=own_expenses,
        tax=tax,
        coverage=coverage,
        expenses_deducted=deducted,
        net_profit=gross - deducted,
        uncovered_revenue=revenue(uncovered),
        uncovered_payout=payout(uncovered),
        uncovered_expenses=overhead - deducted,
        uncovered_lines=len(uncovered),
    )


# --- F16–F18 --------------------------------------------------------------------------------


def _units(lines: Iterable[SaleLine], group: StatusGroup) -> int:
    return sum(line.amount for line in lines if line.group is group)


def realization_rate(window: Iterable[SaleLine], min_units: int = 50) -> Decimal | None:
    """F16. R = yakuniy holatga yetgan donalar ichida Yakunlangan ulushi.

    ``window`` — do'konning oxirgi 90 kunidagi qatorlar (davrni chaqiruvchi tanlaydi). Yakuniy donalar
    ``min_units`` dan kam bo'lsa ``None`` (R ko'rsatilmaydi).
    """
    items = list(window)
    done = _units(items, StatusGroup.COMPLETED)
    final = done + _units(items, StatusGroup.CANCELED)
    if final < min_units:
        return None
    return ratio(done, final)


@dataclass(frozen=True, slots=True)
class ExpectedProfit:
    """F16 natijasi. ``amount`` — R ma'lum bo'lmasa ``None``; tannarxsiz Jarayondagi qatorlar alohida."""

    amount: Money | None
    rate: Decimal | None
    raw: Money  # Σ (F6 − F7), R qo'llanmagan
    uncovered_lines: int


def expected_profit(lines: Iterable[SaleLine], rate: Decimal | None) -> ExpectedProfit:
    """F16. Kutilayotgan foyda = Σ (F6 − F7) Jarayondagi (tannarxi ma'lum) qatorlar × R."""
    pending = _in_group(lines, StatusGroup.PROCESSING)
    known = [line for line in pending if line.unit_cost is not None]
    raw = _uzs(sum((line.payout - (line.cogs or Decimal(0)) for line in known), Decimal(0)))
    return ExpectedProfit(
        amount=None if rate is None else raw * rate,
        rate=rate,
        raw=raw,
        uncovered_lines=len(pending) - len(known),
    )


def cancel_share(lines: Iterable[SaleLine]) -> Decimal | None:
    """F17. Bekor ulushi = Bekor / (Yakunlangan + Bekor), dona bo'yicha."""
    items = list(lines)
    canceled = _units(items, StatusGroup.CANCELED)
    return ratio(canceled, _units(items, StatusGroup.COMPLETED) + canceled)


def return_share(sold: int, returned: int) -> Decimal | None:
    """F18. Qaytish ulushi = qaytgan / (sotilgan + qaytgan) — Uzum ta'rifi (SKU ``quantityReturned``)."""
    return ratio(returned, sold + returned)


def period_return_share(lines: Iterable[SaleLine]) -> Decimal | None:
    """F18 davr bo'yicha: sotilgan = Yakunlangan ``amount``, qaytgan = Σ ``amountReturns``."""
    items = list(lines)
    return return_share(
        _units(items, StatusGroup.COMPLETED), sum(line.amount_returns for line in items)
    )


# --- F19 ------------------------------------------------------------------------------------


def drr(ads: Money, revenue_total: Money) -> Decimal | None:
    """F19. Reklama ulushi (DRR) = reklama / F3."""
    return ratio(ads.amount, revenue_total.amount)


@dataclass(frozen=True, slots=True)
class SkuAds:
    """F19 SKU bo'yicha: bog'langan + taqsimlangan reklama va ACOS."""

    linked: Money
    allocated: Money
    acos: Decimal | None

    @property
    def total(self) -> Money:
        return self.linked + self.allocated


def sku_acos(
    sku_revenue: Mapping[str, Money],
    linked_ads: Mapping[str, Money],
    unlinked_ads: Money,
    distribute: bool = True,
) -> tuple[dict[str, SkuAds], Money]:
    """F19. SKU ACOS = SKU reklamasi / SKU tushumi.

    Bog'lanmagan reklama SKU'larga tushum ulushi bo'yicha taqsimlanadi (``distribute=False`` — sozlamada
    o'chirilgan). Qaytadi: SKU natijalari va taqsimlanmay qolgan reklama (o'chirilgan yoki tushum yo'q).
    """
    skus = sorted(set(sku_revenue) | set(linked_ads))
    zero = Money.zero(UZS)
    weights = [sku_revenue.get(s, zero).amount for s in skus]
    can_split = distribute and skus and any(w > 0 for w in weights)
    shares = allocate(unlinked_ads, weights) if can_split else [zero] * len(skus)
    result = {}
    for sku, share in zip(skus, shares, strict=True):
        linked = linked_ads.get(sku, zero)
        result[sku] = SkuAds(
            linked=linked,
            allocated=share,
            acos=ratio((linked + share).amount, sku_revenue.get(sku, zero).amount),
        )
    return result, zero if can_split else unlinked_ads


# --- F35–F36 --------------------------------------------------------------------------------


def _price_for_share(fixed: Money, share_pct: Decimal) -> Money | None:
    if share_pct >= 100:
        return None
    return Money(fixed.amount / (1 - share_pct / 100), fixed.currency)


def fixed_unit_cost(unit_cost: Money, logistics_fee: Money, packaging: Money) -> Money:
    """F35. Qat'iy xarajat/dona = tannarx + logistika + qadoq."""
    return unit_cost + logistics_fee + packaging


def breakeven_price(
    fixed: Money,
    commission_pct: DecimalLike,
    tax_pct: DecimalLike = 0,
    ads_pct: DecimalLike = 0,
) -> Money | None:
    """F35. Zararsizlik narxi = qat'iy / (1 − ulush/100); ulush = komissiya% + soliq% + reklama%.

    Ulush ≥ 100% bo'lsa ``None`` — hech qanday narx foyda bermaydi.
    """
    share = to_decimal(commission_pct) + to_decimal(tax_pct) + to_decimal(ads_pct)
    return _price_for_share(fixed, share)


def target_margin_price(
    fixed: Money,
    margin_pct: DecimalLike,
    commission_pct: DecimalLike,
    tax_pct: DecimalLike = 0,
    ads_pct: DecimalLike = 0,
) -> Money | None:
    """F36. Maqsadli marja narxi = qat'iy / (1 − (ulush + m)/100)."""
    share = (
        to_decimal(commission_pct)
        + to_decimal(tax_pct)
        + to_decimal(ads_pct)
        + to_decimal(margin_pct)
    )
    return _price_for_share(fixed, share)

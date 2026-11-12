"""Asosiy metrikalar F1–F19, F35–F36 (02-funksiyalar.md, "Formulalar lug'ati").

Kirish — tayyor faktlar: sotuv qatorlari (``SaleLine``), toifalangan xarajat summalari, soliq summasi.
Xarajat kodlarini toifalash (F9 manbasi) — ``upcore.expenses`` (B1.3), sotuv birlik tannarxi (F21) —
lot dvigateli (B1.5), soliq summasi (F11) — ``upcore.tax`` (B1.8). Bu modul ularni faqat yig'adi.

Nisbatlar (marja, ROI, ulushlar) — kasr ``Decimal`` (0,125 = 12,5%), 6 xona; maxraj nol bo'lsa ``None``.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from upcore.money import Currency, DecimalLike, Money, allocate, quantize, to_decimal

TASHKENT = ZoneInfo("Asia/Tashkent")
RATIO_PLACES = 6
UZS = Currency.UZS
ZERO_UZS = Money.zero(UZS)


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


def statuses(group: StatusGroup) -> frozenset[str]:
    """F2. Guruhdagi Uzum holatlari (katta harf) — bazadan filtrlash uchun (``UNKNOWN`` — bo'sh to'plam)."""
    return frozenset(s for s, g in _STATUS_GROUPS.items() if g is group)


@dataclass(frozen=True, slots=True)
class SaleLine:
    """``finance/orders`` qatori (so'mda). ``commission`` va ``logistics`` — qator bo'yicha jami.

    ``unit_cost`` — F21 dan sotuvning birlik tannarxi; noma'lum bo'lsa ``None``. ``estimated`` — tannarxda F22
    taxminiy belgisi bor. ``issued`` — tovar xaridorga topshirilgan (``dateIssued`` bor; F5, ADR-037).
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
    shop: str = ""
    estimated: bool = False
    issued: bool = False

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

    @property
    def gross_profit(self) -> Decimal | None:
        """F8 qator bo'yicha: F6 − F7; tannarx noma'lum bo'lsa ``None``."""
        cost = self.cogs
        return None if cost is None else self.payout - cost


def _in_group(lines: Iterable[SaleLine], group: StatusGroup) -> list[SaleLine]:
    return [line for line in lines if line.group is group]


def completed(lines: Iterable[SaleLine]) -> list[SaleLine]:
    """F2. Yakunlangan qatorlar."""
    return _in_group(lines, StatusGroup.COMPLETED)


COUNTED = frozenset({StatusGroup.COMPLETED, StatusGroup.PROCESSING})


def counted(lines: Iterable[SaleLine]) -> list[SaleLine]:
    """F2 (ADR-036): hisobga olinadigan qatorlar — Yakunlangan va Jarayonda. Jarayondagi qator Uzum hozir bergan
    qiymatlar bilan kiradi; bekor bo'lsa Uzum uni 0 qilib beradi va u o'zi chiqib ketadi."""
    return [line for line in lines if line.group in COUNTED]


def in_period(lines: Iterable[SaleLine], period: Period) -> list[SaleLine]:
    """F1. Buyurtma sanasi davrga tushgan qatorlar."""
    return [line for line in lines if line.order_date in period]


# --- F3–F8 ----------------------------------------------------------------------------------


def revenue(lines: Iterable[SaleLine]) -> Money:
    """F3. Tushum = Σ ``sellPrice`` × ``amount`` (Yakunlangan + Jarayonda, ADR-036)."""
    return _uzs(sum((line.revenue for line in counted(lines)), Decimal(0)))


def commission(lines: Iterable[SaleLine]) -> Money:
    """F4. Uzum komissiyasi = Σ ``commission`` (Yakunlangan + Jarayonda)."""
    return _uzs(sum((to_decimal(line.commission) for line in counted(lines)), Decimal(0)))


def logistics(lines: Iterable[SaleLine]) -> Money:
    """F5. Logistika = Σ ``logisticDeliveryFee`` (Yakunlangan + Jarayonda) — Uzum bergan qiymat. Uzum logistikani tovar
    punktdan olib ketilganda yozadi; undan oldingi Jarayondagi qator (``logistics_due``) uchun kutilayotgan logistika
    F40 bo'yicha taxminiy qo'shiladi — ``upcore.pnl.build_cells`` (ADR-037)."""
    return _uzs(sum((to_decimal(line.logistics) for line in counted(lines)), Decimal(0)))


def expected_logistics(fee: Money, units: int) -> Money:
    """F5 (ADR-037): Uzum hali yozmagan Jarayondagi logistika taxmini = F40 standart logistika/dona × dona."""
    return Money(fee.amount * units, fee.currency)


def with_expected_logistics(line: SaleLine, fee: Money | None) -> tuple[SaleLine, Money | None]:
    """F5 (ADR-037): Uzum logistikasini hali yozmagan qator (``logistics_due``) — logistikasi taxmin bilan to'ldirilgan
    nusxa (F6, F8 shundan) va taxmin summasi. Boshqa qator yoki tarif noma'lum — o'zgarmaydi, taxmin ``None``."""
    if fee is None or not logistics_due(line):
        return line, None
    est = expected_logistics(fee, line.amount)
    return replace(line, logistics=est.amount), est


def logistics_due(line: SaleLine) -> bool:
    """F5 (ADR-037): Uzum logistikasini hali yozmagan Jarayondagi qator — tovar xaridorga topshirilmagan
    (``dateIssued`` yo'q) va logistika 0. Topshirilgandan keyin 0 kelsa — 0 (ADR-035), taxmin qilinmaydi."""
    return (
        line.group is StatusGroup.PROCESSING
        and not line.issued
        and to_decimal(line.logistics) == 0
        and line.amount > 0
    )


def payout(lines: Iterable[SaleLine]) -> Money:
    """F6. Uzum to'lovi = F3 − F4 − F5."""
    items = counted(lines)
    return revenue(items) - commission(items) - logistics(items)


def cogs(lines: Iterable[SaleLine]) -> Money:
    """F7. Tannarx = Σ birlik tannarx (F21) × ``amount`` (Yakunlangan + Jarayonda, tannarxi ma'lum qatorlar)."""
    known = (line.cogs for line in counted(lines))
    return _uzs(sum((c for c in known if c is not None), Decimal(0)))


def gross_profit(lines: Iterable[SaleLine]) -> Money:
    """F8. Yalpi foyda = F6 − F7 (tannarxi ma'lum qatorlar bo'yicha; qamrov — F15)."""
    covered = [line for line in counted(lines) if line.unit_cost is not None]
    return payout(covered) - cogs(covered)


@dataclass(frozen=True, slots=True)
class SaleTotals:
    """Qatorlar to'plami (masalan, do'kon × SKU × kun — ``daily_sku_metrics``) bo'yicha yig'indilar.

    Hammasi yig'iladigan (additiv) qiymatlar: kunlar yig'indisi davr natijasiga teng, nisbatlar (F13–F18) esa
    yig'indilardan hisoblanadi.
    """

    revenue: Money  # F3 (Yakunlangan + Jarayonda)
    units: int  # hisobga olingan dona (Yakunlangan + Jarayonda)
    commission: Money  # F4
    logistics: Money  # F5
    cogs: Money  # F7 (tannarxi ma'lum qatorlar)
    revenue_costed: Money  # F15 surati: tannarxi ma'lum qatorlar tushumi
    payout_costed: Money  # F6 tannarxi ma'lum qatorlar bo'yicha; F8 = payout_costed − cogs
    cogs_estimated: Money  # F22: taxminiy belgili qatorlar tannarxi (F7 ning qismi)
    returns: int  # Yakunlangan qatorlardagi Σ ``amountReturns`` (qisman qaytarish; F18 qismi)
    canceled: int  # Bekor holatdagi hamma dona (``amount`` + ``amountReturns``) — F16 R; F17/F18 bo'linishi quyida
    lines: int = 0  # hisobga olingan qatorlar soni
    uncovered_lines: int = 0  # shundan tannarxsiz (F15 "N ta sotuv tannarxsiz")
    units_costed: int = 0  # tannarxi ma'lum hisobga olingan dona (tannarx/dona, foyda/dona — M6)
    units_processing: int = (
        0  # shundan Jarayonda (yakuniy emas, ADR-036); Yakunlangan = units − units_processing
    )
    revenue_processing: Money = ZERO_UZS  # F3 ning Jarayondagi qismi
    # ADR-037: Jarayondagi qism to'liq (kutilayotgan sof foyda — F16): yuqoridagi ustunlarning shu qismi.
    commission_processing: Money = ZERO_UZS
    logistics_processing: Money = ZERO_UZS  # Uzum yozgani (taxminsiz)
    cogs_processing: Money = ZERO_UZS
    revenue_costed_processing: Money = ZERO_UZS
    payout_costed_processing: Money = ZERO_UZS
    units_costed_processing: int = 0
    lines_processing: int = 0
    uncovered_lines_processing: int = 0
    # F5 (ADR-037): Uzum logistikasini hali yozmagan Jarayondagi qatorlar (``logistics_due``) — taxmin asosi.
    units_logistics_due: int = 0
    units_logistics_due_costed: int = 0  # shundan tannarxi ma'lum qatorlar donasi
    lines_logistics_due: int = 0
    # ADR-043: Bekor holatdagi qatorlar ikkiga bo'linadi — tovar xaridorga topshirilgan (``dateIssued`` bor) — qaytarish
    # (F18), topshirilmagan — bekor (F17). Summalar ``sellPrice`` × dona (F44 yalpi GMV qismlari).
    canceled_issued: int = 0  # Bekor holat, topshirilgan dona (qaytarish)
    canceled_revenue: Money = ZERO_UZS  # Bekor holatdagi hamma dona summasi
    canceled_issued_revenue: Money = ZERO_UZS  # shundan topshirilganlari (qaytarish summasi)
    returns_revenue: Money = ZERO_UZS  # Yakunlangan qatorlardagi ``amountReturns`` summasi


def sale_totals(lines: Iterable[SaleLine]) -> SaleTotals:
    """F3–F8, F15, F17, F18, F22 yig'indilari bitta to'plam uchun (kunlik agregat jadvali manbasi). Pul va dona —
    Yakunlangan + Jarayonda (ADR-036), Jarayondagi qismi alohida (ADR-037: hamma pul ustunlari bo'yicha); F17/F18 uchun
    Yakunlangan = units − units_processing."""
    items = list(lines)
    done = counted(items)
    covered = [line for line in done if line.unit_cost is not None]
    pending = _in_group(done, StatusGroup.PROCESSING)
    pending_covered = [line for line in pending if line.unit_cost is not None]
    due = [line for line in pending if logistics_due(line)]
    canceled_lines = _in_group(items, StatusGroup.CANCELED)
    canceled_issued = [line for line in canceled_lines if line.issued]
    return SaleTotals(
        revenue=revenue(done),
        units=sum(line.amount for line in done),
        commission=commission(done),
        logistics=logistics(done),
        cogs=cogs(covered),
        revenue_costed=revenue(covered),
        payout_costed=payout(covered),
        cogs_estimated=cogs([line for line in covered if line.estimated]),
        returns=sum(line.amount_returns for line in completed(items)),
        canceled=_units(items, StatusGroup.CANCELED),
        lines=len(done),
        uncovered_lines=len(done) - len(covered),
        units_costed=sum(line.amount for line in covered),
        units_processing=sum(line.amount for line in pending),
        revenue_processing=revenue(pending),
        commission_processing=commission(pending),
        logistics_processing=logistics(pending),
        cogs_processing=cogs(pending_covered),
        revenue_costed_processing=revenue(pending_covered),
        payout_costed_processing=payout(pending_covered),
        units_costed_processing=sum(line.amount for line in pending_covered),
        lines_processing=len(pending),
        uncovered_lines_processing=len(pending) - len(pending_covered),
        units_logistics_due=sum(line.amount for line in due),
        units_logistics_due_costed=sum(line.amount for line in due if line.unit_cost is not None),
        lines_logistics_due=len(due),
        canceled_issued=_units(canceled_issued, StatusGroup.CANCELED),
        canceled_revenue=_uzs(sum((_gross_revenue(line) for line in canceled_lines), Decimal(0))),
        canceled_issued_revenue=_uzs(
            sum((_gross_revenue(line) for line in canceled_issued), Decimal(0))
        ),
        returns_revenue=_uzs(
            sum(
                (to_decimal(line.sell_price) * line.amount_returns for line in completed(items)),
                Decimal(0),
            )
        ),
    )


# --- F9–F10 ---------------------------------------------------------------------------------


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


# F12–F15 (sof foyda, marja, ROI, tannarx qamrovi) — ``upcore.pnl.Statement`` da (audit K13).


# --- F16–F18 --------------------------------------------------------------------------------


def _units(lines: Iterable[SaleLine], group: StatusGroup) -> int:
    """Guruh donasi. Bekor qatorda Uzum ``amount`` = 0 beradi, bekor qilingan dona ``amountReturns`` da (B2.11, real
    ma'lumot: 905 ta CANCELED qatorning hammasi shunday) — shuning uchun Bekor dona = ``amount`` + ``amountReturns``."""
    if group is StatusGroup.CANCELED:
        return sum(line.amount + line.amount_returns for line in lines if line.group is group)
    return sum(line.amount for line in lines if line.group is group)


def realization_rate_units(done: int, canceled: int, min_units: int = 50) -> Decimal | None:
    """F16. R = yakuniy holatga yetgan donalar ichida Yakunlangan ulushi (fakt; kutilayotgan sof foydaga
    ko'paytirilmaydi — ADR-036, ADR-037), dona yig'indilaridan (``daily_sku_metrics``: Yakunlangan =
    ``units − units_processing``, ``canceled``). Yakuniy donalar ``min_units`` dan kam bo'lsa ``None``."""
    final = done + canceled
    if final < min_units:
        return None
    return ratio(done, final)


def _gross_revenue(line: SaleLine) -> Decimal:
    """Qatorning buyurtma qilingan summasi: ``sellPrice`` × (``amount`` + ``amountReturns``) — F44 qismi."""
    return to_decimal(line.sell_price) * (line.amount + line.amount_returns)


def cancel_rate(canceled: int, gross: int) -> Decimal | None:
    """F17 dona yig'indilaridan (ADR-043): bekor / yalpi dona."""
    return ratio(canceled, gross)


def return_share(sold: int, returned: int) -> Decimal | None:
    """F18. Qaytarish ulushi = qaytgan / (sotilgan + qaytgan) — mijozga yetgan tovar ichida (Uzum ta'rifi, SKU
    ``quantityReturned``). ADR-043: sotilgan — F3 donasi (Yakunlangan + Jarayonda)."""
    return ratio(returned, sold + returned)


@dataclass(frozen=True, slots=True)
class OrderFlow:
    """Buyurtmalar oqimi (ADR-043): yalpi = sof (sotilgan, F3) + bekor (F17) + qaytarish (F18), dona va so'mda; buyurtma
    soni (F45) va o'rtacha ko'rsatkichlar (F48). Hamma maydon additiv (kunlar va do'konlar bo'yicha yig'iladi);
    nisbatlar yig'indilardan.

    Manba: ``daily_sku_metrics`` (``SaleTotals``) va buyurtma sanoqlari. ``canceled`` / ``canceled_revenue`` — Bekor
    holatdagi hamma qatorlar, ``canceled_issued*`` — shundan tovar xaridorga topshirilganlari (``dateIssued`` bor: mijoz
    olgan yoki punktda ko'rib rad etgan) — qaytarish; ``returns*`` — Yakunlangan qatorlardagi ``amountReturns``.
    """

    units: int = 0  # F3 donasi (Yakunlangan + Jarayonda)
    revenue: Money = ZERO_UZS  # F3 (sof GMV)
    canceled: int = 0
    canceled_revenue: Money = ZERO_UZS
    canceled_issued: int = 0
    canceled_issued_revenue: Money = ZERO_UZS
    returns: int = 0
    returns_revenue: Money = ZERO_UZS
    orders: int = 0  # F45 yalpi buyurtmalar (``orderId`` soni)
    orders_net: int = 0  # F45 sof buyurtmalar (kamida bitta hisobga olingan dona bor)

    def __add__(self, other: OrderFlow) -> OrderFlow:
        return OrderFlow(
            units=self.units + other.units,
            revenue=self.revenue + other.revenue,
            canceled=self.canceled + other.canceled,
            canceled_revenue=self.canceled_revenue + other.canceled_revenue,
            canceled_issued=self.canceled_issued + other.canceled_issued,
            canceled_issued_revenue=self.canceled_issued_revenue + other.canceled_issued_revenue,
            returns=self.returns + other.returns,
            returns_revenue=self.returns_revenue + other.returns_revenue,
            orders=self.orders + other.orders,
            orders_net=self.orders_net + other.orders_net,
        )

    @property
    def cancel_units(self) -> int:
        """F17. Bekor dona — topshirilmagan Bekor qatorlar (mijoz olib ketmagan, bekor qilgan, tovar yetib kelmagan)."""
        return self.canceled - self.canceled_issued

    @property
    def cancel_revenue(self) -> Money:
        """F17. Bekor summasi."""
        return self.canceled_revenue - self.canceled_issued_revenue

    @property
    def return_units(self) -> int:
        """F18. Qaytarish dona — mijoz olgan (yoki punktda ko'rib rad etgan) va qaytgan."""
        return self.canceled_issued + self.returns

    @property
    def return_revenue(self) -> Money:
        """F18. Qaytarish summasi."""
        return self.canceled_issued_revenue + self.returns_revenue

    @property
    def gross_units(self) -> int:
        """F44. Yalpi dona = sotilgan + bekor + qaytarish."""
        return self.units + self.cancel_units + self.return_units

    @property
    def gross_revenue(self) -> Money:
        """F44. Yalpi buyurtmalar summasi (yalpi GMV) = F3 + bekor summasi + qaytarish summasi."""
        return self.revenue + self.cancel_revenue + self.return_revenue

    @property
    def net_order_share(self) -> Decimal | None:
        """F45. Sof buyurtmalar ulushi = sof / yalpi buyurtmalar."""
        return ratio(self.orders_net, self.orders)

    @property
    def cancel_share(self) -> Decimal | None:
        """F17. Bekor ulushi (soni) = bekor dona / yalpi dona."""
        return cancel_rate(self.cancel_units, self.gross_units)

    @property
    def cancel_revenue_share(self) -> Decimal | None:
        """F17. Bekor ulushi (summa) = bekor summasi / yalpi GMV."""
        return ratio(self.cancel_revenue.amount, self.gross_revenue.amount)

    @property
    def return_share(self) -> Decimal | None:
        """F18. Qaytarish ulushi (soni) = qaytgan / (sotilgan + qaytgan)."""
        return return_share(self.units, self.return_units)

    @property
    def return_revenue_share(self) -> Decimal | None:
        """F18. Qaytarish ulushi (summa) = qaytarish summasi / (F3 + qaytarish summasi)."""
        return ratio(self.return_revenue.amount, (self.revenue + self.return_revenue).amount)

    @property
    def average_check(self) -> Money | None:
        """F48. O'rtacha chek = F3 / sof buyurtmalar."""
        return None if self.orders_net == 0 else Money(self.revenue.amount / self.orders_net, UZS)

    @property
    def average_price(self) -> Money | None:
        """F48. O'rtacha tovar narxi = F3 / sotilgan dona."""
        return None if self.units == 0 else Money(self.revenue.amount / self.units, UZS)

    @property
    def units_per_order(self) -> Decimal | None:
        """F48. Buyurtmadagi tovarlar = sotilgan dona / sof buyurtmalar."""
        return ratio(self.units, self.orders_net)


def order_flow(t: SaleTotals, orders: int = 0, orders_net: int = 0) -> OrderFlow:
    """``SaleTotals`` (+ buyurtma sanoqlari, F45) → ``OrderFlow``."""
    return OrderFlow(
        units=t.units,
        revenue=t.revenue,
        canceled=t.canceled,
        canceled_revenue=t.canceled_revenue,
        canceled_issued=t.canceled_issued,
        canceled_issued_revenue=t.canceled_issued_revenue,
        returns=t.returns,
        returns_revenue=t.returns_revenue,
        orders=orders,
        orders_net=orders_net,
    )


def relative_change(current: DecimalLike, previous: DecimalLike) -> Decimal | None:
    """Oldingi davrga nisbatan o'zgarish ulushi = (joriy − oldingi) / |oldingi|; oldingi 0 bo'lsa ``None``."""
    before = to_decimal(previous)
    return ratio(to_decimal(current) - before, abs(before))


def share_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    """Ulushlar o'zgarishi — punktda (0,32 − 0,29 = 0,03 → "+3 punkt"), nisbiy emas (ADR-043); biri yo'q — ``None``."""
    if current is None or previous is None:
        return None
    return quantize(current - previous, RATIO_PLACES)


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


# --- F42, F43: buyurtmaga bog'liq reklama va saqlash SKU bo'yicha (ADR-039) ----------------------


def ad_rate(ads: DecimalLike, revenue: DecimalLike) -> Decimal | None:
    """F42. Buyurtmaga bog'liq reklama ulushi = oxirgi 30 kunda topshirilgan sotuvlarga yechilgan reklama ("Xaridor
    tovarni olganida ... yechib oldik", sotuv qatoriga bog'langan) / shu sotuvlar tushumi (SKU bo'yicha; SKU'da
    topshirilgan sotuv bo'lmasa — do'kon bo'yicha). Tushum 0 bo'lsa ``None`` — taxmin qilinmaydi."""
    return ratio(ads, revenue)


def expected_ads(rate: DecimalLike, revenue: DecimalLike) -> Money:
    """F42. Kutilayotgan reklama (taxminiy, "≈") = ulush × hali topshirilmagan Jarayondagi sotuv tushumi — Uzum bu
    reklamani tovar topshirilganda yechadi, undan oldin uni sotuvga taxminan yozamiz (logistika kabi, ADR-037)."""
    return Money(quantize(to_decimal(rate) * to_decimal(revenue), UZS.places), UZS)


def storage_weights(
    stock: Mapping[str, int],
    prices: Mapping[str, DecimalLike | None],
    paid: Collection[str] | None = None,
) -> dict[str, Decimal]:
    """F43. Kunlik saqlash xarajatini SKU'larga bo'lish og'irligi = shu kungi Uzum omboridagi qoldiq × SKU saqlash
    narxi (Uzum ``paidStoragePriceItem``, dona/kun). Narxi noma'lum SKU — narxi ma'lum SKU'lar o'rtachasi bilan; hech
    birida narx yo'q — faqat qoldiq. Qoldig'i 0 SKU og'irliksiz (saqlash unga tushmaydi).

    ``paid`` — Uzum qoidasi bo'yicha pullik saqlashdagi SKU'lar (``upcore.tariffs.paid_storage``, ADR-040): berilsa va
    qoldig'i bor kamida bittasi bo'lsa — faqat ular; aks holda (qoida hech kimni topmadi, lekin Uzum yechgan) — hammasi."""
    if paid is not None:
        chosen = {s: q for s, q in stock.items() if s in paid and q > 0}
        if chosen:
            stock = chosen
    known = [
        to_decimal(p)
        for s, p in prices.items()
        if p is not None and to_decimal(p) > 0 and stock.get(s, 0) > 0
    ]
    fallback = sum(known, Decimal(0)) / len(known) if known else Decimal(1)
    out: dict[str, Decimal] = {}
    for sku, qty in stock.items():
        if qty <= 0:
            continue
        price = prices.get(sku)
        unit = to_decimal(price) if price is not None and to_decimal(price) > 0 else fallback
        out[sku] = unit * qty
    return out


# --- M4, M6: oy prognozi va SKU holat belgisi -------------------------------------------------


def run_rate(value: DecimalLike, elapsed_days: int, total_days: int) -> Decimal | None:
    """M4 "Oy prognozi" (run-rate): davrning o'tgan kunlaridagi qiymat × jami kunlar / o'tgan kunlar, 2 xona
    (summa yoki dona). Masalan, oyning 10 kunida 1 mln → 30 kunlik oyga 3 mln. O'tgan kun 0 bo'lsa ``None``."""
    if elapsed_days <= 0:
        return None
    return quantize(to_decimal(value) * total_days / elapsed_days, 2)


class ProfitLabel(StrEnum):
    """M6 SKU holat belgisi."""

    LOSS = "loss"  # Zarar: F12 < 0
    BORDERLINE = "borderline"  # Chegarada: F13 < 5%
    PROFITABLE = "profitable"  # Foydali
    NO_DATA = "no_data"  # Ma'lumot yo'q: sotuv bor, lekin hammasi tannarxsiz (F13 hisoblanmaydi)
    IDLE = "idle"  # Sotuv yo'q: davrda sotilmagan (xarajati bo'lsa ham, bo'lmasa ham) — zarar emas (B4.44)


def profit_label(
    net_profit: Money, margin: Decimal | None, borderline: DecimalLike = Decimal("0.05")
) -> ProfitLabel:
    """M6 holat belgisi F12 va F13 dan: Zarar (F12 < 0, masalan sotuvsiz reklama ham) / Chegarada
    (F13 < ``borderline``) / Foydali; marja yo'q (tannarxi ma'lum tushum 0) — Ma'lumot yo'q."""
    if net_profit.amount < 0:
        return ProfitLabel.LOSS
    if margin is None:
        return ProfitLabel.NO_DATA
    if margin < to_decimal(borderline):
        return ProfitLabel.BORDERLINE
    return ProfitLabel.PROFITABLE


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

"""Foyda va zarar (P&L) — F12–F16 hisobot qatorlari va kesimlari (02-funksiyalar.md M5; ADR-026).

Hisob eng mayda **katak**da yuritiladi: (kun, do'kon, SKU). Har katakda F3–F8, unga tushgan F9 / F10 / F11
xarajatlari va F15 qamrovi bo'yicha ayrilgan qismi. Har qanday kesim (davr, oy, do'kon, SKU, tashkilot)
— kataklar **yig'indisi**, qayta hisob emas. Shuning uchun M5 qabul mezoni o'z-o'zidan bajariladi:
oylar yig'indisi = butun davr, do'konlar / SKU'lar yig'indisi = tashkilot, P&L = bosh sahifa = SKU jadvali.

Xarajatlarni kataklarga bo'lish (F19 dagi reklama qoidasi bilan bir xil):
- SKU'ga bog'langan xarajat — o'sha kun va SKU katagiga;
- do'kon xarajati — o'sha kuni do'kon SKU'lariga yakunlangan tushum ulushida; tushum bo'lmagan kunda
  do'konning "taqsimlanmagan" katagiga (``sku=None``);
- tashkilot xarajati (o'z xarajatlari, F10) — o'sha kuni hamma do'kon SKU'lariga tushum ulushida.
O'z xarajatlari kunlarga amortizatsiya qilinadi (F10), kunlar yig'indisi xarajatga aniq teng.

Katakda F15: ayriladigan xarajat = katak xarajati × katak qamrovi (tannarxi ma'lum tushum / tushum;
tushum 0 bo'lsa 1). Qolgani — "tannarxsiz qism".

Sotuvlar ikki ko'rinishda beriladi: qatorlar (``SaleLine``) yoki katak yig'indilari (``CellSales`` —
``daily_sku_metrics`` qatori, ``upcore.metrics.sale_totals`` natijasining xom ko'rinishi). Ikkalasi bir xil
kataklar beradi.

**Yakunlangan va kutilayotgan (ADR-037; ADR-038 — nomi).** Har katakda Jarayondagi sotuvlar qismi (``Cell.processing``) alohida
yuritiladi: o'z tushumi, komissiyasi, logistikasi, tannarxi va katak xarajatlarining (F9, F10) tushum ulushidagi
qismi, o'z soliq summasi (F11) va F15. Kutilayotgan sof foyda (F16) — shu qism sof foydasi; yakunlangan sof foyda — katak
sof foydasi minus shu qism (yig'indi har doim F12 ga teng). Sotuvsiz kun xarajati (taqsimlanmagan katak) — yakunlangan qismda.
Uzum logistikasini hali yozmagan Jarayondagi qatorlar (``logistics_due``) uchun kutilayotgan logistika F40 tarifi ×
dona bilan taxminan qo'shiladi (``logistics_fee``), "taxminiy" sifatida alohida sanaladi (tamoyil 9).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple, cast

from upcore.expenses import ExpenseCategory, ExpenseRecord
from upcore.metrics import (
    ManualExpense,
    OrderFlow,
    Period,
    ProfitLabel,
    SaleLine,
    SaleTotals,
    StatusGroup,
    counted,
    expected_logistics,
    logistics_due,
    own_expense_in_period,
    profit_label,
    ratio,
)
from upcore.money import Currency, Money, quantize, split, to_decimal, total

type LogisticsFee = Callable[[str, str], Money | None]
"""F40 standart logistika/dona (do'kon, SKU kaliti) — kutilayotgan logistika taxmini uchun (ADR-037)."""

UZS = Currency.UZS
ZERO = Money.zero(UZS)
_D0 = Decimal(0)


# --- Kirish ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExpenseItem:
    """Uzum xarajati (F9) P&L uchun: ishorali summa (OUTCOME +, INCOME −), do'kon, ixtiyoriy SKU.

    ADR-039: ``processing`` — xarajat bitta sotuvga tegishli (masalan, buyurtmaga bog'liq reklama): katakda tushum
    ulushida bo'linmaydi, o'sha sotuv qismiga yoziladi (``True`` — kutilayotgan, ``False`` — yakunlangan); ``None`` —
    katak xarajati, qismlarga tushum ulushida. ``estimated`` — taxminiy summa (F42 kutilayotgan reklama, "≈").
    ``weights`` — do'kon xarajatini shu kungi SKU kataklariga berilgan og'irliklarda (F43 saqlash: qoldiq × narx)
    bo'lish; bo'sh yoki yig'indisi 0 — odatdagidek (tushum ulushida)."""

    day: date
    shop: str
    category: ExpenseCategory
    amount: Money
    sku: str | None = None
    processing: bool | None = None
    estimated: bool = False
    weights: Mapping[str, Decimal] | None = None


def expense_items(
    records: Iterable[ExpenseRecord],
    shop: str,
    sku_of: Callable[[ExpenseRecord], str | None] | None = None,
) -> list[ExpenseItem]:
    """B1.3 natijasi → P&L xarajatlari (faqat P&L'ga kiradiganlari). ``sku_of`` — bog'lanish
    (masalan, ``item_id`` / buyurtma → SKU); berilmasa do'kon darajasida."""
    return [
        ExpenseItem(r.day, shop, r.category, r.signed, sku_of(r) if sku_of else None)
        for r in records
        if r.counted
    ]


@dataclass(frozen=True, slots=True)
class OwnExpense:
    """O'z xarajati (F10): toifa va taqsimot doirasi — tashkilot (``shop=None``), do'kon yoki SKU."""

    expense: ManualExpense
    category: str
    shop: str | None = None
    sku: str | None = None
    # ADR-039: tovarga bog'langan, tovarning bir necha SKU'si bo'lsa — (do'kon, SKU) lar: shu SKU'lar kataklariga tushum
    # ulushida (kunda ularning sotuvi bo'lmasa — teng); do'kon yoki tashkilotning hamma SKU'lariga emas.
    skus: tuple[tuple[str, str], ...] = ()


class TaxBase(StrEnum):
    REVENUE = "revenue"  # F3 (standart)
    PAYOUT = "payout"  # F6


@dataclass(frozen=True, slots=True)
class TaxRule:
    """F11 (a): aylanmadan foiz. Profillar va sana bo'yicha tanlash — ``upcore.tax``."""

    rate_pct: Decimal
    base: TaxBase = TaxBase.REVENUE

    def on(self, revenue: Money, payout: Money) -> Money:
        return Money(self.amount_on(revenue.amount, payout.amount), UZS)

    def amount_on(self, revenue: Decimal, payout: Decimal) -> Decimal:
        """``on`` ning xom ko'rinishi (so'm, tiyinga yaxlitlangan) — P&L kataklari uchun."""
        base = revenue if self.base is TaxBase.REVENUE else payout
        return quantize(base * (to_decimal(self.rate_pct) / 100), UZS.places)


# F11 (ADR-058): kunning foizli qatorlari — (qator nomi, qoida). Qat'iy qatorlar o'z xarajati (F10) mexanizmi bilan
# ``tax:<nom>`` toifasida kiritiladi va hisobotda "Soliq" ostiga o'tadi.
TaxRules = tuple[tuple[str, TaxRule], ...]
TAX_PREFIX = "tax:"
LEGACY_TAX_NAME = "Soliq"

# --- Katak ----------------------------------------------------------------------------------


class CellKey(NamedTuple):
    """Katak kaliti (kortej — xeshlash tez: davrda o'n minglab katak)."""

    day: date
    shop: str
    sku: str | None  # None — do'kon (yoki tashkilot) xarajatlarining taqsimlanmagan qismi

    def order(self) -> tuple[date, str, bool, str]:
        """Barqaror tartib: kun, do'kon, SKU (taqsimlanmagan katak oxirida)."""
        return (self.day, self.shop, self.sku is None, self.sku or "")


@dataclass(slots=True)
class Cell:
    """Katak: xom ``Decimal`` (so'm, tiyinga yaxlitlangan qismlar) — tezlik uchun ``Money`` emas. Kesim natijasi
    (``Statement``) kataklar yig'indisidan bir marta yaratiladi. ``tax`` va ``deducted`` — katakda yaxlitlangan
    (kesimlar yig'indisi jamiga tiyinigacha teng bo'lishi uchun)."""

    revenue: Decimal = _D0
    commission: Decimal = _D0
    logistics: Decimal = _D0  # Uzum yozgani + kutilayotgan logistika taxmini (``logistics_est``)
    cogs: Decimal = _D0
    covered_revenue: Decimal = _D0
    covered_payout: Decimal = _D0
    units: int = 0
    covered_units: int = 0
    lines: int = 0
    uncovered_lines: int = 0
    # Xarajatlar (F9 turlari, F10 toifalari) va shundan taqsimlangani; ``None`` — yo'q (lug'at kerak bo'lganda).
    uzum: dict[ExpenseCategory, Decimal] | None = None
    own: dict[str, Decimal] | None = None
    uzum_alloc: dict[ExpenseCategory, Decimal] | None = None
    own_alloc: dict[str, Decimal] | None = None
    tax: Decimal = _D0
    tax_by: dict[str, Decimal] | None = None  # F11: foizli qatorlar bo'yicha (nomi → summa)
    deducted: Decimal = _D0
    idle: Decimal = (
        _D0  # B4.22: sotuvsiz katakda ayrilgan xarajat (sotilmagan tovar saqlashi, sotuvsiz kun)
    )
    # F5 (ADR-037): kutilayotgan logistika taxmini (F40 × dona) va uning asosi; tarif noma'lum qatorlar soni.
    logistics_est: Decimal = _D0
    units_est: int = 0
    lines_est: int = 0
    lines_est_missing: int = 0
    # ADR-036/037: shundan Jarayondagi qism (o'z xarajat ulushi, soliq va F15 bilan — ``_finish``); ``None`` — yo'q.
    processing: Cell | None = None
    # ADR-039: bitta sotuvga tegishli Uzum xarajatlari (``uzum`` ichida) — qismga tushum ulushida emas, sotuv qismiga;
    # taxminiy Uzum xarajatlari (F42, ``uzum`` ichida).
    pin_done: dict[ExpenseCategory, Decimal] | None = None
    pin_processing: dict[ExpenseCategory, Decimal] | None = None
    uzum_est: dict[ExpenseCategory, Decimal] | None = None

    def part(self) -> Cell:
        """Jarayondagi qism katagi (kerak bo'lganda yaratiladi)."""
        if self.processing is None:
            self.processing = Cell()
        return self.processing


def _uzs(amount: Decimal) -> Money:
    return Money.rounded(amount, UZS)


def _cents(amount: Decimal) -> Decimal:
    return quantize(amount, UZS.places)


def _money_map[K: Hashable](bucket: Mapping[K, Decimal]) -> dict[K, Money]:
    return {k: Money.rounded(v, UZS) for k, v in bucket.items()}


@dataclass(frozen=True, slots=True)
class CellSales:
    """Katak sotuvlari yig'indisi, xom so'm (``daily_sku_metrics`` qatori) — ``SaleTotals`` ning P&L uchun
    keragi. Ko'p katakli davrda ``Money`` yaratmaslik uchun (M4: 1 yil, 50 000 qator)."""

    revenue: Decimal  # F3
    commission: Decimal  # F4
    logistics: Decimal  # F5
    cogs: Decimal  # F7
    revenue_costed: Decimal
    payout_costed: Decimal
    units: int
    units_costed: int
    lines: int
    uncovered_lines: int
    units_processing: int = 0  # ADR-036: shundan Jarayonda
    revenue_processing: Decimal = _D0
    # ADR-037: Jarayondagi qismning qolgan ustunlari va Uzum logistikasini hali yozmagan donalar (taxmin asosi).
    commission_processing: Decimal = _D0
    logistics_processing: Decimal = _D0
    cogs_processing: Decimal = _D0
    revenue_costed_processing: Decimal = _D0
    payout_costed_processing: Decimal = _D0
    units_costed_processing: int = 0
    lines_processing: int = 0
    uncovered_lines_processing: int = 0
    units_logistics_due: int = 0
    units_logistics_due_costed: int = 0
    lines_logistics_due: int = 0

    @classmethod
    def of(cls, t: SaleTotals) -> CellSales:
        return cls(
            revenue=t.revenue.amount,
            commission=t.commission.amount,
            logistics=t.logistics.amount,
            cogs=t.cogs.amount,
            revenue_costed=t.revenue_costed.amount,
            payout_costed=t.payout_costed.amount,
            units=t.units,
            units_costed=t.units_costed,
            lines=t.lines,
            uncovered_lines=t.uncovered_lines,
            units_processing=t.units_processing,
            revenue_processing=t.revenue_processing.amount,
            commission_processing=t.commission_processing.amount,
            logistics_processing=t.logistics_processing.amount,
            cogs_processing=t.cogs_processing.amount,
            revenue_costed_processing=t.revenue_costed_processing.amount,
            payout_costed_processing=t.payout_costed_processing.amount,
            units_costed_processing=t.units_costed_processing,
            lines_processing=t.lines_processing,
            uncovered_lines_processing=t.uncovered_lines_processing,
            units_logistics_due=t.units_logistics_due,
            units_logistics_due_costed=t.units_logistics_due_costed,
            lines_logistics_due=t.lines_logistics_due,
        )


@dataclass(frozen=True, slots=True)
class Statement:
    """P&L hisoboti (bitta kesim). Hamma summalar kataklar yig'indisi."""

    revenue: Money  # F3
    commission: Money  # F4
    logistics: Money  # F5
    cogs: Money  # F7 (tannarxi ma'lum qatorlar)
    covered_revenue: Money
    covered_payout: Money
    uzum_expenses: Mapping[ExpenseCategory, Money]  # F9 turlari (kompensatsiya manfiy)
    own_expenses: Mapping[str, Money]  # F10 toifalari
    tax: Money  # F11
    expenses_deducted: Money  # F15: qamrov bo'yicha ayrilgan qism
    units: int
    lines: int
    uncovered_lines: int
    # ADR-026: shundan tushum ulushida taqsimlangan qism (do'kon / tashkilot xarajatidan SKU'larga).
    uzum_allocated: Mapping[ExpenseCategory, Money] = field(default_factory=dict)
    own_allocated: Mapping[str, Money] = field(default_factory=dict)
    # F11 (ADR-058): ``tax`` ning qatorlar bo'yicha tarkibi (foizli va qat'iy); yig'indisi ``tax`` ga teng.
    tax_lines: Mapping[str, Money] = field(default_factory=dict)
    covered_units: int = 0  # tannarxi ma'lum hisobga olingan dona
    # ADR-036: sotuvlar Yakunlangan + Jarayonda; shundan Jarayondagi (yakuniy emas) qism — "shundan jarayonda".
    units_processing: int = 0
    revenue_processing: Money = ZERO
    # ADR-037: Jarayondagi qism hisoboti (kutilayotgan sof foyda — F16); ``None`` — Jarayondagi sotuv yo'q.
    processing: Statement | None = None
    # F5 (ADR-037): ``logistics`` ning taxminiy qismi (Uzum hali yozmagan, F40 × dona), uning asosi va tarifi noma'lum
    # bo'lgani uchun taxmin qo'shilmagan qatorlar soni.
    logistics_estimated: Money = ZERO
    logistics_estimated_units: int = 0
    logistics_estimated_lines: int = 0
    logistics_missing_lines: int = 0
    # ADR-039: Uzum xarajatlarining taxminiy qismi turlar bo'yicha (F42 kutilayotgan reklama).
    uzum_estimated: Mapping[ExpenseCategory, Money] = field(default_factory=dict)
    # B4.22: shundan sotuvsiz kataklarda ayrilgan xarajat — yakunlangan qismda (sotilmagan tovar saqlashi, F43; sotuvsiz
    # kun xarajati). Yakunlangan sotuv yo'q davrda ham yakunlangan sof foyda shu sababli manfiy bo'ladi.
    idle_expenses: Money = ZERO

    @property
    def uzum_estimated_total(self) -> Money:
        return total(list(self.uzum_estimated.values()), UZS)

    @property
    def revenue_done(self) -> Money:
        """F3 ning Yakunlangan qismi (ADR-036): tushum − Jarayondagi qism."""
        return self.revenue - self.revenue_processing

    @property
    def units_done(self) -> int:
        """Yakunlangan dona (ADR-037, yakunlangan qism)."""
        return self.units - self.units_processing

    @property
    def lines_processing(self) -> int:
        return 0 if self.processing is None else self.processing.lines

    @property
    def net_profit_processing(self) -> Money:
        """F16 (ADR-037): kutilayotgan sof foyda — Jarayondagi qism sof foydasi."""
        return ZERO if self.processing is None else self.processing.net_profit

    @property
    def net_profit_done(self) -> Money:
        """ADR-037: yakunlangan sof foyda = F12 − kutilayotgan sof foyda (yig'indi doim F12)."""
        return self.net_profit - self.net_profit_processing

    @property
    def payout(self) -> Money:
        """F6 = F3 − F4 − F5."""
        return self.revenue - self.commission - self.logistics

    @property
    def gross_profit(self) -> Money:
        """F8 = F6 − F7 (tannarxi ma'lum qism)."""
        return self.covered_payout - self.cogs

    @property
    def uzum_total(self) -> Money:
        return total(list(self.uzum_expenses.values()), UZS)

    @property
    def uzum_costs(self) -> Money:
        """F46 (ADR-043). Uzum ushlab qolgan = F4 + F5 + F9 — tushumdan (F3) Uzum olib qolgan pul (F9 "Uzum xarajatlari"dan
        keng: komissiya va logistika ham)."""
        return self.commission + self.logistics + self.uzum_total

    @property
    def uzum_costs_share(self) -> Decimal | None:
        """F46. Uzum ushlab qolgan ulushi = F46 / F3."""
        return ratio(self.uzum_costs.amount, self.revenue.amount)

    @property
    def after_uzum(self) -> Money:
        """F47 (ADR-043). Uzumdan keyin qoladi = F3 − F46 (= F6 − F9); tannarx, o'z xarajatlari va soliq ayrilmagan."""
        return self.revenue - self.uzum_costs

    @property
    def own_total(self) -> Money:
        return total(list(self.own_expenses.values()), UZS)

    @property
    def allocated_total(self) -> Money:
        """Taqsimlangan xarajatlar (F9 + F10): do'kon / tashkilot xarajatining tushum ulushidagi qismi."""
        return total([*self.uzum_allocated.values(), *self.own_allocated.values()], UZS)

    @property
    def uzum_allocated_total(self) -> Money:
        """ADR-026: F9 ning tushum ulushida taqsimlangan qismi (do'kon xarajatidan SKU'larga)."""
        return total(list(self.uzum_allocated.values()), UZS)

    @property
    def uzum_direct(self) -> Money:
        """ADR-026: F9 ning to'g'ridan-to'g'ri qismi (SKU'ga bog'langan yoki o'z darajasida, taqsimlanmagan)."""
        return self.uzum_total - self.uzum_allocated_total

    @property
    def own_allocated_total(self) -> Money:
        """ADR-026: F10 ning tushum ulushida taqsimlangan qismi."""
        return total(list(self.own_allocated.values()), UZS)

    @property
    def own_direct(self) -> Money:
        """ADR-026: F10 ning to'g'ridan-to'g'ri qismi."""
        return self.own_total - self.own_allocated_total

    @property
    def direct_total(self) -> Money:
        """To'g'ridan-to'g'ri xarajatlar (F9 + F10): shu SKU'ga bog'langan yoki o'z darajasidagi."""
        return self.uzum_total + self.own_total - self.allocated_total

    @property
    def overhead(self) -> Money:
        """F9 + F10 + F11."""
        return self.uzum_total + self.own_total + self.tax

    @property
    def net_profit(self) -> Money:
        """F12 (F15 bilan): ma'lum qism yalpi foydasi − qamrov bo'yicha ayrilgan xarajatlar."""
        return self.gross_profit - self.expenses_deducted

    @property
    def all_uncosted(self) -> bool:
        """Sotuv bor, lekin hammasi tannarxsiz (F15 qamrovi 0): foyda hisoblanmaydi."""
        return self.lines > 0 and self.uncovered_lines == self.lines

    @property
    def label(self) -> ProfitLabel:
        """M6 holat belgisi (F12, F13). Davrda sotilmagan SKU — doim "Sotuv yo'q" (``IDLE``; B4.44): xarajati bormi
        (saqlash, reklama), yo'qmi yoki kompensatsiya tushganmi — farqi yo'q. "Zarar" faqat davrda sotilgan SKU uchun.
        Hamma sotuvi tannarxsiz SKU "Ma'lumot yo'q": sotuvsiz kunlardagi xarajat F15 da to'liq ayriladi, tushumi esa
        hisobga kirmaydi — manfiy son tannarx yo'qligidan chiqadi."""
        if self.lines == 0:
            return ProfitLabel.IDLE
        if self.all_uncosted:
            return ProfitLabel.NO_DATA
        return profit_label(self.net_profit, self.margin)

    @property
    def sold_at_loss(self) -> bool:
        """Davrda sotilgan (tannarxi ma'lum sotuvi bor) va F12 < 0: "zarar bilan sotilayotgan" SKU. Sotuvsiz SKU
        (faqat saqlash yoki reklama xarajati) bunga kirmaydi."""
        return self.label is ProfitLabel.LOSS

    @property
    def uncovered_revenue(self) -> Money:
        return self.revenue - self.covered_revenue

    @property
    def uncovered_payout(self) -> Money:
        return self.payout - self.covered_payout

    @property
    def uncovered_expenses(self) -> Money:
        return self.overhead - self.expenses_deducted

    @property
    def coverage(self) -> Decimal:
        """F15 tushum bo'yicha (tushum 0 bo'lsa 1)."""
        share = ratio(self.covered_revenue.amount, self.revenue.amount)
        return Decimal(1) if share is None else share

    @property
    def uncovered_share(self) -> Decimal:
        return 1 - self.coverage

    @property
    def margin(self) -> Decimal | None:
        """F13 (ADR-024): F12 / tannarxi ma'lum tushum."""
        return ratio(self.net_profit.amount, self.covered_revenue.amount)

    @property
    def roi(self) -> Decimal | None:
        """F14 = F12 / F7."""
        return ratio(self.net_profit.amount, self.cogs.amount)

    def rows(self) -> list[tuple[str, Money]]:
        """M5 hisob varag'i qatorlari tartibida: kod → summa (UI matni i18n'dan)."""
        out: list[tuple[str, Money]] = [
            ("revenue", self.revenue),
            ("commission", -self.commission),
            ("logistics", -self.logistics),
            ("payout", self.payout),
            ("cogs", -self.cogs),
            ("gross_profit", self.gross_profit),
        ]
        out += [(f"uzum:{c.value}", -a) for c, a in sorted(self.uzum_expenses.items())]
        out += [(f"own:{c}", -a) for c, a in sorted(self.own_expenses.items())]
        out += [("tax", -self.tax)]
        if len(self.tax_lines) > 1:  # bir necha qator — "Soliq" ostida alohida ko'rsatiladi
            out += [(f"{TAX_PREFIX}{n}", -a) for n, a in sorted(self.tax_lines.items())]
        if not self.uncovered_expenses.is_zero() or not self.uncovered_revenue.is_zero():
            out += [
                ("uncovered_payout", self.uncovered_payout),
                ("uncovered_expenses", self.uncovered_expenses),
            ]
        out += [("net_profit", self.net_profit)]
        return out


class FlowStep(NamedTuple):
    """F49 qatori: kalit, F-raqam, summa va yalpi buyurtmalar summasidagi (F44) ulushi (F44 = 0 — ``None``)."""

    key: str
    formula: str
    amount: Money
    share: Decimal | None


def order_to_profit(s: Statement, flow: OrderFlow) -> list[FlowStep]:
    """F49 (ADR-053). Buyurtmadan sof foydagacha: yalpi buyurtmalar summasi (F44) bo'laklarga bo'linadi — bekor (F17),
    qaytarish (F18), Uzum ushlab qolgan (F46), tannarx (F7), o'z xarajatlar (F10), soliq (F11), tannarxsiz qism (F15)
    va sof foyda (F12). Bo'laklar yig'indisi doim F44 ga teng.

    F44 = F3 + bekor + qaytarish (F3 — hisobotdagi tushum). Tannarxsiz qism = tannarxi noma'lum sotuvlarning to'lovi
    (F6) − ularga to'g'ri keladigan xarajatlar (F15): sof foydaga kirmaydi (taxmin qilinmaydi), shuning uchun alohida
    bo'lak; hamma sotuv tannarxli bo'lsa 0. Sof foyda manfiy bo'lsa — ayrilganlar F44 dan ko'p."""
    gross = s.revenue + flow.cancel_revenue + flow.return_revenue
    uncosted = s.uncovered_payout - s.uncovered_expenses
    parts = [
        ("gross_revenue", "F44", gross),
        ("cancel_revenue", "F17", flow.cancel_revenue),
        ("return_revenue", "F18", flow.return_revenue),
        ("uzum_costs", "F46", s.uzum_costs),
        ("cogs", "F7", s.cogs),
        ("own_expenses", "F10", s.own_total),
        ("tax", "F11", s.tax),
        ("uncosted", "F15", uncosted),
        ("net_profit", "F12", s.net_profit),
    ]
    return [FlowStep(k, code, m, ratio(m.amount, gross.amount)) for k, code, m in parts]


@dataclass(frozen=True, slots=True)
class Cells:
    """Davr kataklari; kesimlar shu yerdan olinadi (har kesim — kataklar yig'indisi)."""

    period: Period
    cells: Mapping[CellKey, Cell]

    @property
    def items(self) -> dict[CellKey, Statement]:
        """Har katak hisoboti (kam kataklar uchun: tekshiruv, izoh)."""
        return {k: _total([c]) for k, c in self.cells.items()}

    def within(self, period: Period, where: Callable[[CellKey], bool] | None = None) -> Cells:
        """Ichki davr (va tanlangan) kataklari — masalan, joriy va oldingi davr bitta hisobdan."""
        first, last = period.start, period.end
        return Cells(
            period,
            {
                k: c
                for k, c in self.cells.items()
                if first <= k[0] <= last and (where is None or where(k))
            },
        )

    def statement(self, where: Callable[[CellKey], bool] | None = None) -> Statement:
        """Tanlangan kataklar yig'indisi (``where`` yo'q — butun davr, tashkilot)."""
        return _total(c for k, c in self.cells.items() if where is None or where(k))

    def statements[K: Hashable](
        self, groups: Mapping[K, Callable[[CellKey], bool]]
    ) -> dict[K, Statement]:
        """Bir necha (kesishishi mumkin bo'lgan) kesim bir o'tishda: masalan, joriy va oldingi davr, bugun,
        shu oy — har biri ``statement(where)`` bilan bir xil."""
        chosen: dict[K, list[Cell]] = {g: [] for g in groups}
        tests = list(groups.items())
        for k, c in self.cells.items():
            for g, where in tests:
                if where(k):
                    chosen[g].append(c)
        return {g: _total(cells) for g, cells in chosen.items()}

    def by[K: Hashable](self, key: Callable[[CellKey], K]) -> dict[K, Statement]:
        return self.by_and_total(key)[0]

    def by_and_total[K: Hashable](
        self, key: Callable[[CellKey], K]
    ) -> tuple[dict[K, Statement], Statement]:
        """``by`` va ``statement()`` bir o'tishda: jami — guruhlar (xom) yig'indisi, kataklar yig'indisi bilan
        bir xil (summalar aniq qo'shiladi)."""
        groups: dict[K, list[Cell]] = defaultdict(list)
        for k, c in self.cells.items():
            groups[key(k)].append(c)
        rolled = {g: _roll(groups[g]) for g in sorted(groups, key=lambda g: (g is None, str(g)))}
        return {g: _statement(c) for g, c in rolled.items()}, _total(rolled.values())

    def by_month(self) -> dict[date, Statement]:
        return self.by(lambda k: k.day.replace(day=1))

    def by_day(self) -> dict[date, Statement]:
        return self.by(lambda k: k.day)

    def by_shop(self) -> dict[str, Statement]:
        return self.by(lambda k: k.shop)

    def by_sku(self) -> dict[str | None, Statement]:
        return self.by(lambda k: k.sku)


def _roll(cells: Iterable[Cell]) -> Cell:
    """Kataklar yig'indisi (xom): kesim natijasi va kesimlar jami uchun (Jarayondagi qismlar ham yig'iladi)."""
    revenue = commission = logistics = cogs = covered_revenue = covered_payout = _D0
    tax = deducted = logistics_est = idle = _D0
    units = lines = uncovered = covered_units = 0
    units_est = lines_est = lines_est_missing = 0
    uzum: dict[ExpenseCategory, Decimal] = {}
    own: dict[str, Decimal] = {}
    uzum_alloc: dict[ExpenseCategory, Decimal] = {}
    own_alloc: dict[str, Decimal] = {}
    uzum_est: dict[ExpenseCategory, Decimal] = {}
    tax_by: dict[str, Decimal] = {}
    parts: list[Cell] = []
    for c in cells:
        revenue += c.revenue
        commission += c.commission
        logistics += c.logistics
        cogs += c.cogs
        covered_revenue += c.covered_revenue
        covered_payout += c.covered_payout
        tax += c.tax
        deducted += c.deducted
        idle += c.idle
        units += c.units
        lines += c.lines
        uncovered += c.uncovered_lines
        covered_units += c.covered_units
        if c.processing is not None:
            parts.append(c.processing)
        if c.lines_est or c.lines_est_missing:
            logistics_est += c.logistics_est
            units_est += c.units_est
            lines_est += c.lines_est
            lines_est_missing += c.lines_est_missing
        if c.uzum:
            for cat, a in c.uzum.items():
                uzum[cat] = uzum.get(cat, _D0) + a
        if c.own:
            for oc, a in c.own.items():
                own[oc] = own.get(oc, _D0) + a
        if c.uzum_alloc:
            for cat, a in c.uzum_alloc.items():
                uzum_alloc[cat] = uzum_alloc.get(cat, _D0) + a
        if c.own_alloc:
            for oc, a in c.own_alloc.items():
                own_alloc[oc] = own_alloc.get(oc, _D0) + a
        if c.uzum_est:
            for cat, a in c.uzum_est.items():
                uzum_est[cat] = uzum_est.get(cat, _D0) + a
        if c.tax_by:
            for name, a in c.tax_by.items():
                tax_by[name] = tax_by.get(name, _D0) + a
    return Cell(
        revenue=revenue,
        commission=commission,
        logistics=logistics,
        cogs=cogs,
        covered_revenue=covered_revenue,
        covered_payout=covered_payout,
        units=units,
        covered_units=covered_units,
        lines=lines,
        uncovered_lines=uncovered,
        uzum=uzum,
        own=own,
        uzum_alloc=uzum_alloc,
        own_alloc=own_alloc,
        tax=tax,
        tax_by=tax_by,
        deducted=deducted,
        idle=idle,
        logistics_est=logistics_est,
        units_est=units_est,
        lines_est=lines_est,
        lines_est_missing=lines_est_missing,
        processing=_roll(parts) if parts else None,
        uzum_est=uzum_est,
    )


def _statement(c: Cell) -> Statement:
    p = c.processing
    own, own_alloc = dict(c.own or {}), dict(c.own_alloc or {})
    tax, tax_by = c.tax, dict(c.tax_by or {})
    for category in [k for k in own if k.startswith(TAX_PREFIX)]:
        # Qat'iy soliq qatori (ADR-058) F10 mexanizmi bilan taqsimlangan, lekin hisobotda "Soliq" ostida.
        amount = own.pop(category)
        own_alloc.pop(category, None)
        name = category[len(TAX_PREFIX) :]
        tax_by[name] = tax_by.get(name, _D0) + amount
        tax += amount
    return Statement(
        revenue=_uzs(c.revenue),
        commission=_uzs(c.commission),
        logistics=_uzs(c.logistics),
        cogs=_uzs(c.cogs),
        covered_revenue=_uzs(c.covered_revenue),
        covered_payout=_uzs(c.covered_payout),
        uzum_expenses=_money_map(c.uzum or {}),
        own_expenses=_money_map(own),
        tax=_uzs(tax),
        tax_lines=_money_map(tax_by),
        expenses_deducted=_uzs(c.deducted),
        units=c.units,
        lines=c.lines,
        uncovered_lines=c.uncovered_lines,
        uzum_allocated=_money_map(c.uzum_alloc or {}),
        own_allocated=_money_map(own_alloc),
        covered_units=c.covered_units,
        units_processing=0 if p is None else p.units,
        revenue_processing=ZERO if p is None else _uzs(p.revenue),
        processing=None if p is None else _statement(p),
        logistics_estimated=_uzs(c.logistics_est),
        logistics_estimated_units=c.units_est,
        logistics_estimated_lines=c.lines_est,
        logistics_missing_lines=c.lines_est_missing,
        uzum_estimated=_money_map(c.uzum_est or {}),
        idle_expenses=_uzs(c.idle),
    )


def _total(cells: Iterable[Cell]) -> Statement:
    return _statement(_roll(cells))


def _put(a: Cell, own: bool, category: str, amount: Decimal) -> None:
    """Katakka to'g'ridan-to'g'ri (taqsimlanmagan) xarajat: ``own`` — o'z xarajati toifasi (F10), aks holda Uzum
    turi (F9). Tushum ulushidagi taqsimot — ``build_cells`` ichidagi ``spread``."""
    if own:
        if a.own is None:
            a.own = {}
        a.own[category] = a.own.get(category, _D0) + amount
    else:
        c = cast(ExpenseCategory, category)
        if a.uzum is None:
            a.uzum = {}
        a.uzum[c] = a.uzum.get(c, _D0) + amount


def _add(
    bucket: dict[ExpenseCategory, Decimal] | None, category: ExpenseCategory, amount: Decimal
) -> dict[ExpenseCategory, Decimal]:
    out = {} if bucket is None else bucket
    out[category] = out.get(category, _D0) + amount
    return out


TaxArg = TaxRule | TaxRules | Callable[[date], TaxRule | TaxRules | None] | None


def _as_rules(value: TaxRule | TaxRules | None) -> TaxRules:
    if value is None:
        return ()
    if isinstance(value, TaxRule):
        return ((LEGACY_TAX_NAME, value),)
    return value


def _rules(tax: TaxArg) -> Callable[[date], TaxRules]:
    """Kun → F11 foizli qatorlari (profil sana bo'yicha bo'lsa — kun bo'yicha keshda). Bitta ``TaxRule`` — bitta
    "Soliq" qatori (eski ko'rinish)."""
    if not callable(tax):
        fixed = _as_rules(tax)
        return lambda _day: fixed
    cache: dict[date, TaxRules] = {}

    def rule(day: date) -> TaxRules:
        if day not in cache:
            cache[day] = _as_rules(tax(day))
        return cache[day]

    return rule


def _deduct(a: Cell, rules: TaxRules) -> None:
    """Katak (yoki uning qismi) foizli soliq summasi (F11, qatorlar bo'yicha) va F15 bo'yicha ayriladigan xarajati:
    xarajat × qamrov (tushum 0 bo'lsa hammasi). Qat'iy soliq qatorlari ``own`` ichida (``tax:<nom>``) — xarajat kabi."""
    a.tax = _D0
    a.tax_by = None
    if rules:
        payout = a.revenue - a.commission - a.logistics
        a.tax_by = {name: rule.amount_on(a.revenue, payout) for name, rule in rules}
        a.tax = sum(a.tax_by.values(), _D0)
    overhead = a.tax
    if a.uzum:
        overhead += sum(a.uzum.values(), _D0)
    if a.own:
        overhead += sum(a.own.values(), _D0)
    a.deducted = _D0
    if a.revenue == 0:
        a.deducted = _cents(overhead)
    elif overhead:
        a.deducted = _cents(overhead * a.covered_revenue / a.revenue)


def _finish(a: Cell, rule: TaxRules, day_share: Decimal | None = None) -> None:
    """Katak F11 va F15; Jarayondagi qism (ADR-037) katak xarajatlarining (F9, F10) tushum ulushidagi qismini oladi,
    soliq va F15 — o'z tushumidan. Yakunlangan qism = katak − Jarayondagi qism (``Statement.net_profit_done``).

    ADR-040: sotuvsiz katak (masalan, o'sha kuni sotilmagan SKU'ning saqlashi) xarajati SKU'da qoladi, qismlarga esa
    shu kuni do'kon tushumining Jarayondagi ulushida (``day_share``) bo'linadi — do'konning boshqa xarajatlari kabi;
    do'konda kun bo'yi sotuv bo'lmasa — yakunlangan qismda."""
    _deduct(a, rule)
    if a.revenue == 0:
        a.idle = a.deducted
    p = a.part() if a.pin_processing else a.processing
    share = p.revenue / a.revenue if p is not None and a.revenue > 0 and p.revenue > 0 else None
    if a.revenue == 0 and day_share and (a.uzum or a.own):
        p, share = a.part(), day_share
    if p is None:
        return
    if a.uzum and (share is not None or a.pin_processing):
        # ADR-039: bitta sotuvga tegishli xarajat (``pin_*``) bo'linmaydi — o'sha sotuv qismiga.
        pin_p, pin_d = a.pin_processing or {}, a.pin_done or {}
        p.uzum = {}
        for cat, v in a.uzum.items():
            rest = v - pin_p.get(cat, _D0) - pin_d.get(cat, _D0)
            part = (_cents(rest * share) if share is not None else _D0) + pin_p.get(cat, _D0)
            if part or share is not None:
                p.uzum[cat] = part
    if a.own and share is not None:
        p.own = {cat: _cents(v * share) for cat, v in a.own.items()}
    _deduct(p, rule)


def _days(period: Period) -> list[date]:
    return [period.start + timedelta(days=i) for i in range(period.days)]


def _estimate(a: Cell, fee: Money | None, units: int, units_costed: int, lines: int) -> None:
    """F5 (ADR-037): Uzum logistikasini hali yozmagan Jarayondagi ``units`` dona uchun kutilayotgan logistika =
    F40 tarifi × dona — katakka va uning Jarayondagi qismiga; tannarxi ma'lum donalar qismi F8 (``covered_payout``)
    dan ham ayriladi. Tarif noma'lum (pullik qator yo'q) — taxmin qo'shilmaydi, qatorlar soni sanaladi."""
    if lines == 0:
        return
    p = a.part()
    if fee is None:
        a.lines_est_missing += lines
        p.lines_est_missing += lines
        return
    est = expected_logistics(fee, units).amount
    est_costed = expected_logistics(fee, units_costed).amount
    for c in (a, p):
        c.logistics += est
        c.covered_payout -= est_costed
        c.logistics_est += est
        c.units_est += units
        c.lines_est += lines


def build_cells(
    period: Period,
    lines: Iterable[SaleLine],
    expenses: Iterable[ExpenseItem] = (),
    own_expenses: Iterable[OwnExpense] = (),
    tax: TaxArg = None,
    totals: Iterable[tuple[CellKey, CellSales]] = (),
    logistics_fee: LogisticsFee | None = None,
) -> Cells:
    """F12–F15 kataklari. Davrdan tashqari sotuv va xarajatlar e'tiborga olinmaydi.

    ``totals`` — tayyor katak yig'indilari (``CellSales``, masalan ``daily_sku_metrics``); ``lines`` bilan bir
    xil natija beradi (hisobga olinadigan qatori yo'q yig'indi katak yaratmaydi). Sotuvlar — Yakunlangan + Jarayonda
    (ADR-036), Jarayondagi qismi katakda alohida (ADR-037). ``logistics_fee`` — F40 tarifi (do'kon, SKU → dona
    logistikasi): Uzum hali yozmagan Jarayondagi logistika uchun taxmin (funksiya ``None`` qaytarsa — tarif noma'lum,
    qatorlar sanaladi); funksiyaning o'zi berilmasa — taxmin yo'q (ADR-041: Uzum 2026-11 dan logistikani buyurtma
    paytida yozadi, 0 — bepul)."""
    acc: dict[CellKey, Cell] = defaultdict(Cell)
    first, last = period.start, period.end

    def fee_of(key: CellKey) -> Money | None:
        return None if logistics_fee is None else logistics_fee(key.shop, key.sku or "")

    for key, t in totals:
        if not first <= key[0] <= last or t.lines == 0:
            continue
        a = acc[key]
        a.revenue += t.revenue
        a.commission += t.commission
        a.logistics += t.logistics
        a.cogs += t.cogs
        a.covered_revenue += t.revenue_costed
        a.covered_payout += t.payout_costed
        a.units += t.units
        a.covered_units += t.units_costed
        a.lines += t.lines
        a.uncovered_lines += t.uncovered_lines
        if t.lines_processing:
            p = a.part()
            p.revenue += t.revenue_processing
            p.commission += t.commission_processing
            p.logistics += t.logistics_processing
            p.cogs += t.cogs_processing
            p.covered_revenue += t.revenue_costed_processing
            p.covered_payout += t.payout_costed_processing
            p.units += t.units_processing
            p.covered_units += t.units_costed_processing
            p.lines += t.lines_processing
            p.uncovered_lines += t.uncovered_lines_processing
            if logistics_fee is not None:  # ADR-041: tarif funksiyasi berilmasa — taxmin o'chiq
                _estimate(
                    a,
                    fee_of(key) if t.lines_logistics_due else None,
                    t.units_logistics_due,
                    t.units_logistics_due_costed,
                    t.lines_logistics_due,
                )

    for line in counted(x for x in lines if x.order_date in period):
        key = CellKey(line.order_date, line.shop, line.sku)
        a = acc[key]
        rev = _cents(line.revenue)
        fee = _cents(to_decimal(line.commission))
        logistic = _cents(to_decimal(line.logistics))
        cost = line.cogs
        into = [a, a.part()] if line.group is StatusGroup.PROCESSING else [a]
        for c in into:
            c.revenue += rev
            c.commission += fee
            c.logistics += logistic
            c.units += line.amount
            c.lines += 1
            if cost is None:
                c.uncovered_lines += 1
            else:
                c.cogs += _cents(cost)
                c.covered_units += line.amount
                c.covered_revenue += rev
                c.covered_payout += rev - fee - logistic
        if logistics_fee is not None and logistics_due(line):
            costed = 0 if cost is None else line.amount
            _estimate(a, fee_of(key), line.amount, costed, 1)

    # Kun × do'kon bo'yicha SKU tushumlari — taqsimot og'irliklari (kataklar yaratilishidan oldin olinadi).
    sales_by_day: dict[date, list[CellKey]] = defaultdict(list)
    sales_by_shop: dict[tuple[date, str], list[CellKey]] = defaultdict(list)
    for key in sorted(acc, key=CellKey.order):
        sales_by_day[key.day].append(key)
        sales_by_shop[key.day, key.shop].append(key)
    weights_of: dict[tuple[date, str | None], tuple[list[CellKey], list[Decimal]] | None] = {}

    def targets(day: date, shop: str | None) -> tuple[list[CellKey], list[Decimal]] | None:
        """Taqsimot kataklari va og'irliklari (tushumlar) — keshda: kataklar tushumi keyin o'zgarmaydi."""
        if (day, shop) not in weights_of:
            keys = sales_by_day.get(day, []) if shop is None else sales_by_shop.get((day, shop), [])
            weights = [acc[k].revenue for k in keys]
            ok = keys and any(w > 0 for w in weights)
            weights_of[day, shop] = (keys, weights) if ok else None
        return weights_of[day, shop]

    def spread(day: date, shop: str | None, own: bool, category: str, amount: Money) -> None:
        """Summani kun bo'yicha SKU kataklariga tushum ulushida ("taqsimlangan"); tushum yo'q —
        do'kon / tashkilot darajasidagi taqsimlanmagan katakka (o'z darajasida, taqsimlanmagan).
        ``own`` — o'z xarajati (F10), aks holda Uzum xarajati (F9; ``category`` — ``ExpenseCategory``)."""
        found = targets(day, shop)
        if found is None:
            _put(acc[CellKey(day, shop or "", None)], own, category, amount.amount)
            return
        keys, weights = found
        for k, part in zip(keys, split(amount.amount, weights, UZS.places), strict=True):
            a = acc[k]  # taqsimlangan qism: ichma-ich (ko'p chaqiriladi)
            if own:
                if a.own is None:
                    a.own, a.own_alloc = {}, {}
                elif a.own_alloc is None:
                    a.own_alloc = {}
                a.own[category] = a.own.get(category, _D0) + part
                a.own_alloc[category] = a.own_alloc.get(category, _D0) + part
            else:
                c = cast(ExpenseCategory, category)
                if a.uzum is None:
                    a.uzum, a.uzum_alloc = {}, {}
                elif a.uzum_alloc is None:
                    a.uzum_alloc = {}
                a.uzum[c] = a.uzum.get(c, _D0) + part
                a.uzum_alloc[c] = a.uzum_alloc.get(c, _D0) + part

    for e in expenses:
        if e.day not in period:
            continue
        if e.weights and e.sku is None:
            # F43 (ADR-039): do'kon xarajati SKU'larga berilgan og'irliklarda (saqlash — qoldiq × narx).
            chosen = [(sku, w) for sku, w in sorted(e.weights.items()) if w > 0]
            if chosen:
                parts = split(e.amount.amount, [w for _, w in chosen], UZS.places)
                for (sku, _), share in zip(chosen, parts, strict=True):
                    _put(acc[CellKey(e.day, e.shop, sku)], False, e.category, share)
                continue
        if e.sku is not None:
            a = acc[CellKey(e.day, e.shop, e.sku)]
            amount = e.amount.amount
            _put(a, False, e.category, amount)
            if e.processing is True:
                a.pin_processing = _add(a.pin_processing, e.category, amount)
            elif e.processing is False:
                a.pin_done = _add(a.pin_done, e.category, amount)
            if e.estimated:
                a.uzum_est = _add(a.uzum_est, e.category, amount)
                if e.processing is True:
                    p = a.part()
                    p.uzum_est = _add(p.uzum_est, e.category, amount)
        else:
            spread(e.day, e.shop, False, e.category, e.amount)

    for oe in own_expenses:
        for day in _days(period):
            part = own_expense_in_period(oe.expense, Period(day, day))
            if part.is_zero():
                continue
            if oe.sku is not None:
                _put(acc[CellKey(day, oe.shop or "", oe.sku)], True, oe.category, part.amount)
            elif oe.skus:
                # ADR-039: tovarning SKU'lariga — shu kungi tushum ulushida, sotuv bo'lmasa teng.
                keys = [CellKey(day, shop, sku) for shop, sku in sorted(set(oe.skus))]
                weights = [acc[k].revenue if k in acc else _D0 for k in keys]
                if not any(w > 0 for w in weights):
                    weights = [Decimal(1)] * len(keys)
                for k, share in zip(keys, split(part.amount, weights, UZS.places), strict=True):
                    _put(acc[k], True, oe.category, share)
            else:
                spread(day, oe.shop, True, oe.category, part)

    rule_of = _rules(tax)  # F11 profili sana bo'yicha (upcore.tax), kun bo'yicha keshda
    # ADR-040: kun × do'kon tushumining Jarayondagi ulushi — sotuvsiz kataklar xarajatini qismlarga bo'lish uchun.
    day_rev: dict[tuple[date, str], list[Decimal]] = defaultdict(lambda: [_D0, _D0])
    for key, a in acc.items():
        day_total = day_rev[key.day, key.shop]
        day_total[0] += a.processing.revenue if a.processing is not None else _D0
        day_total[1] += a.revenue
    for key, a in acc.items():
        pending, whole = day_rev[key.day, key.shop]
        _finish(a, rule_of(key[0]), pending / whole if whole > 0 and pending > 0 else None)
    return Cells(period, dict(acc))


# --- Unit-iqtisod (M6) ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnitEconomics:
    """M6 jadvali ustunlari bitta kesim (SKU) uchun; maxraj nol bo'lsa ``None``.

    Tannarx/dona va foyda/dona — tannarxi ma'lum dona bo'yicha (F15: sof foyda faqat shu qism uchun)."""

    avg_price: Money | None  # F3 / dona
    commission_share: Decimal | None  # F4 / F3
    logistics_per_unit: Money | None  # F5 / dona
    cogs_per_unit: Money | None  # F7 / tannarxi ma'lum dona
    ads_per_unit: Money | None  # F19 reklamasi (bog'langan + taqsimlangan) / dona
    acos: Decimal | None  # F19 = reklama / F3
    profit_per_unit: Money | None  # F12 / tannarxi ma'lum dona


def _per(amount: Money, n: int) -> Money | None:
    return None if n == 0 else Money(amount.amount / n, amount.currency)


def unit_economics(s: Statement) -> UnitEconomics:
    """M6 unit-iqtisod kesim hisobotidan (``Cells.by_sku``): reklama — F9 ning reklama turi (F19 qoidasi bilan
    SKU'ga bog'langan va tushum ulushida taqsimlangan)."""
    ads = s.uzum_expenses.get(ExpenseCategory.ADVERTISING, ZERO)
    return UnitEconomics(
        avg_price=_per(s.revenue, s.units),
        commission_share=ratio(s.commission.amount, s.revenue.amount),
        logistics_per_unit=_per(s.logistics, s.units),
        cogs_per_unit=_per(s.cogs, s.covered_units),
        ads_per_unit=_per(ads, s.units),
        acos=ratio(ads.amount, s.revenue.amount),
        profit_per_unit=_per(s.net_profit, s.covered_units),
    )


# --- Solishtirish (yakunlangan va kutilayotgan qismlar bilan) -----------------------------


@dataclass(frozen=True, slots=True)
class CompareRow:
    """M5 ustunlari: joriy (jami), shundan yakunlangan va kutilayotgan (ADR-037), tushumga nisbatan %, oldingi davr, farq va
    o'zgarish ulushi.

    ``change`` = farq / |oldingi davr| (ishorali qiymat bo'yicha: yuqori — yaxshi); oldingi davr nol bo'lsa yoki oldingi
    davrda sotuv bo'lmasa (tushum 0 — masalan, do'kon hali ulanmagan) ``None``: aks holda foiz ma'nosiz (47 228%).
    """

    code: str
    current: Money
    share_of_revenue: Decimal | None
    previous: Money
    diff: Money
    change: Decimal | None
    processing: Money = ZERO  # ADR-037: Jarayondagi qism (kutilayotgan)
    done: Money = ZERO  # yakunlangan qism = joriy − kutilayotgan
    estimated: bool = (
        False  # ``change`` kutilayotgan qism × yakunlanish ulushi bilan (ADR-057 Q4) — taxminiy
    )


def expected_value(full: Money, processing: Money, completion: Decimal | None) -> Money:
    """ADR-057 Q4 (F16 R): qiymatning kutilgan yakuniy qismi = yakunlangan + Jarayondagi × yakunlanish ulushi.
    Ulush noma'lum (``None``) — qiymat o'zgarmaydi. Uch raqam (ADR-036/037) bunga ko'paytirilmaydi; faqat prognoz va
    "▲ %" uchun."""
    if completion is None:
        return full
    return full - processing + processing * completion


def compare(
    current: Statement, previous: Statement, completion: Decimal | None = None
) -> list[CompareRow]:
    """Ikki davr hisobot qatorlari: joriy davrda yo'q qator oldingisida bo'lsa ham ko'rsatiladi. Har qatorda joriy
    davrning Jarayondagi (kutilayotgan) va yakunlangan qismi — bir xil ``rows()`` kodlari bo'yicha (ADR-037).

    ADR-057 Q4: ``completion`` (F16 R) berilsa, o'zgarish ulushi (``change``, "▲ %") ikkala davrning kutilgan yakuniy
    qiymatlari bo'yicha — Jarayondagi qism × R (joriy davrda jarayondagi buyurtmalar ko'p, oldingisida bekorlar allaqachon
    chiqib ketgan — aks holda o'sish tizimli ravishda ko'proq ko'rinadi); shunday qatorda ``estimated``. Summalar (joriy,
    oldingi, farq) o'zgarmaydi."""
    cur, prev = dict(current.rows()), dict(previous.rows())
    part = dict(current.processing.rows()) if current.processing is not None else {}
    prev_part = dict(previous.processing.rows()) if previous.processing is not None else {}
    comparable = not previous.revenue.is_zero()
    codes = [c for c, _ in current.rows()]
    codes += [c for c in prev if c not in cur] + [c for c in part if c not in cur and c not in prev]
    rows = []
    for code in codes:
        now, before = cur.get(code, ZERO), prev.get(code, ZERO)
        pending, pending_before = part.get(code, ZERO), prev_part.get(code, ZERO)
        diff = now - before
        estimated = completion is not None and not (pending.is_zero() and pending_before.is_zero())
        change = None
        if comparable:
            if estimated:
                now_x = expected_value(now, pending, completion)
                before_x = expected_value(before, pending_before, completion)
                change = ratio((now_x - before_x).amount, abs(before_x.amount))
            else:
                change = ratio(diff.amount, abs(before.amount))
        rows.append(
            CompareRow(
                code,
                now,
                ratio(now.amount, current.revenue.amount),
                before,
                diff,
                change,
                processing=pending,
                done=now - pending,
                estimated=estimated,
            )
        )
    return rows

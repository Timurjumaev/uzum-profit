"""Xarid (partiya) birlik tannarxi — F20, belgilar — F22 (02-funksiyalar.md M9, F20, F22).

Xarid = qatorlar (tovar, dona, narx, vazn, hajm) + istalgancha xarajat komponentlari (tovar, kargo, bojxona,
qadoq ...). Har komponent kurs bilan so'mga o'tkaziladi (kurs rejimi — ``upcore.fx``: CBU, qo'lda,
kartadan yechilgan summa) va taqsimot asosiga ko'ra o'z qatorlariga bo'linadi. Taqsimot aniq: qatorlar
yig'indisi komponent summasiga tiyinigacha teng (qoldiq eng katta qatorga, ``upcore.money.allocate``).

Qatorning birlik tannarxi = qatorga tushgan komponentlar / qabul qilingan dona (hali qabul qilinmagan bo'lsa
buyurtma qilingan dona, "taxminiy").

Xarid hayoti — "Partiya yo'li" (M9, 04 §6.2): har bosqich ixtiyoriy, sanasi yoziladi; joriy bosqich — sanasi bor eng
oxirgisi. Joriy bosqichda necha kun o'tgani va keyingi bosqichning kutilgan sanasi (F25 bosqichi medianasi).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from upcore.fx import FxRate, RateSource, to_uzs
from upcore.money import Currency, Money, allocate, to_decimal, total

UZS = Currency.UZS


class ComponentKind(StrEnum):
    """Xarajat komponenti turlari (M9)."""

    GOODS = "goods"  # tovar
    CN_DELIVERY = "cn_delivery"  # Xitoy ichki yetkazish
    AGENT_FEE = "agent_fee"  # xarid komissiyasi (agent)
    CARGO = "cargo"
    CUSTOMS = "customs"  # bojxona
    PACKAGING = "packaging"  # qadoqlash
    LABELING = "labeling"  # shtrix-kod / yorliq
    UZUM_DELIVERY = "uzum_delivery"  # Uzum omboriga yetkazish
    OTHER = "other"


class AllocationBase(StrEnum):
    """Taqsimot asosi (M9). Kargo uchun standart — vazn."""

    UNITS = "units"
    WEIGHT = "weight"
    VOLUME = "volume"
    VALUE = "value"  # qatorning tovar qiymati (narx × dona) bo'yicha
    MANUAL = "manual"  # qo'lda ulushlar


# Standart taqsimot asosi (M9): kargo — vazn (vazn yo'q bo'lsa dona, ``BASE_FALLBACK``), tovar — qiymat (narx × dona;
# narx yo'q bo'lsa dona), qolganlari — dona.
DEFAULT_BASE: Mapping[ComponentKind, AllocationBase] = {
    ComponentKind.CARGO: AllocationBase.WEIGHT,
    ComponentKind.GOODS: AllocationBase.VALUE,
}


def default_base(kind: ComponentKind) -> AllocationBase:
    """Komponent turi uchun standart taqsimot asosi (M9)."""
    return DEFAULT_BASE.get(kind, AllocationBase.UNITS)


class Flag(StrEnum):
    """F22 taxminiy belgilari (lot darajasida)."""

    CARGO_MISSING = "cargo_missing"  # kargo kiritilmagan
    NOT_RECEIVED = "not_received"  # qabul qilinmagan: buyurtma donasi bilan hisoblandi
    CBU_RATE = "cbu_rate"  # kurs qo'lda emas, CBU (haqiqiy to'langan kurs emas)
    BASE_FALLBACK = "base_fallback"  # vazn/hajm/qiymat yo'q — dona bo'yicha bo'lindi


class PurchaseError(ValueError):
    """Xarid ma'lumoti hisoblab bo'lmaydigan holatda (raqam o'ylab topilmaydi)."""


@dataclass(frozen=True, slots=True)
class PurchaseLine:
    """Xarid qatori. ``unit_price`` — valyutada dona narxi (ixtiyoriy); vazn (kg) va hajm (m³) — donaga."""

    id: str
    ordered_qty: int
    received_qty: int | None = None
    unit_price: Money | None = None
    unit_weight: Decimal | None = None
    unit_volume: Decimal | None = None

    def __post_init__(self) -> None:
        if self.ordered_qty < 0 or (self.received_qty is not None and self.received_qty < 0):
            raise PurchaseError(f"qator {self.id}: dona manfiy bo'lishi mumkin emas")

    @property
    def qty(self) -> int:
        """Tannarx uchun dona: qabul qilingan, yo'q bo'lsa buyurtma qilingan."""
        return self.ordered_qty if self.received_qty is None else self.received_qty


@dataclass(frozen=True, slots=True)
class CostComponent:
    """Xarajat komponenti. ``rate`` so'mdan boshqa valyutada shart (fx: CBU / qo'lda / effektiv).

    ``line_ids`` — tegishli qatorlar (``None`` — hammasi); ``manual_shares`` — ``MANUAL`` asos uchun.
    """

    kind: ComponentKind
    amount: Money
    rate: FxRate | None = None
    base: AllocationBase = AllocationBase.UNITS
    line_ids: tuple[str, ...] | None = None
    manual_shares: Mapping[str, Decimal] = field(default_factory=dict)

    def in_uzs(self) -> Money:
        """F20: summa × kurs → so'm."""
        return to_uzs(self.amount, self.rate)


@dataclass(frozen=True, slots=True)
class Purchase:
    """Xarid. ``goods_rate`` — qatorlardagi valyuta narxlarini so'mga o'tkazish kursi (``VALUE`` asos va
    ``residual_goods`` uchun). Sanalar — lot tayyor sanasi uchun (F21)."""

    id: str
    lines: tuple[PurchaseLine, ...]
    components: tuple[CostComponent, ...] = ()
    goods_rate: FxRate | None = None
    order_date: date | None = None
    cargo_paid_date: date | None = None
    received_date: date | None = None

    @property
    def ready_date(self) -> date | None:
        """F21: lot sotuvga tayyor sanasi = qabul sanasi; yo'q bo'lsa kargo to'langan sana; ikkalasi ham
        yo'q — ``None`` ("yo'lda")."""
        return self.received_date or self.cargo_paid_date


@dataclass(frozen=True, slots=True)
class LotCost:
    """Qator natijasi (lot): komponentlar bo'yicha tarkib, jami, birlik tannarx va F22 belgilari."""

    line_id: str
    qty: int
    breakdown: Mapping[ComponentKind, Money]
    total: Money
    unit_cost: Money | None  # dona 0 bo'lsa None
    flags: frozenset[Flag]

    @property
    def estimated(self) -> bool:
        return bool(self.flags)


def residual_goods(
    goods_total: Money, lines: Sequence[PurchaseLine]
) -> tuple[Money, tuple[str, ...]]:
    """Legacy usuli: qatorda narx yozilgan bo'lsa shu narx, qolgan tovar summasi narxsiz qatorlarga.

    Qaytadi: narxsiz qatorlarga bo'linadigan qoldiq (manfiy bo'lsa 0) va o'sha qatorlar.
    Narxli qatorlar summasi narx × dona (valyutada) bo'yicha ayriladi.
    """
    explicit = total(
        [line.unit_price * line.ordered_qty for line in lines if line.unit_price is not None],
        goods_total.currency,
    )
    rest = goods_total - explicit
    unpriced = tuple(line.id for line in lines if line.unit_price is None)
    return (rest if rest.amount > 0 else Money.zero(goods_total.currency)), unpriced


def _line_value(line: PurchaseLine, goods_rate: FxRate | None) -> Decimal | None:
    if line.unit_price is None:
        return None
    return to_uzs(line.unit_price * line.qty, goods_rate).amount


def _weights(
    component: CostComponent,
    lines: Sequence[PurchaseLine],
    goods_rate: FxRate | None,
) -> tuple[list[Decimal], bool]:
    """Taqsimot og'irliklari; ikkinchi qiymat — dona bo'yicha zaxira usul ishlatildimi."""
    units = [Decimal(line.qty) for line in lines]
    base = component.base
    if base is AllocationBase.UNITS:
        return units, False
    if base is AllocationBase.MANUAL:
        missing = [line.id for line in lines if line.id not in component.manual_shares]
        if missing:
            raise PurchaseError(f"{component.kind}: qo'lda ulush berilmagan qatorlar: {missing}")
        return [to_decimal(component.manual_shares[line.id]) for line in lines], False
    per_line: list[Decimal | None]
    if base is AllocationBase.WEIGHT:
        per_line = [None if x.unit_weight is None else x.unit_weight * x.qty for x in lines]
    elif base is AllocationBase.VOLUME:
        per_line = [None if x.unit_volume is None else x.unit_volume * x.qty for x in lines]
    else:
        per_line = [_line_value(x, goods_rate) for x in lines]
    if any(w is None for w in per_line) or not any(per_line):
        return units, True
    return [w for w in per_line if w is not None], False


def compute_lots(purchase: Purchase) -> list[LotCost]:
    """F20. Har xarid qatori uchun lot tannarxi.

    Komponent ``line_ids`` dagi qatorlarga (``None`` — hamma qatorga) bo'linadi; donasi 0 qatorlar
    taqsimotda qatnashmaydi. Kargo komponenti bo'lmasa hamma lotlarda "kargo kiritilmagan" belgisi.
    """
    lines = {line.id: line for line in purchase.lines}
    if len(lines) != len(purchase.lines):
        raise PurchaseError("qator id'lari takrorlangan")
    parts: dict[str, dict[ComponentKind, Money]] = {lid: {} for lid in lines}
    flags: dict[str, set[Flag]] = {lid: set() for lid in lines}

    for component in purchase.components:
        targets_ids = component.line_ids if component.line_ids is not None else tuple(lines)
        unknown = [lid for lid in targets_ids if lid not in lines]
        if unknown:
            raise PurchaseError(f"{component.kind}: noma'lum qatorlar {unknown}")
        targets = [lines[lid] for lid in targets_ids if lines[lid].qty > 0]
        amount = component.in_uzs()
        if amount.is_zero():
            continue
        if not targets:
            raise PurchaseError(f"{component.kind}: summani bo'ladigan qator yo'q (dona 0)")
        weights, fallback = _weights(component, targets, purchase.goods_rate)
        cbu = component.rate is not None and component.rate.source is RateSource.CBU
        for line, share in zip(targets, allocate(amount, weights), strict=True):
            bucket = parts[line.id]
            bucket[component.kind] = bucket.get(component.kind, Money.zero(UZS)) + share
            if fallback:
                flags[line.id].add(Flag.BASE_FALLBACK)
            if cbu:
                flags[line.id].add(Flag.CBU_RATE)

    has_cargo = any(c.kind is ComponentKind.CARGO for c in purchase.components)
    result = []
    for lid, line in lines.items():
        line_flags = flags[lid]
        if not has_cargo:
            line_flags.add(Flag.CARGO_MISSING)
        if line.received_qty is None:
            line_flags.add(Flag.NOT_RECEIVED)
        line_total = total(list(parts[lid].values()), UZS)
        result.append(
            LotCost(
                line_id=lid,
                qty=line.qty,
                breakdown=dict(parts[lid]),
                total=line_total,
                unit_cost=None if line.qty == 0 else Money(line_total.amount / line.qty, UZS),
                flags=frozenset(line_flags),
            )
        )
    return result


def purchase_total(purchase: Purchase) -> Money:
    """Xaridning so'mdagi jami xarajati (hamma komponentlar)."""
    return total([c.in_uzs() for c in purchase.components], UZS)


def average_unit_cost(lots: Sequence[LotCost]) -> Money | None:
    """Xarid bo'yicha o'rtacha birlik tannarx (jami / dona)."""
    units = sum(lot.qty for lot in lots)
    if units == 0:
        return None
    return Money(total([lot.total for lot in lots], UZS).amount / units, UZS)


# --- Partiya yo'li (xarid hayoti, M9) ---------------------------------------------------------


class Stage(StrEnum):
    """Xarid hayoti bosqichlari tartib bilan (M9). ``DRAFT`` dan boshqa har birining sanasi bor."""

    DRAFT = "draft"
    ORDERED = "ordered"  # buyurtma berildi
    PAID = "paid"
    CN_WAREHOUSE = "cn_warehouse"  # Xitoy omborida
    SHIPPED = "shipped"  # yo'lda
    ARRIVED = "arrived"  # Toshkentga keldi
    RECEIVED = "received"  # qabul qilindi
    SENT_TO_UZUM = "sent_to_uzum"
    CLOSED = "closed"


DATED_STAGES: tuple[Stage, ...] = tuple(s for s in Stage if s is not Stage.DRAFT)

# F25 bosqichlari: (bosqich nomi, boshlanish — birinchi sanasi bor, tugash). Tayyorlash to'lovdan (yo'q bo'lsa
# buyurtmadan) boshlanadi.
LEAD_STAGES: tuple[tuple[str, tuple[Stage, ...], Stage], ...] = (
    ("prep", (Stage.PAID, Stage.ORDERED), Stage.CN_WAREHOUSE),
    ("china", (Stage.CN_WAREHOUSE,), Stage.SHIPPED),
    ("cargo", (Stage.SHIPPED,), Stage.ARRIVED),
    ("receive", (Stage.ARRIVED,), Stage.RECEIVED),
    ("handover", (Stage.RECEIVED,), Stage.SENT_TO_UZUM),
)


def _first(dates: Mapping[Stage, date | None], stages: Sequence[Stage]) -> date | None:
    return next((d for d in (dates.get(s) for s in stages) if d is not None), None)


def stage_days(dates: Mapping[Stage, date | None]) -> dict[str, int]:
    """F25 o'rganish: xarid sanalari → bosqich kunlari (ikkala sana bor va tartib to'g'ri bo'lsa)."""
    out = {}
    for name, starts, end in LEAD_STAGES:
        a, b = _first(dates, starts), dates.get(end)
        if a is not None and b is not None and b >= a:
            out[name] = (b - a).days
    return out


def current_stage(dates: Mapping[Stage, date | None]) -> Stage:
    """Joriy bosqich — sanasi bor eng oxirgi bosqich; hech biri yo'q — qoralama."""
    return next((s for s in reversed(DATED_STAGES) if dates.get(s) is not None), Stage.DRAFT)


@dataclass(frozen=True, slots=True)
class StageMark:
    """Partiya yo'li nuqtasi. ``state``: ``done`` (o'tilgan; sanasiz bo'lsa — o'tkazib yuborilgan), ``current``
    (joriy: ``days`` o'tdi, keyingi bosqich ``expected`` da kutiladi), ``upcoming``."""

    stage: Stage
    state: str
    on: date | None
    days: int | None = None
    expected: date | None = None
    delayed: bool = False


def timeline(
    dates: Mapping[Stage, date | None], today: date, lead: Mapping[str, Decimal] | None = None
) -> list[StageMark]:
    """Partiya yo'li (M9, 04 §6.2). ``lead`` — F25 bosqich kunlari (tashkilot tarixidan median); joriy bosqichdan
    keyingisiga muddat ma'lum bo'lsa kutilgan sana = joriy bosqich sanasi + muddat (yuqoriga yaxlitlab), bugun undan
    keyin bo'lsa — kechikish. Muddat noma'lum bo'lsa kutilgan sana yo'q (raqam o'ylab topilmaydi). Yopilgan xaridda
    hamma bosqich o'tilgan."""
    current = current_stage(dates)
    index = DATED_STAGES.index(current) if current is not Stage.DRAFT else -1
    marks = []
    for i, stage in enumerate(DATED_STAGES):
        on = dates.get(stage)
        if i < index or (i == index and stage is Stage.CLOSED):
            marks.append(StageMark(stage, "done", on))
        elif i == index and on is not None:
            expected = None
            for name, starts, end in LEAD_STAGES:
                if stage in starts and dates.get(end) is None and lead and name in lead:
                    expected = on + timedelta(days=math.ceil(lead[name]))
            marks.append(
                StageMark(
                    stage,
                    "current",
                    on,
                    days=max((today - on).days, 0),
                    expected=expected,
                    delayed=expected is not None and today > expected,
                )
            )
        else:
            marks.append(StageMark(stage, "upcoming", on))
    return marks

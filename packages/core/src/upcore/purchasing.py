"""Xarid (partiya) birlik tannarxi — F20, belgilar — F22 (02-funksiyalar.md M9, F20, F22).

Xarid = qatorlar (tovar, dona, narx, vazn, hajm) + istalgancha xarajat komponentlari (tovar, kargo, bojxona,
qadoq ...). Har komponent kurs bilan so'mga o'tkaziladi (kurs rejimi — ``upcore.fx``: CBU, qo'lda,
kartadan yechilgan summa) va taqsimot asosiga ko'ra o'z qatorlariga bo'linadi. Taqsimot aniq: qatorlar
yig'indisi komponent summasiga tiyinigacha teng (qoldiq eng katta qatorga, ``upcore.money.allocate``).

Qatorning birlik tannarxi = qatorga tushgan komponentlar / qabul qilingan dona (hali qabul qilinmagan bo'lsa
buyurtma qilingan dona, "taxminiy").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
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

"""Xarid (partiya) birlik tannarxi — F20, belgilar — F22 (02-funksiyalar.md M9, F20, F22).

Xarid = qatorlar (tovar, dona, narx, vazn, hajm) + istalgancha xarajat komponentlari (tovar, kargo, bojxona,
qadoq ...). Har komponent kurs bilan so'mga o'tkaziladi (kurs rejimi — ``upcore.fx``: CBU, qo'lda,
kartadan yechilgan summa) va taqsimot asosiga ko'ra o'z qatorlariga bo'linadi. Taqsimot aniq: qatorlar
yig'indisi komponent summasiga tiyinigacha teng (qoldiq eng katta qatorga, ``upcore.money.allocate``).

Qatorning birlik tannarxi = qatorga tushgan komponentlar / **sog' dona** (kelgan − sanashdagi brak; hali sanalmagan
bo'lsa buyurtma qilingan dona, "taxminiy") + tovarning qadoq qo'shimchasi (ADR-061).

Ta'minot qayta loyihasi (ADR-061): tovar summasi ("jami to'landi") qator summalariga mutanosib bo'linadi
(``AllocationBase.LINE_SUM``; kiritilmagan bo'lsa dona), sotuvchi qaytargan summa tovar summasidan ayriladi, kodli quti
puli xaridlarga dona bo'yicha yoki qo'lda yozilgan summalar bilan bo'linadi (:func:`split_by_purchase`).

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
    TRANSFER_FEE = "transfer_fee"  # pul o'tkazma komissiyasi (ADR-061 §4)
    LOCAL_DELIVERY = "local_delivery"  # taksi / mahalliy tashish (ADR-061 §4)
    OTHER = "other"  # sotuvchining o'z turi (``cost_types`` lug'ati) ham shu


# Kargo xarajatlari (ADR-046, ADR-049): kargodagi hamma xaridning hamma tovariga bo'linadigan turlar. Tovar narxi, Xitoy ichki
# yetkazish va agent komissiyasi — har xaridning o'zida (yetkazib beruvchi bo'yicha), kargoga tegishli emas.
SHIPMENT_KINDS: frozenset[ComponentKind] = frozenset(
    {
        ComponentKind.CARGO,
        ComponentKind.CUSTOMS,
        ComponentKind.PACKAGING,
        ComponentKind.LABELING,
        ComponentKind.UZUM_DELIVERY,
        ComponentKind.TRANSFER_FEE,
        ComponentKind.LOCAL_DELIVERY,
        ComponentKind.OTHER,
    }
)


class AllocationBase(StrEnum):
    """Taqsimot asosi (M9). Kargo uchun standart — vazn."""

    UNITS = "units"
    WEIGHT = "weight"
    VOLUME = "volume"
    VALUE = "value"  # qatorning tovar qiymati (narx × dona) bo'yicha
    LINE_SUM = "line_sum"  # qator summasi bo'yicha (ADR-061); kiritilmagan bo'lsa dona
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
    MARKET_RATE = (
        "market_rate"  # kurs bozor kursi, CBU emas (CBU serverdan ochilmadi, ADR-045) — taxminiy
    )
    BASE_FALLBACK = "base_fallback"  # vazn/hajm/qiymat yo'q — dona bo'yicha bo'lindi
    NO_LINE_SUMS = (
        "no_line_sums"  # bir necha qator, qator summasi yo'q — dona bo'yicha (eslatma, ADR-061 §2)
    )


# ADR-057 Q6 (B4.69): ma'lumot uchun belgilar — raqam noaniq emas, "Taxminiy" qo'yilmaydi. Markaziy bank kursi —
# standart rejim (sotuvchi qo'lda kurs kiritmagan): izoh ("kurs: Markaziy bank"), taxmin emas.
# ADR-061 §2: qator summalari kiritilmagan — xarid sahifasida eslatma, taxminiy qismga qo'shilmaydi.
INFO_FLAGS: frozenset[Flag] = frozenset({Flag.CBU_RATE, Flag.NO_LINE_SUMS})


class PurchaseError(ValueError):
    """Xarid ma'lumoti hisoblab bo'lmaydigan holatda (raqam o'ylab topilmaydi)."""


@dataclass(frozen=True, slots=True)
class PurchaseLine:
    """Xarid qatori. ``unit_price`` — valyutada dona narxi (ixtiyoriy); vazn (kg) va hajm (m³) — donaga.

    ADR-061: ``received_qty`` — sanashda kelgan dona, ``defect_qty`` — sanashda topilgan brak (kelganning ichida);
    ``line_sum`` — qator summasi (xarid valyutasida, faqat nisbat uchun); ``pack_unit_cost`` — tovarning qadoq
    qo'shimchasi (so'm/dona), har sog' donaga qo'shiladi.
    """

    id: str
    ordered_qty: int
    received_qty: int | None = None
    unit_price: Money | None = None
    unit_weight: Decimal | None = None
    unit_volume: Decimal | None = None
    defect_qty: int = 0
    line_sum: Decimal | None = None
    pack_unit_cost: Money | None = None
    # ADR-061 §7 "Boshqa SKU'ga o'tkazish": shu xariddagi manba qator — dona uning birlik tannarxi bilan o'tadi
    # (taqsimotda qatnashmaydi, :func:`apply_transfers`).
    source_id: str | None = None

    def __post_init__(self) -> None:
        if self.ordered_qty < 0 or (self.received_qty is not None and self.received_qty < 0):
            raise PurchaseError(f"qator {self.id}: dona manfiy bo'lishi mumkin emas")
        if self.defect_qty < 0 or self.defect_qty > self.arrived_qty:
            raise PurchaseError(f"qator {self.id}: brak kelgan donadan ko'p yoki manfiy")
        if self.line_sum is not None and self.line_sum < 0:
            raise PurchaseError(f"qator {self.id}: qator summasi manfiy")
        if self.pack_unit_cost is not None and (
            self.pack_unit_cost.currency is not UZS or self.pack_unit_cost.amount < 0
        ):
            raise PurchaseError(f"qator {self.id}: qadoq qo'shimchasi so'mda va manfiy emas")

    @property
    def arrived_qty(self) -> int:
        """Kelgan dona (brak bilan): sanalgan, yo'q bo'lsa buyurtma qilingan."""
        return self.ordered_qty if self.received_qty is None else self.received_qty

    @property
    def qty(self) -> int:
        """F20: tannarx bo'linadigan **sog' dona** = kelgan − sanashdagi brak (sanalmagan — buyurtma qilingan)."""
        return self.arrived_qty - self.defect_qty


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
    later_date: date | None = (
        None  # qabuldan keyingi bosqich (Uzumga yuborildi / yopildi) — eng ertasi
    )
    # ADR-061 §6: sotuvchi qaytargan summa (tovar summasidan ayriladi); kurs — so'mdan boshqa valyutada shart.
    refund: Money | None = None
    refund_rate: FxRate | None = None
    # ADR-061 §2: "Tovar qo'limda" (mahalliy xarid) — kargo kutilmaydi, "kargo kiritilmagan" belgisi chiqmaydi.
    on_hand: bool = False

    @property
    def ready_date(self) -> date | None:
        """F21: lot sotuvga tayyor sanasi = qabul sanasi; yo'q bo'lsa kargo to'langan sana; ikkalasi ham yo'q bo'lsa
        qabuldan keyingi bosqich sanasi (Uzumga yuborildi / yopildi — tovar qo'lda bo'lgan; ADR-057 Q6, audit K8);
        hech biri yo'q — ``None`` ("yo'lda")."""
        return self.received_date or self.cargo_paid_date or self.later_date


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
        """F22: taxminiy — ma'lumot uchun belgilardan (``INFO_FLAGS``) boshqa belgi bor."""
        return bool(self.flags - INFO_FLAGS)


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
    # Dona asosi — kelgan dona (brak bilan: puli to'langan, ADR-061 §3); eski yozuvlarda brak 0 — avvalgidek.
    units = [Decimal(line.arrived_qty) for line in lines]
    base = component.base
    if base is AllocationBase.UNITS:
        return units, False
    if base is AllocationBase.LINE_SUM:
        sums = [line.line_sum for line in lines]
        if any(x is None for x in sums) or not any(sums):
            return units, False  # eslatma belgisi (``NO_LINE_SUMS``) — ``compute_lots`` da
        return [x for x in sums if x is not None], False
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
    Boshqa SKU'ga o'tkazilgan donalar manba qatorning birlik tannarxi bilan o'tadi (:func:`apply_transfers`).
    """
    return apply_transfers(_compute_lots(purchase), purchase.lines)


def apply_transfers(lots: Sequence[LotCost], lines: Sequence[PurchaseLine]) -> list[LotCost]:
    """F20, "Boshqa SKU'ga o'tkazish" (ADR-061 §7): o'tkazilgan qator (``source_id``) manba qator chiqimining o'z
    donasiga mos qismini oladi — har tur bo'yicha dona nisbatida, yig'indi aniq (``allocate``); manba lot donasi va
    chiqimi shuncha kamayadi, birlik tannarxi o'zgarmaydi. Belgilar manbadan. O'tkazilgan dona manbaning sog' donasidan
    ko'p bo'lsa — ``PurchaseError``."""
    moved: dict[str, list[PurchaseLine]] = {}
    for line in lines:
        if line.source_id is not None:
            moved.setdefault(line.source_id, []).append(line)
    if not moved:
        return list(lots)
    by_id = {lot.line_id: lot for lot in lots}
    out: dict[str, LotCost] = dict(by_id)
    for source_id, takers in moved.items():
        source = by_id.get(source_id)
        if source is None:
            raise PurchaseError(f"o'tkazma manbasi {source_id} shu xaridda yo'q")
        taken = sum(x.qty for x in takers)
        rest = source.qty - taken
        if rest < 0:
            raise PurchaseError(f"qator {source_id}: o'tkazilgan dona sog' donadan ko'p")
        weights = [Decimal(rest), *(Decimal(x.qty) for x in takers)]
        parts: list[dict[ComponentKind, Money]] = [{} for _ in weights]
        if sum(weights, Decimal(0)) > 0:
            for kind, amount in source.breakdown.items():
                for i, share in enumerate(allocate(amount, weights)):
                    parts[i][kind] = share
        for i, (lot_id, qty) in enumerate([(source_id, rest), *((x.id, x.qty) for x in takers)]):
            line_total = total(list(parts[i].values()), UZS)
            out[lot_id] = LotCost(
                line_id=lot_id,
                qty=qty,
                breakdown=parts[i],
                total=line_total,
                unit_cost=None if qty == 0 else Money(line_total.amount / qty, UZS),
                flags=source.flags,
            )
    return [out[lot.line_id] for lot in lots]


def _compute_lots(purchase: Purchase) -> list[LotCost]:
    """F20 taqsimoti (o'tkazmalarsiz): o'tkazilgan qatorlar bo'sh lot oladi — :func:`apply_transfers` to'ldiradi."""
    all_lines = {line.id: line for line in purchase.lines}
    if len(all_lines) != len(purchase.lines):
        raise PurchaseError("qator id'lari takrorlangan")
    lines = {lid: x for lid, x in all_lines.items() if x.source_id is None}
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
        market = component.rate is not None and component.rate.source is RateSource.MARKET
        for line, share in zip(targets, allocate(amount, weights), strict=True):
            bucket = parts[line.id]
            bucket[component.kind] = bucket.get(component.kind, Money.zero(UZS)) + share
            if fallback:
                flags[line.id].add(Flag.BASE_FALLBACK)
            if cbu:
                flags[line.id].add(Flag.CBU_RATE)
            if market:
                flags[line.id].add(Flag.MARKET_RATE)
            if (
                component.base is AllocationBase.LINE_SUM
                and len(targets) > 1
                and any(x.line_sum is None for x in targets)
            ):
                flags[line.id].add(Flag.NO_LINE_SUMS)

    _apply_refund(purchase, lines, parts)
    has_cargo = purchase.on_hand or any(c.kind is ComponentKind.CARGO for c in purchase.components)
    result = []
    for lid, line in lines.items():
        line_flags = flags[lid]
        if not has_cargo:
            line_flags.add(Flag.CARGO_MISSING)
        if line.received_qty is None:
            line_flags.add(Flag.NOT_RECEIVED)
        if line.pack_unit_cost is not None and line.qty > 0 and not line.pack_unit_cost.is_zero():
            bucket = parts[lid]
            bucket[ComponentKind.PACKAGING] = (
                bucket.get(ComponentKind.PACKAGING, Money.zero(UZS))
                + line.pack_unit_cost * line.qty
            )
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
    for lid, line in all_lines.items():
        if line.source_id is not None:
            result.append(LotCost(lid, line.qty, {}, Money.zero(UZS), None, frozenset()))
    order = {lid: i for i, lid in enumerate(all_lines)}
    result.sort(key=lambda lot: order[lot.line_id])
    return result


def _apply_refund(
    purchase: Purchase,
    lines: Mapping[str, PurchaseLine],
    parts: dict[str, dict[ComponentKind, Money]],
) -> None:
    """F20 (ADR-061 §6): sotuvchi qaytargan summa tovar summasidan ayriladi — qator summasiga mutanosib (yo'q bo'lsa
    dona). Qaytarilgan summa qatorning tovar summasidan ko'p bo'lsa — xato (raqam o'ylab topilmaydi)."""
    if purchase.refund is None or purchase.refund.is_zero():
        return
    if purchase.refund.amount < 0:
        raise PurchaseError("qaytarilgan summa manfiy bo'lishi mumkin emas")
    targets = [line for line in lines.values() if line.qty > 0]
    if not targets:
        raise PurchaseError("qaytarilgan summani ayiradigan qator yo'q (dona 0)")
    pseudo = CostComponent(
        ComponentKind.GOODS, purchase.refund, purchase.refund_rate, AllocationBase.LINE_SUM
    )
    weights, _ = _weights(pseudo, targets, purchase.goods_rate)
    for line, share in zip(targets, allocate(pseudo.in_uzs(), weights), strict=True):
        goods = parts[line.id].get(ComponentKind.GOODS, Money.zero(UZS)) - share
        if goods.amount < 0:
            raise PurchaseError("qaytarilgan summa tovar summasidan ko'p")
        parts[line.id][ComponentKind.GOODS] = goods


def split_by_purchase(
    component: CostComponent,
    purchases: Sequence[Purchase],
    fixed: Mapping[str, Decimal],
) -> list[CostComponent]:
    """Kodli quti puli (ADR-061 §3): summa xaridlarga **dona bo'yicha** bo'linadi, ``fixed`` (xarid id → summa,
    komponent valyutasida) — sotuvchi qo'lda yozgan ulushlar: ular o'zgarmaydi, qolgan summa qolgan xaridlarga kelgan
    dona bo'yicha (sanashda dona o'zgarsa — o'zi qayta bo'linadi). Xarid ichida — qatorlarga dona bo'yicha.

    Qaytadi: har qo'lda ulush uchun alohida komponent (o'sha xarid qatorlariga) + qoldiq komponenti. Qo'lda ulushlar
    yig'indisi summadan ko'p bo'lsa yoki qoldiqni oladigan xarid qolmasa (qoldiq > 0) — ``PurchaseError``.
    """
    by_id = {p.id: p for p in purchases}
    unknown = [pid for pid in fixed if pid not in by_id]
    if unknown:
        raise PurchaseError(f"{component.kind}: kargoda yo'q xaridlar {unknown}")
    currency = component.amount.currency
    out: list[CostComponent] = []
    rest = component.amount
    for pid, raw in fixed.items():
        share = Money(to_decimal(raw), currency)
        if share.amount < 0:
            raise PurchaseError(f"{component.kind}: qo'lda ulush manfiy")
        rest = rest - share
        out.append(
            CostComponent(
                component.kind,
                share,
                component.rate,
                AllocationBase.UNITS,
                tuple(line.id for line in by_id[pid].lines),
            )
        )
    if rest.amount < 0:
        raise PurchaseError(f"{component.kind}: qo'lda ulushlar yig'indisi summadan ko'p")
    others = tuple(line.id for p in purchases if p.id not in fixed for line in p.lines)
    if not rest.is_zero():
        if not others:
            raise PurchaseError(f"{component.kind}: qo'lda ulushlar yig'indisi summaga teng emas")
        out.append(
            CostComponent(component.kind, rest, component.rate, AllocationBase.UNITS, others)
        )
    return out


def box_shares(
    amount: Money, units: Mapping[str, int], fixed: Mapping[str, Decimal]
) -> dict[str, Money]:
    """F20, kodli quti (ADR-061 §3): har xaridga tushadigan kargo puli — kargo puli jadvalidagi inputlar uchun tayyor
    ulushlar. ``units`` — xarid id → dona (sanalgan bo'lsa kelgan, bo'lmasa buyurtma qilingan); ``fixed`` — sotuvchi
    qo'lda yozgan ulushlar (o'zgarmaydi). Qolgan summa qolgan xaridlarga dona bo'yicha (qoldiq eng ko'p donali xaridga);
    natija yig'indisi summaga tiyinigacha teng. Hisobdagi bo'linish bilan bir xil qoida (:func:`split_by_purchase`).

    Xato (``PurchaseError``): noma'lum xarid, manfiy ulush, qo'lda ulushlar summadan ko'p yoki qoldiqni oladigan xarid
    (dona > 0) qolmagan bo'lsa.
    """
    if not units:
        raise PurchaseError("kodli qutida kamida bitta xarid bo'lishi kerak")
    unknown = [pid for pid in fixed if pid not in units]
    if unknown:
        raise PurchaseError(f"qutida yo'q xaridlar {unknown}")
    currency = amount.currency
    out: dict[str, Money] = {}
    rest = amount
    for pid, raw in fixed.items():
        share = Money(to_decimal(raw), currency)
        if share.amount < 0:
            raise PurchaseError("qo'lda ulush manfiy")
        out[pid] = share
        rest = rest - share
    if rest.amount < 0:
        raise PurchaseError("qo'lda ulushlar yig'indisi summadan ko'p")
    others = [pid for pid in units if pid not in fixed]
    weights = [Decimal(max(units[pid], 0)) for pid in others]
    if not others or sum(weights, Decimal(0)) == 0:
        if not rest.is_zero():
            raise PurchaseError("qo'lda ulushlar yig'indisi summaga teng emas")
        for pid in others:
            out[pid] = Money.zero(currency)
    else:
        for pid, part in zip(others, allocate(rest, weights), strict=True):
            out[pid] = part
    return {pid: out[pid] for pid in units}


def defect_cost(lot: LotCost, line: PurchaseLine) -> Money | None:
    """F20, sanash (ADR-061 §6): sanashdagi brak tannarxga qancha qo'shdi — "5 ta brak — tannarxga X so'm qo'shdi".

    Chiqim (qadoq qo'shimchasisiz — u faqat sog' donaga) kelgan dona o'rniga sog' donaga bo'linadi, shuning uchun brak
    donalarining ulushi = chiqim × brak / kelgan. Brak yo'q yoki kelgan dona 0 — ``None``.
    """
    if line.defect_qty <= 0 or line.arrived_qty <= 0:
        return None
    pack = line.pack_unit_cost * line.qty if line.pack_unit_cost is not None else Money.zero(UZS)
    base = lot.total - pack
    return Money(base.amount * line.defect_qty / line.arrived_qty, UZS)


def split_units(amount: Money, kept: int, moved: int) -> tuple[Money, Money]:
    """F20, "Xaridni ikkiga bo'lish" (ADR-061 §6): summa qolgan va ko'chgan donaga mutanosib (yig'indi aniq teng,
    qoldiq ko'proq donaliga). Ikkalasi 0 bo'lsa — ``PurchaseError``."""
    if kept < 0 or moved < 0 or kept + moved == 0:
        raise PurchaseError("bo'lish uchun dona musbat bo'lishi kerak")
    if moved == 0:
        return amount, Money.zero(amount.currency)
    if kept == 0:
        return Money.zero(amount.currency), amount
    first, second = allocate(amount, [kept, moved])
    return first, second


def compute_shipment_shares(
    purchases: Sequence[Purchase], shipment_components: Sequence[CostComponent]
) -> dict[str, LotCost]:
    """Faqat kargo komponentlarining har qatorga tushgan ulushi (qator id → ulush; xarid ichidagi komponentlarsiz).

    Kargo tovarlari — bitta "virtual xarid": qiymat asosi uchun narx so'mga o'z xaridining kursi bilan o'tkaziladi;
    vazn / hajm yo'q qator bo'lsa taqsimot butun kargo bo'yicha dona asosiga o'tadi (``base_fallback``).
    """
    ids = [line.id for p in purchases for line in p.lines]
    if len(set(ids)) != len(ids):
        raise PurchaseError("qator id'lari takrorlangan")
    virtual_lines = []
    for p in purchases:
        for line in p.lines:
            price = line.unit_price
            if price is not None:
                price = Money(to_uzs(price, p.goods_rate).amount, UZS)
            virtual_lines.append(
                PurchaseLine(
                    line.id,
                    line.ordered_qty,
                    line.received_qty,
                    price,
                    line.unit_weight,
                    line.unit_volume,
                    defect_qty=line.defect_qty,
                    line_sum=line.line_sum,
                    source_id=line.source_id,
                )
            )
    return {
        lot.line_id: lot
        for lot in compute_lots(
            # ``on_hand``: virtual xaridda "kargo kiritilmagan" belgisi kerak emas (chaqiruvchi o'zi hal qiladi).
            Purchase("shipment", tuple(virtual_lines), tuple(shipment_components))
        )
    }


def compute_shipment_lots(
    purchases: Sequence[Purchase], shipment_components: Sequence[CostComponent]
) -> dict[str, list[LotCost]]:
    """F20, kargo bilan (ADR-046): bitta kargoga tegishli xaridlar lotlari (xarid id → lotlar).

    Har xaridning o'z komponentlari avvalgidek o'z qatorlariga bo'linadi (:func:`compute_lots`). **Kargo komponentlari
    butun kargoning hamma xaridlari qatorlariga** bitta taqsimotda bo'linadi (dona / vazn / hajm / qiymat / qo'lda):
    yaxlitlash qoldig'i butun kargo bo'yicha eng katta qatorga, shuning uchun xaridlarga tushgan ulushlar yig'indisi
    kargo summasiga tiyinigacha teng. Qator ``line_ids`` kargodagi istalgan xaridning qatori bo'lishi mumkin
    (``None`` — hammasi). "Kargo kiritilmagan" belgisi (``cargo_missing``) faqat kargo ham, xarid ham kargo
    komponentiga ega bo'lmasa chiqadi.
    """
    ids = [line.id for p in purchases for line in p.lines]
    if len(set(ids)) != len(ids):
        raise PurchaseError("qator id'lari takrorlangan")
    own = {p.id: compute_lots(p) for p in purchases}
    if not shipment_components:
        return own
    shared = compute_shipment_shares(purchases, shipment_components)
    has_cargo = any(c.kind is ComponentKind.CARGO for c in shipment_components)
    result: dict[str, list[LotCost]] = {}
    for p in purchases:
        lots = []
        for lot in own[p.id]:
            extra = shared[lot.line_id]
            breakdown = dict(lot.breakdown)
            for kind, amount in extra.breakdown.items():
                breakdown[kind] = breakdown.get(kind, Money.zero(UZS)) + amount
            line_total = total(list(breakdown.values()), UZS)
            flags = set(lot.flags) | (set(extra.flags) - {Flag.CARGO_MISSING, Flag.NOT_RECEIVED})
            if has_cargo:
                flags.discard(Flag.CARGO_MISSING)
            lots.append(
                LotCost(
                    line_id=lot.line_id,
                    qty=lot.qty,
                    breakdown=breakdown,
                    total=line_total,
                    unit_cost=None if lot.qty == 0 else Money(line_total.amount / lot.qty, UZS),
                    flags=frozenset(flags),
                )
            )
        result[p.id] = lots
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


# --- Uch holat (ADR-061 §1) --------------------------------------------------------------------


class SupplyState(StrEnum):
    """Xaridning holati (ADR-061 §1) — hosila, qo'lda bosilmaydi."""

    IN_TRANSIT = "in_transit"  # Yo'lda: saqlangan, sanalmagan
    IN_STOCK = "in_stock"  # Omborimda: sanalgan, tovar sotuvchining qo'lida
    AT_UZUM = "at_uzum"  # Uzumda: Uzumga jo'natilgan


# Sanashgacha bo'lgan bosqichlar (eski xaridlarda sanasi bo'lishi mumkin): "Yo'lda" shulardan eng ertasidan boshlanadi.
_BEFORE_COUNT: tuple[Stage, ...] = (
    Stage.ORDERED,
    Stage.PAID,
    Stage.CN_WAREHOUSE,
    Stage.SHIPPED,
    Stage.ARRIVED,
)


def supply_state(dates: Mapping[Stage, date | None]) -> SupplyState:
    """ADR-061 §1, §11: sanalar → holat. Uzumga yuborilgan yoki yopilgan — Uzumda; sanalgan (qabul sanasi bor) —
    Omborimda; qolgan hammasi (qoralama, buyurtma, to'landi, Xitoy omborida, yo'lda, Toshkentga keldi) — Yo'lda."""
    if dates.get(Stage.SENT_TO_UZUM) is not None or dates.get(Stage.CLOSED) is not None:
        return SupplyState.AT_UZUM
    if dates.get(Stage.RECEIVED) is not None:
        return SupplyState.IN_STOCK
    return SupplyState.IN_TRANSIT


def transit_start(dates: Mapping[Stage, date | None]) -> date | None:
    """ "Yo'lda" boshlangan kun: buyurtma sanasi, yo'q bo'lsa sanashgacha bo'lgan eng erta sana."""
    known = [d for d in (dates.get(s) for s in _BEFORE_COUNT) if d is not None]
    return dates.get(Stage.ORDERED) or (min(known) if known else None)


def transit_days(dates: Mapping[Stage, date | None]) -> int | None:
    """F25 o'rganish (ADR-061): buyurtma → sanash kunlari (ikkala sana bor va tartib to'g'ri bo'lsa)."""
    start, counted = transit_start(dates), dates.get(Stage.RECEIVED)
    if start is None or counted is None or counted < start:
        return None
    return (counted - start).days


@dataclass(frozen=True, slots=True)
class PathMark:
    """Partiya yo'li nuqtasi (04 §6.2, uch nuqta). ``mark``: ``done`` / ``current`` / ``upcoming``; "Yo'lda" joriy
    bo'lsa — ``days`` o'tdi, sanash ``expected`` da kutiladi."""

    state: SupplyState
    mark: str
    on: date | None
    days: int | None = None
    expected: date | None = None
    delayed: bool = False


def supply_path(
    dates: Mapping[Stage, date | None],
    today: date,
    transit_lead: Decimal | None = None,
    started: date | None = None,
) -> list[PathMark]:
    """Partiya yo'li (ADR-061 §1): Yo'lda → Omborimda → Uzumda. ``transit_lead`` — buyurtma → sanash muddati (F25:
    tashkilot tarixidan median yoki standart; noma'lum bo'lsa kutilgan sana yo'q — raqam o'ylab topilmaydi).
    ``started`` — buyurtma sanasi yo'q xaridda "Yo'lda" boshlanishi (yaratilgan kun)."""
    state = supply_state(dates)
    start = transit_start(dates) or started
    counted = dates.get(Stage.RECEIVED)
    sent = dates.get(Stage.SENT_TO_UZUM) or dates.get(Stage.CLOSED)
    if state is SupplyState.IN_TRANSIT:
        expected = None
        if start is not None and transit_lead is not None:
            expected = start + timedelta(days=math.ceil(transit_lead))
        first = PathMark(
            SupplyState.IN_TRANSIT,
            "current",
            start,
            days=None if start is None else max((today - start).days, 0),
            expected=expected,
            delayed=expected is not None and today > expected,
        )
        return [
            first,
            PathMark(SupplyState.IN_STOCK, "upcoming", None),
            PathMark(SupplyState.AT_UZUM, "upcoming", None),
        ]
    at_uzum = state is SupplyState.AT_UZUM
    return [
        PathMark(SupplyState.IN_TRANSIT, "done", start),
        PathMark(SupplyState.IN_STOCK, "done" if at_uzum else "current", counted),
        PathMark(SupplyState.AT_UZUM, "current" if at_uzum else "upcoming", sent),
    ]

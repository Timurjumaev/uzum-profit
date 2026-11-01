"""Lot dvigateli: sotuv tannarxi F21, belgilar F22 (02-funksiyalar.md; 03-arxitektura.md §7).

Bitta tovar bo'yicha hodisalar sana tartibida: lot kirimi (+), sotuvga yaroqli qaytish (+), sotuv (−),
brak / yo'qotish (−). Usul — tashkilot sozlamasi: FIFO (standart, ADR-008/025) yoki harakatlanuvchi o'rtacha.

Bir kundagi tartib: kirimlar → qaytishlar → sotuvlar va hisobdan chiqarishlar (id bo'yicha). Natija
deterministik: bir xil kirish → bir xil natija, shuning uchun qayta hisob har doim to'liq va idempotent.
B2.8 (``upapi.calc``) faqat o'zgargan tovarlarni qayta hisoblaydi va faqat o'zgargan sotuvlarni yozadi; tovar
ichida sanadan kesilmaydi: keyinroq tayyor bo'lgan lot "erta sotuv" orqali oldingi sotuvga ta'sir qilishi mumkin.

Tayyor lot yetmasa (F21): avval tayyor sanasi keyinroq bo'lgan lot ("erta sotuv"), keyin sanasiz — yo'ldagi
lot ("qabul belgilanmagan": sotuv bor — demak tovar kelgan). Hammasi tugasa — oxirgi ma'lum narx + "lot
yetmadi"; tovarda lot umuman yo'q bo'lsa tannarx yo'q (``None``).

Boshlang'ich holat (F41, ADR-033): ``Opening`` berilsa, boshlash sanasidan oldingi sotuvlar lotlarga tegmaydi —
sotuvchi kiritgan tarixiy tannarx (sana bo'yicha narxlar) bilan, "tarixiy" belgisi bilan hisoblanadi. Boshlash
kunidagi qoldiq (dona × shu sanadagi narx) birinchi lot bo'ladi; tayyor sanasi boshlashdan oldingi lotlar
qoldiqqa kirgan deb hisoblanadi va ishlatilmaydi (``superseded``). Boshlashdan keyin — odatdagi FIFO / o'rtacha.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from upcore.money import Currency, Money
from upcore.purchasing import Flag, LotCost, Purchase

UZS = Currency.UZS


class CostMethod(StrEnum):
    """Tannarx usuli (tashkilot sozlamasi)."""

    FIFO = "fifo"
    AVERAGE = "average"


class CostFlag(StrEnum):
    """F22: sotuv darajasidagi taxminiy belgilar (lot belgilari ``purchasing.Flag`` qo'shimcha keladi)."""

    EARLY_SALE = "early_sale"  # sotuv lot tayyor bo'lishidan oldin
    NOT_RECEIVED_MARKED = "not_received_marked"  # yo'ldagi (sanasiz) lotdan olindi
    LOT_SHORTAGE = "lot_shortage"  # lotlar yetmadi — oxirgi ma'lum narx
    RETURN_UNMATCHED = "return_unmatched"  # qaytishning asl sotuvi topilmadi
    NO_LOTS = "no_lots"  # tovarda lot umuman yo'q — tannarx yo'q
    HISTORICAL = "historical"  # boshlash sanasidan oldingi sotuv — tarixiy tannarx (F41)
    NO_ITEM = (
        "no_item"  # SKU tovarga bog'lanmagan — tannarx yo'q (dvigatelga kirmaydi, B2.8 belgisi)
    )


type AnyFlag = CostFlag | Flag


class CostingError(ValueError):
    """Hodisa ma'lumoti noto'g'ri."""


@dataclass(frozen=True, slots=True)
class Lot:
    """Tovar kirimi: ``total`` so'mda, ``ready`` — sotuvga tayyor sana (``None`` — yo'lda).

    ``seq`` — yo'ldagi lotlar tartibi uchun (masalan, buyurtma sanasi ordinal'i).
    """

    id: str
    ready: date | None
    qty: int
    total: Money
    flags: frozenset[Flag] = frozenset()
    seq: int = 0

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise CostingError(f"lot {self.id}: dona musbat bo'lishi kerak")

    @property
    def unit(self) -> Decimal:
        return self.total.amount / self.qty


@dataclass(frozen=True, slots=True)
class Sale:
    id: str
    day: date
    qty: int


@dataclass(frozen=True, slots=True)
class Return:
    """Sotuvga yaroqli qaytish: asl sotuv lot(lar)iga, o'sha narxda qaytadi."""

    id: str
    day: date
    qty: int
    sale_id: str


@dataclass(frozen=True, slots=True)
class WriteOff:
    """Brak, yo'qotish, kamomad — lotdan sotuv kabi chiqadi, lekin sotuv tannarxiga kirmaydi."""

    id: str
    day: date
    qty: int


type Event = Sale | Return | WriteOff

OPENING_LOT = "opening"  # boshlang'ich qoldiq lotining id'si (F41)


@dataclass(frozen=True, slots=True)
class PricePoint:
    """Tarixiy tannarx: ``valid_from`` dan (``None`` — boshidan) boshlab dona narxi (so'm)."""

    valid_from: date | None
    unit: Money


@dataclass(frozen=True, slots=True)
class Opening:
    """F41. Boshlang'ich holat: boshlash sanasi, shu kungi qoldiq (dona) va tarixiy narxlar."""

    start: date
    qty: int = 0
    prices: tuple[PricePoint, ...] = ()

    def __post_init__(self) -> None:
        if self.qty < 0:
            raise CostingError("boshlang'ich qoldiq manfiy bo'lmaydi")

    def price_on(self, day: date) -> Money | None:
        """F41: ``day`` dagi tarixiy narx — ``valid_from <= day`` bo'lgan eng oxirgisi; ``day`` hamma narxdan
        oldin bo'lsa — eng birinchisi; narx yo'q — ``None``."""
        ordered = sorted(self.prices, key=lambda x: x.valid_from or date.min)
        if not ordered:
            return None
        valid = [x for x in ordered if (x.valid_from or date.min) <= day]
        return (valid[-1] if valid else ordered[0]).unit

    def lot(self) -> Lot | None:
        """Boshlang'ich qoldiq loti (narxi boshlash sanasidagi tarixiy narx); dona 0 yoki narx yo'q — ``None``."""
        unit = self.price_on(self.start)
        if self.qty == 0 or unit is None:
            return None
        return Lot(OPENING_LOT, self.start, self.qty, Money(unit.amount * self.qty, UZS))


@dataclass(frozen=True, slots=True)
class Allocation:
    lot_id: str | None  # None — lot yetmagan qism (oxirgi ma'lum narx)
    qty: int
    unit: Decimal


@dataclass(frozen=True, slots=True)
class Outflow:
    """Sotuv yoki hisobdan chiqarish natijasi. ``cost`` ``None`` — tovarda lot yo'q."""

    id: str
    day: date
    qty: int
    cost: Money | None
    allocations: tuple[Allocation, ...]
    flags: frozenset[AnyFlag]

    @property
    def unit_cost(self) -> Money | None:
        return (
            None if self.cost is None or self.qty == 0 else Money(self.cost.amount / self.qty, UZS)
        )


@dataclass(frozen=True, slots=True)
class ReturnResult:
    id: str
    sale_id: str
    qty: int
    cost: Money | None  # sotuv tannarxidan ayriladi
    flags: frozenset[AnyFlag]


@dataclass(frozen=True, slots=True)
class CostingResult:
    sales: dict[str, Outflow]
    writeoffs: dict[str, Outflow]
    returns: dict[str, ReturnResult]
    remaining: dict[str, int]  # lot → qolgan dona
    remaining_value: Money
    superseded: frozenset[str] = (
        frozenset()
    )  # boshlash sanasidan oldingi lotlar (F41) — ishlatilmadi


def lots_from_purchase(
    purchase: Purchase, costs: Sequence[LotCost], item_of: dict[str, str]
) -> dict[str, list[Lot]]:
    """F20 natijasini tovarlar bo'yicha lotlarga aylantiradi (``item_of``: qator id → tovar id).

    Donasi 0 qatorlar lot bo'lmaydi; ``seq`` — buyurtma sanasi (yo'ldagi lotlar tartibi).
    """
    seq = purchase.order_date.toordinal() if purchase.order_date else 0
    result: dict[str, list[Lot]] = {}
    for cost in costs:
        if cost.qty == 0 or cost.line_id not in item_of:
            continue
        lot = Lot(
            f"{purchase.id}:{cost.line_id}",
            purchase.ready_date,
            cost.qty,
            cost.total,
            cost.flags,
            seq,
        )
        result.setdefault(item_of[cost.line_id], []).append(lot)
    return result


class _Layer:
    __slots__ = ("flags", "lot", "remaining")

    def __init__(self, lot: Lot, extra: CostFlag | None = None) -> None:
        self.lot = lot
        self.remaining = lot.qty
        self.flags: set[AnyFlag] = set(lot.flags)
        if extra is not None:
            self.flags.add(extra)


# Bir kun ichida: qaytishlar sotuvlardan oldin (kirimlar har hodisadan oldin qabul qilinadi).
_ORDER: dict[type, int] = {Return: 0, Sale: 1, WriteOff: 1}


def compute_costs(
    lots: Iterable[Lot],
    events: Iterable[Event],
    method: CostMethod = CostMethod.FIFO,
    opening: Opening | None = None,
) -> CostingResult:
    """F21 (+ F41 ``opening`` bilan). Bitta tovarning lotlari va hodisalari bo'yicha sotuv tannarxi."""
    all_lots = list(lots)
    all_events = list(events)
    if len({lot.id for lot in all_lots}) != len(all_lots):
        raise CostingError("lot id'lari takrorlangan")
    if any(lot.id == OPENING_LOT for lot in all_lots):
        raise CostingError(f"lot id {OPENING_LOT!r} band (boshlang'ich qoldiq)")
    for event in all_events:
        if event.qty <= 0:
            raise CostingError(f"hodisa {event.id}: dona musbat bo'lishi kerak")

    def order(e: Event) -> tuple[date, int, str]:
        return (e.day, _ORDER[type(e)], e.id)

    superseded: frozenset[str] = frozenset()
    if opening is None:
        engine = _Engine(method, all_lots)
    else:
        start = opening.start
        superseded = frozenset(x.id for x in all_lots if x.ready is not None and x.ready < start)
        engine = _Engine(method, [x for x in all_lots if x.id not in superseded], opening.lot())
        for event in sorted((e for e in all_events if e.day < start), key=order):
            engine.historical(event, opening.price_on(event.day))
        all_events = [e for e in all_events if e.day >= start]
    for event in sorted(all_events, key=order):
        engine.receive_until(event.day)
        if isinstance(event, Return):
            engine.give_back(event)
        else:
            engine.take(event)
    return engine.result(superseded)


class _Engine:
    """Ochiq qatlamlar (lotlar) navbati. FIFO: eng eski qatlamdan; AVERAGE: hovuzning o'rtacha narxida,
    donalar qatlamlardan FIFO tartibida yechiladi (qoldiq va qaytish uchun)."""

    def __init__(self, method: CostMethod, lots: list[Lot], first: Lot | None = None) -> None:
        self.method = method
        self.pending = sorted(
            (x for x in lots if x.ready is not None), key=lambda x: (x.ready, x.id)
        )
        if first is not None:  # boshlang'ich qoldiq — o'sha kungi lotlardan ham oldin
            self.pending.insert(0, first)
        self.transit = sorted((x for x in lots if x.ready is None), key=lambda x: (x.seq, x.id))
        self.open: list[_Layer] = []
        self.by_id: dict[str, _Layer] = {}
        self.pool_qty = 0
        self.pool_value = Decimal(0)
        self.last_unit: Decimal | None = None
        self.last_flags: set[AnyFlag] = set()
        self.sales: dict[str, Outflow] = {}
        self.writeoffs: dict[str, Outflow] = {}
        self.returns: dict[str, ReturnResult] = {}

    def _activate(self, lot: Lot, extra: CostFlag | None = None) -> None:
        layer = _Layer(lot, extra)
        self.open.append(layer)
        self.by_id[lot.id] = layer
        self.pool_qty += lot.qty
        self.pool_value += lot.total.amount

    def receive_until(self, day: date) -> None:
        while self.pending and self.pending[0].ready is not None and self.pending[0].ready <= day:
            self._activate(self.pending.pop(0))

    def _fallback(self) -> bool:
        """Tayyor lot tugadi: avval keyingi sanali lot ("erta sotuv"), keyin yo'ldagi lot."""
        if self.pending:
            self._activate(self.pending.pop(0), CostFlag.EARLY_SALE)
            return True
        if self.transit:
            self._activate(self.transit.pop(0), CostFlag.NOT_RECEIVED_MARKED)
            return True
        return False

    def take(self, event: Sale | WriteOff) -> None:
        need = event.qty
        allocations: list[Allocation] = []
        flags: set[AnyFlag] = set()
        while need > 0 and (self.pool_qty > 0 or self._fallback()):
            avg = self.pool_value / self.pool_qty
            layer = next(x for x in self.open if x.remaining > 0)
            take = min(need, layer.remaining)
            unit = layer.lot.unit if self.method is CostMethod.FIFO else avg
            layer.remaining -= take
            self.pool_qty -= take
            self.pool_value -= unit * take
            need -= take
            flags |= layer.flags
            allocations.append(Allocation(layer.lot.id, take, unit))
            self.last_unit, self.last_flags = unit, set(layer.flags)
        if need > 0:
            if self.last_unit is None:  # tovarda lot umuman yo'q
                self._record(event, None, (), flags | {CostFlag.NO_LOTS})
                return
            flags |= self.last_flags | {CostFlag.LOT_SHORTAGE}
            allocations.append(Allocation(None, need, self.last_unit))
        cost = Money(sum((a.unit * a.qty for a in allocations), Decimal(0)), UZS)
        self._record(event, cost, tuple(allocations), flags)

    def historical(self, event: Event, unit: Money | None) -> None:
        """F41: boshlashdan oldingi hodisa — lotga tegmaydi; sotuv tarixiy narxda (narx yo'q — ``None``).

        Qaytish hodisasi asl sotuvga qaytadi: tarixiy sotuvning qaytishi qoldiqqa qo'shilmaydi (u boshlang'ich
        qoldiq sonida)."""
        if isinstance(event, Return):
            sale = self.sales.get(event.sale_id)
            cost = None
            if sale is not None and sale.unit_cost is not None:
                cost = Money(sale.unit_cost.amount * min(event.qty, sale.qty), UZS)
            flags: frozenset[AnyFlag] = frozenset({CostFlag.HISTORICAL})
            self.returns[event.id] = ReturnResult(event.id, event.sale_id, event.qty, cost, flags)
            return
        if unit is None:
            self._record(event, None, (), {CostFlag.HISTORICAL})
            return
        cost = Money(unit.amount * event.qty, UZS)
        self._record(
            event, cost, (Allocation(None, event.qty, unit.amount),), {CostFlag.HISTORICAL}
        )

    def _record(
        self,
        event: Sale | WriteOff,
        cost: Money | None,
        allocations: tuple[Allocation, ...],
        flags: set[AnyFlag],
    ) -> None:
        out = Outflow(event.id, event.day, event.qty, cost, allocations, frozenset(flags))
        (self.sales if isinstance(event, Sale) else self.writeoffs)[event.id] = out

    def give_back(self, event: Return) -> None:
        """Qaytish asl sotuv qatlamlariga, sotuvdagi narxda (oxirgi olingan qatlamdan boshlab)."""
        sale = self.sales.get(event.sale_id)
        if sale is None or sale.cost is None:
            self.returns[event.id] = ReturnResult(
                event.id, event.sale_id, event.qty, None, frozenset({CostFlag.RETURN_UNMATCHED})
            )
            return
        returned = sum(
            r.qty for r in self.returns.values() if r.sale_id == sale.id and r.cost is not None
        )
        left = qty = min(event.qty, sale.qty - returned)
        value = Decimal(0)
        for alloc in reversed(sale.allocations):
            back = min(left, alloc.qty)
            if back == 0:
                break
            left -= back
            value += alloc.unit * back
            layer = self.by_id.get(alloc.lot_id or "")
            if layer is None:
                # Lot yetmagan qism: qaytgan tovar o'z narxida yangi qatlam bo'ladi.
                ghost = Lot(
                    f"{event.id}:{alloc.lot_id or 'shortage'}",
                    event.day,
                    back,
                    Money(alloc.unit * back, UZS),
                )
                self._activate(ghost)
                continue
            layer.remaining += back
            self.pool_qty += back
            self.pool_value += alloc.unit * back
        flags: set[AnyFlag] = set(sale.flags)
        if qty < event.qty:
            flags.add(CostFlag.RETURN_UNMATCHED)  # sotilganidan ko'p qaytish
        self.returns[event.id] = ReturnResult(
            event.id, event.sale_id, qty, Money(value, UZS), frozenset(flags)
        )

    def result(self, superseded: frozenset[str] = frozenset()) -> CostingResult:
        self.receive_until(date.max)
        remaining = {lid: layer.remaining for lid, layer in self.by_id.items()}
        remaining.update({lot.id: lot.qty for lot in self.transit})
        value = self.pool_value + sum((lot.total.amount for lot in self.transit), Decimal(0))
        return CostingResult(
            self.sales, self.writeoffs, self.returns, remaining, Money(value, UZS), superseded
        )

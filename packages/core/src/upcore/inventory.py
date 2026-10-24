"""Ombor va zaxira: F23–F34 (02-funksiyalar.md M10).

Kirish — kunlik statistika (sotuv, qaytish, snapshot qoldig'i), qoldiqlar, lot narxlari, postavkalar.
Chegaralar va koeffitsiyentlar ``InventorySettings`` da (standart qiymatlar — 02 dan; tashkilot sozlamasi).
Ma'lumot yetmasa raqam o'ylab topilmaydi: ``None`` qaytadi.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from statistics import median

from upcore.metrics import ratio
from upcore.money import Currency, DecimalLike, Money, quantize, to_decimal, total

D0, D1 = Decimal(0), Decimal(1)


class AbcClass(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class XyzClass(StrEnum):
    X = "X"
    Y = "Y"
    Z = "Z"


@dataclass(frozen=True, slots=True)
class InventorySettings:
    """F23–F30 parametrlari (standart — 02-funksiyalar.md)."""

    velocity_window: int = 14  # F23
    recent_window: int = 7  # oxirgi 7 kun 2 barobar vazn
    recent_weight: int = 2
    min_divisor_days: int = 7  # yangi tovar uchun kamida 7 kunga bo'linadi
    max_return_rate: Decimal = Decimal("0.5")
    trend_long_window: int = 30
    # (r chegarasi, koeffitsiyent): r ≥ 1,3 → 1,20; r ≥ 1,1 → 1,10; r > 0,9 → 1,00; r > 0,7 → 0,93; aks holda 0,85
    trend_steps: tuple[tuple[Decimal, Decimal], ...] = (
        (Decimal("1.3"), Decimal("1.20")),
        (Decimal("1.1"), Decimal("1.10")),
    )
    trend_neutral_low: Decimal = Decimal("0.9")
    trend_mild_low: Decimal = Decimal("0.7")
    trend_mild_factor: Decimal = Decimal("0.93")
    trend_low_factor: Decimal = Decimal("0.85")
    status_high_extra: int = 7  # F26: Yuqori ≤ muddat + 7
    status_medium_extra: int = 21  # O'rta ≤ muddat + 21
    leading_variant_share: Decimal = Decimal("0.2")
    cover_days: Mapping[AbcClass, int] = field(
        default_factory=lambda: {AbcClass.A: 60, AbcClass.B: 30, AbcClass.C: 14}
    )
    abc_a: Decimal = Decimal("0.80")
    abc_b: Decimal = Decimal("0.95")
    xyz_x: Decimal = Decimal("0.25")
    xyz_y: Decimal = Decimal("0.5")
    illiquid_days: int = 180  # F30
    slow_days: int = 90
    lead_history: int = 5  # F25: oxirgi 5 xarid medianasi
    lost_recent_supply_days: int = 3  # F31


DEFAULT = InventorySettings()


# --- F23. Sof sotuv tezligi -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DayStat:
    """Kunlik SKU statistikasi. ``in_stock`` — snapshot bo'yicha (``None`` — snapshot yo'q, hisobga olinadi)."""

    day: date
    sold: int = 0
    returned: int = 0
    in_stock: bool | None = None


@dataclass(frozen=True, slots=True)
class Velocity:
    """F23 natijasi va tarkibi (izoh uchun)."""

    base: Decimal  # vaznli o'rtacha, dona/kun
    return_rate: Decimal
    trend_ratio: Decimal | None
    trend_factor: Decimal
    days_counted: int

    @property
    def value(self) -> Decimal:
        return quantize(self.base * (1 - self.return_rate) * self.trend_factor, 4)


def _window(
    days: Sequence[DayStat], as_of: date, length: int, first_day: date | None
) -> list[DayStat]:
    start = as_of - timedelta(days=length - 1)
    if first_day is not None:
        start = max(start, first_day)
    return [d for d in days if start <= d.day <= as_of and d.in_stock is not False]


def _rate(items: Sequence[DayStat]) -> Decimal | None:
    return None if not items else Decimal(sum(d.sold for d in items)) / len(items)


def trend_factor(r: Decimal | None, s: InventorySettings = DEFAULT) -> Decimal:
    """F23 trend koeffitsiyenti: r = v7 / v30."""
    if r is None:
        return D1
    for bound, factor in s.trend_steps:
        if r >= bound:
            return factor
    if r > s.trend_neutral_low:
        return D1
    if r > s.trend_mild_low:
        return s.trend_mild_factor
    return s.trend_low_factor


def velocity(
    days: Sequence[DayStat],
    as_of: date,
    first_day: date | None = None,
    s: InventorySettings = DEFAULT,
) -> Velocity:
    """F23. Sof sotuv tezligi (dona/kun).

    Oxirgi 14 kun, oxirgi 7 kun 2 barobar vazn bilan; snapshot bo'yicha qoldiq 0 kunlar chiqariladi;
    ``first_day`` dan oldingi kunlar (tovar hali yo'q) olinmaydi. Hisobga olingan kunlar 7 dan kam bo'lsa —
    sotuvlar yig'indisi / 7 (yangi tovar). Keyin × (1 − qaytish darajasi, ≤ 0,5) × trend koeffitsiyenti.
    """
    window = _window(days, as_of, s.velocity_window, first_day)
    recent_from = as_of - timedelta(days=s.recent_window - 1)
    recent = [d for d in window if d.day >= recent_from]
    older = [d for d in window if d.day < recent_from]
    sold = sum(d.sold for d in window)
    if len(window) < s.min_divisor_days:
        base = Decimal(sold) / s.min_divisor_days
    else:
        w = s.recent_weight
        num = w * sum(d.sold for d in recent) + sum(d.sold for d in older)
        base = Decimal(num) / (w * len(recent) + len(older))
    returned = sum(d.returned for d in window)
    rate = ratio(returned, sold + returned) or D0
    rate = min(rate, s.max_return_rate)
    v7 = _rate(_window(days, as_of, s.recent_window, first_day))
    v30 = _rate(_window(days, as_of, s.trend_long_window, first_day))
    r = None if v7 is None or not v30 else quantize(v7 / v30, 4)
    return Velocity(base, rate, r, trend_factor(r, s), len(window))


# --- F24–F27 --------------------------------------------------------------------------------


def days_of_stock(fbo_active: int, fbs: int, speed: DecimalLike) -> Decimal | None:
    """F24. Zaxira kunlari = (FBO ``quantityActive`` + FBS ``quantityFbs``) / F23. Tezlik 0 — ``None``."""
    v = to_decimal(speed)
    if v <= 0:
        return None
    return quantize(Decimal(fbo_active + fbs) / v, 1)


@dataclass(frozen=True, slots=True)
class LeadTime:
    """F25 natijasi: bosqichlar bo'yicha kunlar va manba (tarix yoki standart)."""

    stages: Mapping[str, Decimal]
    learned: frozenset[str]

    @property
    def total(self) -> Decimal:
        return sum(self.stages.values(), D0)


def lead_time(
    history: Mapping[str, Sequence[int]],
    defaults: Mapping[str, int],
    s: InventorySettings = DEFAULT,
) -> LeadTime:
    """F25. To'liq muddat = bosqichlar yig'indisi. Har bosqich — oxirgi 5 xarid medianasi (tarix eng
    eskisidan yangisiga), tarix yo'q bo'lsa sozlamadagi standart. Bosqichlar: tayyorlash, Xitoy ichki,
    kargo yo'li, qabul/yorliq, Uzumga topshirish."""
    stages: dict[str, Decimal] = {}
    learned = set()
    for stage in {**defaults, **history}:
        past = list(history.get(stage, ()))[-s.lead_history :]
        if past:
            stages[stage] = Decimal(str(median(past)))
            learned.add(stage)
        elif stage in defaults:
            stages[stage] = Decimal(defaults[stage])
    return LeadTime(stages, frozenset(learned))


class StockStatus(StrEnum):
    """F26 holatlari (og'irlik tartibida)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    GOOD = "good"
    DEAD = "dead"  # Harakatsiz: tezlik 0, qoldiq > 0


def stock_status(
    stock: int, speed: DecimalLike, lead: DecimalLike, s: InventorySettings = DEFAULT
) -> StockStatus | None:
    """F26. Kritik (zaxira ≤ muddat) · Yuqori (≤ +7) · O'rta (≤ +21) · Yaxshi · Harakatsiz.

    Tezlik 0 va qoldiq 0 — ``None`` (sotuv ham, tovar ham yo'q)."""
    v, lt = to_decimal(speed), to_decimal(lead)
    if v <= 0:
        return StockStatus.DEAD if stock > 0 else None
    cover = Decimal(stock) / v
    if cover <= lt:
        return StockStatus.CRITICAL
    if cover <= lt + s.status_high_extra:
        return StockStatus.HIGH
    if cover <= lt + s.status_medium_extra:
        return StockStatus.MEDIUM
    return StockStatus.GOOD


_SEVERITY = list(StockStatus)


def product_status(
    variants: Sequence[tuple[StockStatus | None, int]], s: InventorySettings = DEFAULT
) -> StockStatus | None:
    """F26 mahsulot darajasida: ``variants`` — (holat, sotuv donasi).

    Sotuvning ≥ 20% ini bergan variant kritik bo'lsa — butun mahsulot kritik; aks holda eng ko'p
    sotilgan variant holati (sotuv yo'q bo'lsa — eng og'ir holat)."""
    known = [(st, n) for st, n in variants if st is not None]
    if not known:
        return None
    sold = sum(n for _, n in known)
    if sold > 0:
        for st, n in known:
            if st is StockStatus.CRITICAL and Decimal(n) / sold >= s.leading_variant_share:
                return StockStatus.CRITICAL
        return max(known, key=lambda x: x[1])[0]
    return min((st for st, _ in known), key=_SEVERITY.index)


@dataclass(frozen=True, slots=True)
class Reorder:
    """F27 natijasi: miqdor va byudjet (valyutalar bo'yicha)."""

    qty: int
    raw: Decimal
    budget: tuple[Money, ...]


def reorder(
    speed: DecimalLike,
    lead: DecimalLike,
    abc: AbcClass,
    stock: int,
    in_transit: int = 0,
    ordered: int = 0,
    batch: int = 1,
    last_unit_prices: Iterable[Money] = (),
    s: InventorySettings = DEFAULT,
) -> Reorder:
    """F27. Tavsiya miqdor = max(0, F23 × (F25 + qamrov) − (qoldiq + yo'lda + buyurtma qilingan)).

    Qamrov ABC bo'yicha (A 60, B 30, C 14 kun); natija odatiy partiya hajmiga yuqoriga yaxlitlanadi.
    Byudjet = miqdor × oxirgi lot narxi (har valyutada, masalan CNY va so'm)."""
    need = to_decimal(speed) * (to_decimal(lead) + s.cover_days[abc]) - (
        stock + in_transit + ordered
    )
    raw = max(need, D0)
    step = max(batch, 1)
    qty = int((raw / step).to_integral_value(rounding=ROUND_CEILING)) * step
    return Reorder(qty, quantize(raw, 2), tuple(p * qty for p in last_unit_prices))


# --- F28. ABC / XYZ -------------------------------------------------------------------------


def abc_classes(values: Mapping[str, Money], s: InventorySettings = DEFAULT) -> dict[str, AbcClass]:
    """F28 ABC: oxirgi 30 kun tushumi (yoki foydasi) kamayish tartibida; o'zidan oldingi jamlangan ulush
    < 80% — A, < 95% — B, qolgani C. Nol yoki manfiy qiymat — C."""
    positive = sorted(
        ((k, v.amount) for k, v in values.items() if v.amount > 0), key=lambda kv: (-kv[1], kv[0])
    )
    whole = sum((v for _, v in positive), D0)
    result = {k: AbcClass.C for k in values}
    cumulative = D0
    for key, value in positive:
        share = cumulative / whole
        result[key] = (
            AbcClass.A if share < s.abc_a else AbcClass.B if share < s.abc_b else AbcClass.C
        )
        cumulative += value
    return result


def xyz_class(weekly: Sequence[int], s: InventorySettings = DEFAULT) -> XyzClass | None:
    """F28 XYZ: oxirgi 8 hafta haftalik sotuvlarning variatsiya koeffitsiyenti (standart chetlanish / o'rtacha):
    ≤ 0,25 X, ≤ 0,5 Y, > 0,5 Z. Sotuv yo'q — ``None``."""
    if not weekly or sum(weekly) == 0:
        return None
    mean = Decimal(sum(weekly)) / len(weekly)
    var = sum(((Decimal(w) - mean) ** 2 for w in weekly), D0) / len(weekly)
    cv = var.sqrt() / mean
    return XyzClass.X if cv <= s.xyz_x else XyzClass.Y if cv <= s.xyz_y else XyzClass.Z


# --- F29–F30 --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Holding:
    """Joydagi qoldiq: joy (Xitoyda, yo'lda, o'z omborim, FBO, FBS, brak ...), dona, lot narxi (so'm)."""

    location: str
    qty: int
    unit_cost: Money


def frozen_money(holdings: Iterable[Holding]) -> dict[str, Money]:
    """F29. Muzlagan pul = Σ qoldiq × lot narxi, joylar bo'yicha."""
    result: dict[str, Money] = {}
    for h in holdings:
        result[h.location] = result.get(h.location, Money.zero(Currency.UZS)) + h.unit_cost * h.qty
    return result


def average_days_to_sell(items: Iterable[tuple[Decimal | None, Money]]) -> Decimal | None:
    """F29. O'rtacha sotilish muddati = Σ (zaxira kunlari × qiymat) / Σ qiymat (tezligi bor SKU'lar)."""
    pairs = [(dd, v.amount) for dd, v in items if dd is not None and v.amount > 0]
    weight = sum((v for _, v in pairs), D0)
    if weight == 0:
        return None
    return quantize(sum((dd * v for dd, v in pairs), D0) / weight, 1)


class Liquidity(StrEnum):
    ILLIQUID = "illiquid"  # nelikvid
    SLOW = "slow"  # sekin


def liquidity(
    stock: int,
    speed: DecimalLike,
    last_sale: date | None,
    as_of: date,
    s: InventorySettings = DEFAULT,
) -> Liquidity | None:
    """F30. Nelikvid = qoldiq > 0, tezlik 0 va (hech sotilmagan yoki oxirgi sotuvdan > 180 kun);
    "Sekin" = oxirgi sotuvdan 90–180 kun."""
    if stock <= 0 or to_decimal(speed) > 0:
        return None
    if last_sale is None:
        return Liquidity.ILLIQUID
    idle = (as_of - last_sale).days
    if idle > s.illiquid_days:
        return Liquidity.ILLIQUID
    if idle >= s.slow_days:
        return Liquidity.SLOW
    return None


# --- F31–F34 --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SupplyLine:
    """Postavka × SKU: e'lon qilingan (``quantityToStock``) va qabul qilingan (``quantityAccepted``)."""

    day: date
    declared: int
    accepted: int


@dataclass(frozen=True, slots=True)
class LostGoods:
    expected: int
    on_hand: int
    gap: int
    in_return_transit: int
    lost: int


def lost_goods(
    supplies: Sequence[SupplyLine],
    fbs_shipped: int,
    sold: int,
    returned: int,
    fbs_returned: int,
    defected: int,
    on_hand: int,
    in_return_transit: int,
    as_of: date,
    history_reliable: bool,
    s: InventorySettings = DEFAULT,
) -> LostGoods | None:
    """F31. Yo'qolgan tovar (SKU).

    Kutilgan = (FBO'ga qabul qilingan + FBS jo'natilgan) − sotilgan − (qaytarilgan + FBS qaytgan + brak);
    farq = max(0, kutilgan − omborda); yo'qolgan = max(0, farq − min(qaytish yo'lida, farq)).
    Asos — qabul qilingan dona (kamomad F33 da). Oxirgi 3 kunlik postavkalar chiqariladi; tarix
    ishonchsiz bo'lsa ``None`` (ko'rsatilmaydi)."""
    if not history_reliable:
        return None
    cutoff = as_of - timedelta(days=s.lost_recent_supply_days)
    accepted = sum(x.accepted for x in supplies if x.day < cutoff)
    expected = accepted + fbs_shipped - sold - (returned + fbs_returned + defected)
    gap = max(0, expected - on_hand)
    lost = max(0, gap - min(in_return_transit, gap))
    return LostGoods(expected, on_hand, gap, in_return_transit, lost)


def compensation_estimate(
    lost: int, last_prices: Sequence[Money], commission_pct: DecimalLike
) -> Money | None:
    """F32. Kompensatsiya taxmini = yo'qolgan × o'rtacha sotuv narxi (oxirgi 30 sotuv) × (1 − komissiya%)."""
    prices = list(last_prices)[-30:]
    if lost <= 0 or not prices:
        return None
    avg = total(prices, prices[0].currency).amount / len(prices)
    return Money(avg * lost * (1 - to_decimal(commission_pct) / 100), prices[0].currency)


def acceptance_shortage(supplies: Iterable[SupplyLine]) -> int:
    """F33. Qabul kamomadi = Σ (``quantityToStock`` − ``quantityAccepted``), postavka × SKU bo'yicha.

    Ortiqcha qabul qilingan qator (manfiy farq) boshqa qatorning kamomadini yopmaydi — har qator ≥ 0."""
    return sum(max(0, x.declared - x.accepted) for x in supplies)


def stockout_days(days: Iterable[DayStat]) -> int:
    """F34 uchun: snapshot bo'yicha qoldiq 0 bo'lgan kunlar (snapshot yo'q kunlar sanalmaydi)."""
    return sum(1 for d in days if d.in_stock is False)


def stockout_lost_profit(
    zero_days: int, speed_before: DecimalLike, avg_profit_per_unit: Money
) -> Money:
    """F34. Tugab qolishdan yo'qotilgan foyda = qoldiq 0 kunlar × tugashdan oldingi F23 × o'rtacha
    foyda/dona (oxirgi 90 kun). Manfiy foyda/dona bo'lsa yo'qotish 0."""
    if avg_profit_per_unit.amount <= 0:
        return Money.zero(avg_profit_per_unit.currency)
    return avg_profit_per_unit * (to_decimal(speed_before) * zero_days)


def weekly_sales(days: Iterable[DayStat], as_of: date, weeks: int = 8) -> list[int]:
    """F28 XYZ uchun: oxirgi ``weeks`` haftaning (``as_of`` bilan tugaydigan 7 kunlik bloklar) sotuvi."""
    result = [0] * weeks
    for d in days:
        idx = (as_of - d.day).days // 7
        if 0 <= idx < weeks:
            result[weeks - 1 - idx] += d.sold
    return result

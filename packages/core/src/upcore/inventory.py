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

    velocity_window: int = 14  # F23: oxirgi 14 ta savdoda bo'lgan kun (ADR-057 Q1)
    velocity_lookback: int = 60  # ... 60 kungacha orqaga qarab
    recent_window: int = 7  # eng yangi 7 ta hisobga olingan kun 2 barobar vazn
    recent_weight: int = 2
    min_divisor_days: int = 7  # tovar yoshi 7 kundan kam bo'lsa kamida 7 kunga bo'linadi
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
    storage_free_days: int = 60  # F43/F54: Uzum 60 kundan oshgan aylanmaga saqlash haqi oladi
    # F54: Uzumda maqsad zaxira (kun, ABC sinfi bo'yicha). Standarti yo'q (``None``) — sotuvchi sozlamaguncha reja chiqmaydi.
    ship_cover_days: Mapping[AbcClass, int] | None = None


DEFAULT = InventorySettings()


# --- F23. Sof sotuv tezligi -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DayStat:
    """Kunlik SKU statistikasi. ``sold`` — Yakunlangan + Jarayondagi dona (ADR-036), ``processing`` — shundan
    Jarayondagisi; ``in_stock`` — snapshot bo'yicha (``None`` — snapshot yo'q, hisobga olinadi)."""

    day: date
    sold: int = 0
    returned: int = 0
    in_stock: bool | None = None
    processing: int = 0

    def expected(self, completion: Decimal | None) -> Decimal:
        """Kutilgan yakuniy dona: Yakunlangan + Jarayondagi × yakunlanish ulushi (F16 R; noma'lum — 1)."""
        share = D1 if completion is None else completion
        return Decimal(self.sold - self.processing) + Decimal(self.processing) * share


@dataclass(frozen=True, slots=True)
class Velocity:
    """F23 natijasi va tarkibi (izoh uchun)."""

    base: Decimal  # vaznli o'rtacha, dona/kun (kutilgan yakuniy dona bo'yicha)
    completion: (
        Decimal | None
    )  # F16 R — Jarayondagi donaga ko'paytirilgan ulush (None — ma'lumot kam, 1 olingan)
    trend_ratio: Decimal | None
    trend_factor: Decimal
    days_counted: int
    new_item: bool = False  # tovar yoshi 7 kundan kam — kamida 7 kunga bo'lingan

    @property
    def value(self) -> Decimal:
        return quantize(self.base * self.trend_factor, 4)


def _window(
    days: Sequence[DayStat], as_of: date, length: int, first_day: date | None
) -> list[DayStat]:
    start = as_of - timedelta(days=length - 1)
    if first_day is not None:
        start = max(start, first_day)
    return [d for d in days if start <= d.day <= as_of and d.in_stock is not False]


def _rate(items: Sequence[DayStat], completion: Decimal | None) -> Decimal | None:
    return None if not items else sum((d.expected(completion) for d in items), D0) / len(items)


def _on_sale_days(
    days: Sequence[DayStat], as_of: date, s: InventorySettings, first_day: date | None
) -> list[DayStat]:
    """F23 oynasi: ``as_of`` dan orqaga ``velocity_lookback`` kun ichidagi savdoda bo'lgan (qoldiq 0 emas) kunlardan
    eng yangi ``velocity_window`` tasi, yangidan eskiga."""
    pool = _window(days, as_of, s.velocity_lookback, first_day)
    return sorted(pool, key=lambda d: d.day, reverse=True)[: s.velocity_window]


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
    completion: Decimal | None = None,
) -> Velocity:
    """F23. Sof sotuv tezligi (dona/kun; ADR-057 Q1).

    Oyna — oxirgi 14 ta **savdoda bo'lgan** kun (snapshot bo'yicha qoldiq 0 kunlar o'tkazib yuboriladi), 60 kungacha
    orqaga; ``first_day`` dan oldingi kunlar (tovar hali yo'q) olinmaydi. Eng yangi 7 ta kun 2 barobar vazn bilan.
    Kunlik dona — kutilgan yakuniy: Yakunlangan + Jarayondagi × ``completion`` (F16 R; ``None`` — 1). Tovar yoshi
    (``first_day`` dan) 7 kundan kam bo'lsa — yig'indi / 7; aks holda faqat hisobga olingan kunlarga bo'linadi.
    Keyin × trend koeffitsiyenti (r = v7 / v30, kalendar kunlari bo'yicha, qoldiq 0 kunlarsiz).
    """
    window = _on_sale_days(days, as_of, s, first_day)
    new_item = first_day is not None and (as_of - first_day).days + 1 < s.min_divisor_days
    units = [d.expected(completion) for d in window]  # yangidan eskiga
    if new_item:
        base = sum(units, D0) / s.min_divisor_days
    elif not window:
        base = D0
    else:
        recent, older = units[: s.recent_window], units[s.recent_window :]
        w = s.recent_weight
        base = (w * sum(recent, D0) + sum(older, D0)) / (w * len(recent) + len(older))
    v7 = _rate(_window(days, as_of, s.recent_window, first_day), completion)
    v30 = _rate(_window(days, as_of, s.trend_long_window, first_day), completion)
    r = None if v7 is None or not v30 else quantize(v7 / v30, 4)
    return Velocity(base, completion, r, trend_factor(r, s), len(window), new_item)


# --- F24–F27 --------------------------------------------------------------------------------


def days_of_stock(fbo_active: int, fbs: int, speed: DecimalLike) -> Decimal | None:
    """F24. Zaxira kunlari = (FBO ``quantityActive`` + FBS ``quantityFbs``) / F23. Tezlik 0 — ``None``."""
    v = to_decimal(speed)
    if v <= 0:
        return None
    return quantize(Decimal(fbo_active + fbs) / v, 1)


LEAD_ITEM = "item"  # tovarning o'z xaridlari (oxirgi 5 ta medianasi)
LEAD_SUPPLIER = "supplier"  # shu yetkazib beruvchining xaridlari
LEAD_ORG = "org"  # tashkilotning hamma xaridlari
LEAD_DEFAULT = "default"  # Sozlamalardagi standart


@dataclass(frozen=True, slots=True)
class LeadTime:
    """F25 natijasi: bo'laklar bo'yicha kunlar va manba (B5.1): har bo'lak qaysi manbadan (tovar → yetkazib beruvchi →
    tashkilot → standart) va nechta xariddan o'rganilgani — UI "5 xaridingizdan" / "standart" deb yozadi."""

    stages: Mapping[str, Decimal]
    learned: frozenset[str]
    sources: Mapping[str, str] = field(default_factory=dict)
    samples: Mapping[str, int] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        return sum(self.stages.values(), D0)


def learn_lead(
    item: Mapping[str, Sequence[int]],
    supplier: Mapping[str, Sequence[int]],
    org: Mapping[str, Sequence[int]],
    defaults: Mapping[str, int],
    s: InventorySettings = DEFAULT,
) -> LeadTime:
    """F25 (B5.1). To'liq muddat = bo'laklar yig'indisi (yo'l + Uzumga topshirish). Har bo'lak uchun tartib bilan birinchi
    manba: tovar (oxirgi 5 xarid medianasi, tarix eng eskisidan yangisiga) → yetkazib beruvchi (ko'rsatilgan bo'lsa) →
    tashkilot medianasi → Sozlamalardagi standart; hech biri yo'q bo'lsa bo'lak noma'lum (raqam o'ylab topilmaydi)."""
    stages: dict[str, Decimal] = {}
    learned: set[str] = set()
    sources: dict[str, str] = {}
    samples: dict[str, int] = {}
    parts = {*defaults, *item, *supplier, *org}
    for part in sorted(parts):
        for source, history in ((LEAD_ITEM, item), (LEAD_SUPPLIER, supplier), (LEAD_ORG, org)):
            past = list(history.get(part, ()))[-s.lead_history :]
            if past:
                stages[part] = Decimal(str(median(past)))
                learned.add(part)
                sources[part], samples[part] = source, len(past)
                break
        else:
            if part in defaults:
                stages[part] = Decimal(defaults[part])
                sources[part], samples[part] = LEAD_DEFAULT, 0
    return LeadTime(stages, frozenset(learned), sources, samples)


def lead_time(
    history: Mapping[str, Sequence[int]],
    defaults: Mapping[str, int],
    s: InventorySettings = DEFAULT,
) -> LeadTime:
    """F25, bitta tarix manbasi (tashkilot): :func:`learn_lead` ning soddalashgan ko'rinishi."""
    return learn_lead({}, {}, history, defaults, s)


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
    """F26 "Buyurtma berish" (ADR-057 Q2). Kritik (zaxira ≤ muddat) · Yuqori (≤ +7) · O'rta (≤ +21) · Yaxshi ·
    Harakatsiz. ``stock`` — **hamma joydagi** tovar (Uzum + postavka + o'z omborim + yo'lda + Xitoyda), ``lead`` —
    to'liq muddat (F25). Tezlik 0 va qoldiq 0 — ``None`` (sotuv ham, tovar ham yo'q)."""
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


@dataclass(frozen=True, slots=True)
class ItemSku:
    """Tovarning bitta SKU'si F27 tovar darajasidagi hisobi uchun: talab (F23), Uzumdagi qoldiq va postavkadagi dona."""

    key: str
    speed: Decimal
    stock: int
    inbound: int = 0


def split_by_weight(total: int, weights: Sequence[Decimal]) -> list[int]:
    """``total`` ni og'irliklarga mutanosib butun sonlarga bo'ladi (eng katta qoldiq usuli): yig'indi doim ``total``;
    nol og'irlik — nol ulush (hamma og'irlik nol bo'lsa, hammasi nol)."""
    weight = sum(weights, D0)
    if total <= 0 or weight <= 0:
        return [0] * len(weights)
    exact = [Decimal(total) * w / weight for w in weights]
    parts = [int(x) for x in exact]
    rest = total - sum(parts)
    order = sorted(
        range(len(weights)), key=lambda i: (exact[i] - parts[i], weights[i]), reverse=True
    )
    for i in order[:rest]:
        parts[i] += 1
    return parts


def item_reorder(
    skus: Sequence[ItemSku],
    lead: DecimalLike,
    abc: AbcClass,
    china: int,
    road: int,
    own: int,
    batch: int = 1,
    last_unit_prices: Iterable[Money] = (),
    s: InventorySettings = DEFAULT,
) -> tuple[Reorder, dict[str, Reorder]]:
    """F27 tovar darajasida (B5.2, 09 §12 B11): bir tovar bir necha SKU'da bo'lsa talab — SKU'lar tezligi yig'indisi,
    qoldiq — SKU'lar yig'indisi, yo'ldagi, o'z omborimdagi va Xitoydagi dona — **bir marta** (har SKU'ga to'liq emas).
    Tovar miqdori SKU'larga talabiga mutanosib bo'linadi (yig'indi — tovar miqdori); tezligi nol SKU — nol ulush.
    Qaytaradi: tovar rejasi va SKU kaliti → ulush."""
    speed = sum((x.speed for x in skus), D0)
    stock = sum(x.stock for x in skus)
    inbound = sum(x.inbound for x in skus)
    whole = reorder(
        speed,
        lead,
        abc,
        stock,
        in_transit=road + own + inbound,
        ordered=china,
        batch=batch,
        last_unit_prices=last_unit_prices,
        s=s,
    )
    prices = tuple(last_unit_prices)
    shares = split_by_weight(whole.qty, [x.speed for x in skus])
    raws = (
        [quantize(whole.raw * x.speed / speed, 2) for x in skus] if speed > 0 else [D0] * len(skus)
    )
    parts = {
        x.key: Reorder(q, r, tuple(p * q for p in prices))
        for x, q, r in zip(skus, shares, raws, strict=True)
    }
    return whole, parts


@dataclass(frozen=True, slots=True)
class OrderBy:
    """F27 buyurtma sanasi: ``day`` — shu kungacha buyurtma berilsa tovar tugamasdan keladi."""

    day: date
    overdue: bool  # zaxira muddatdan oldin tugaydi — buyurtma berish kechikkan (sana — bugun)


def order_by(
    as_of: date, cover_days: DecimalLike | None, lead: DecimalLike | None
) -> OrderBy | None:
    """F27 buyurtma sanasi = bugun + (zaxira kunlari F24 − to'liq muddat F25), butun kunga pastga yaxlitlanadi.

    Zaxira kunlari ``cover_days`` (F24) tovar tugaydigan kungacha; ``lead`` (F25) — buyurtma kelgunicha o'tadigan
    muddat. Farq 0 yoki manfiy (F26 "Kritik") bo'lsa buyurtma kechikkan: sana — bugun, ``overdue``. Tezlik 0
    (zaxira kunlari yo'q) yoki muddat noma'lum bo'lsa — ``None`` (sana o'ylab topilmaydi)."""
    if cover_days is None or lead is None:
        return None
    slack = to_decimal(cover_days) - to_decimal(lead)
    if slack <= 0:
        return OrderBy(as_of, True)
    return OrderBy(as_of + timedelta(days=int(slack)), False)


@dataclass(frozen=True, slots=True)
class ShipSignal:
    """F26 "Uzumga yuborish" signali (ADR-057 Q2): Uzumdagi (va postavkadagi) zaxira Uzumga topshirish muddatiga
    yetmaydi, o'z omborimda esa tovar bor."""

    cover_days: Decimal  # Uzum + postavka zaxirasi necha kunga yetadi
    handover_days: Decimal  # F25 "Uzumga topshirish" bosqichi
    own: int  # o'z omborimdagi dona (yuborish mumkin)


def ship_signal(
    uzum: int, own: int, speed: DecimalLike, handover_days: DecimalLike | None
) -> ShipSignal | None:
    """F26 "Uzumga yuborish" (ADR-057 Q2): ``uzum`` — Uzum qoldig'i + postavkadagi (yo'lda Uzumga) dona; signal —
    o'z omborimda tovar bor va ``uzum / tezlik`` ≤ topshirish muddati. Tezlik 0, muddat noma'lum yoki omborim bo'sh
    bo'lsa — ``None`` (yuborishga sabab yo'q yoki raqam o'ylab topilmaydi)."""
    v = to_decimal(speed)
    if own <= 0 or v <= 0 or handover_days is None:
        return None
    cover = Decimal(uzum) / v
    lt = to_decimal(handover_days)
    if cover > lt:
        return None
    return ShipSignal(quantize(cover, 1), lt, own)


@dataclass(frozen=True, slots=True)
class ShipPlan:
    """F54 "Uzumga yuborish rejasi": ``qty`` — yuboriladigan dona (omboringdan oshmaydi), ``need`` — omborim cheklovisiz
    kerak bo'lgan dona, ``target_days`` — maqsad qamrov, ``days_after`` — yuborgandan keyin Uzumda necha kunga yetadi,
    ``overstock`` — ``days_after`` Uzum bepul saqlash muddatidan (60 kun, F43) oshdi."""

    qty: int
    need: int
    target_days: int
    days_after: Decimal
    overstock: bool


def ship_plan(
    uzum: int,
    own: int,
    speed: DecimalLike,
    handover_days: DecimalLike | None,
    target_days: int | None,
    s: InventorySettings = DEFAULT,
) -> ShipPlan | None:
    """F54. Yuborish = min(omborim, max(0, F23 × (topshirish muddati + maqsad qamrov) − (Uzum qoldig'i + postavkada))).

    ``uzum`` — Uzum qoldig'i + postavkadagi dona (F26 "Uzumga yuborish" dagidek). Maqsad qamrov sotuvchi sozlaydi (ABC
    sinfi bo'yicha, standarti yo'q): tezlik 0, muddat yoki maqsad noma'lum bo'lsa — ``None`` (raqam o'ylab topilmaydi).
    Yuborgandan keyingi zaxira ``s.storage_free_days`` dan oshsa — ``overstock`` (Uzum saqlash haqi oladi, F43)."""
    v = to_decimal(speed)
    if v <= 0 or handover_days is None or target_days is None:
        return None
    raw = max(v * (to_decimal(handover_days) + target_days) - uzum, D0)
    need = int(raw.to_integral_value(rounding=ROUND_CEILING))
    qty = min(max(own, 0), need)
    after = quantize(Decimal(uzum + qty) / v, 1)
    return ShipPlan(qty, need, target_days, after, after > s.storage_free_days)


# --- M10 joylar: yo'ldagi, buyurtma qilingan va o'z omboridagi tovar -------------------------


def own_warehouse_qty(received: int, adjustments: int = 0, writeoffs: int = 0) -> int:
    """M10 "O'z omborim": qabul qilingan, hali Uzumga yuborilmagan xarid qatorlari + inventarizatsiya tuzatishlari
    (``adjustments`` — ishorali) − hisobdan chiqarilgan (``writeoffs`` — musbat dona). Manfiy bo'lmaydi.

    F27 da bu tovar qoldiqqa qo'shiladi (Uzumga yuborilishi kutilmoqda), F29 da alohida joy."""
    return max(0, received + adjustments - abs(writeoffs))


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


# Uzum shartnomasi (08 §9): 4.6 — postavka 24 soatdan 7 kungacha qabul qilinadi; 4.13 — nomuvofiqlik dalolatnomasiga
# 30 kun ichida e'tiroz bildiriladi (TM9.2, ADR-068 (2)).
RECEIVING_WINDOW_DAYS = 7
CLAIM_DAYS = 30


def receiving_done(
    accepted_on: date,
    today: date,
    declared: int,
    accepted: int,
    window_days: int = RECEIVING_WINDOW_DAYS,
) -> bool:
    """F33 qachon hisoblanadi (TM9.2): Uzum qabulni bosqichma-bosqich qiladi (ADR-055: 719 dona, ertasiga yana 25) —
    farq faqat **qabul tugagach**: postavka ``ACCEPTED`` bo'lgan kundan ``window_days`` kun o'tdi yoki qabul qilingan
    dona e'lon qilinganga yetdi. Undan oldin — "qabul davom etmoqda"."""
    return accepted >= declared or today >= accepted_on + timedelta(days=window_days)


def claim_until(accepted_on: date, days: int = CLAIM_DAYS) -> date:
    """ "Uzum yo'qotdi" kamomadi bo'yicha da'vo muddati (shartnoma 4.13): qabul kunidan ``days`` kun."""
    return accepted_on + timedelta(days=days)


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

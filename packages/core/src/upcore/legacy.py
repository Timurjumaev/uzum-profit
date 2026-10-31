"""Legacy partiyalarini ko'chirish (B4.9, 03 §16): legacy ``batches`` → yangi xarid modeli (F20) va legacy formulasi.

Legacy partiyasi (``uzum_profit/costs.py``): tovar uchun to'langan CNY + CNY kursi, qatorlar (SKU yoki vaqtinchalik
nom, dona, ixtiyoriy CNY narx), kargo USD + kurs (``NULL`` — hali kiritilmagan, 0 — kargo yo'q), qo'shimcha chiqimlar
(so'm). Ko'chirish qoidasi (legacy natijasi 1 tiyingacha saqlanadi, M9 qabul mezoni):

- tovar — narxli qatorlar o'z narxida (har biri alohida komponent, faqat o'sha qatorga), qolgan summa narxsiz qatorlarga
  dona bo'yicha (``residual_goods``); hamma qator narxli bo'lsa umumiy summa e'tiborga olinmaydi (legacy kabi);
- kargo va qo'shimchalar — hamma qatorga dona bo'yicha (legacy kabi; vazn bo'yicha emas);
- kurslar — partiyadagi qo'lda kurs (``RateSource.MANUAL``): tovar — buyurtma sanasi, kargo — kargo sanasi;
- sotuvga tayyor sana (F21): kargo sanasi; kargo kiritilgan, sanasi yo'q — buyurtma sanasi (legacy
  ``effective_date``); kargo kiritilmagan — "yo'lda".

Kursi yo'q summa (masalan CNY kursisiz tovar) legacy'da 0 deb olinadi — ko'chirishda komponent yaratilmaydi va
ogohlantirish qaytadi (raqam o'ylab topilmaydi).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from upcore.fx import manual_rate
from upcore.money import Money, to_decimal
from upcore.purchasing import (
    AllocationBase,
    ComponentKind,
    CostComponent,
    Purchase,
    PurchaseLine,
    residual_goods,
)

ZERO = Decimal(0)
TOLERANCE = Decimal("0.01")  # so'm/dona: legacy va yangi birlik tannarx farqi (M9 qabul mezoni)
HALF_TIYIN = Decimal("0.005")


def decimal_of(value: object) -> Decimal | None:
    """Legacy (SQLite REAL/INTEGER/TEXT) qiymati → ``Decimal`` (float ikkilik xatosisiz, matn orqali)."""
    if value is None or value == "":
        return None
    if isinstance(value, float):
        return Decimal(repr(value))
    return to_decimal(str(value).strip().replace(",", "."))


@dataclass(frozen=True, slots=True)
class LegacyLine:
    id: int
    qty: int
    sku: str | None = None
    label: str | None = None
    cny_unit: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LegacyExtra:
    id: int
    name: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LegacyBatch:
    """Legacy partiyasi (``batches`` + ``batch_lines`` + ``batch_extras``)."""

    id: int
    shop_id: int | None
    day: date
    goods_cny: Decimal | None = None
    cny_rate: Decimal | None = None
    cargo_usd: Decimal | None = None
    usd_rate: Decimal | None = None
    cargo_day: date | None = None
    title: str | None = None
    note: str | None = None
    lines: tuple[LegacyLine, ...] = ()
    extras: tuple[LegacyExtra, ...] = ()

    @property
    def cargo_entered(self) -> bool:
        return self.cargo_usd is not None

    @property
    def ready_date(self) -> date | None:
        """F21 (legacy ``effective_date``): kargo sanasi (buyurtmadan oldin emas); kargo kiritilgan, sanasi yo'q —
        buyurtma sanasi; kargo kiritilmagan — ``None`` ("yo'lda")."""
        if self.cargo_day is not None:
            return max(self.day, self.cargo_day)
        return self.day if self.cargo_entered else None


def legacy_unit_costs(batch: LegacyBatch) -> list[Decimal]:
    """Legacy formulasi (``uzum_profit.costs.compute_batch``, Decimal'da) — solishtirma hisobot uchun (F20 bilan):

    tovar/dona = qator CNY narxi (yo'q bo'lsa: (tovar CNY − narxli qatorlar) / narxsiz dona, manfiy bo'lsa 0) × CNY
    kursi; kargo/dona = kargo USD / jami dona × USD kursi; qo'shimcha/dona = qo'shimchalar / jami dona. Har qator uchun
    birlik tannarx (qatorlar tartibida); donasiz partiya — bo'sh ro'yxat.
    """
    units = sum(x.qty for x in batch.lines)
    if units <= 0:
        return []
    explicit = sum((x.qty * x.cny_unit for x in batch.lines if x.cny_unit is not None), ZERO)
    rest_units = sum(x.qty for x in batch.lines if x.cny_unit is None)
    rest = max((batch.goods_cny or ZERO) - explicit, ZERO) / rest_units if rest_units else ZERO
    cargo = (batch.cargo_usd or ZERO) / units * (batch.usd_rate or ZERO)
    extra = sum((e.amount for e in batch.extras), ZERO) / units
    rate = batch.cny_rate or ZERO
    return [
        (x.cny_unit if x.cny_unit is not None else rest) * rate + cargo + extra for x in batch.lines
    ]


@dataclass(frozen=True, slots=True)
class Migration:
    """Ko'chirish natijasi: yangi model (qator id — legacy qator id satri) va ogohlantirishlar."""

    purchase: Purchase
    warnings: tuple[str, ...]


def to_purchase(batch: LegacyBatch) -> Migration:
    """Legacy partiyasi → ``Purchase`` (modul hujjatidagi qoida). Komponent kursining sanasi — to'lov sanasi."""
    lines = tuple(
        PurchaseLine(
            str(x.id),
            x.qty,
            x.qty,
            None if x.cny_unit is None else Money.of(x.cny_unit, "CNY"),
        )
        for x in batch.lines
    )
    warnings: list[str] = []
    comps: list[CostComponent] = []
    goods = batch.goods_cny or ZERO
    if batch.cny_rate:
        cny = manual_rate(batch.day, "CNY", batch.cny_rate)
        comps += [
            CostComponent(
                ComponentKind.GOODS,
                x.unit_price * x.qty,
                cny,
                AllocationBase.UNITS,
                line_ids=(x.id,),
            )
            for x in lines
            if x.unit_price is not None and x.qty > 0 and x.unit_price.amount > 0
        ]
        rest, unpriced = residual_goods(Money.of(goods, "CNY"), lines)
        if not rest.is_zero() and (unpriced or not lines):
            target = None if len(unpriced) == len(lines) else unpriced
            comps.append(
                CostComponent(ComponentKind.GOODS, rest, cny, AllocationBase.UNITS, line_ids=target)
            )
    elif goods or any(x.cny_unit for x in batch.lines):
        warnings.append(
            "CNY kursi yo'q — tovar summasi ko'chirilmadi (legacy ham 0 deb hisoblaydi)"
        )

    if batch.cargo_usd is not None:
        rate = batch.usd_rate or (Decimal(1) if batch.cargo_usd == 0 else None)
        if rate is None:
            warnings.append(
                "USD kursi yo'q — kargo summasi ko'chirilmadi (legacy ham 0 deb hisoblaydi)"
            )
        else:
            comps.append(
                CostComponent(
                    ComponentKind.CARGO,
                    Money.of(batch.cargo_usd, "USD"),
                    manual_rate(batch.ready_date or batch.day, "USD", rate),
                    AllocationBase.UNITS,
                )
            )
    comps += [
        CostComponent(ComponentKind.OTHER, Money.of(e.amount, "UZS"), None, AllocationBase.UNITS)
        for e in batch.extras
        if e.amount
    ]
    if not lines:
        warnings.append("qatorlar yo'q — birlik tannarx qatorlar kiritilgach hisoblanadi")
    elif sum(x.qty for x in lines) <= 0:
        warnings.append("hamma qatorda dona 0 — birlik tannarx yo'q")
    has_cargo_comp = any(c.kind is ComponentKind.CARGO for c in comps)
    return Migration(
        Purchase(
            f"B{batch.id}",
            lines,
            tuple(comps),
            order_date=batch.day,
            cargo_paid_date=batch.ready_date if has_cargo_comp else None,
        ),
        tuple(warnings),
    )


def tolerance(qty: int, lines: int, components: int) -> Decimal:
    """Birlik tannarx farqi uchun ruxsat (so'm/dona): 1 tiyin yoki yaxlitlash qoldig'i — yangi hisobda har komponent
    qatorlarga tiyingacha bo'linadi va qoldiq eng katta qatorga tushadi (F20), ya'ni qator jami legacy'dan ko'pi bilan
    0,005 × qatorlar × komponentlar so'm farq qiladi (legacy esa donaga yaxlitlamasdan bo'ladi)."""
    if qty <= 0:
        return TOLERANCE
    return max(TOLERANCE, HALF_TIYIN * max(lines, 1) * max(components, 1) / qty)


def worst_difference(legacy: Sequence[Decimal], new: Sequence[Decimal | None]) -> Decimal:
    """Qatorlar bo'yicha eng katta |legacy − yangi| birlik tannarx farqi (yangi yo'q qator — legacy qiymati)."""
    return max(
        (abs(old - (n if n is not None else ZERO)) for old, n in zip(legacy, new, strict=True)),
        default=ZERO,
    )

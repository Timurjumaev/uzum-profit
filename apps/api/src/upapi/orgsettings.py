"""Tashkilot sozlamalari (``orgs.settings``, B4.8): standart yetkazish muddatlari (F25), ABC qamrov kunlari (F27) va
ogohlantirish chegaralari (ADR-043: bekor va qaytarish ulushi — bosh sahifa kartochkasi chegaradan oshsa belgilanadi),
"Chegarada" marja chegarasi (B5.0b, F13 — Mahsulotlar holat belgisi).

Biznes doimiylari bazada (tamoyil 2). Bo'sh sozlama — standart: muddat faqat xaridlar tarixidan o'rganiladi (tarix
yo'q bo'lsa noma'lum — raqam o'ylab topilmaydi), qamrov — ``upcore.inventory`` standarti (A 60, B 30, C 14). Bu yerda
faqat o'qish va tekshirish; hisob — ``upcore``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.inventory import DEFAULT, AbcClass, InventorySettings
from upcore.metrics import DEFAULT_BORDERLINE
from upcore.purchasing import LEAD_PARTS, TRANSIT

from upapi.db import models as m

STAGES = LEAD_PARTS  # F25 (B5.1): yo'l va Uzumga topshirish
OLD_TRANSIT = ("prep", "china", "cargo", "receive")  # eski besh bosqichli sozlama (B5.1 gacha)
MAX_LEAD_DAYS = 365
MAX_COVER_DAYS = 365
ALERTS = ("cancel_share", "return_share")  # ADR-043: F17 va F18 ulushlari (kasr, 0..1)
type Alert = Literal["cancel_share", "return_share"]


def _share(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        share = Decimal(str(value))
    except InvalidOperation:
        return None
    return share if 0 < share <= 1 else None


@dataclass(frozen=True, slots=True)
class OrgSettings:
    lead_days: dict[str, int] = field(default_factory=dict)  # bosqich → kun; bo'sh — sozlanmagan
    cover_days: dict[AbcClass, int] = field(default_factory=dict)  # bo'sh — standart
    # F54: Uzumda maqsad zaxira (kun, ABC bo'yicha); bo'sh — sozlanmagan (yuborish rejasi chiqmaydi, standart yo'q).
    ship_cover_days: dict[AbcClass, int] = field(default_factory=dict)
    # ADR-043: ogohlantirish chegaralari (ulush, 0..1); bo'sh — ogohlantirish yo'q (kodda standart chegara yo'q).
    alerts: dict[str, Decimal] = field(default_factory=dict)
    # B5.0b: "Chegarada" chegarasi (F13 marja, kasr 0..1); ``None`` — standart (``upcore.metrics.DEFAULT_BORDERLINE``).
    borderline: Decimal | None = None

    @property
    def margin_borderline(self) -> Decimal:
        """M6 holat belgisi uchun amaldagi chegara: sozlangan yoki standart."""
        return DEFAULT_BORDERLINE if self.borderline is None else self.borderline

    def over(self, key: Alert, value: Decimal | None) -> bool:
        """Ulush sozlangan chegaradan oshdimi (chegara yo'q yoki qiymat yo'q — ``False``)."""
        limit = self.alerts.get(key)
        return limit is not None and value is not None and value > limit

    def inventory(self) -> InventorySettings:
        """F23–F30 parametrlari: sozlangan qamrov standartni almashtiradi."""
        if not self.cover_days and not self.ship_cover_days:
            return DEFAULT
        return InventorySettings(
            cover_days={**DEFAULT.cover_days, **self.cover_days},
            ship_cover_days=dict(self.ship_cover_days) if self.ship_cover_days else None,
        )


def _lead_days(lead: dict[str, Any]) -> dict[str, int]:
    """Standart muddatlar (F25). Eski besh bosqichli saqlangan qiymatlar ikki bo'lakka ko'chadi (B5.1): yo'l = tayyorlash +
    Xitoy ichki + kargo + qabul yig'indisi, topshirish o'zgarmaydi; yangi kalitlar ustun."""

    def ok(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0

    out = {k: int(v) for k, v in lead.items() if k in STAGES and ok(v)}
    if TRANSIT not in out and all(ok(lead.get(k)) for k in OLD_TRANSIT):
        out[TRANSIT] = sum(int(lead[k]) for k in OLD_TRANSIT)
    return out


def parse(raw: Any) -> OrgSettings:
    """Bazadagi JSON → sozlama. Noto'g'ri yoki noma'lum kalitlar tashlanadi (qo'lda tahrir ham tizimni buzmaydi)."""
    data = raw if isinstance(raw, dict) else {}
    lead = data.get("lead_days")
    cover = data.get("cover_days")
    ship = data.get("ship_cover_days")
    lead_days = _lead_days(lead) if isinstance(lead, dict) else {}
    cover_days = (
        {
            AbcClass(k): int(v)
            for k, v in cover.items()
            if k in AbcClass.__members__ and isinstance(v, int) and v >= 0
        }
        if isinstance(cover, dict)
        else {}
    )
    ship_cover = (
        {
            AbcClass(k): int(v)
            for k, v in ship.items()
            if k in AbcClass.__members__
            and isinstance(v, int)
            and not isinstance(v, bool)
            and v >= 0
        }
        if isinstance(ship, dict)
        else {}
    )
    if set(ship_cover) != set(AbcClass):  # to'liq A, B, C bo'lmasa — sozlanmagan
        ship_cover = {}
    alerts_raw = data.get("alerts")
    alerts = (
        {k: v for k, v in ((k, _share(alerts_raw.get(k))) for k in ALERTS) if v is not None}
        if isinstance(alerts_raw, dict)
        else {}
    )
    return OrgSettings(
        lead_days, cover_days, ship_cover, alerts, _share(data.get("margin_borderline"))
    )


def dump(settings: OrgSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if settings.lead_days:
        out["lead_days"] = dict(settings.lead_days)
    if settings.cover_days:
        out["cover_days"] = {k.value: v for k, v in settings.cover_days.items()}
    if settings.ship_cover_days:
        out["ship_cover_days"] = {k.value: v for k, v in settings.ship_cover_days.items()}
    if settings.alerts:
        out["alerts"] = {k: str(v) for k, v in settings.alerts.items()}
    if settings.borderline is not None:
        out["margin_borderline"] = str(settings.borderline)
    return out


async def load(conn: AsyncConnection) -> OrgSettings:
    """Joriy tashkilot sozlamasi (RLS faqat o'z tashkilot qatorini ko'rsatadi)."""
    raw = await conn.scalar(select(m.orgs.c.settings))
    return parse(raw)

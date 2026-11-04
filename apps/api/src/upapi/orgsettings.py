"""Tashkilot sozlamalari (``orgs.settings``, B4.8): standart yetkazish muddatlari (F25), ABC qamrov kunlari (F27) va
ogohlantirish chegaralari (ADR-043: bekor va qaytarish ulushi — bosh sahifa kartochkasi chegaradan oshsa belgilanadi).

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
from upcore.purchasing import LEAD_STAGES

from upapi.db import models as m

STAGES = tuple(name for name, _, _ in LEAD_STAGES)
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
    # ADR-043: ogohlantirish chegaralari (ulush, 0..1); bo'sh — ogohlantirish yo'q (kodda standart chegara yo'q).
    alerts: dict[str, Decimal] = field(default_factory=dict)

    def over(self, key: Alert, value: Decimal | None) -> bool:
        """Ulush sozlangan chegaradan oshdimi (chegara yo'q yoki qiymat yo'q — ``False``)."""
        limit = self.alerts.get(key)
        return limit is not None and value is not None and value > limit

    def inventory(self) -> InventorySettings:
        """F23–F30 parametrlari: sozlangan qamrov standartni almashtiradi."""
        if not self.cover_days:
            return DEFAULT
        return InventorySettings(cover_days={**DEFAULT.cover_days, **self.cover_days})


def parse(raw: Any) -> OrgSettings:
    """Bazadagi JSON → sozlama. Noto'g'ri yoki noma'lum kalitlar tashlanadi (qo'lda tahrir ham tizimni buzmaydi)."""
    data = raw if isinstance(raw, dict) else {}
    lead = data.get("lead_days")
    cover = data.get("cover_days")
    lead_days = (
        {k: int(v) for k, v in lead.items() if k in STAGES and isinstance(v, int) and v >= 0}
        if isinstance(lead, dict)
        else {}
    )
    cover_days = (
        {
            AbcClass(k): int(v)
            for k, v in cover.items()
            if k in AbcClass.__members__ and isinstance(v, int) and v >= 0
        }
        if isinstance(cover, dict)
        else {}
    )
    alerts_raw = data.get("alerts")
    alerts = (
        {k: v for k, v in ((k, _share(alerts_raw.get(k))) for k in ALERTS) if v is not None}
        if isinstance(alerts_raw, dict)
        else {}
    )
    return OrgSettings(lead_days, cover_days, alerts)


def dump(settings: OrgSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if settings.lead_days:
        out["lead_days"] = dict(settings.lead_days)
    if settings.cover_days:
        out["cover_days"] = {k.value: v for k, v in settings.cover_days.items()}
    if settings.alerts:
        out["alerts"] = {k: str(v) for k, v in settings.alerts.items()}
    return out


async def load(conn: AsyncConnection) -> OrgSettings:
    """Joriy tashkilot sozlamasi (RLS faqat o'z tashkilot qatorini ko'rsatadi)."""
    raw = await conn.scalar(select(m.orgs.c.settings))
    return parse(raw)

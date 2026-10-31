"""Tashkilot sozlamalari (``orgs.settings``, B4.8): standart yetkazish muddatlari (F25) va ABC qamrov kunlari (F27).

Biznes doimiylari bazada (tamoyil 2). Bo'sh sozlama — standart: muddat faqat xaridlar tarixidan o'rganiladi (tarix
yo'q bo'lsa noma'lum — raqam o'ylab topilmaydi), qamrov — ``upcore.inventory`` standarti (A 60, B 30, C 14). Bu yerda
faqat o'qish va tekshirish; hisob — ``upcore``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.inventory import DEFAULT, AbcClass, InventorySettings
from upcore.purchasing import LEAD_STAGES

from upapi.db import models as m

STAGES = tuple(name for name, _, _ in LEAD_STAGES)
MAX_LEAD_DAYS = 365
MAX_COVER_DAYS = 365


@dataclass(frozen=True, slots=True)
class OrgSettings:
    lead_days: dict[str, int] = field(default_factory=dict)  # bosqich → kun; bo'sh — sozlanmagan
    cover_days: dict[AbcClass, int] = field(default_factory=dict)  # bo'sh — standart

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
    return OrgSettings(lead_days, cover_days)


def dump(settings: OrgSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if settings.lead_days:
        out["lead_days"] = dict(settings.lead_days)
    if settings.cover_days:
        out["cover_days"] = {k.value: v for k, v in settings.cover_days.items()}
    return out


async def load(conn: AsyncConnection) -> OrgSettings:
    """Joriy tashkilot sozlamasi (RLS faqat o'z tashkilot qatorini ko'rsatadi)."""
    raw = await conn.scalar(select(m.orgs.c.settings))
    return parse(raw)

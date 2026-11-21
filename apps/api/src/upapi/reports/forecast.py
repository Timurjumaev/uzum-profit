"""Oy prognozi asosi (M4 "Oy prognozi", M12 reja-fakt): to'liq o'tgan kunlar qiymati, Jarayondagi qismi yakunlanish ulushi
(R, ADR-057 Q4) bilan tuzatilgan. Bosh sahifa va maqsadlar sahifasi bitta hisobdan foydalanadi."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from upcore.metrics import Period
from upcore.money import Currency, Money
from upcore.pnl import Statement, expected_value


def forecast_basis(today: date) -> Period | None:
    """Oy prognozi asosi — oyning **to'liq o'tgan** kunlari (oy boshidan kechagacha). Bugungi kun hali tugamagan:
    uni to'liq kun deb sanash prognozni pasaytiradi (soat 10:00 da 1-sanada −60%, 10-sanada −6%). Oyning 1-kuni to'liq kun
    yo'q — ``None`` (prognoz ko'rsatilmaydi, raqam o'ylab topilmaydi)."""
    if today.day == 1:
        return None
    return Period(today.replace(day=1), today - timedelta(days=1))


def basis_values(done: Statement, r: Decimal | None) -> tuple[Decimal, Decimal, Decimal]:
    """Asosdagi (tushum, sof foyda, dona): Jarayondagi qism × yakunlanish ulushi ``r`` (noma'lum bo'lsa — to'liq)."""
    part = done.processing
    zero = Money.zero(Currency.UZS)
    revenue = expected_value(done.revenue, part.revenue if part else zero, r).amount
    profit = expected_value(done.net_profit, part.net_profit if part else zero, r).amount
    pending = done.units_processing
    units = (
        Decimal(done.units) if r is None else Decimal(done.units - pending) + Decimal(pending) * r
    )
    return revenue, profit, units

"""Bildirishnomalar (02 M15, B6.1): hodisalar katalogi, tinch soatlar, signal qoidalari.

Katalog — qaysi hodisa bor, standart holati, sozlanadigan chegaralari va kritikligi (kritik hodisa tinch soatlarda ham
yuboriladi). Hodisani topish va yuborish — ``upapi.notify`` da; bu yerda faqat sof qoidalar (tamoyil 4).
Vaqt — tashkilot vaqt zonasidagi mahalliy vaqt (Toshkent, yoz vaqti yo'q).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from upcore.metrics import return_share


class Event(StrEnum):
    DAILY_SUMMARY = "daily_summary"
    WEEKLY_SUMMARY = "weekly_summary"
    STOCK_CRITICAL = "stock_critical"
    LOSS_SALES = "loss_sales"
    UNCOSTED_SALES = "uncosted_sales"
    NEW_FINE = "new_fine"
    RETURNS_SPIKE = "returns_spike"
    RECEIVING_SHORTAGE = "receiving_shortage"
    LOST_GOODS = "lost_goods"
    SYNC_STOPPED = "sync_stopped"
    PAYOUT_LATE = "payout_late"
    CARGO_LATE = "cargo_late"
    COMMISSION_CHANGED = "commission_changed"
    FBS_DEADLINE = "fbs_deadline"
    UNCOUNTED_PURCHASE = "uncounted_purchase"  # TM9.8: xarid keldi, N kun sanalmagan
    SHIP_NEEDED = "ship_needed"  # B6.5: Uzumdagi zaxira yetmaydi, omborimda tovar bor (F26, F54)
    MONTHLY_REPORT = "monthly_report"  # B7.3: oylik hisobot — oyning 1-sanasida dastlabki, yopilganda yakuniy havola
    EXPORT_READY = (
        "export_ready"  # B7.5: to'liq eksport tayyor (faqat so'ragan egasiga, 24 soatlik havola)
    )
    GOAL_BEHIND = (
        "goal_behind"  # B5.8: oylik maqsad bo'yicha prognoz maqsaddan 15% dan ko'p past (F59)
    )


class Audience(StrEnum):
    """Kimga boradi (rol bo'yicha): moliya — egasi, menejer, buxgalter; ombor — egasi, menejer, omborchi."""

    FINANCE = "finance"
    STOCK = "stock"
    ALL = "all"


ROLE_AUDIENCE: dict[str, frozenset[Audience]] = {
    "owner": frozenset(Audience),
    "manager": frozenset(Audience),
    "accountant": frozenset({Audience.FINANCE, Audience.ALL}),
    "warehouse": frozenset({Audience.STOCK, Audience.ALL}),
}


@dataclass(frozen=True)
class EventSpec:
    event: Event
    audience: Audience
    critical: bool = False  # tinch soatlarda ham yuboriladi
    default_enabled: bool = True
    params: Mapping[str, Any] = field(
        default_factory=dict
    )  # sozlanadigan chegaralar va standart qiymatlari
    stage: str | None = None  # hali ishlamaydi — qaysi bosqichda (``None`` — ishlaydi)


CATALOG: dict[Event, EventSpec] = {
    s.event: s
    for s in (
        EventSpec(Event.DAILY_SUMMARY, Audience.FINANCE, params={"at": "09:00"}),
        EventSpec(Event.WEEKLY_SUMMARY, Audience.FINANCE, params={"at": "09:00"}),
        EventSpec(Event.STOCK_CRITICAL, Audience.STOCK),
        EventSpec(Event.LOSS_SALES, Audience.FINANCE, params={"streak": 3}),
        EventSpec(Event.UNCOSTED_SALES, Audience.FINANCE),
        EventSpec(Event.NEW_FINE, Audience.FINANCE),
        # B5.4 (Temur qarori, 2026-11-20): daraja va N — foydalanuvchi tanlaydi, standart yo'q (``None`` — xabar yo'q).
        EventSpec(
            Event.RETURNS_SPIKE,
            Audience.FINANCE,
            params={"level": None, "min_returns": None},
        ),
        EventSpec(Event.RECEIVING_SHORTAGE, Audience.STOCK),
        # B5.4 (real o'lchov, 2026-11-19): faqat Uzumning `quantityMissing > 0` maydoni; balans usuli shovqinli — ko'rsatilmaydi.
        EventSpec(Event.LOST_GOODS, Audience.STOCK),
        EventSpec(Event.SYNC_STOPPED, Audience.ALL, critical=True, params={"hours": 2}),
        EventSpec(Event.PAYOUT_LATE, Audience.FINANCE, stage="B5.7"),
        EventSpec(Event.CARGO_LATE, Audience.STOCK, params={"days": 5}),
        # B5.5: SKU komissiyasi (Uzum) oldingi snapshotdan farq qilsa; sozlanadigan chegara yo'q.
        EventSpec(Event.COMMISSION_CHANGED, Audience.FINANCE),
        EventSpec(Event.FBS_DEADLINE, Audience.STOCK, critical=True, stage="B9.5"),
        # TM9.8 (ADR-069, ADR-064): kritik emas, har xarid uchun bir marta.
        EventSpec(Event.UNCOUNTED_PURCHASE, Audience.STOCK, params={"days": 3}),
        # B6.5: kritik emas; yangi SKU kirganda bir marta (bazaviy ro'yxat, `stock_critical` kabi).
        EventSpec(Event.SHIP_NEEDED, Audience.STOCK),
        # B5.8 (F59): kritik emas; oyning 7-kunidan boshlab (oldin prognoz beqaror); sozlanadigan chegara yo'q (15% — F59).
        EventSpec(Event.GOAL_BEHIND, Audience.FINANCE),
        # B7.3 (ADR-065): kritik emas; har oy bitta dastlabki va (hammasi yakuniy holatga yetganda) bitta yakuniy xabar — havola, fayl emas.
        EventSpec(Event.MONTHLY_REPORT, Audience.FINANCE),
        # B7.5: kritik emas; faqat eksportni so'ragan egasiga (``upapi.export_full`` yozadi, baholovchi yo'q).
        EventSpec(Event.EXPORT_READY, Audience.FINANCE),
    )
}

# Chegaralar oralig'i (sozlamada tekshiriladi).
PARAM_LIMITS: dict[str, tuple[int, int]] = {
    "streak": (2, 10),
    "hours": (1, 24),
    "days": (1, 30),
    "min_returns": (1, 1000),
}
# Matnli tanlov parametrlari (``None`` — hali tanlanmagan).
PARAM_CHOICES: dict[str, tuple[str, ...]] = {"level": ("shop", "sku")}
# Qiymati bo'lmasligi mumkin bo'lgan parametrlar: standart yo'q, kiritilmaguncha hodisa ishlamaydi.
PARAM_OPTIONAL = frozenset({"level", "min_returns"})
SPIKE_FACTOR = 2

QUIET_FROM = time(22, 0)
QUIET_TO = time(8, 0)


def audience_of(role: str) -> frozenset[Audience]:
    return ROLE_AUDIENCE.get(role, frozenset())


def merged_params(event: Event, saved: Mapping[str, Any] | None) -> dict[str, Any]:
    """Standart parametrlar ustiga saqlangani (faqat katalogdagi kalitlar)."""
    base = dict(CATALOG[event].params)
    for key, value in (saved or {}).items():
        if key in base:
            base[key] = value
    return base


def parse_hhmm(value: str) -> time:
    """``"09:00"`` → ``time(9, 0)``; noto'g'ri bo'lsa ``ValueError``."""
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def in_quiet(at: time, quiet_from: time | None, quiet_to: time | None) -> bool:
    """Tinch soatlar ichidami: ``[quiet_from, quiet_to)``, yarim tundan o'tishi mumkin (22:00–08:00). Ikkalasi bir xil
    yoki bo'sh — tinch soat yo'q."""
    if quiet_from is None or quiet_to is None or quiet_from == quiet_to:
        return False
    if quiet_from < quiet_to:
        return quiet_from <= at < quiet_to
    return at >= quiet_from or at < quiet_to


def due_at(
    now: datetime, quiet_from: time | None, quiet_to: time | None, *, critical: bool
) -> datetime:
    """Yuborish vaqti: kritik yoki tinch soat emas — hozir; aks holda tinch soat tugaganda (mahalliy ``now`` bilan
    bir xil vaqt zonasida)."""
    if critical or not in_quiet(now.timetz().replace(tzinfo=None), quiet_from, quiet_to):
        return now
    assert quiet_to is not None
    end = now.replace(hour=quiet_to.hour, minute=quiet_to.minute, second=0, microsecond=0)
    return end if end > now else end + timedelta(days=1)


def summary_due(now: datetime, at: time) -> bool:
    """Xulosa vaqti keldimi: mahalliy vaqt ``at`` dan o'tgan. Haftalik xulosa ham shunday (B6.4, A6): faqat dushanba emas —
    hafta ichida birinchi imkoniyatda (dushanba kuni sinxron yetib kelmagan bo'lsa ham hafta xulosasi yo'qolmaydi).
    Takror yuborilmasligi — kun / hafta bo'yicha ``dedupe_key`` bilan."""
    return now.time() >= at


def line_profit(seller_profit: Decimal | None, cogs: Decimal | None) -> Decimal | None:
    """F53 uchun bitta sotuv qatorining foydasi: Uzum to'lovi (F6 ``sellerProfit`` — komissiya va logistika ayirilgan)
    − tannarx (F21). Biri noma'lum bo'lsa — ``None`` (soliq va reklama bu signalga kirmaydi)."""
    if seller_profit is None or cogs is None:
        return None
    return seller_profit - cogs


def loss_streak(profits: Sequence[Decimal | None], streak: int) -> bool:
    """F53. Zarar bilan sotuv signali: SKU'ning oxirgi ``streak`` ta sotuvining (yangisi oxirida) hammasida birlik foyda
    < 0. Tannarxi noma'lum sotuv (``None``) zanjirni uzadi — taxmin bilan signal berilmaydi (tamoyil 9)."""
    if streak < 1 or len(profits) < streak:
        return False
    return all(p is not None and p < 0 for p in profits[-streak:])


def returns_spike(
    units7: int, returns7: int, units30: int, returns30: int, min_returns: int | None
) -> bool:
    """F18 asosidagi signal "Qaytish keskin oshdi" (02 M15): oxirgi 7 kunning qaytarish ulushi, oxirgi 30 kunnikidan
    ``SPIKE_FACTOR`` (2) barobar yoki ko'p **va** 7 kunda kamida ``min_returns`` (N) qaytish. Ulush = qaytgan /
    (sotilgan + qaytgan) (``metrics.return_share``); 30 kun 7 kunni ham o'z ichiga oladi. N kiritilmagan (``None``) —
    signal yo'q (tamoyil 9: taxmin bilan xabar berilmaydi)."""
    if min_returns is None or min_returns < 1 or returns7 < min_returns:
        return False
    share7 = return_share(units7, returns7)
    share30 = return_share(units30, returns30)
    if share7 is None or share30 is None or share30 <= 0:
        return False
    return share7 >= share30 * SPIKE_FACTOR


def week_start(day: date) -> date:
    """Dushanba (haftalik xulosa — o'tgan dushanba–yakshanba)."""
    return day - timedelta(days=day.weekday())

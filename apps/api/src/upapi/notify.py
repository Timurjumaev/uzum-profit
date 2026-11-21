"""Bildirishnomalar: hodisalarni topish va navbatga yozish (B6.1, 02 M15).

Har 5 daqiqada (``notify.tick``) har tashkilot uchun: a'zolar va ularning qoidalari (``notification_rules``, yo'q bo'lsa
katalog standarti — ``upcore.notify.CATALOG``) yuklanadi, yoqilgan hodisalar topiladi va har oluvchiga bitta
``notifications`` qatori yoziladi. Takror yo'q: ``UNIQUE (org_id, user_id, dedupe_key)`` — ``ON CONFLICT DO NOTHING``
(02 M15: "bitta hodisa takror yuborilmaydi"). Tinch soatlarda kritik bo'lmagan hodisa ``due_at`` — tinch soat
tugaganda (``upcore.notify.due_at``). Yuborish — B6.2 (Telegram), shu jadvaldan.

Hodisalar (ishlaydiganlari; qolganlari katalogda ``stage`` bilan):

- **Kunlik xulosa** — foydalanuvchi tanlagan vaqtdan keyin, kecha: buyurtmalar (F45), tushum (F3), sof foyda (F12),
  bekorlar (F17). Buyurtmalar sinxroni kecha oxirigacha yetib kelmagan bo'lsa yuborilmaydi (keyingi tekshiruvda) —
  Uzum uzilishida "sotuv yo'q" xabari bormasin.
- **Haftalik xulosa** — o'tgan hafta (xuddi shu ko'rsatkichlar); vaqti kelgach hafta ichida birinchi imkoniyatda (B6.4, A6).
- **Qoldiq kritik** (F26) — faqat ro'yxatga **yangi** SKU kirganda (B6.4, A2): yangi SKU'lar soni va birinchi 5 tasi; davom
  etayotgan holat takrorlanmaydi. Oluvchining oxirgi qatori — "bazaviy ro'yxat" (`payload.ids`); ro'yxat qisqarsa baza
  `skipped` holat qatori bilan yangilanadi (SKU qaytib kirsa yana "yangi").
- **Zarar bilan sotuv** (F53) — SKU'ning oxirgi N ta sotuvi zararda; xuddi shunday, faqat yangi SKU kirganda.
- **Tannarxsiz sotuvlar** — kecha tannarxsiz sotilgan **yangi** SKU (har SKU bir marta; B6.4, A3); soni — kunlik xulosada.
- **Yangi jarima** — oxirgi 3 kunda paydo bo'lgan jarima xarajati (har biri bir marta).
- **SKU komissiyasi o'zgardi** (B5.5) — kunlik qoldiq snapshotidagi Uzum komissiyasi (`sku_daily.commission_pct`) oldingi
  snapshotdan farq qilsa (oxirgi 2 kun ichida); o'zgargan kun bo'yicha bitta xabar (SKU, eski → yangi %), takror yo'q.
- **Reja orqada** (B5.8, F59) — oylik maqsad bo'yicha oy oxiri prognozi maqsaddan 15% dan ko'p past; oyning 7-kunidan boshlab
  (oldin prognoz beqaror); o'sha oy uchun "orqada" maqsadlar to'plami o'zgarsa bitta yangi xabar, takror yo'q.
- **Postavka kamomadi** — Uzum kam qabul qilgan va qaror yozilmagan farq (TM7).
- **Xarid sanalmagan** (TM9.8) — "Keldi" belgilangan xarid N kun (standart 3) sanalmay tursa, har xarid uchun bir marta.
- **Kargo kechikmoqda** (B5.1) — "Yo'lda" xarid kutilgan keldi sanasi (F25 "yo'l") + N kun (standart 5) dan o'tgan, har xarid bir marta.
- **Sinxron to'xtadi** (B6.4, A4) — ikki xil: *kalit yaroqsiz* (kritik, bir marta, har 3 kunda eslatma) va
  *yangilanmayapti* (kritik emas, Uzum uzilishida yuborilmaydi, har to'xtash uchun bir marta); tiklanganda bitta "tiklandi".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from upcore.expenses import ExpenseCategory
from upcore.inventory import StockStatus
from upcore.metrics import COUNTED, GoalStatus, Period, return_share, status_group
from upcore.notify import (
    CATALOG,
    PARAM_CHOICES,
    QUIET_FROM,
    QUIET_TO,
    Event,
    audience_of,
    due_at,
    line_profit,
    loss_streak,
    merged_params,
    parse_hhmm,
    returns_spike,
    summary_due,
    week_start,
)

from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.logs import get_logger
from upapi.reports import cells as rc
from upapi.reports import receiving as rr
from upapi.reports.common import Filters, freshness, sku_catalog
from upapi.reports.goals import month_goals
from upapi.reports.purchases import late_cargo
from upapi.reports.stock import load_stock

TASHKENT = ZoneInfo("Asia/Tashkent")
TOP = 5
FINE_DAYS = 3
COMMISSION_DAYS = 2  # komissiya o'zgarishi shuncha kun ichida xabar qilinadi
GOAL_MIN_DAYS = 7  # "Reja orqada" shu to'liq o'tgan kundan boshlab (oldin run-rate beqaror)
COMMISSION_LOOKBACK = 10  # oldingi snapshotni topish uchun (snapshot yo'q kunlar bo'lishi mumkin)
IDS_CAP = 500  # bazaviy ro'yxat (`payload.ids`) uzunligi
HEAVY_EVERY_MINUTES = (
    5  # og'ir tekshiruvlar (qoldiq, zarar) — soatda bir marta (har soatning dastlabki 5 daqiqasi)
)
_log = get_logger("upapi.notify")


@dataclass(frozen=True)
class Found:
    """Topilgan hodisa (tashkilot darajasida): har oluvchiga shu ``dedupe_key`` bilan bitta qator."""

    event: Event
    dedupe_key: str
    payload: dict[str, Any]
    status: str = "pending"  # "skipped" — faqat bazaviy ro'yxatni yangilaydi, yuborilmaydi
    critical: bool | None = None  # ``None`` — katalogdagi qiymat (``CATALOG[event].critical``)


@dataclass
class Recipient:
    user_id: UUID
    role: str
    rules: dict[Event, tuple[bool, dict[str, Any]]] = field(default_factory=dict)
    quiet_from: time | None = QUIET_FROM
    quiet_to: time | None = QUIET_TO

    def wants(self, event: Event) -> bool:
        spec = CATALOG[event]
        if spec.stage is not None or spec.audience not in audience_of(self.role):
            return False
        enabled, _ = self.rules.get(event, (spec.default_enabled, {}))
        return enabled

    def params(self, event: Event) -> dict[str, Any]:
        return merged_params(event, self.rules.get(event, (True, {}))[1])


async def recipients(conn: AsyncConnection) -> list[Recipient]:
    """Tashkilot a'zolari, qoidalari va tinch soatlari bilan."""
    out = {
        r.user_id: Recipient(r.user_id, r.role)
        for r in await conn.execute(select(m.memberships.c.user_id, m.memberships.c.role))
    }
    nr, npf = m.notification_rules, m.notification_prefs
    known = {e.value for e in Event}
    for r in await conn.execute(select(nr.c.user_id, nr.c.event, nr.c.enabled, nr.c.params)):
        if r.user_id in out and r.event in known:
            out[r.user_id].rules[Event(r.event)] = (r.enabled, dict(r.params or {}))
    for q in await conn.execute(select(npf.c.user_id, npf.c.quiet_from, npf.c.quiet_to)):
        if q.user_id in out:
            out[q.user_id].quiet_from, out[q.user_id].quiet_to = q.quiet_from, q.quiet_to
    return sorted(out.values(), key=lambda x: str(x.user_id))


# --- Hodisalar ------------------------------------------------------------------------------


def _num(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


async def summary(
    conn: AsyncConnection, period: Period, today: date, *, require_fresh: bool = True
) -> dict[str, Any] | None:
    """Davr xulosasi (Dashboard bilan bitta hisob — ``reports.cells``). Buyurtmalar sinxroni davr oxirigacha yetib
    kelmagan bo'lsa ``None`` (raqam yo'q ≠ sotuv yo'q, tamoyil 8); ``require_fresh=False`` (bot buyrug'i, davr hali
    tugamagan) — raqamlar beriladi, ``fresh_at`` bilan (xabarda "ma'lumot yangiligi")."""
    fresh = (await freshness(conn, ["orders"]))["orders"]
    end = datetime.combine(period.end + timedelta(days=1), time(0), TASHKENT)
    if require_fresh and (fresh is None or fresh < end):
        return None
    f = Filters(period, None, today)
    book = await rc.load_book(conn, period, today)
    s = book.scoped(f, period).statement()
    counts = await rc.order_counts(conn, f, period)
    flow = (await rc.sale_sums(conn, f, period=period)).get(None)
    rate = (
        await rc.realization(conn, f)
    ).total  # F16 R: bunday sotuvlarning qancha ulushi yakunlanadi
    return {
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "orders": sum(c[0] for c in counts.values()),
        "units": s.units,
        "revenue": _num(s.revenue.amount),
        "net_profit": _num(s.net_profit.amount),
        # B6.4 (A1): sof foyda uch qismda — jami, shundan kutilayotgan (Jarayondagi sotuvlar, F16) va R (fakt).
        "net_profit_expected": _num(s.net_profit_processing.amount),
        "rate": None if rate is None else str(rate),
        "canceled": flow.canceled if flow else 0,
        "uncosted_lines": s.uncovered_lines,
        "fresh_at": None if fresh is None else fresh.isoformat(),
    }


def _digest(ids: list[str]) -> str:
    return hashlib.sha1(",".join(sorted(ids)).encode()).hexdigest()[:12]


async def critical_stock(conn: AsyncConnection, today: date) -> list[tuple[UUID, Decimal | None]]:
    """Hamma kritik SKU (F26), eng kam kunlik zaxiradan boshlab."""
    stock = await load_stock(conn, None, today)
    critical = sorted(
        (x for x in stock.skus.values() if x.status is StockStatus.CRITICAL),
        key=lambda x: (
            x.days_of_stock if x.days_of_stock is not None else Decimal(0),
            str(x.sku_id),
        ),
    )
    return [(x.sku_id, x.days_of_stock) for x in critical]


async def stock_found(
    conn: AsyncConnection,
    items: list[tuple[UUID, Decimal | None]],
    today: date,
    known: set[str] | None = None,
) -> Found | None:
    """Kritik SKU'lardan hodisa. ``known`` berilsa — faqat undan tashqari (yangi) SKU'lar (B6.4, A2); ``None`` —
    hammasi (``/qoldiq`` buyrug'i)."""
    fresh = [(i, d) for i, d in items if known is None or str(i) not in known]
    if not fresh:
        return None
    catalog = await sku_catalog(conn, ids=[i for i, _ in fresh[:TOP]])
    return Found(
        Event.STOCK_CRITICAL,
        f"stock_critical:{today.isoformat()}:{_digest([str(i) for i, _ in fresh])}",
        {
            "count": len(fresh),
            "total": len(items),
            "new": known is not None,
            "ids": [str(i) for i, _ in items][:IDS_CAP],
            "skus": [
                {
                    "sku_id": str(i),
                    "title": catalog[i].title if i in catalog else None,
                    "days": None if d is None else str(d),
                }
                for i, d in fresh[:TOP]
            ],
        },
    )


async def stock_critical(conn: AsyncConnection, today: date) -> Found | None:
    """``/qoldiq``: hamma kritik SKU (to'liq ro'yxat)."""
    return await stock_found(conn, await critical_stock(conn, today), today)


async def ship_needed(conn: AsyncConnection, today: date) -> list[tuple[UUID, Decimal, int]]:
    """B6.5: Uzumga yuborish kerak bo'lgan SKU'lar (F26): Uzumdagi (+ postavkadagi) zaxira topshirish muddatiga yetmaydi,
    omborimda tovar bor. ``(sku, Uzumda necha kunga yetadi, yuboriladigan dona)`` — eng kam zaxiradan boshlab. Yuboriladigan
    dona — F54 rejasi (maqsad qamrov sozlangan bo'lsa), aks holda omborimdagi son."""
    stock = await load_stock(conn, None, today)
    rows = sorted(
        (x for x in stock.skus.values() if x.ship is not None),
        key=lambda x: (x.ship.cover_days if x.ship else Decimal(0), str(x.sku_id)),
    )
    return [
        (
            x.sku_id,
            x.ship.cover_days if x.ship else Decimal(0),
            x.ship_plan.qty if x.ship_plan is not None and x.ship_plan.qty > 0 else x.own,
        )
        for x in rows
    ]


async def ship_found(
    conn: AsyncConnection,
    items: list[tuple[UUID, Decimal, int]],
    today: date,
    known: set[str],
) -> Found | None:
    """Yuborish hodisasi: faqat bazaviy ro'yxatda yo'q (yangi) SKU'lar — har SKU kirganda bir marta."""
    fresh = [x for x in items if str(x[0]) not in known]
    if not fresh:
        return None
    catalog = await sku_catalog(conn, ids=[i for i, _, _ in fresh[:TOP]])
    return Found(
        Event.SHIP_NEEDED,
        f"ship_needed:{today.isoformat()}:{_digest([str(i) for i, _, _ in fresh])}",
        {
            "count": len(fresh),
            "total": len(items),
            "ids": [str(i) for i, _, _ in items][:IDS_CAP],
            "skus": [
                {
                    "sku_id": str(i),
                    "title": catalog[i].title if i in catalog else None,
                    "days": _num(d),
                    "qty": q,
                }
                for i, d, q in fresh[:TOP]
            ],
        },
    )


async def missing_skus(conn: AsyncConnection) -> list[tuple[UUID, int]]:
    """B5.4 (F31 (c)): Uzumning o'z `quantityMissing` maydoni > 0 bo'lgan SKU'lar (to'g'ridan-to'g'ri signal), eng ko'pidan.
    Balans usuli real ma'lumotda shovqinli chiqdi (manfiy farq ko'p) — ko'rsatilmaydi."""
    k = m.mp_skus
    qty = (k.c.raw["quantityMissing"].astext).cast(Integer)
    rows = await conn.execute(
        select(k.c.id, qty.label("qty"))
        .where(k.c.raw["quantityMissing"].astext.op("~")("^[0-9]+$"), qty > 0)
        .order_by(qty.desc(), k.c.id)
    )
    return [(r.id, int(r.qty)) for r in rows]


async def missing_found(
    conn: AsyncConnection, items: list[tuple[UUID, int]], today: date, known: set[str]
) -> Found | None:
    """Yangi (xabar qilinmagan) SKU'lardan "Yo'qolgan tovar" hodisasi."""
    fresh = [x for x in items if str(x[0]) not in known]
    if not fresh:
        return None
    catalog = await sku_catalog(conn, ids=[i for i, _ in fresh[:TOP]])
    return Found(
        Event.LOST_GOODS,
        f"lost_goods:{today.isoformat()}:{_digest([str(i) for i, _ in fresh])}",
        {
            "count": len(fresh),
            "total": len(items),
            "ids": [str(i) for i, _ in items][:IDS_CAP],
            "skus": [
                {
                    "sku_id": str(i),
                    "title": catalog[i].title if i in catalog else None,
                    "qty": q,
                }
                for i, q in fresh[:TOP]
            ],
        },
    )


SPIKE_DAYS = 7
SPIKE_BASE_DAYS = 30


async def return_windows(
    conn: AsyncConnection, today: date, level: str
) -> dict[UUID, tuple[int, int, int, int]]:
    """F18, B5.4: har do'kon (``level="shop"``) yoki SKU (``"sku"``) uchun (sotilgan7, qaytgan7, sotilgan30, qaytgan30)
    — tugagan oxirgi 7 / 30 kun (bugun kirmaydi); qaytgan = ``canceled_issued + returns`` (``OrderFlow.return_units``)."""
    d = m.daily_sku_metrics
    key = d.c.shop_id if level == "shop" else d.c.sku_id
    recent = d.c.day >= today - timedelta(days=SPIKE_DAYS)
    ret = d.c.canceled_issued + d.c.returns
    rows = await conn.execute(
        select(
            key.label("k"),
            func.coalesce(func.sum(d.c.units).filter(recent), 0).label("u7"),
            func.coalesce(func.sum(ret).filter(recent), 0).label("r7"),
            func.coalesce(func.sum(d.c.units), 0).label("u30"),
            func.coalesce(func.sum(ret), 0).label("r30"),
        )
        .where(
            key.is_not(None),
            d.c.day >= today - timedelta(days=SPIKE_BASE_DAYS),
            d.c.day < today,
        )
        .group_by(key)
    )
    return {r.k: (int(r.u7), int(r.r7), int(r.u30), int(r.r30)) for r in rows}


def spiking(
    windows: dict[UUID, tuple[int, int, int, int]], min_returns: int
) -> list[tuple[UUID, int, int, int, int]]:
    """Signal bergan kalitlar (qaytgan7 kamayish tartibida): F18 ``returns_spike`` qoidasi."""
    hit = [(k, *w) for k, w in windows.items() if returns_spike(*w, min_returns)]
    return sorted(hit, key=lambda x: (-x[2], str(x[0])))


def _pct(returns: int, units: int) -> str:
    share = return_share(units, returns)
    return str(((share or Decimal(0)) * 100).quantize(Decimal("0.1")))


async def spike_found(
    conn: AsyncConnection,
    items: list[tuple[UUID, int, int, int, int]],
    level: str,
    min_returns: int,
    today: date,
    known: set[str],
) -> Found | None:
    """Yangi (xabar qilinmagan) kalitlardan "Qaytish keskin oshdi" hodisasi."""
    fresh = [x for x in items if str(x[0]) not in known]
    if not fresh:
        return None
    top = fresh[:TOP]
    if level == "shop":
        names = {
            r.id: r.alias or r.name
            for r in await conn.execute(
                select(m.shops.c.id, m.shops.c.alias, m.shops.c.name).where(
                    m.shops.c.id.in_([k for k, *_ in top])
                )
            )
        }
    else:
        cat = await sku_catalog(conn, ids=[k for k, *_ in top])
        names = {k: cat[k].title for k in cat}
    ids = [str(x[0]) for x in items]
    return Found(
        Event.RETURNS_SPIKE,
        f"returns_spike:{level}:{today.isoformat()}:{_digest([str(x[0]) for x in fresh])}",
        {
            "level": level,
            "min_returns": min_returns,
            "count": len(fresh),
            "total": len(items),
            "ids": ids[:IDS_CAP],
            "items": [
                {
                    "id": str(k),
                    "title": names.get(k),
                    "returns": r7,
                    "share7": _pct(r7, u7),
                    "share30": _pct(r30, u30),
                }
                for k, u7, r7, u30, r30 in top
            ],
        },
    )


async def known_ids(conn: AsyncConnection, user_id: UUID, event: Event) -> set[str] | None:
    """Oluvchining shu hodisa bo'yicha oxirgi qatoridagi ro'yxat (`payload.ids`); qator yo'q — ``None``."""
    n = m.notifications
    payload = await conn.scalar(
        select(n.c.payload)
        .where(n.c.user_id == user_id, n.c.event == event.value, n.c.status != "failed")
        .order_by(n.c.created_at.desc(), n.c.id.desc())
        .limit(1)
    )
    if payload is None:
        return None
    return {str(x) for x in payload.get("ids", [])}


async def all_known_ids(conn: AsyncConnection, user_id: UUID, event: Event) -> set[str]:
    """Oluvchiga shu hodisa bo'yicha shu paytgacha xabar qilingan hamma SKU (``payload.ids`` birlashmasi)."""
    n = m.notifications
    out: set[str] = set()
    for r in await conn.execute(
        select(n.c.payload).where(n.c.user_id == user_id, n.c.event == event.value)
    ):
        out |= {str(x) for x in r.payload.get("ids", [])}
    return out


def snapshot_row(event: Event, ids: list[str], now: datetime) -> Found:
    """Ro'yxat qisqardi: bazaviy ro'yxatni yangilaydigan, yuborilmaydigan qator (SKU qaytib kirsa — yana yangi)."""
    return Found(
        event,
        f"{event.value}:state:{_digest(ids)}:{now.isoformat()}",
        {"ids": ids[:IDS_CAP]},
        status="skipped",
    )


async def losing_skus(conn: AsyncConnection, today: date, streak: int) -> list[UUID]:
    """F53: har SKU'ning oxirgi ``streak`` ta hisobga olinadigan sotuvi (oxirgi 30 kun) zararda bo'lgan SKU'lar."""
    si, sc = m.sale_items, m.sale_costs
    rows = await conn.execute(
        select(si.c.sku_id, si.c.status, si.c.seller_profit, sc.c.cogs)
        .join(sc, sc.c.sale_item_id == si.c.id, isouter=True)
        .where(
            si.c.sku_id.is_not(None),
            si.c.ordered_at >= datetime.combine(today - timedelta(days=30), time(0), TASHKENT),
        )
        .order_by(si.c.sku_id, si.c.ordered_at, si.c.external_id)
    )
    by_sku: dict[UUID, list[Decimal | None]] = {}
    for r in rows:
        if status_group(r.status) in COUNTED:
            by_sku.setdefault(r.sku_id, []).append(line_profit(r.seller_profit, r.cogs))
    return sorted(k for k, v in by_sku.items() if loss_streak(v, streak))


async def loss_found(
    conn: AsyncConnection, losing: list[UUID], today: date, streak: int, known: set[str]
) -> Found | None:
    """Faqat ``known`` da yo'q (yangi) SKU'lar (B6.4, A2)."""
    fresh = [k for k in losing if str(k) not in known]
    if not fresh:
        return None
    catalog = await sku_catalog(conn, ids=fresh[:TOP])
    return Found(
        Event.LOSS_SALES,
        f"loss_sales:{today.isoformat()}:{_digest([str(k) for k in fresh])}",
        {
            "count": len(fresh),
            "total": len(losing),
            "streak": streak,
            "new": True,
            "ids": [str(k) for k in losing][:IDS_CAP],
            "skus": [
                {"sku_id": str(k), "title": catalog[k].title if k in catalog else None}
                for k in fresh[:TOP]
            ],
        },
    )


async def uncosted_new_skus(conn: AsyncConnection, day: date) -> list[tuple[UUID, int]]:
    """Kecha (``day``) tannarxsiz sotilgan SKU'lar va ularning qator soni (B6.4, A3); SKU bog'lanmagan qatorlar —
    kunlik xulosadagi umumiy qatorda."""
    si, sc = m.sale_items, m.sale_costs
    rows = await conn.execute(
        select(si.c.sku_id, si.c.status, sc.c.cogs)
        .join(sc, sc.c.sale_item_id == si.c.id, isouter=True)
        .where(
            si.c.sku_id.is_not(None),
            si.c.ordered_at >= datetime.combine(day, time(0), TASHKENT),
            si.c.ordered_at < datetime.combine(day + timedelta(days=1), time(0), TASHKENT),
        )
        .order_by(si.c.sku_id)
    )
    lines: dict[UUID, int] = {}
    for r in rows:
        if r.cogs is None and status_group(r.status) in COUNTED:
            lines[r.sku_id] = lines.get(r.sku_id, 0) + 1
    return sorted(lines.items(), key=lambda kv: str(kv[0]))


def _pct_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")).normalize(), "f")


async def commission_changes(conn: AsyncConnection, today: date) -> list[Found]:
    """B5.5. Uzum komissiyasi o'zgargan SKU'lar: har SKU'ning kunlik snapshotidagi ``commission_pct`` o'zidan oldingi
    snapshotdan farq qilsa (o'zgarish kuni oxirgi ``COMMISSION_DAYS`` kunda). Oldingi snapshot yo'q (birinchi ko'rinish) —
    taqqoslash yo'q, xabar yo'q. O'zgarish kuni bo'yicha bitta ``Found``; kaliti — o'zgarish ro'yxati (SKU, yangi qiymat),
    shuning uchun bir xil ro'yxat takror yuborilmaydi, yangi o'zgargan SKU esa yangi xabar beradi."""
    sd = m.sku_daily
    known = (
        select(
            sd.c.sku_id,
            sd.c.day,
            sd.c.commission_pct.label("new"),
            func.lag(sd.c.commission_pct)
            .over(partition_by=sd.c.sku_id, order_by=sd.c.day)
            .label("old"),
        )
        .where(
            sd.c.commission_pct.is_not(None),
            sd.c.day >= today - timedelta(days=COMMISSION_DAYS + COMMISSION_LOOKBACK),
            sd.c.day <= today,
        )
        .subquery()
    )
    rows = (
        await conn.execute(
            select(known.c.sku_id, known.c.day, known.c.old, known.c.new)
            .where(
                known.c.old.is_not(None),
                known.c.new != known.c.old,
                known.c.day >= today - timedelta(days=COMMISSION_DAYS),
            )
            .order_by(known.c.day, known.c.sku_id)
        )
    ).all()
    by_day: dict[date, list[Any]] = {}
    for r in rows:
        by_day.setdefault(r.day, []).append(r)
    out = []
    for day, items in by_day.items():
        # Eng katta o'zgarish birinchi (xabarda birinchi 5 ta).
        items = sorted(items, key=lambda r: (-abs(r.new - r.old), str(r.sku_id)))
        catalog = await sku_catalog(conn, ids=[r.sku_id for r in items[:TOP]])
        digest = _digest([f"{r.sku_id}:{r.new}" for r in items])
        out.append(
            Found(
                Event.COMMISSION_CHANGED,
                f"commission:{day.isoformat()}:{digest}",
                {
                    "day": day.isoformat(),
                    "count": len(items),
                    "skus": [
                        {
                            "sku_id": str(r.sku_id),
                            "title": catalog[r.sku_id].title if r.sku_id in catalog else None,
                            "old": _pct_text(r.old),
                            "new": _pct_text(r.new),
                        }
                        for r in items[:TOP]
                    ],
                },
            )
        )
    return out


async def goals_behind(conn: AsyncConnection, today: date) -> list[Found]:
    """B5.8 (F59). Oylik maqsadlardan prognozi 15% dan ko'p past ("orqada") bo'lganlari — bitta xabar; oyning
    ``GOAL_MIN_DAYS``-kunidan boshlab. Kaliti — oy va "orqada" maqsadlar to'plami: to'plam o'zgarmasa takror yuborilmaydi,
    yangi maqsad orqada qolsa yangi xabar."""
    data = await month_goals(conn, None, today)
    if data.elapsed_days < GOAL_MIN_DAYS:
        return []
    behind = sorted(
        (g for g in data.goals if g.status is GoalStatus.BEHIND),
        key=lambda g: (g.deviation_pct or Decimal(0), str(g.id)),
    )
    if not behind:
        return []
    names = {s.id: s.name for s in data.shops}
    return [
        Found(
            Event.GOAL_BEHIND,
            f"goal_behind:{data.month.isoformat()}:{_digest([str(g.id) for g in behind])}",
            {
                "month": data.month.isoformat(),
                "count": len(behind),
                "goals": [
                    {
                        "shop": names.get(g.shop_id) if g.shop_id else None,
                        "metric": g.metric,
                        "target": str(g.target),
                        "forecast": str(g.forecast),
                        "forecast_percent": str(g.forecast_percent),
                    }
                    for g in behind[:TOP]
                ],
            },
        )
    ]


async def new_fines(conn: AsyncConnection, now: datetime) -> list[Found]:
    e = m.mp_expenses
    shops = {r.id: r.alias or r.name for r in await conn.execute(select(m.shops))}
    rows = await conn.execute(
        select(e.c.id, e.c.shop_id, e.c.amount, e.c.name, e.c.code, e.c.created_on)
        .where(
            e.c.category == ExpenseCategory.FINE.value,
            e.c.excluded.is_(None),
            e.c.amount != 0,
            e.c.created_on >= now - timedelta(days=FINE_DAYS),
        )
        .order_by(e.c.created_on, e.c.id)
    )
    return [
        Found(
            Event.NEW_FINE,
            f"fine:{r.id}",
            {
                "shop": shops.get(r.shop_id),
                "amount": _num(abs(r.amount)),
                "name": r.name,
                "code": r.code,
                "on": r.created_on.astimezone(TASHKENT).date().isoformat(),
            },
        )
        for r in rows
    ]


async def receiving_shortages(conn: AsyncConnection) -> list[Found]:
    found = [x for x in await rr.diffs(conn) if x.resolution is None and x.diff < 0]
    catalog = await sku_catalog(conn, ids=[x.sku_id for x in found]) if found else {}
    return [
        Found(
            Event.RECEIVING_SHORTAGE,
            f"receiving:{x.dispatch_id}:{x.sku_id}",
            {
                "invoice_number": x.invoice_number,
                "title": catalog[x.sku_id].title if x.sku_id in catalog else None,
                "shipped": x.shipped,
                "accepted": x.accepted,
                "missing": -x.diff,
            },
        )
        for x in found
    ]


async def uncounted_purchases(conn: AsyncConnection, today: date, days: int) -> list[Found]:
    """TM9.8: "Keldi", lekin ``days`` kundan beri sanalmagan xaridlar — har biri bir marta (``dedupe_key`` — xarid)."""
    p = m.purchases
    rows = await conn.execute(
        select(p.c.id, p.c.title, p.c.arrived_on).where(
            p.c.arrival_marked.is_(True),
            p.c.arrived_on.is_not(None),
            p.c.arrived_on <= today - timedelta(days=days),
            p.c.received_on.is_(None),
            p.c.sent_to_uzum_on.is_(None),
            p.c.closed_on.is_(None),
        )
    )
    return [
        Found(
            Event.UNCOUNTED_PURCHASE,
            f"uncounted:{r.id}",
            {
                "purchase_id": str(r.id),
                "title": r.title,
                "arrived_on": r.arrived_on.isoformat(),
                "days": (today - r.arrived_on).days,
            },
        )
        for r in rows
    ]


async def cargo_late(conn: AsyncConnection, today: date, days: int) -> list[Found]:
    """B5.1: kargo kechikmoqda — kutilgan keldi sanasi (F25 "yo'l") + ``days`` kundan o'tgan "Yo'lda" xaridlar; har xarid
    bir marta (``dedupe_key`` — xarid)."""
    return [
        Found(
            Event.CARGO_LATE,
            f"cargo_late:{x.id}",
            {
                "purchase_id": str(x.id),
                "title": x.title,
                "expected": x.expected.isoformat(),
                "days_late": x.days_late,
            },
        )
        for x in await late_cargo(conn, today, days)
    ]


REMIND_KEY_DAYS = 3  # kalit yaroqsiz bo'lib qolsa — eslatma har 3 kunda
RESTORED_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class ShopSync:
    id: UUID
    name: str
    key_invalid: bool
    last_success_at: datetime | None


async def shop_syncs(conn: AsyncConnection) -> list[ShopSync]:
    s, a, st = m.shops, m.mp_accounts, m.sync_state
    rows = await conn.execute(
        select(s.c.id, s.c.name, s.c.alias, a.c.status, st.c.last_success_at)
        .join(a, a.c.id == s.c.account_id)
        .join(st, (st.c.shop_id == s.c.id) & (st.c.kind == "orders"), isouter=True)
        .where(s.c.active)
        .order_by(s.c.id)
    )
    return [
        ShopSync(r.id, r.alias or r.name, r.status == "invalid", r.last_success_at) for r in rows
    ]


async def provider_outage(conn: AsyncConnection) -> bool:
    """Uzum uzilishi belgilangan (``provider_health.outage_since``) — sotuvchi hech narsa qila olmaydi (M3)."""
    since = await conn.scalar(
        select(m.provider_health.c.outage_since).where(m.provider_health.c.provider == "uzum")
    )
    return since is not None


def _stale(x: ShopSync, now: datetime, hours: int) -> bool:
    return (
        not x.key_invalid
        and x.last_success_at is not None
        and now - x.last_success_at >= timedelta(hours=hours)
    )


def sync_stopped(shops: list[ShopSync], now: datetime, hours: int, *, outage: bool) -> list[Found]:
    """Sinxron to'xtashi — ikki xil (B6.4, A4). Birinchi sinxron hali tugamagan do'kon hisobga olinmaydi.

    - **Kalit yaroqsiz** (sotuvchi tuzatadi): kritik; bir marta, tuzalmasa har 3 kunda eslatma (kalit — to'xtagan kundan
      boshlab 3 kunlik davr).
    - **Yangilanmayapti** (Uzum uzilishi, WAF yoki bizning ishchi — sotuvchi qila olmaydi): kritik emas (tunda yuborilmaydi),
      uzilish davrida umuman yo'q, har to'xtash uchun bir marta (kalit — oxirgi muvaffaqiyatli sinxron vaqti)."""
    today = now.astimezone(TASHKENT).date()
    out = []
    for x in shops:
        since = None if x.last_success_at is None else x.last_success_at.isoformat()
        base = {"shop": x.name, "shop_id": str(x.id), "since": since}
        if x.key_invalid:
            start = (
                today
                if x.last_success_at is None
                else x.last_success_at.astimezone(TASHKENT).date()
            )
            bucket = max(0, (today - start).days) // REMIND_KEY_DAYS
            out.append(
                Found(
                    Event.SYNC_STOPPED,
                    f"sync_key:{x.id}:{start.isoformat()}:{bucket}",
                    {**base, "reason": "key_invalid"},
                    critical=True,
                )
            )
        elif _stale(x, now, hours) and not outage:
            out.append(
                Found(
                    Event.SYNC_STOPPED,
                    f"sync_stale:{x.id}:{since}",
                    {**base, "reason": "stale"},
                    critical=False,
                )
            )
    return out


async def sync_restored(
    conn: AsyncConnection, shops: list[ShopSync], now: datetime, hours: int
) -> list[tuple[UUID, Found]]:
    """Tiklandi (B6.4, A4): oxirgi 7 kunda "to'xtadi" xabari yuborilgan oluvchi uchun, do'kon endi sog'lom bo'lsa — bitta
    "tiklandi" xabari (kalit — shu to'xtash xabarining kaliti, takror yo'q). Qaytaradi: (oluvchi, hodisa)."""
    healthy = {
        x.id
        for x in shops
        if not x.key_invalid and not _stale(x, now, hours) and x.last_success_at is not None
    }
    names = {x.id: x.name for x in shops}
    n = m.notifications
    rows = await conn.execute(
        select(n.c.user_id, n.c.dedupe_key, n.c.payload, n.c.created_at)
        .where(
            n.c.event == Event.SYNC_STOPPED.value,
            n.c.status.in_(("pending", "sent")),
            n.c.created_at >= now - RESTORED_WINDOW,
        )
        .order_by(n.c.created_at, n.c.id)
    )
    latest: dict[tuple[UUID, str], tuple[str, dict[str, Any]]] = {}
    for r in rows:  # har (oluvchi, do'kon) uchun eng oxirgi to'xtash/tiklandi qatori
        shop = r.payload.get("shop_id")
        if shop:
            latest[(r.user_id, shop)] = (r.dedupe_key, r.payload)
    out = []
    for (user_id, shop), (key, payload) in latest.items():
        if payload.get("reason") == "restored" or UUID(shop) not in healthy:
            continue
        out.append(
            (
                user_id,
                Found(
                    Event.SYNC_STOPPED,
                    f"sync_restored:{key}",
                    {
                        "shop": names.get(UUID(shop), payload.get("shop")),
                        "shop_id": shop,
                        "reason": "restored",
                    },
                    critical=False,
                ),
            )
        )
    return out


# --- Baholash -------------------------------------------------------------------------------


async def evaluate(conn: AsyncConnection, org_id: UUID, now: datetime) -> int:
    """Bitta tashkilot (``org_transaction`` ichida): hodisalarni topib navbatga yozadi. Qaytaradi: yangi qatorlar."""
    local = now.astimezone(TASHKENT)
    today = local.date()
    people = await recipients(conn)
    wanted = {e for e in Event if any(p.wants(e) for p in people)}
    if not wanted:
        return 0
    common: list[Found] = []  # hamma oluvchiga bir xil
    personal: list[tuple[Recipient, Found]] = []  # oluvchining vaqti / chegarasi bilan
    yesterday = Period(today - timedelta(days=1), today - timedelta(days=1))
    cache: dict[Period, dict[str, Any] | None] = {}

    async def summary_of(period: Period) -> dict[str, Any] | None:
        if period not in cache:
            cache[period] = await summary(conn, period, today)
        return cache[period]

    last_week = Period(week_start(today) - timedelta(days=7), week_start(today) - timedelta(days=1))
    n = m.notifications
    due = (
        (Event.DAILY_SUMMARY, yesterday, f"daily:{yesterday.start}"),
        (Event.WEEKLY_SUMMARY, last_week, f"weekly:{last_week.start}"),
    )
    # Bugungi kalit allaqachon bor bo'lsa — og'ir hisob (kitob) qayta bajarilmaydi (B6.4, A10).
    done = {
        (r.user_id, r.dedupe_key)
        for r in await conn.execute(
            select(n.c.user_id, n.c.dedupe_key).where(n.c.dedupe_key.in_([k for _, _, k in due]))
        )
    }
    for person in people:
        for event, period, key in due:
            if not person.wants(event) or (person.user_id, key) in done:
                continue
            try:
                at = parse_hhmm(str(person.params(event)["at"]))
            except (ValueError, KeyError):
                at = parse_hhmm(str(CATALOG[event].params["at"]))
            if not summary_due(local.replace(tzinfo=None), at):
                continue
            data = await summary_of(period)
            if data is not None:
                personal.append((person, Found(event, key, data)))
    # Og'ir tekshiruvlar (kitob, zaxira) soatda bir marta — har 5 daqiqada emas (B6.4, A10).
    heavy = local.minute < HEAVY_EVERY_MINUTES
    if Event.LOSS_SALES in wanted and heavy:
        for streak in sorted(
            {int(p.params(Event.LOSS_SALES)["streak"]) for p in people if p.wants(Event.LOSS_SALES)}
        ):
            losing = await losing_skus(conn, today, streak)
            ids = [str(k) for k in losing]
            for p in people:
                if (
                    not p.wants(Event.LOSS_SALES)
                    or int(p.params(Event.LOSS_SALES)["streak"]) != streak
                ):
                    continue
                base = await known_ids(conn, p.user_id, Event.LOSS_SALES)
                found = await loss_found(conn, losing, today, streak, base or set())
                if found is not None:
                    personal.append((p, found))
                elif base is not None and set(ids) != base:
                    personal.append((p, snapshot_row(Event.LOSS_SALES, ids, now)))
    if Event.SYNC_STOPPED in wanted:
        shops = await shop_syncs(conn)
        outage = await provider_outage(conn)
        by_id = {p.user_id: p for p in people}
        for hours in sorted(
            {
                int(p.params(Event.SYNC_STOPPED)["hours"])
                for p in people
                if p.wants(Event.SYNC_STOPPED)
            }
        ):
            group = [
                p
                for p in people
                if p.wants(Event.SYNC_STOPPED)
                and int(p.params(Event.SYNC_STOPPED)["hours"]) == hours
            ]
            for found in sync_stopped(shops, now, hours, outage=outage):
                personal += [(p, found) for p in group]
            if not outage:
                allowed = {p.user_id for p in group}
                personal += [
                    (by_id[u], f)
                    for u, f in await sync_restored(conn, shops, now, hours)
                    if u in allowed
                ]
    if Event.CARGO_LATE in wanted and heavy:
        for days in sorted(
            {int(p.params(Event.CARGO_LATE)["days"]) for p in people if p.wants(Event.CARGO_LATE)}
        ):
            for found in await cargo_late(conn, today, days):
                personal += [
                    (p, found)
                    for p in people
                    if p.wants(Event.CARGO_LATE) and int(p.params(Event.CARGO_LATE)["days"]) == days
                ]
    if Event.UNCOUNTED_PURCHASE in wanted:
        for days in sorted(
            {
                int(p.params(Event.UNCOUNTED_PURCHASE)["days"])
                for p in people
                if p.wants(Event.UNCOUNTED_PURCHASE)
            }
        ):
            for found in await uncounted_purchases(conn, today, days):
                personal += [
                    (p, found)
                    for p in people
                    if p.wants(Event.UNCOUNTED_PURCHASE)
                    and int(p.params(Event.UNCOUNTED_PURCHASE)["days"]) == days
                ]
    if Event.STOCK_CRITICAL in wanted and heavy:
        items = await critical_stock(conn, today)
        ids = [str(i) for i, _ in items]
        for p in people:
            if not p.wants(Event.STOCK_CRITICAL):
                continue
            base = await known_ids(conn, p.user_id, Event.STOCK_CRITICAL)
            found = await stock_found(conn, items, today, base or set())
            if found is not None:
                personal.append((p, found))
            elif base is not None and set(ids) != base:
                personal.append((p, snapshot_row(Event.STOCK_CRITICAL, ids, now)))
    if Event.SHIP_NEEDED in wanted and heavy:
        ship_items = await ship_needed(conn, today)
        ship_ids = [str(i) for i, _, _ in ship_items]
        for p in people:
            if not p.wants(Event.SHIP_NEEDED):
                continue
            base = await known_ids(conn, p.user_id, Event.SHIP_NEEDED)
            found = await ship_found(conn, ship_items, today, base or set())
            if found is not None:
                personal.append((p, found))
            elif base is not None and set(ship_ids) != base:
                personal.append((p, snapshot_row(Event.SHIP_NEEDED, ship_ids, now)))
    if Event.LOST_GOODS in wanted and heavy:
        lost_items = await missing_skus(conn)
        lost_ids = [str(i) for i, _ in lost_items]
        for p in people:
            if not p.wants(Event.LOST_GOODS):
                continue
            base = await known_ids(conn, p.user_id, Event.LOST_GOODS)
            found = await missing_found(conn, lost_items, today, base or set())
            if found is not None:
                personal.append((p, found))
            elif base is not None and set(lost_ids) != base:
                personal.append((p, snapshot_row(Event.LOST_GOODS, lost_ids, now)))
    if Event.RETURNS_SPIKE in wanted and heavy:
        spike_cache: dict[str, dict[UUID, tuple[int, int, int, int]]] = {}
        for p in people:
            if not p.wants(Event.RETURNS_SPIKE):
                continue
            prm = p.params(Event.RETURNS_SPIKE)
            level, n_min = prm["level"], prm["min_returns"]
            if level not in PARAM_CHOICES["level"] or not isinstance(n_min, int):
                continue  # Temur qarori: daraja va N kiritilmaguncha xabar yo'q
            if level not in spike_cache:
                spike_cache[level] = await return_windows(conn, today, level)
            hits = spiking(spike_cache[level], n_min)
            hit_ids = [str(x[0]) for x in hits]
            base = await known_ids(conn, p.user_id, Event.RETURNS_SPIKE)
            found = await spike_found(conn, hits, level, n_min, today, base or set())
            if found is not None:
                personal.append((p, found))
            elif base is not None and set(hit_ids) != base:
                personal.append((p, snapshot_row(Event.RETURNS_SPIKE, hit_ids, now)))
    if Event.UNCOSTED_SALES in wanted and heavy:
        # B6.4 (A3): kunlik xulosada tannarxsiz qatorlar soni allaqachon bor; alohida xabar faqat tannarxsiz YANGI SKU
        # (hech qachon xabar qilinmagan) birinchi marta sotilganda — xulosa o'chirilgan bo'lsa ham.
        sold = await uncosted_new_skus(conn, yesterday.start)
        if sold:
            for p in people:
                if not p.wants(Event.UNCOSTED_SALES):
                    continue
                seen = await all_known_ids(conn, p.user_id, Event.UNCOSTED_SALES)
                fresh = [(k, c) for k, c in sold if str(k) not in seen]
                if not fresh:
                    continue
                catalog = await sku_catalog(conn, ids=[k for k, _ in fresh[:TOP]])
                ids = [str(k) for k, _ in fresh]
                personal.append(
                    (
                        p,
                        Found(
                            Event.UNCOSTED_SALES,
                            f"uncosted:{_digest(ids)}",
                            {
                                "day": yesterday.start.isoformat(),
                                "count": len(fresh),
                                "lines": sum(c for _, c in fresh),
                                "ids": ids[:IDS_CAP],
                                "skus": [
                                    {
                                        "sku_id": str(k),
                                        "title": catalog[k].title if k in catalog else None,
                                    }
                                    for k, _ in fresh[:TOP]
                                ],
                            },
                        ),
                    )
                )
    if Event.NEW_FINE in wanted:
        common += await new_fines(conn, now)
    if Event.RECEIVING_SHORTAGE in wanted:
        common += await receiving_shortages(conn)
    if Event.COMMISSION_CHANGED in wanted and heavy:
        common += await commission_changes(conn, today)
    if Event.GOAL_BEHIND in wanted and heavy:
        common += await goals_behind(conn, today)

    rows = [(p, f) for f in common for p in people if p.wants(f.event)] + personal
    created = 0
    for person, found in rows:
        critical = CATALOG[found.event].critical if found.critical is None else found.critical
        when = due_at(local, person.quiet_from, person.quiet_to, critical=critical)
        result = await conn.execute(
            insert(m.notifications)
            .values(
                org_id=org_id,
                user_id=person.user_id,
                event=found.event.value,
                dedupe_key=found.dedupe_key,
                status=found.status,
                critical=critical,
                payload=found.payload,
                due_at=when,
            )
            .on_conflict_do_nothing(index_elements=["org_id", "user_id", "dedupe_key"])
        )
        created += result.rowcount or 0
    return created


async def evaluate_org(engine: AsyncEngine, org_id: UUID, now: datetime) -> int:
    async with org_transaction(engine, org_id) as conn:
        created = await evaluate(conn, org_id, now)
    if created:
        _log.info("notifications_queued", org_id=str(org_id), created=created)
    return created

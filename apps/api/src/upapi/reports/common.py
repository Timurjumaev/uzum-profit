"""Umumiy filtrlar va ``meta`` (03 §8): davr (Toshkent kunlari, F1), do'konlar, ma'lumot yangiligi, kursor.

Davr: ``start`` va ``end`` (ikkalasi kiradi); berilmasa — bugun bilan tugaydigan 30 kun. Tayyor davrlar ("Shu oy",
"Hammasi" ...) frontendda URL'ga sana bo'lib yoziladi (M4: havola ulashilsa shu ko'rinish ochiladi).
Do'kon filtri ``shop`` (bir necha marta) — boshqa tashkilot do'koni RLS bilan baribir ko'rinmaydi.
"""

from __future__ import annotations

import base64
import binascii
import gc
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.metrics import TASHKENT, Period

from upapi.db import models as m
from upapi.errors import AppError

DEFAULT_DAYS = 30
MAX_DAYS = 3_700  # ~10 yil: "Hammasi" uchun yetarli, xato so'rov bazani bosmaydi
MAX_LIMIT = 500


@contextmanager
def paused_gc() -> Iterator[None]:
    """Og'ir hisobot paytida avtomatik GC to'xtatiladi (M4 tezlik mezoni): o'n minglab qisqa umrli obyekt (katak,
    qator) GC'ni qayta-qayta ishga tushirib, vaqtning ~40% ini olardi; ular tsiklsiz — keyin odatdagidek tozalanadi.
    Parallel so'rovlarda ham oxirida GC yoqilgan holatga qaytadi (faqat uni o'chirgan chaqiruv yoqadi)."""
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()


def gc_paused() -> Iterator[None]:
    """FastAPI bog'liqligi: endpoint davomida :func:`paused_gc` (``Depends(gc_paused, scope="function")``)."""
    with paused_gc():
        yield


Heavy = Annotated[None, Depends(gc_paused, scope="function")]


def today() -> date:
    """Toshkent bo'yicha bugun (F1)."""
    return datetime.now(TASHKENT).date()


async def db_now(conn: AsyncConnection) -> datetime:
    """Bazaning ``now()`` (tranzaksiya vaqti) — ``changed_at`` kabi bazadagi vaqtlar bilan solishtirish uchun."""
    now: datetime | None = await conn.scalar(select(func.now()))
    return now or datetime.now(TASHKENT)


@dataclass(frozen=True, slots=True)
class Filters:
    period: Period
    shops: frozenset[UUID] | None
    today: date
    _keys: frozenset[str] = field(default=frozenset(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        keys = frozenset(str(s) for s in self.shops) if self.shops else frozenset()
        object.__setattr__(self, "_keys", keys)

    def shop_ok(self, shop: str) -> bool:
        """``shop`` — P&L katagidagi do'kon satri (tashkilot darajasi ``""`` — filtr bo'lsa kirmaydi)."""
        return self.shops is None or shop in self._keys


def filters(
    start: Annotated[date | None, Query(description="Davr boshi (Toshkent kuni)")] = None,
    end: Annotated[date | None, Query(description="Davr oxiri, kiradi; standart — bugun")] = None,
    shop: Annotated[list[UUID] | None, Query(description="Do'konlar (bir necha marta)")] = None,
) -> Filters:
    now = today()
    end = end or now
    start = start or end - timedelta(days=DEFAULT_DAYS - 1)
    if end < start:
        raise AppError("bad_period", 422, detail="Davr oxiri boshidan oldin")
    if (end - start).days + 1 > MAX_DAYS:
        raise AppError("bad_period", 422, detail=f"Davr {MAX_DAYS} kundan uzun")
    return Filters(Period(start, end), frozenset(shop) if shop else None, now)


class PeriodOut(BaseModel):
    start: date
    end: date
    days: int

    @classmethod
    def of(cls, period: Period) -> PeriodOut:
        return cls(start=period.start, end=period.end, days=period.days)


class Meta(BaseModel):
    """``meta.freshness`` — tegishli ma'lumot turlari bo'yicha oxirgi muvaffaqiyatli sinxron (faol do'konlarning eng
    eskisi; biror do'kon hali yangilanmagan bo'lsa ``null``). Tamoyil 8: "ma'lumot yo'q" ≠ "sinxron ishlamayapti"."""

    period: PeriodOut
    previous: PeriodOut | None = None
    shops: list[UUID] | None
    freshness: dict[str, datetime | None]


async def freshness(conn: AsyncConnection, kinds: Sequence[str]) -> dict[str, datetime | None]:
    """Har tur bo'yicha faol do'konlarning eng eski oxirgi muvaffaqiyati (03 §8)."""
    active = [r.id for r in await conn.execute(select(m.shops.c.id).where(m.shops.c.active))]
    st = m.sync_state
    last = {
        (r.shop_id, r.kind): r.last_success_at
        for r in await conn.execute(
            select(st.c.shop_id, st.c.kind, st.c.last_success_at).where(st.c.kind.in_(kinds))
        )
    }
    out: dict[str, datetime | None] = {}
    for kind in kinds:
        values = [last.get((shop, kind)) for shop in active]
        known = [v for v in values if v is not None]
        out[kind] = min(known) if known and len(known) == len(values) else None
    return out


async def meta(
    conn: AsyncConnection, f: Filters, kinds: Sequence[str], previous: Period | None = None
) -> Meta:
    return Meta(
        period=PeriodOut.of(f.period),
        previous=PeriodOut.of(previous) if previous else None,
        shops=sorted(f.shops, key=str) if f.shops else None,
        freshness=await freshness(conn, kinds),
    )


# --- Kursor (03 §8: ro'yxatlar kursor bilan) -------------------------------------------------


def encode_cursor(values: Sequence[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(list(values), default=str).encode()).decode()


def decode_cursor(cursor: str | None, size: int) -> list[Any] | None:
    """Mijozga ochiq bo'lmagan (opaque) kursor; buzilgan bo'lsa — 422 ``bad_cursor``."""
    if cursor is None:
        return None
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, binascii.Error):
        raise AppError("bad_cursor", 422) from None
    if not isinstance(values, list) or len(values) != size:
        raise AppError("bad_cursor", 422)
    return values


Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Cursor = Annotated[str | None, Query(description="Oldingi javobdagi ``next_cursor``")]


# --- Qidiruv (M6: lotin/kirill, apostrof turidan qat'i nazar) --------------------------------

# Kirill (o'zbek va rus) → lotin; ruff RUF001 tufayli kodlar bilan. "-" — olib tashlanadi (ъ, ь).
_CYRILLIC = (
    "\u0430\u0431\u0432\u0433\u0434\u0435\u0451\u0436\u0437\u0438\u0439\u043a"
    "\u043b\u043c\u043d\u043e\u043f\u0440\u0441\u0442\u0443\u0444\u0445\u0446"
    "\u0447\u0448\u0449\u044a\u044b\u044c\u044d\u044e\u044f\u045e\u049b\u0493"
    "\u04b3"
)
_LATIN = [
    "a",
    "b",
    "v",
    "g",
    "d",
    "e",
    "yo",
    "j",
    "z",
    "i",
    "y",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "r",
    "s",
    "t",
    "u",
    "f",
    "x",
    "ts",
    "ch",
    "sh",
    "sh",
    "-",
    "i",
    "-",
    "e",
    "yu",
    "ya",
    "o",
    "q",
    "g",
    "h",
]
_APOSTROPHES = "'\u0060\u02bb\u02bc\u2018\u2019\u02b9"  # tutuq, apostrof va bir tirnoq turlari
_FOLD = str.maketrans(
    {
        **{c: "" if lat == "-" else lat for c, lat in zip(_CYRILLIC, _LATIN, strict=True)},
        **dict.fromkeys(_APOSTROPHES, ""),
    }
)


def fold(text: str | None) -> str:
    """Qidiruv uchun: kichik harf, kirill → lotin, hamma tutuq/apostrof turlari olib tashlanadi
    ("Oʻyinchoq" = "o'yinchoq" = "ўйинчоқ" → "oyinchoq")."""
    return (text or "").lower().translate(_FOLD)


# --- Katalog --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SkuInfo:
    id: UUID
    shop_id: UUID
    item_id: UUID | None
    product_id: UUID | None
    title: str | None  # ``skuFullTitle``
    product_title: str | None
    article: str | None
    barcode: str | None
    image_url: str | None
    price: Any
    rank: str | None
    status: str | None
    commission_pct: Any = None  # Uzum katalogidagi komissiya, %
    storage_price: Any = None  # Uzum ``paidStoragePriceItem`` (saqlash narxi, dona/kun)
    product_external_id: int | None = None  # Uzum mahsulot id (sahifaga havola)

    def haystack(self) -> str:
        return fold(
            " ".join(x or "" for x in (self.title, self.product_title, self.article, self.barcode))
        )


async def sku_catalog(
    conn: AsyncConnection, shops: frozenset[UUID] | None = None, ids: Sequence[UUID] | None = None
) -> dict[UUID, SkuInfo]:
    k, p, i = m.mp_skus, m.mp_products, m.items
    query = (
        select(
            k,
            p.c.title.label("product_title"),
            p.c.external_id.label("product_external_id"),
            i.c.image_url,
        )
        .outerjoin(p, p.c.id == k.c.product_id)
        .outerjoin(i, i.c.id == k.c.item_id)
        .order_by(k.c.shop_id, k.c.external_id)
    )
    if shops:
        query = query.where(k.c.shop_id.in_(shops))
    if ids is not None:
        query = query.where(k.c.id.in_(list(ids)))
    return {
        r.id: SkuInfo(
            id=r.id,
            shop_id=r.shop_id,
            item_id=r.item_id,
            product_id=r.product_id,
            title=r.sku_code,
            product_title=r.product_title,
            article=r.article,
            barcode=r.barcode,
            image_url=r.image_url,
            price=r.price,
            rank=r.rank,
            status=r.status,
            commission_pct=r.commission_pct,
            storage_price=r.storage_price,
            product_external_id=r.product_external_id,
        )
        for r in await conn.execute(query)
    }
